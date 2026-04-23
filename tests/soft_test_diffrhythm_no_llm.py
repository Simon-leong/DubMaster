from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experts import SongExpert
from llm import LLM
from plan import AudioEvent
from tools_v2 import ToolLibrary, run_tool


class FakeLLM(LLM):
    """No real LLM calls: deterministic local responses only."""

    def chat(self, system: str, user: str, stop=None, **kwargs) -> str:
        sys_l = (system or "").lower()

        # SongExpert._synthesize_lrc
        if "lyricist creating time-aligned lrc files" in sys_l:
            return json.dumps(
                {
                    "lrc": "[00:00.00]Gentle waves in the evening sky\n[00:02.50]Soft lights drift across the shore\n[00:05.00]oh, oh, oh",
                    "ref_prompt": "Pop Emotional Piano",
                },
                ensure_ascii=False,
            )

        if "audio critic" in sys_l:
            return json.dumps(
                {
                    "quality": 0.9,
                    "alignment": 0.9,
                    "aesthetics": 0.9,
                    "suggestions": ["ok"],
                },
                ensure_ascii=False,
            )

        return "{}"


def _jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    return str(x)


def _find_diffrhythm_tool_name(tool_lib: ToolLibrary) -> str:
    for name, spec in getattr(tool_lib, "tools", {}).items():
        task = str(getattr(spec, "task", "")).lower()
        model = str(getattr(spec, "default_model", "")).lower()
        if ("diffrhythm" in name.lower() or "diffrhythm" in model) and task in (
            "song_gen",
            "song",
            "music",
            "music_gen",
            "song_generation",
        ):
            return name
    raise RuntimeError("No DiffRhythm-like song tool found in tool library.")


def _build_diffrhythm_only_config(src_cfg: str, dst_cfg: str) -> str:
    with open(src_cfg, "r", encoding="utf-8") as f:
        obj = yaml.safe_load(f) or {}
    tools = obj.get("tools") or {}
    diffrhythm_tools = {}
    for name, conf in tools.items():
        name_l = str(name).lower()
        model_l = str((conf or {}).get("default_model", "")).lower()
        if "diffrhythm" in name_l or "diffrhythm" in model_l:
            diffrhythm_tools[name] = conf
    if not diffrhythm_tools:
        raise RuntimeError("No diffrhythm tool config found in source config")
    obj["tools"] = diffrhythm_tools
    with open(dst_cfg, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, allow_unicode=True, sort_keys=False)
    return dst_cfg


def _write_silent_wav(path: str, duration_sec: float = 1.0, sample_rate: int = 24000) -> None:
    nframes = int(max(duration_sec, 0.1) * sample_rate)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * nframes)


def main() -> None:
    ap = argparse.ArgumentParser(description="FakeLLM validation for DiffRhythm routing")
    ap.add_argument("--config", default="config.yaml", help="Source config path")
    ap.add_argument("--outdir", default="test_outputs/soft_diffrhythm_fake_llm", help="Output directory")
    ap.add_argument("--run-live", action="store_true", help="Enable real DiffRhythm API call")
    args = ap.parse_args()

    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="diffrhythm_only_cfg_") as tmp:
        diffrhythm_cfg = os.path.join(tmp, "diffrhythm_only.yaml")
        _build_diffrhythm_only_config(os.path.abspath(args.config), diffrhythm_cfg)

        tool_lib = ToolLibrary(diffrhythm_cfg)
        tool_name = _find_diffrhythm_tool_name(tool_lib)
        spec = tool_lib.get(tool_name)
        runtime = getattr(spec, "runtime", None)

        predict_calls = []
        orig_predict = getattr(runtime, "_predict", None)
        fake_tool_out = os.path.join(outdir, "mock_diffrhythm.wav")
        _write_silent_wav(fake_tool_out, duration_sec=2.0)

        if callable(orig_predict):

            def traced_predict(**kwargs):
                predict_calls.append(dict(kwargs))
                print("[TRACE] DiffRhythm _predict kwargs:")
                print(json.dumps(_jsonable(kwargs), ensure_ascii=False, indent=2))
                if args.run_live:
                    return orig_predict(**kwargs)
                return fake_tool_out

            runtime._predict = traced_predict

        ref_audio = os.path.join(outdir, "prompt_song.wav")
        _write_silent_wav(ref_audio, duration_sec=1.0)

        old_prompt_song = os.environ.get("PROMPT_SONG")
        os.environ["PROMPT_SONG"] = ""

        try:
            events = [
                AudioEvent(
                    audio_type="song",
                    start_time=0.0,
                    end_time=10.0,
                    description="A lyrical pop ballad with warm emotional tone.",
                    volume_db=-14.0,
                    object="Song",
                )
            ]
            plan_ctx = {"__outdir__": outdir}
            out_events = SongExpert(tool_lib).process_batch(events, plan_ctx, FakeLLM())
            if not out_events:
                raise RuntimeError("SongExpert returned no events")

            e0 = out_events[0]

            # DiffRhythm runtime requires ref_prompt/text_prompt even when ref audio is present.
            if selected_model := (e0.model_candidates[0] if e0.model_candidates else None):
                payload = e0.refined_inputs.get(selected_model)
                if isinstance(payload, dict):
                    has_prompt = str(payload.get("ref_prompt") or payload.get("text_prompt") or "").strip()
                    if not has_prompt:
                        payload["ref_prompt"] = "Pop Emotional"

            print("[TRACE] stage2 model_candidates:", e0.model_candidates)
            print("[TRACE] stage2 refined_inputs:")
            print(json.dumps(_jsonable(e0.refined_inputs), ensure_ascii=False, indent=2))

            selected_model = None
            for m in (e0.model_candidates or []):
                if "diffrhythm" in m.lower():
                    selected_model = m
                    break
            selected_model = selected_model or tool_name
            selected_spec = tool_lib.get(selected_model)

            out_wav = os.path.join(outdir, "soft_diffrhythm_fake_llm.wav")
            print(f"[TRACE] invoking tool: {selected_model} (run_live={args.run_live})")
            wav_path = run_tool(selected_spec, e0.refined_inputs, output_wav=out_wav)
            print(f"[RESULT] run_tool success: {wav_path}")
            if not os.path.exists(wav_path):
                raise RuntimeError(f"Expected output does not exist: {wav_path}")

            if predict_calls:
                api_names = [str(c.get("api_name")) for c in predict_calls]
                print("[TRACE] api_name sequence:", api_names)
            else:
                print("[TRACE] no _predict call captured")
        finally:
            if callable(orig_predict):
                runtime._predict = orig_predict
            if old_prompt_song is None:
                os.environ.pop("PROMPT_SONG", None)
            else:
                os.environ["PROMPT_SONG"] = old_prompt_song

    print("Validation finished (fake LLM; tool call is mock by default, live with --run-live).")


if __name__ == "__main__":
    main()
