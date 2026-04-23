from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experts import SFXExpert
from llm import LLM
from plan import AudioEvent
from tools_v2 import ToolLibrary, run_tool


class FakeLLM(LLM):
    """No real LLM calls: deterministic local responses only."""

    def chat(self, system: str, user: str, stop=None, **kwargs) -> str:
        sys_l = (system or "").lower()

        # Force fallback path in Stage-2 to inspect refined_inputs clearly.
        if "audio sfx planning reviewer" in sys_l:
            return json.dumps(
                {
                    "decision": "DISCARD",
                    "merged_video_event": [],
                    "residual_events": [],
                },
                ensure_ascii=False,
            )

        # Generic critic output if reached.
        if "audio critic" in sys_l:
            return json.dumps(
                {
                    "quality": 0.8,
                    "alignment": 0.8,
                    "aesthetics": 0.8,
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


def _find_mmaudio_tool_name(tool_lib: ToolLibrary) -> str:
    for name, spec in getattr(tool_lib, "tools", {}).items():
        task = str(getattr(spec, "task", "")).lower()
        model = str(getattr(spec, "default_model", "")).lower()
        if ("mmaudio" in name.lower() or "mmaudio" in model) and task in ("sfx", "sound effect", "sound_effect"):
            return name
    raise RuntimeError("No MMAudio-like SFX tool found in tool library.")


def _build_mmaudio_only_config(src_cfg: str, dst_cfg: str) -> str:
    with open(src_cfg, "r", encoding="utf-8") as f:
        obj = yaml.safe_load(f) or {}
    tools = obj.get("tools") or {}
    mmaudio_tools = {}
    for name, conf in tools.items():
        name_l = str(name).lower()
        model_l = str((conf or {}).get("default_model", "")).lower()
        if "mmaudio" in name_l or "mmaudio" in model_l:
            mmaudio_tools[name] = conf
    if not mmaudio_tools:
        raise RuntimeError("No mmaudio tool config found in source config.yaml")
    obj["tools"] = mmaudio_tools
    with open(dst_cfg, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, allow_unicode=True, sort_keys=False)
    return dst_cfg


def main() -> None:
    ap = argparse.ArgumentParser(description="Real-tool + FakeLLM validation for MMAudio routing")
    ap.add_argument("--video", default="bin/searainbow.mp4", help="Input video path for video-conditioned SFX")
    ap.add_argument("--config", default="config.yaml", help="Source config path")
    ap.add_argument("--outdir", default="test_outputs/soft_real_tool_fake_llm", help="Output directory")
    args = ap.parse_args()

    video_in = os.path.abspath(args.video)
    if not os.path.exists(video_in):
        raise FileNotFoundError(f"Video not found: {video_in}")

    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mmaudio_only_cfg_") as tmp:
        mmaudio_cfg = os.path.join(tmp, "mmaudio_only.yaml")
        _build_mmaudio_only_config(os.path.abspath(args.config), mmaudio_cfg)

        # Real ToolLibrary and real MMAudio runtime.
        tool_lib = ToolLibrary(mmaudio_cfg)
        mmaudio_tool_name = _find_mmaudio_tool_name(tool_lib)
        spec = tool_lib.get(mmaudio_tool_name)
        runtime = getattr(spec, "runtime", None)

        # Trace real runtime kwargs passed into Gradio client.
        predict_calls = []
        orig_predict = getattr(runtime, "_predict", None)
        if callable(orig_predict):
            def traced_predict(**kwargs):
                predict_calls.append(dict(kwargs))
                print("[TRACE] MMAudio _predict kwargs:")
                print(json.dumps(_jsonable(kwargs), ensure_ascii=False, indent=2))
                return orig_predict(**kwargs)

            runtime._predict = traced_predict

        try:
            events = [
                AudioEvent(
                    audio_type="sound_effect",
                    start_time=0.0,
                    end_time=5.0,
                    description="Gentle, continuous sea waves with natural rhythm.",
                    volume_db=-12.0,
                    object="Sea waves",
                )
            ]
            plan_ctx = {"video": video_in, "video_seconds": 5.0, "__outdir__": outdir}
            out_events = SFXExpert(tool_lib).process_batch(events, plan_ctx, FakeLLM())
            if not out_events:
                raise RuntimeError("SFXExpert returned no events")

            e0 = out_events[0]
            print("[TRACE] stage2 model_candidates:", e0.model_candidates)
            print("[TRACE] stage2 refined_inputs:")
            print(json.dumps(_jsonable(e0.refined_inputs), ensure_ascii=False, indent=2))

            has_video_arg = ("video" in e0.refined_inputs) or ("video_arg" in e0.refined_inputs)
            print(f"[TRACE] refined_inputs has video/video_arg: {has_video_arg}")

            selected_model = None
            for m in (e0.model_candidates or []):
                if "mmaudio" in m.lower():
                    selected_model = m
                    break
            selected_model = selected_model or mmaudio_tool_name
            selected_spec = tool_lib.get(selected_model)

            out_wav = os.path.join(outdir, "real_tool_fake_llm.wav")
            print(f"[TRACE] invoking real tool: {selected_model}")
            try:
                wav_path = run_tool(selected_spec, e0.refined_inputs, output_wav=out_wav)
                print(f"[RESULT] run_tool success: {wav_path}")
            except Exception as e:
                print(f"[RESULT] run_tool failed: {type(e).__name__}: {e}")

            if predict_calls:
                api_names = [str(c.get("api_name")) for c in predict_calls]
                print("[TRACE] api_name sequence:", api_names)
            else:
                print("[TRACE] no _predict call captured")
        finally:
            if callable(orig_predict):
                runtime._predict = orig_predict

    print("Validation finished (real tool library/tool runtime, fake LLM only).")


if __name__ == "__main__":
    main()
