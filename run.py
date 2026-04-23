from __future__ import annotations
import argparse, json, os, pathlib
import os
import argparse
import json
import pathlib
from router import load_llm
from agents import DubMasterSystem
from utils.runtime_logger import log_step


os.environ['GEMINI_API_KEY'] = 'Your_Gemini_Api_Key'


def main():
    log_step("Entrypoint started: parsing CLI arguments")
    parser = argparse.ArgumentParser(description="DubMaster (training-free multi-agent)")
    parser.add_argument("--text", default=None)
    parser.add_argument("--image", default=None)
    parser.add_argument("--video", default=None, help="Path to .mp4 video file.")
    parser.add_argument("--prompt_wav_path", default=None, help="Optional prompt wav path for speech cloning.")
    parser.add_argument("--outdir", default="/hpc2hdd/home/yrong854/jhaidata/Agent/outputs_gemini/bird_sea")
    parser.add_argument("--llm", default="kimi")
    parser.add_argument("--max_depth", type=int, default=3)
    parser.add_argument("--max_siblings", type=int, default=1)
    args = parser.parse_args()

    outdir = os.path.abspath(args.outdir or "outputs")
    pathlib.Path(outdir).mkdir(parents=True, exist_ok=True)
    log_step(f"Output directory ready: {outdir}")

    llm = load_llm(args.llm)
    log_step(f"LLM loaded from router: {args.llm}")

    ctx = {
        "text": args.text,
        "image": args.image,
        "video": args.video if args.video not in ("None", "none", "") else None,
        "prompt_wav_path": args.prompt_wav_path if args.prompt_wav_path not in ("None", "none", "") else None,
    }

    try:
        critic_llm = load_llm("qwen-omni-critic")
    except Exception:
        critic_llm = None
    system = DubMasterSystem(llm, outdir=outdir, critic_llm=critic_llm)
    log_step("System initialized; starting run pipeline")
    out = system.run(ctx, max_depth=args.max_depth, max_siblings=args.max_siblings)

    log_step("Pipeline completed; printing final JSON output (deprecated: check output directory for generated media files)")
    # print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
