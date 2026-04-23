from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
import os, uuid, json, copy, shlex, subprocess, re

from tools_v2 import ToolLibrary, run_tool
from tool.base import ToolRunError
from critiquers import AudioEvalCritic
from llm import LLM
from tree_memory import TreeMemory, SCORE_WEIGHTS
from utils.runtime_logger import log_step


def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

def _sec_from_event(ev: Dict[str, Any]) -> float:
    st = _safe_float(ev.get("start_time"), 0.0)
    et = _safe_float(ev.get("end_time"), st)
    dur = _safe_float(ev.get("duration"), et - st)
    return max(dur, 0.2)

def _norm_type(t: str) -> str:
    return (t or "").strip().lower()

def _weighted_score(scores: Dict[str, float]) -> float:
    return sum(scores.get(k, 0.0) * w for k, w in SCORE_WEIGHTS.items())

def _best_threshold_met(scores: Dict[str, float]) -> bool:
    return (
        scores.get("alignment", 0.0) >= 0.7 and
        scores.get("quality", 0.0) >= 0.6 and
        scores.get("aesthetics", 0.0) >= 0.6
    )

def _pick_text_key(args: Dict[str, Any]) -> Optional[str]:
    for k in ("text", "prompt", "ref_prompt", "tts_text"):
        if k in args and isinstance(args[k], str):
            return k
    return None

def _as_flag(k: str, v) -> List[str]:
    if v is None:
        return []
    if isinstance(v, bool):
        return [f"--{k}"] if v else []
    return [f"--{k}", str(v)]


def _audio_is_non_silent(path: str, rms_threshold: int = 8) -> Tuple[bool, str]:
    if not path or not os.path.exists(path):
        return False, "missing output file"

    try:
        import audioop
        import wave

        with wave.open(path, "rb") as reader:
            frames = reader.getnframes()
            if frames <= 0:
                return False, "audio has no frames"
            data = reader.readframes(frames)
            if not data:
                return False, "audio has no sample data"
            rms = audioop.rms(data, reader.getsampwidth())
            peak = audioop.max(data, reader.getsampwidth())
            if rms <= rms_threshold or peak <= rms_threshold:
                return False, f"silent audio detected (rms={rms}, peak={peak})"
            return True, ""
    except Exception:
        pass

    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(path)
        if len(audio) <= 0:
            return False, "audio has no duration"
        if audio.rms <= rms_threshold or audio.max <= rms_threshold:
            return False, f"silent audio detected (rms={audio.rms}, peak={audio.max})"
        return True, ""
    except Exception as exc:
        return False, f"failed to inspect generated audio: {type(exc).__name__}: {exc}"


@dataclass
class ToTNode:
    node_id: str
    node_type: str  # "initial" | "generation" | "refinement"
    model: Optional[str] = None
    output_wav: Optional[str] = None
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

