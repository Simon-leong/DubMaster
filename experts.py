from __future__ import annotations
from typing import Dict, Any, List, Optional
import os
import json
import re

from llm import LLM
from plan import AudioEvent


def _f(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def _sec(ev: AudioEvent) -> float:
    return max(_f(ev.end_time) - _f(ev.start_time), 0.2)


def _norm_type(t: str) -> str:
    return (t or "").strip().lower()


def _extract_quoted(s: str) -> Optional[str]:
    if not s:
        return None
    m = re.search(r"[“\"]([^”\"]+)[”\"]", s)
    return m.group(1) if m else None


def _ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)
    return p


class BaseExpert:
    def __init__(self, tool_lib):
        self.tool_lib = tool_lib

    def has_tool(self, name: str) -> bool:
        return getattr(self.tool_lib, "has")(name)

    def _tools_for_tasks(self, *tasks: str) -> List[str]:
        """Return tool names whose `task` matches one of the requested task labels."""
        wanted = {str(t).strip().lower() for t in tasks if str(t).strip()}
        out: List[str] = []
        for name, spec in getattr(self.tool_lib, "tools", {}).items():
            task = str(getattr(spec, "task", "")).strip().lower()
            if task in wanted:
                out.append(name)
        return out

    def process_batch(self, events: List[AudioEvent], plan_ctx: Dict[str, Any], llm: LLM) -> List[AudioEvent]:
        raise NotImplementedError

    def _llm_json(
        self,
        llm: LLM,
        system: str,
        user: str,
        media: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        system = (system or "").strip() + (
            "\n\nThink step-by-step. "
            "Return JSON only."
        )
        try:
            try:
                raw = llm.chat(system, user, media=media)  
            except TypeError:
                raw = llm.chat(system, user) 
        except Exception:
            return None

        if not raw:
            return None

        raw = raw.strip()

        m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
        if m:
            raw = m.group(1)

        try:
            return json.loads(raw)
        except Exception:
            m2 = re.search(r"(\{.*\}|\[.*\])", raw, flags=re.DOTALL)
            if m2:
                try:
                    return json.loads(m2.group(1))
                except Exception:
                    return None
        return None

    def _llm_text(self, llm: LLM, system: str, user: str) -> str:
        try:
            return (llm.chat(system, user) or "").strip()
        except Exception:
            return ""

# --------- SFX Expert ----------
class SFXExpert(BaseExpert):
    """
    speech expert
    """

    def _sfx_refined_inputs(self, ev: AudioEvent, use_video: bool, video_path: Optional[str]) -> Dict[str, Any]:
        dur = max(1, int(round(_sec(ev))))
        args = {
            "variant": "large_44k_v2",
            "text": ev.description or (ev.object or "a concise sfx for the scene."),
            "seconds": dur,
            "cfg_strength": 4.5,
            "num_steps": 25,
            "seed": -1,
        }
        if use_video and video_path:
            args["video"] = video_path
        return args

    def _pick_sfx_models(self, use_video: bool = False) -> List[str]:
        cands = self._tools_for_tasks("sfx", "sound effect", "sound_effect")
        if use_video:
            video_first = [m for m in cands if "mmaudio" in m.lower()]
            return video_first or cands
        return cands

    def _pick_video_sfx_tool(self) -> Optional[str]:
        """Return a video-capable SFX tool name, preferring MMAudio-like tools."""
        cands = self._pick_sfx_models(use_video=True)
        for name in cands:
            if "mmaudio" in name.lower() and self.has_tool(name):
                return name
        return cands[0] if cands else None

    def process_batch(self, events: List[AudioEvent], plan_ctx: Dict[str, Any], llm: LLM) -> List[AudioEvent]:
        if not events:
            return []

        outdir = plan_ctx.get("__outdir__", os.getcwd())
        video_path = plan_ctx.get("video")
        has_video = bool(video_path)
        video_tool_name = self._pick_video_sfx_tool() if has_video else None

        def _fnum(x, default=0.0):
            try:
                return float(x)
            except Exception:
                return default

        probe_seconds = 6.0

        video_seconds = plan_ctx.get("video_seconds")
        if has_video:
            if not video_seconds:
                try:
                    from utils.media import probe_video_seconds
                    video_seconds = probe_video_seconds(video_path)
                    plan_ctx["video_seconds"] = video_seconds
                except Exception:
                    video_seconds = None

            if video_seconds and video_seconds > 0:
                probe_seconds = float(video_seconds)
            else:
                if events:
                    s_min = min(_fnum(e.start_time, 0.0) for e in events)
                    e_max = max(_fnum(e.end_time, 0.0)   for e in events)
                    probe_seconds = max(1.0, e_max - s_min)
                else:
                    probe_seconds = 6.0
        else:
            if events:
                s_min = min(_fnum(e.start_time, 0.0) for e in events)
                e_max = max(_fnum(e.end_time, 0.0)   for e in events)
                probe_seconds = max(1.0, e_max - s_min)
            else:
                probe_seconds = 6.0

        probe_wav = None
        probe_mp4 = None
        if has_video and video_tool_name:
            probe_dir = os.path.join(outdir, "stage2_sfx_probe")
            os.makedirs(probe_dir, exist_ok=True)
            tool = self.tool_lib.get(video_tool_name)
            video_arg = f'--video "{video_path}"'
            video_stem = os.path.splitext(os.path.basename(video_path))[0]
            probe_wav_path = os.path.join(probe_dir, f"{video_stem}_probe.wav")
            # take first event with sound effect
            first_ev = next((e for e in events if _norm_type(e.audio_type) in ("sound effect", "sound_effect", "sfx")), None)
            text = (first_ev.object) if first_ev else ""

            args = {
                "variant": "large_44k_v2",
                "video_arg": video_arg,
                "text": text,
                "seconds": int(max(1, round(probe_seconds))),
                "cfg_strength": 4.5,
                "num_steps": 25,
                "output_dir": probe_dir,
                "seed": -1,
                "output": probe_wav_path,
            }
            try:
                from tools_v2 import run_tool
                wav_out = run_tool(tool, args, output_wav=probe_wav_path)
                probe_wav = wav_out if wav_out and os.path.exists(wav_out) else None
                guess_mp4 = os.path.splitext(probe_wav)[0] + ".mp4" if probe_wav else None
                probe_mp4 = guess_mp4 if (guess_mp4 and os.path.exists(guess_mp4)) else None
            except Exception:
                probe_wav = None
                probe_mp4 = None

        # ============ Evaluation ============
        def _pack_src(ev: AudioEvent) -> dict:
            return {
                "audio_type": ev.audio_type or "sound effect",
                "Object": ev.object or "",
                "start_time": str(_f(ev.start_time, 0.0)),
                "end_time": str(_f(ev.end_time, 0.0)),
                "description": ev.description or "",
                "volume": getattr(ev, "volume_db", -6.0),
            }

        src_list = [_pack_src(e) for e in events]

        decision_keep = False
        merged_items: List[dict] = []
        residual_items: List[dict] = []

        if probe_mp4:
            system = (
                "You are an audio SFX planning reviewer.\n"
                "Given: (a) a video-with-audio MP4 generated by a video-conditioned SFX model, "
                "(b) the original Stage-1 SFX plan (JSON list).\n"
                "Tasks:\n"
                "1) Decide KEEP or DISCARD for this generated result.\n"
                "2) If KEEP: produce a revised SFX plan where covered on-screen SFX are merged into ONE consolidated event; "
                "   keep residual (off-screen/implicit) SFX as separate items (text-only later).\n"
                "Return JSON only: {decision: KEEP|DISCARD, merged_video_event: [ ...one item... ], residual_events: [...]}."
            )
            user = json.dumps({"original_sfx_plan": src_list}, ensure_ascii=False)
            media = {"videos": [probe_mp4]}
            obj = self._llm_json(llm, system, user, media=media)
            if isinstance(obj, dict):
                decision_keep = (str(obj.get("decision","")).upper() == "KEEP")
                mve = obj.get("merged_video_event") or []
                if isinstance(mve, dict):
                    merged_items = [mve]
                if isinstance(mve, list):
                    merged_items = mve
                res = obj.get("residual_events") or []
                if isinstance(res, list):
                    residual_items = res
                if isinstance(res, dict):
                    residual_items = [res]

        # ============ Final Decision ============
        out_events: List[AudioEvent] = []

        if has_video and decision_keep and merged_items:
            m = merged_items[0]
            main_ev = AudioEvent(
                audio_type=m.get("audio_type","sound effect"),
                object=m.get("Object","") or "",
                start_time=_f(m.get("start_time"), 0.0),
                end_time=_f(m.get("end_time"), _f(m.get("start_time"), 0.0)),
                description=m.get("description","") or "",
                volume_db=_f(m.get("volume"), -6.0),
            )
            # === key markers ===
            main_ev.keep = True
            main_ev.keep_wav = probe_wav if (probe_wav and os.path.exists(probe_wav)) else ""
            # avoid regeneation in Stage 3 
            main_ev.model_candidates = []
            main_ev.refined_inputs = {}

            out_events.append(main_ev)

            # write keep list
            if probe_wav and os.path.exists(probe_wav):
                keep_seg = {
                    "audio_type": "sound effect",
                    "Object": main_ev.object or "Primary on-screen SFX (MMAudio+video)",
                    "start_time": str(main_ev.start_time),
                    "end_time": str(main_ev.end_time),
                    "duration": str(max(0.0, main_ev.end_time - main_ev.start_time)),
                    "description": main_ev.description,
                    "volume": float(main_ev.volume_db),
                    "keep": main_ev.keep,
                    "wav_file": probe_wav
                }
                try:
                    keep_file = os.path.join(outdir, "stage2_sfx_probe_keep.json")
                    if os.path.exists(keep_file):
                        prev = json.load(open(keep_file, "r", encoding="utf-8"))
                        if isinstance(prev, list):
                            if not any((isinstance(x, dict) and x.get("wav_file")==keep_seg["wav_file"]) for x in prev):
                                prev.append(keep_seg)
                        else:
                            prev = [prev, keep_seg]
                        json.dump(prev, open(keep_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                    else:
                        json.dump([keep_seg], open(keep_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                except Exception:
                    pass

            # text-only
            for it in residual_items:
                ev = AudioEvent(
                    audio_type=it.get("audio_type","sound effect"),
                    object=it.get("Object","") or "",
                    start_time=_f(it.get("start_time"), 0.0),
                    end_time=_f(it.get("end_time"), _f(it.get("start_time"), 0.0)),
                    description=it.get("description","") or "",
                    volume_db=_f(it.get("volume"), -6.0),
                )
                ev.model_candidates = self._pick_sfx_models(use_video=False)
                ev.refined_inputs = self._sfx_refined_inputs(ev, use_video=False, video_path=None)
                out_events.append(ev)
            return out_events

        # no video / fail to meet the requirement
        for e in events:
            ev = AudioEvent(
                audio_type=e.audio_type or "sound effect",
                object=e.object or "",
                start_time=_f(e.start_time, 0.0),
                end_time=_f(e.end_time, _f(e.start_time, 0.0)),
                description=e.description or "",
                volume_db=getattr(e, "volume_db", -6.0),
            )
            use_video = bool(has_video and video_tool_name)
            ev.model_candidates = self._pick_sfx_models(use_video=use_video)
            ev.refined_inputs = self._sfx_refined_inputs(ev, use_video=use_video, video_path=video_path if use_video else None)
            out_events.append(ev)

        return out_events

# --------- Speech Expert ----------
class SpeechExpert(BaseExpert):
    """
    Speech expert
    """
    DEFAULT_PROMPT_TRANSCRIPT = "希望你以后能够做的比我还好呦。"
    DEFAULT_PROMPT_WAV = "bin/zero_shot_prompt.wav"

    def _recognize_prompt_transcript(self, prompt_wav_path: str) -> str:
        if not prompt_wav_path or not os.path.exists(prompt_wav_path):
            return ""

        for tool_name in self._tools_for_tasks("tts", "speech", "voice"):
            if "cosyvoice3" not in tool_name.lower():
                continue
            try:
                runtime = getattr(self.tool_lib.get(tool_name), "runtime", None)
                if runtime is None or not hasattr(runtime, "recognize_prompt_wav"):
                    continue
                transcript = str(runtime.recognize_prompt_wav(prompt_wav_path) or "").strip()
                if transcript:
                    return transcript
            except Exception:
                continue
        return ""

    def _resolve_prompt_reference(self, plan_ctx: Dict[str, Any]) -> tuple[str, str]:
        prompt_wav_path = str(
            (plan_ctx or {}).get("prompt_wav_path")
            or (plan_ctx or {}).get("reference_audio")
            or ""
        ).strip()
        prompt_transcript = str(
            (plan_ctx or {}).get("prompt_transcript")
            or (plan_ctx or {}).get("reference_audio_transcript")
            or ""
        ).strip()
        fallback_transcript = str((plan_ctx or {}).get("speech_target_text") or "").strip()

        if prompt_wav_path and os.path.exists(prompt_wav_path):
            if not prompt_transcript:
                cache_key = "__recognized_prompt_transcript__"
                prompt_transcript = str((plan_ctx or {}).get(cache_key) or "").strip()
                if not prompt_transcript:
                    prompt_transcript = self._recognize_prompt_transcript(prompt_wav_path)
                    if prompt_transcript:
                        plan_ctx[cache_key] = prompt_transcript
                        plan_ctx["prompt_transcript"] = prompt_transcript
            return prompt_wav_path, (prompt_transcript or fallback_transcript or self.DEFAULT_PROMPT_TRANSCRIPT)

        return self.DEFAULT_PROMPT_WAV, (prompt_transcript or fallback_transcript or self.DEFAULT_PROMPT_TRANSCRIPT)

    def process_batch(self, events: List[AudioEvent], plan_ctx: Dict[str, Any], llm: LLM) -> List[AudioEvent]:
        if not events:
            return []
        sys = (
            "You are a TTS planning expert. For each speech event, extract the exact utterance text, "
            "infer a stable speaker_id (same character shares the same id), and give a brief voice_style cue."
        )
        user = json.dumps({
            "speech_events": [e.__dict__ for e in events],
            "output_schema": {
                "keys": ["index","utterance","speaker_id","voice_style"]
            }
        }, ensure_ascii=False)
        obj = self._llm_json(llm, sys, user) or {}
        idx_map = {}
        if isinstance(obj, list):
            for it in obj:
                idx_map[int(it.get("index", -1))] = it
        elif isinstance(obj, dict) and isinstance(obj.get("items"), list):
            for i,it in enumerate(obj["items"]):
                idx_map[i] = it
        elif isinstance(obj, dict) and "index" in obj:
            idx_map[int(obj.get("index", -1))] = obj
        else:
            idx_map = {}

        user_target_text = (plan_ctx.get("speech_target_text") or "").strip()
        out: List[AudioEvent] = []
        prompt_wav, prompt_transcript = self._resolve_prompt_reference(plan_ctx)
        for i,e in enumerate(events):
            it = idx_map.get(i, {})
            utter = user_target_text or it.get("utterance") or _extract_quoted(e.object) or _extract_quoted(e.description) or (e.description or e.object or "...")
            style = it.get("voice_style") or "neutral narration"
            cands = self._tools_for_tasks("tts", "speech", "voice")
            e.model_candidates = cands[:2]
            e.refined_inputs = {}
            for model_name in e.model_candidates:
                lname = model_name.lower()
                if "cosyvoice3" in lname:
                    e.refined_inputs[model_name] = {
                        "target_text": utter,
                        "prompt_text": prompt_transcript,
                        "prompt_wav": prompt_wav
                    }
                elif "cosyvoice2" in lname:
                    e.refined_inputs[model_name] = {
                        "text": utter,
                        "prompt_transcript": prompt_transcript,
                        "prompt_wav": prompt_wav,
                        "instruct_text": style,
                    }
                elif "firered" in lname:
                    e.refined_inputs[model_name] = {
                        "text": utter,
                        "style": "narration_warm" if "warm" in style else "narration"
                    }
                else:
                    e.refined_inputs[model_name] = {
                        "text": utter,
                        "style": style,
                    }
            out.append(e)
        return out

# --------- Music Expert ----------
class MusicExpert(BaseExpert):
    """
    Music Expert
    """
    def process_batch(self, events: List[AudioEvent], plan_ctx: Dict[str, Any], llm: LLM) -> List[AudioEvent]:
        if not events:
            return []
        sys = "You are a background music planning expert. For each event, produce a concise text prompt and choose a chorus part from {intro, verse, chorus, outro}."
        user_payload = {
            "instruction": "Your response MUST be a JSON object with a single key 'music_events'. The value of this key must be a list of items.",
            "music_events_input": [e.__dict__ for e in events],
            "output_schema": {"keys": ["index", "text", "chorus"]}
        }
        user = json.dumps(user_payload, ensure_ascii=False)
        obj = self._llm_json(llm, sys, user) or {}
        decided: Dict[int, Dict[str,str]] = {}
        if isinstance(obj, dict):
            for it in obj.get('music_events', []):
                if isinstance(it, dict) and "index" in it:
                    decided[int(it.get("index"))] = {"text": it.get("text", ""), "chorus": it.get("chorus", "verse")}
        elif isinstance(obj, list):
            for it in obj:
                if isinstance(it, dict) and "index" in it:
                    decided[int(it.get("index"))] = {"text": it.get("text", ""), "chorus": it.get("chorus", "verse")}

        out: List[AudioEvent] = []
        for i,e in enumerate(events):
            dur = round(_sec(e), 1)
            choice = decided.get(i, {"text": (e.description or "Ambient underscore, unobtrusive."), "chorus": "verse"})
            cands = self._tools_for_tasks("music")
            e.model_candidates = cands[:2]
            e.refined_inputs = {}
            for model_name in e.model_candidates:
                lname = model_name.lower()
                if "inspiremusic" in lname:
                    e.refined_inputs[model_name] = {"text": choice["text"], "seconds": dur, "chorus": choice["chorus"]}
                else:
                    e.refined_inputs[model_name] = {"text": choice["text"], "seconds": dur}
            out.append(e)
        return out

# --------- Song Expert ----------
class SongExpert(BaseExpert):
    """
    Song expert
    1) lrc_path（[mm:ss.xx] timestamp）
    2) ref-audio-path or ref-prompt；
    3) refined_inputs or bin/run_diffrhythm.py alignment
    """
    def _synthesize_lrc(self, llm: LLM, desc: str, total_duration_sec: float, out_path: str) -> str:
        system = "You are a lyricist creating time-aligned LRC files and music planner. Return a STRICT JSON object with keys 'lrc' and 'ref_prompt' and NOTHING ELSE."
        user = (
            "Task:\n"
            f"1) Create an .lrc for a song whose TOTAL duration is exactly {total_duration_sec:.2f} seconds.\n"
            f"   Content hint: {desc}\n"
            "   Requirements for 'lrc':\n"
            "   - Each line: [mm:ss.xx]LyricText\n"
            "   - Timestamps strictly increasing and span the whole duration.\n"
            "   - The FINAL line MUST be the TOTAL-DURATION timestamp AND include a trivial filler lyric\n"
            "     (Chinese lyrics → use something like 「哦，哦，哦」/「啦啦啦」; English lyrics → use \"oh, oh, oh\").\n"
            "   Example for 8s total:\n"
            "     [00:00.85]牵你的手啊\n"
            "     [00:02.55]在岁月种下鲜花\n"
            "     [00:05.35]在寻常烟火人家\n"
            "     [00:08.00]哦，哦，哦\n"
            "\n"
            "2) Produce 'ref_prompt' as a SINGLE-LINE phrase (NO newlines). "
            "It can be English, Chinese, or mixed, e.g.:\n"
            "   Pop Emotional Piano\n"
            "   Indie folk ballad, coming-of-age themes, acoustic guitar with harmonica\n"
            "   独立民谣, 成长主题, 原声吉他与口琴间奏\n"
            "   流行 情感 钢琴\n"
            "\n"
            "Return ONLY JSON (no code fences). Example schema:\n"
            "{\n"
            '  \"lrc\": \"[00:00.85]...\\n[00:08.00]\\n\",\n'
            '  \"ref_prompt\": \"Pop Emotional Piano\"\n'
            "}"
        )
        raw = self._llm_json(llm, system, user) or {}
        lrc_str = (raw.get("lrc") or "").strip()
        ref_prompt = (raw.get("ref_prompt") or "").strip()
        _ensure_dir(os.path.dirname(out_path))
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(lrc_str.strip())
        return out_path, ref_prompt

    def process_batch(self, events: List[AudioEvent], plan_ctx: Dict[str, Any], llm: LLM) -> List[AudioEvent]:
        if not events:
            return []

        out: List[AudioEvent] = []
        base = plan_ctx.get("__outdir__", os.getcwd())

        for idx, e in enumerate(events):
            dur = max(_sec(e), 0.2)

            # 1) generate lrc
            lrc_dir = _ensure_dir(os.path.join(base, "stage2_song_lrc"))
            lrc_path = os.path.join(lrc_dir, f"event_{idx}.lrc")
            lrc_path, gemini_ref_prompt = self._synthesize_lrc(llm, e.description or e.object or "流行抒情", dur, lrc_path)

            # 2) ref-audio-path / ref-prompt 
            prompt_wav = os.environ.get("PROMPT_SONG", None)
            # prompt_wav = None
            ref_audio_path = getattr(e, "ref_audio_path", None) or plan_ctx.get("ref_audio_path")  or prompt_wav
            ref_prompt     = getattr(e, "ref_prompt",     None) or plan_ctx.get("ref_prompt") or gemini_ref_prompt
            if not ref_audio_path and not ref_prompt:
                ref_prompt = (e.description or e.object or "pop, gentle vocal, warm.").strip()

            # 3) choose model + refined_inputs
            cands = self._tools_for_tasks("song", "singing", "vocal", "song_gen")
            e.model_candidates = cands[:1]
            e.refined_inputs = {}

            audio_seconds = int(round(dur))

            if e.model_candidates:
                model_name = e.model_candidates[0]
                if ref_audio_path:
                    e.refined_inputs[model_name] = {
                        "lrc_path": lrc_path,
                        "ref_audio_path": ref_audio_path,
                        "ref_prompt": "",
                        "seconds": audio_seconds,
                        "batch_infer_num": 5,
                        "chunked": True
                    }
                else:
                    e.refined_inputs[model_name] = {
                        "lrc_path": lrc_path,
                        "ref_audio_path": "",
                        "ref_prompt": ref_prompt,
                        "seconds": audio_seconds,
                        "batch_infer_num": 5,
                        "chunked": True
                    }

            out.append(e)
        return out

# --------- factory ----------
def build_expert(audio_type: str, tool_lib) -> BaseExpert:
    t = _norm_type(audio_type)
    if t in ("sound effect","sound_effect","sfx"):
        return SFXExpert(tool_lib)
    if t in ("speech","tts","voice"):
        return SpeechExpert(tool_lib)
    if t in ("music",):
        return MusicExpert(tool_lib)
    if t in ("song","singing","vocal"):
        return SongExpert(tool_lib)
    return SFXExpert(tool_lib)
