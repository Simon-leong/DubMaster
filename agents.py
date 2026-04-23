from typing import Dict, Any, List, Optional
import json, os, pathlib, re

from llm import LLM
from plan import Plan, AudioEvent
from experts import build_expert, BaseExpert
from tools_v2 import ToolLibrary
from critiquers import PlanningCritic, DomainCritic, AudioEvalCritic, LLMPlanningReviewer
from tot import ToTExecutor
from mixer import mix_and_maybe_mux
from utils.media import probe_video_seconds
from utils.runtime_logger import log_step


def _norm_type(t: str) -> str:
    return (t or "").strip().lower()

def _tolist(x):
    if not x:
        return []
    return x if isinstance(x, (list, tuple)) else [x]

def _to_canonical_plan_json(s: str) -> str:
    """
    {"audio_seg":[...]} 
    """
    s = (s or "").strip()
    if not s:
        raise ValueError("empty plan json")

    m = re.match(r"^\s*audio_seg\s*=\s*(\[.*\])\s*$", s, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return json.dumps({"audio_seg": json.loads(m.group(1))}, ensure_ascii=False)

    # {"audio_seg":[...]} / {"events":[...]}
    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and ("audio_seg" in obj or "events" in obj):
            if "audio_seg" in obj:
                return json.dumps({"audio_seg": obj["audio_seg"]}, ensure_ascii=False)
            else:
                return json.dumps({"audio_seg": obj["events"]}, ensure_ascii=False)
        if isinstance(obj, list):
            return json.dumps({"audio_seg": obj}, ensure_ascii=False)
    except json.JSONDecodeError:
        pass

    # 3)  markdown
    try:
        m2 = re.search(r"\[\s*{.*?}\s*\]", s, flags=re.DOTALL)
        if m2:
            s2 = '{"audio_seg": ' + m2.group(0) + '}'
            json.loads(s2) 
            return s2
    except Exception:
        pass

    # 4) make sure
    try:
        json.loads(s)
        return json.dumps({"audio_seg": json.loads(s)}, ensure_ascii=False)
    except json.JSONDecodeError:
        m3 = re.search(r"\[\s*{.*?}\s*\]", s, flags=re.DOTALL)
        if m3:
            s2 = '{"audio_seg": ' + m3.group(0) + '}'
            json.loads(s2)
            return s2
        raise


class GenerationTeam:
    def __init__(self, llm: LLM, tool_lib: ToolLibrary):
        self.llm = llm
        self.tool_lib = tool_lib

    def plan(self, multimodal_context: Dict[str, Any]) -> Plan:
        log_step("Stage-1 planning: building multimodal event plan")
        ctx = multimodal_context or {}
        video_path = ctx.get("video")
        video_duration = None
        if video_path:
            try:
                # get seconds of the video
                from utils.media import probe_video_seconds
                video_duration = probe_video_seconds(video_path)
            except Exception as e:
                print(f"Error extracting video duration: {e}")

        output_class = (ctx.get("output_class") or "").strip()
        target_duration = ctx.get("target_duration")

        system = "You are a multimodal audio planning expert."
        user = (
            "Your task is to analyze all given inputs (video, images, text or their mix) and identify every distinct audio event implied.\n" 
            "For each audio event, determine its audio_type (one of \"speech\", \"sound effect\", \"music\", \"song\"), its object, its start and end times, its duration, and a detail description of the sound content. Also, assign an appropriate volume (db). Ensure the timing of each event matches the timeline of input and that the descriptions clearly describe the intended audio.\n"
            "[Output Format Example]: (JSON list) \n"
            "Organize all identified events in a structured JSON list, where each list element is an object with keys. Output only the JSON structured plan without additional commentary.\n"
            "audio_seg=[\n"
            "  {\n"
            "    \"audio_type\": \"Sound effect\",\n"
            "    \"Object\": \"Footstep\",\n"
            "    \"start_time\": \"2\",\n"
            "    \"end_time\": \"7\",\n"
            "    \"duration\": \"5\",\n"
            "    \"description\": \"Footsteps in the forest, light gravel crunch, moderate pace.\",\n"
            "    \"volume\": -2\n"
            "  },\n"
            "  {\n"
            "    \"audio_type\": \"Speech\",\n"
            "    \"Object\": \"Character 1 (young girl's voice) says, \\\"Woa! It is so beautiful!\\\"\",\n"
            "    \"start_time\": \"8\",\n"
            "    \"end_time\": \"12\",\n"
            "    \"duration\": \"4\",\n"
            "    \"description\": \"Bright timbre, soft onset, rising-falling contour, full of surprise and delight; exact words: \\\"Woa! It is so beautiful!\\\"\",\n"
            "    \"volume\": 0\n"
            "  },\n"
            "  {\n"
            "    \"audio_type\": \"Music\",\n"
            "    \"Object\": \"Background Music\",\n"
            "    \"start_time\": \"0\",\n"
            "    \"end_time\": \"13.8\",\n"
            "    \"duration\": \"13.8\",\n"
            "    \"description\": \"Fresh, serene guitar-and-piano bed; gentle tempo, airy pads, evokes a light breeze across grassy fields; unobtrusive underscore.\",\n"
            "    \"volume\": -10\n"
            "  }\n"
            "]\n"
        )

        if video_duration:
            user = user + (f"\n The total duration of given video is {video_duration}")

        hint_lines = []
        if output_class:
            classes = [c.strip() for c in output_class.split(",") if c.strip()]
            if len(classes) == 1:
                hint_lines.append(
                    f"- Preferred audio category: {classes[0]}. Bias the plan strongly toward this category; "
                    f"only include other categories if they are essential support."
                )
            else:
                hint_lines.append(
                    f"- Preferred audio categories: {', '.join(classes)}. "
                    f"The plan should include events from ALL of these categories. "
                    f"Do not include categories outside this list unless essential."
                )
        if target_duration:
            hint_lines.append(
                f"- Target total duration: {target_duration} seconds. Keep every event inside [0, {target_duration}]."
            )
        speech_target_text = (ctx.get("speech_target_text") or "").strip()
        if speech_target_text:
            hint_lines.append(
                f"- The user has provided the EXACT speech utterance: \"{speech_target_text}\". "
                f"Produce exactly ONE speech event whose Object and description contain this verbatim sentence; "
                f"do not paraphrase, split, or translate it."
            )
        if hint_lines:
            user = user + "\n\nUser constraints (respect these):\n" + "\n".join(hint_lines)

        media = {
            "texts":  _tolist(ctx.get("text")),
            "images": _tolist(ctx.get("image")),
            "videos": _tolist(ctx.get("video")),
        }

        reply = self.llm.chat(system, user, media=media)

        cleaned = _to_canonical_plan_json(reply)
        plan = Plan.from_json(cleaned)
        log_step(f"Stage-1 planning complete: events={len(plan.events)}")
        return plan

    def assign_and_refine(
        self,
        plan: Plan,
        critics: DomainCritic,
        plan_ctx: Dict[str, Any],
        outdir: str,
    ) -> Plan:
        """
        Stage-2:
        1) SFX 
        2) other expert (speech/song/music)
        """
        log_step("Stage-2 assign/refine: routing events to experts")
        buckets: Dict[str, List[AudioEvent]] = {"sfx": [], "speech": [], "music": [], "song": []}
        for e in plan.events:
            t = _norm_type(e.audio_type)
            if t in ("sound effect", "sound_effect", "sfx"):
                buckets["sfx"].append(e)
            elif t in ("speech", "tts", "voice"):
                buckets["speech"].append(e)
            elif t in ("music",):
                buckets["music"].append(e)
            elif t in ("song", "singing", "vocal"):
                buckets["song"].append(e)

        ctx = {
            "video": (plan_ctx or {}).get("video"),
            "video_seconds": probe_video_seconds((plan_ctx or {}).get("video")) if (plan_ctx or {}).get("video") else None,
            "text": (plan_ctx or {}).get("text"),
            "image": (plan_ctx or {}).get("image"),
            "prompt_wav_path": (plan_ctx or {}).get("prompt_wav_path") or (plan_ctx or {}).get("reference_audio"),
            "prompt_transcript": (
                (plan_ctx or {}).get("prompt_transcript")
                or (plan_ctx or {}).get("reference_audio_transcript")
                or ""
            ),
            "reference_audio": (plan_ctx or {}).get("reference_audio"),
            "reference_audio_transcript": (plan_ctx or {}).get("reference_audio_transcript") or "",
            "speech_target_text": (plan_ctx or {}).get("speech_target_text") or "",
            "__outdir__": outdir,
        }

        processed: List[AudioEvent] = []

        # SFX
        if buckets["sfx"]:
            log_step(f"Stage-2 expert run: sfx count={len(buckets['sfx'])}")
            sfx_expert: BaseExpert = build_expert("sound effect", self.tool_lib)
            sfx_out = sfx_expert.process_batch(buckets["sfx"], ctx, self.llm)
            processed.extend(sfx_out)

        # other type
        for key in ("speech", "music", "song"):
            lst = buckets[key]
            if not lst:
                continue
            log_step(f"Stage-2 expert run: {key} count={len(lst)}")
            expert: BaseExpert = build_expert(key, self.tool_lib)
            out_list = expert.process_batch(lst, ctx, self.llm)
            processed.extend(out_list)

        new_events: List[AudioEvent] = []
        for e in processed:
            before_mc = getattr(e, "model_candidates", [])
            before_ri = getattr(e, "refined_inputs", {})
            event_dict = e.__dict__ | {"model_candidates": before_mc, "refined_inputs": before_ri}
            event_dict, _ = critics.review(event_dict)

            mc = event_dict.get("model_candidates")
            ri = event_dict.get("refined_inputs")
            e.model_candidates = mc if mc else before_mc
            e.refined_inputs  = ri if ri else before_ri

            new_events.append(e)

        new_events.sort(key=lambda x: float(x.start_time))
        plan.events = new_events
        log_step(f"Stage-2 assign/refine complete: events={len(plan.events)}")
        return plan

    def collaborative_refine(self, plan: Plan) -> Plan:
        system = (
            "You are the collaborative refinement coordinator across domain experts. "
            "Review the entire event list for temporal alignment, overlap sanity, and volume planning. "
            "Keep the same number of items and the same schema. Return ONLY a JSON object with key 'audio_seg'."
        )
        user = plan.to_json()

        raw = self.llm.chat(system, user)
        try:
            cleaned = _to_canonical_plan_json(raw)
            revised = Plan.from_json(cleaned)
            return revised
        except Exception:
            return plan  

    def synthesize_with_tot(
        self,
        plan: Plan,
        outdir: str,
        eval_critic: AudioEvalCritic,
        max_depth: int = 3,
        max_siblings: int = 3,
        critic_llm: "LLM | None" = None,
    ) -> Dict[str, Any]:
        log_step("Stage-3 synthesis: launching ToT executor")
        pathlib.Path(outdir).mkdir(parents=True, exist_ok=True)
        executor = ToTExecutor(self.tool_lib, self.llm, eval_critic, max_depth=max_depth, max_siblings=max_siblings, critic_llm=critic_llm)
        results = []
        for idx, e in enumerate(plan.events):
            log_step(f"Stage-3 event begin: index={idx}, type={e.audio_type}")
            event_dict = e.__dict__ | {"visual_caption": plan.visual_caption}
            workdir = os.path.join(outdir, f"event_{idx:02d}")
            os.makedirs(workdir, exist_ok=True)

            if getattr(e, "keep", False) and isinstance(getattr(e, "keep_wav", ""), str) and os.path.exists(getattr(e, "keep_wav", "")):
                best_wav = getattr(e, "keep_wav")
                scores = {"quality": 1.0, "alignment": 1.0, "aesthetics": 1.0}
                nodes = {
                    "kept": {
                        "node_id": "kept",
                        "node_type": "kept",
                        "model": "PROBE_KEEP",
                        "output_wav": best_wav,
                        "parent": None,
                        "children": [],
                        "meta": {"note": "Kept from Stage-2 video probe"}
                    }
                }
            else:
                best_wav, scores, nodes = executor.run(event_dict, workdir)

            results.append({
                "index": idx,
                "model_candidates": e.model_candidates,
                "refined_inputs": e.refined_inputs,
                "wav": best_wav,
                "scores": scores,
                "nodes": nodes
            })
            log_step(f"Stage-3 event complete: index={idx}, wav={best_wav}, scores={scores}")
        log_step("Stage-3 synthesis complete")
        return {"events": results}


class SupervisorTeam:
    def __init__(self, llm):
        self.plan_critic = PlanningCritic()
        self.domain_critic = DomainCritic()
        self.eval_critic = AudioEvalCritic()
        self.llm_reviewer = LLMPlanningReviewer(llm)

    def review_plan(self, plan: Plan, multimodal_context: Dict[str, Any]) -> Plan:
        draft = plan.to_json()
        try:
            revised = self.llm_reviewer.review(draft, multimodal_context)
            plan = Plan.from_json(revised)
        except Exception:
            obj = json.loads(plan.to_json())
            obj2, _ = self.plan_critic.review(obj)
            plan = Plan.from_json(json.dumps(obj2, ensure_ascii=False))
        return plan

    def get_domain_critic(self) -> DomainCritic:
        return self.domain_critic

    def get_eval_critic(self) -> AudioEvalCritic:
        return self.eval_critic


_shared_tool_lib: Optional[ToolLibrary] = None


def get_shared_tool_lib() -> ToolLibrary:
    """Return a process-wide singleton ToolLibrary.

    Building a ToolLibrary eagerly handshakes with every Gradio Space in the
    config, which takes several seconds and can hang if a Space is slow. The
    backend spawns a fresh DubMasterSystem per job, so without caching, each
    request pays that cost again and one slow Space can time the whole job out.
    """
    global _shared_tool_lib
    if _shared_tool_lib is None:
        _shared_tool_lib = ToolLibrary()
    return _shared_tool_lib


class DubMasterSystem:
    def __init__(self, llm: LLM, outdir: str = "outputs", critic_llm: LLM = None):
        self.tool_lib = get_shared_tool_lib()
        self.eval_critic = AudioEvalCritic()
        self.critic_llm = critic_llm
        self.generation = GenerationTeam(llm, self.tool_lib)
        self.supervisor = SupervisorTeam(llm)
        self.outdir = outdir

    def run(self, multimodal_context: Dict[str, Any], max_depth: int = 3, max_siblings: int = 3) -> Dict[str, Any]:
        log_step("Pipeline start")
        plan = self.generation.plan(multimodal_context)
        os.makedirs(self.outdir, exist_ok=True)
        with open(os.path.join(self.outdir, "stage1_output.json"), "w", encoding="utf-8") as f:
            f.write(plan.to_json())
        log_step("Saved stage1_output.json")

        plan = self.generation.assign_and_refine(
            plan,
            self.supervisor.get_domain_critic(),
            plan_ctx=multimodal_context,
            outdir=self.outdir,
        )
        with open(os.path.join(self.outdir, "stage2_output.json"), "w", encoding="utf-8") as f:
            f.write(plan.to_json())
        log_step("Saved stage2_output.json")

        results = self.generation.synthesize_with_tot(
            plan, outdir=self.outdir, eval_critic=self.eval_critic,
            max_depth=max_depth, max_siblings=max_siblings,
            critic_llm=self.critic_llm,
        )
        audio_segments = []
        res_events = results.get("events", [])
        seen_wavs = set()

        for i, e in enumerate(plan.events):
            wav = (res_events[i].get("wav") if i < len(res_events) else None) or ""
            if wav and os.path.exists(wav) and (wav not in seen_wavs):
                seen_wavs.add(wav)
                audio_segments.append({
                    "audio_type": e.audio_type,
                    "Object": e.object or "",
                    "start_time": e.start_time,
                    "end_time": e.end_time,
                    "duration": e.end_time - e.start_time,
                    "description": e.description,
                    "volume": getattr(e, "volume_db", 0.0),
                    "wav_file": wav
                })

        keep_file = os.path.join(self.outdir, "stage2_sfx_probe_keep.json")
        if os.path.exists(keep_file):
            try:
                with open(keep_file, "r", encoding="utf-8") as _kf:
                    keep_list = json.load(_kf)
                if isinstance(keep_list, list):
                    for seg in keep_list:
                        w = seg.get("wav_file")
                        if w and os.path.exists(w) and w not in seen_wavs:
                            seen_wavs.add(w)
                            audio_segments.append(seg)
            except Exception:
                pass

        mixed = None
        if audio_segments:
            video_path = (multimodal_context or {}).get("video")
            final_wav = os.path.join(self.outdir, "final_mixed_audio.wav")
            final_mp4 = os.path.join(self.outdir, "final_video_with_audio.mp4")
            try: 
                log_step(f"Mixing {len(audio_segments)} audio segments")
                mixed = mix_and_maybe_mux(
                    video_path=(multimodal_context or {}).get("video"),
                    audio_segments=audio_segments,
                    output_audio_path=final_wav,
                    output_video_path=final_mp4
                )
                log_step("Mixing completed")
            except Exception as _e:
                mixed = {"error": str(_e)}
                log_step(f"Mixing failed: {_e}")

        with open(os.path.join(self.outdir, "stage3_mix_segments.json"), "w", encoding="utf-8") as f:
            json.dump(audio_segments, f, ensure_ascii=False, indent=2)
        with open(os.path.join(self.outdir, "stage3_output.json"), "w", encoding="utf-8") as f:
            json.dump({"results": results, "mixed": mixed}, f, ensure_ascii=False, indent=2)

        log_step("Pipeline finished")
        return {"plan": json.loads(plan.to_json()), "results": results, "mixed": mixed}