class ToTExecutor:
    def __init__(
        self,
        tool_lib: ToolLibrary,
        llm: LLM,
        critic: AudioEvalCritic,
        prompt_max_retries: int = 1,
        max_depth: int = 3,
        max_siblings: int = 2,
        prefer_bin: bool = True,
        critic_llm: LLM = None,
    ):
        self.tool_lib = tool_lib
        self.llm = llm
        self.critic = critic
        self.critic_llm = critic_llm  # None means audio scoring is disabled
        self.prompt_max_retries = max(0, int(prompt_max_retries))
        self.max_depth = max_depth
        self.max_siblings = max_siblings
        self.prefer_bin = prefer_bin
        self.nodes: Dict[str, ToTNode] = {}

    def _new_node(self, node_type: str, parent: Optional[str] = None, **meta) -> ToTNode:
        nid = str(uuid.uuid4())[:8]
        n = ToTNode(node_id=nid, node_type=node_type, parent=parent, meta=meta)
        self.nodes[nid] = n
        if parent:
            self.nodes[parent].children.append(nid)
        return n

    def _revise_text_prompt(self, model: str, prev_args: Dict[str, Any], event: Dict[str, Any],
                            memory_context: Dict[str, Any], focus: str = "general") -> Dict[str, Any]:
        if model not in ("MMAudio", "InspireMusic", "CosyVoice2", "DiffRhythm"):
            return prev_args

        text_key = _pick_text_key(prev_args)
        if not text_key:
            return prev_args

        _FOCUS_HINTS: Dict[str, str] = {
            "alignment": "FOCUS on temporal precision and semantic match with the event's described start/end time and object.",
            "quality":   "FOCUS on acoustic clarity, sound fidelity, and richness of audio detail.",
            "aesthetics":"FOCUS on stylistic appropriateness and emotional fit with the scene.",
            "general":   "Improve overall audio quality, alignment, and aesthetic appeal.",
        }

        system = (
            "You are an audio prompt refining assistant. "
            "Given the previous generation arguments and the full exploration history, "
            "rewrite ONLY the text prompt to better match the described scene and timing. "
            "Learn from all past attempts and suggestions to avoid repeating mistakes. "
            "Return JSON with one field: {\"text\": \"...\"}."
        )
        user = json.dumps({
            "model": model,
            "current_args": prev_args,
            "event": {
                "audio_type": event.get("audio_type"),
                "Object": event.get("Object"),
                "description": event.get("description"),
                "start_time": event.get("start_time"),
                "end_time": event.get("end_time"),
                "duration": event.get("duration"),
            },
            "memory_context": memory_context,
            "refinement_focus": _FOCUS_HINTS.get(focus, _FOCUS_HINTS["general"]),
            "requirements": [
                "Keep structure unchanged; revise only the text field.",
                "Respect timing/duration and scene realism.",
                "Avoid generic terms; add concrete acoustic details.",
                "Learn from all past attempts in memory_context to avoid repeating the same mistakes.",
                "Pay special attention to the refinement_focus instruction above."
            ]
        }, ensure_ascii=False)

        try:
            raw = self.llm.chat(system, user)
            raw = (raw or "").strip()
            m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
            if m:
                raw = m.group(1)
            obj = json.loads(raw)
            if isinstance(obj, dict) and isinstance(obj.get("text"), str) and obj["text"].strip():
                new_args = copy.deepcopy(prev_args)
                new_args[text_key] = obj["text"].strip()
                return new_args
        except Exception:
            pass
        return prev_args

    def _diagnose_failure(self, scores: Dict[str, float]) -> str:
        dims = ("alignment", "quality", "aesthetics")
        return min(dims, key=lambda k: scores.get(k, 0.0))

    def _should_abandon_model(self, memory: TreeMemory, model: str) -> bool:
        history = memory.get_model_history(model)
        if len(history) < 2:
            return False
        delta = history[-1].weighted_score - history[-2].weighted_score
        return delta <= 0.0

    def _prewarm_initial_args(self, model: str, base_args: Dict[str, Any],
                               event: Dict[str, Any],
                               prior_suggestions: List[str]) -> Dict[str, Any]:
        if model not in ("MMAudio", "InspireMusic", "CosyVoice2", "DiffRhythm"):
            return base_args
        text_key = _pick_text_key(base_args)
        if not text_key or not prior_suggestions:
            return base_args

        system = (
            "You are an audio prompt assistant. "
            "Prior generation attempts with other models have failed. "
            "Write an improved initial prompt for a new model that avoids these known issues. "
            "Return JSON with one field: {\"text\": \"...\"}."
        )
        user = json.dumps({
            "model": model,
            "current_args": base_args,
            "event": {
                "audio_type": event.get("audio_type"),
                "description": event.get("description"),
                "start_time": event.get("start_time"),
                "end_time": event.get("end_time"),
            },
            "prior_model_suggestions": prior_suggestions,
            "requirements": [
                "Write a fresh, improved prompt avoiding known failure patterns.",
                "Respect timing/duration and scene realism.",
                "Add concrete acoustic details.",
            ]
        }, ensure_ascii=False)

        try:
            raw = self.llm.chat(system, user)
            raw = (raw or "").strip()
            m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
            if m:
                raw = m.group(1)
            obj = json.loads(raw)
            if isinstance(obj, dict) and isinstance(obj.get("text"), str) and obj["text"].strip():
                new_args = copy.deepcopy(base_args)
                new_args[text_key] = obj["text"].strip()
                return new_args
        except Exception:
            pass
        return base_args

    def _call_model(self, model_name: str, args: Dict[str, Any], out_wav: str, workdir: str) -> Tuple[str, Dict[str, Any]]:
        a = copy.deepcopy(args)
        a.setdefault("out", out_wav)

        try:
            tool = self.tool_lib.get(model_name)
            wav = run_tool(tool, a, out_wav)
            return wav or "", {"runner": "tool_lib"}
        except ToolRunError as e:
            return "", {
                "runner": "tool_lib",
                "error": str(e),
                "error_type": type(e).__name__,
                "cmd": e.cmd,
                "returncode": e.returncode,
                "stdout": e.stdout,
                "stderr": e.stderr,
            }
        except Exception as e:
            return "", {
                "runner": "tool_lib",
                "error": str(e),
                "error_type": type(e).__name__,
            }


    def run(self, event: Dict[str, Any], workdir: str) -> Tuple[str, Dict[str, Any], Dict[str, dict]]:
        self.nodes = {}  # reset per-event to avoid cross-event node pollution
        if event.get("keep") and isinstance(event.get("keep_wav"), str) and os.path.exists(event["keep_wav"]):
            log_step("ToT skip generation: using keep_wav from stage-2")
            nodes_snapshot = {
                "kept": {
                    "node_id": "kept",
                    "node_type": "kept",
                    "model": "PROBE_KEEP",
                    "output_wav": event["keep_wav"],
                    "parent": None,
                    "children": [],
                    "meta": {"note": "Kept from Stage-2 video probe"}
                }
            }
            scores = {"quality": 1.0, "alignment": 1.0, "aesthetics": 1.0}
            return event["keep_wav"], scores, nodes_snapshot

        root = self._new_node("initial", meta={"event": event})
        candidates: List[str] = list(event.get("model_candidates") or [])[: self.max_siblings]
        refined_inputs: Dict[str, Dict[str, Any]] = dict(event.get("refined_inputs") or {})
        log_step(f"ToT start: candidates={candidates}, max_depth={self.max_depth}, max_siblings={self.max_siblings}")
        if not candidates:
            self.nodes[root.node_id].meta["note"] = "no candidates in event; skipped"
            nodes_snapshot = {nid: self.nodes[nid].__dict__ for nid in self.nodes}
            return "", {"quality":0,"alignment":0,"aesthetics":0}, nodes_snapshot

        memory = TreeMemory()
        best_wav: Optional[str] = None
        best_scores: Dict[str, float] = {"quality": 0.0, "alignment": 0.0, "aesthetics": 0.0}

        for model_name in candidates:
            log_step(f"Memory Tree candidate start: model={model_name}")
            base_args = copy.deepcopy(refined_inputs)
            tries = 1 + self.prompt_max_retries
            prev_node_id = root.node_id
            prev_scores: Dict[str, float] = {}

            if len(memory) > 0:
                prior_suggestions = memory.get_all_suggestions(deduplicate=True)
                base_args = self._prewarm_initial_args(model_name, base_args, event, prior_suggestions)
                log_step(f"Memory Tree: prewarmed initial args for model={model_name}")

            for attempt in range(tries):
                log_step(f"Memory Tree attempt: model={model_name}, attempt={attempt + 1}/{tries}")
                node = self._new_node(
                    "generation" if attempt == 0 else "refinement",
                    parent=prev_node_id,
                    model=model_name,
                    attempt=attempt
                )

                if attempt == 0:
                    args = base_args
                else:
                    failure_dim = self._diagnose_failure(prev_scores)
                    log_step(f"Memory Tree: refinement focus={failure_dim}")
                    mem_context = memory.to_refinement_context(prev_node_id)
                    args = self._revise_text_prompt(model_name, base_args, event, mem_context, focus=failure_dim)

                out_wav = os.path.join(workdir, f"{node.node_id}_{model_name}.wav")
                wav_path, meta_extras = self._call_model(model_name, args, out_wav, workdir)
                node.output_wav = wav_path
                node.meta["argv"] = args
                node.meta["runner"] = meta_extras.get("runner")
                if "cmd" in meta_extras: node.meta["cmd"] = meta_extras["cmd"]
                if "returncode" in meta_extras: node.meta["returncode"] = meta_extras["returncode"]
                if "stdout" in meta_extras: node.meta["stdout"] = meta_extras["stdout"]
                if "stderr" in meta_extras: node.meta["stderr"] = meta_extras["stderr"]
                if "mp4" in meta_extras: node.meta["mp4"] = meta_extras["mp4"]
                if "error" in meta_extras: node.meta["error"] = meta_extras["error"]
                if "error_type" in meta_extras: node.meta["error_type"] = meta_extras["error_type"]

                valid_audio = False
                validation_error = ""
                if wav_path and os.path.exists(wav_path):
                    valid_audio, validation_error = _audio_is_non_silent(wav_path)

                if not valid_audio:
                    scores = {"quality": 0.0, "alignment": 0.0, "aesthetics": 0.0}
                    err_msg = meta_extras.get("error") or validation_error
                    if err_msg:
                        err_type = meta_extras.get("error_type") or "Error"
                        suggestions = [f"Tool failed: {err_type}: {err_msg}"]
                        node.meta["error"] = err_msg
                        node.meta["error_type"] = meta_extras.get("error_type") or "InvalidAudio"
                    else:
                        suggestions = ["Tool failed to generate valid audio output"]
                    log_step(f"Tool output validation failed: wav_path={wav_path} error={err_msg}")
                else:
                    if self.critic_llm is None:
                        # No audio-capable LLM available; use neutral scores so ToT
                        # continues refining rather than abandoning after one attempt.
                        scores = {"quality": 0.5, "alignment": 0.5, "aesthetics": 0.5}
                        suggestions = ["Audio scoring unavailable (no critic LLM configured)"]
                    else:
                        scores, suggestions = self.critic.evaluate(event, wav_path, self.critic_llm)
                node.meta["scores"] = scores
                node.meta["weighted_score"] = _weighted_score(scores)
                node.meta["suggestions"] = suggestions
                log_step(f"Memory Tree evaluation: model={model_name}, scores={scores}, weighted={_weighted_score(scores):.3f}")

                memory.record(
                    node_id=node.node_id,
                    model=model_name,
                    attempt=attempt,
                    node_type=node.node_type,
                    parent_id=node.parent,
                    args_used=args,
                    scores=scores,
                    suggestions=suggestions,
                )

                # Always promote a valid wav when best_wav is still empty — the critic
                # may be a text-only LLM that returns all-zero scores for audio inputs,
                # in which case strict `>` comparison would never pick any candidate.
                has_valid_wav = valid_audio
                if has_valid_wav and (
                    best_wav is None
                    or _weighted_score(scores) > _weighted_score(best_scores)
                ):
                    best_scores = scores
                    best_wav = wav_path
                    log_step(f"Memory Tree best update: model={model_name}, weighted={_weighted_score(scores):.3f}")

                if _best_threshold_met(scores):
                    log_step(f"Memory Tree early stop: model={model_name} met threshold")
                    nodes_snapshot = {nid: self.nodes[nid].__dict__ for nid in self.nodes}
                    nodes_snapshot["_memory"] = memory.to_dict()
                    return wav_path or "", scores, nodes_snapshot

                if self._should_abandon_model(memory, model_name):
                    log_step(f"Memory Tree: abandon model={model_name} (weighted score not improving), switching")
                    break

                prev_node_id = node.node_id
                prev_scores = scores
                base_args = args

        nodes_snapshot = {nid: self.nodes[nid].__dict__ for nid in self.nodes}
        nodes_snapshot["_memory"] = memory.to_dict()
        log_step("Memory Tree finished: returning best candidate")
        return best_wav or "", best_scores, nodes_snapshot
