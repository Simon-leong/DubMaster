import argparse, os, sys, json, logging
from pathlib import Path
import torch

def add_repo_to_sys_path(home: str):
    home = os.path.expanduser(home)
    if home not in sys.path:
        sys.path.insert(0, home)

def _safe_stem_from_prompt(p: str) -> str:
    p = (p or "").strip()
    if not p:
        p = "mmaudio"
    return p.replace(" ", "_").replace("/", "_").replace(".", "_")[:80]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=os.environ.get("MMAUDIO_HOME", "/hpc2hdd/home/yrong854/jhaidata/audio/MMAudio"))
    ap.add_argument("--variant", default="large_44k_v2")
    ap.add_argument("--video", default=None) 
    ap.add_argument("--prompt", default="")
    ap.add_argument("--negative_prompt", default="low quality")
    ap.add_argument("--duration", type=float, default=8.0)
    ap.add_argument("--cfg_strength", type=float, default=4.5)
    ap.add_argument("--num_steps", type=int, default=25)
    ap.add_argument("--mask_away_clip", action="store_true")
    ap.add_argument("--skip_video_composite", action="store_true") 
    ap.add_argument("--output_dir", default="./output")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--full_precision", action="store_true")
    ap.add_argument("--out", required=True)  
    args = ap.parse_args()

    add_repo_to_sys_path(args.home)
    os.chdir(args.home)

    import torchaudio
    from mmaudio.eval_utils import (ModelConfig, all_model_cfg, generate, load_video, make_video, setup_eval_logging)
    from mmaudio.model.flow_matching import FlowMatching
    from mmaudio.model.networks import MMAudio, get_my_mmaudio
    from mmaudio.model.utils.features_utils import FeaturesUtils

    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    setup_eval_logging()
    log = logging.getLogger("run_mmaudio")

    if args.variant not in all_model_cfg:
        raise ValueError(f"Unknown variant: {args.variant}")
    model: ModelConfig = all_model_cfg[args.variant]
    model.download_if_needed()
    seq_cfg = model.seq_cfg

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    dtype = torch.float32 if args.full_precision else torch.bfloat16

    out_dir = Path(args.output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    net: MMAudio = get_my_mmaudio(model.model_name).to(device, dtype).eval()
    net.load_weights(torch.load(model.model_path, map_location=device, weights_only=True))

    rng = torch.Generator(device=device)
    rng.manual_seed(args.seed)
    fm = FlowMatching(min_sigma=0, inference_mode='euler', num_steps=args.num_steps)

    feature_utils = FeaturesUtils(
        tod_vae_ckpt=model.vae_path,
        synchformer_ckpt=model.synchformer_ckpt,
        enable_conditions=True,
        mode=model.mode,
        bigvgan_vocoder_ckpt=model.bigvgan_16k_path,
        need_vae_encoder=False
    ).to(device, dtype).eval()

    video_path = Path(args.video).expanduser() if args.video else None
    if video_path is not None:
        log.info(f"Using video {video_path}")
        video_info = load_video(video_path, args.duration)
        clip_frames = None if args.mask_away_clip else video_info.clip_frames.unsqueeze(0)
        sync_frames = video_info.sync_frames.unsqueeze(0)
        duration = float(video_info.duration_sec) 
        stem = video_path.stem
    else:
        clip_frames = sync_frames = None
        duration = float(args.duration)
        stem = _safe_stem_from_prompt(args.prompt)

    seq_cfg.duration = duration
    net.update_seq_lengths(seq_cfg.latent_seq_len, seq_cfg.clip_seq_len, seq_cfg.sync_seq_len)

    # Generation
    torch.set_grad_enabled(False)
    with torch.no_grad():
        audios = generate(
            clip_frames, sync_frames, [args.prompt],
            negative_text=[args.negative_prompt],
            feature_utils=feature_utils, net=net, fm=fm, rng=rng, cfg_strength=args.cfg_strength
        )
    audio = audios.float().cpu()[0]

    # ---------- output（wav/mp4/manifest） ----------
    out_wav = Path(args.out).expanduser()
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    out_mp4 = None
    if (video_path is not None) and (not args.skip_video_composite):
        out_mp4 = out_wav.with_suffix(".mp4")
    manifest_path = out_wav.with_suffix(".manifest.json")

    # ---------- save the audio ----------
    torchaudio.save(out_wav, audio, seq_cfg.sampling_rate, encoding="PCM_S", bits_per_sample=16)
    log.info(f"Audio saved to {out_wav} (encoded as 16-bit PCM)")

    if out_mp4 is not None:
        make_video(video_info, out_mp4, audio, sampling_rate=seq_cfg.sampling_rate)
        log.info(f"Video saved to {out_mp4}")

    # ---------- manifest ----------
    try:
        meta = {
            "model_variant": args.variant,
            "prompt": args.prompt,
            "negative_prompt": args.negative_prompt,
            "seed": args.seed,
            "num_steps": args.num_steps,
            "cfg_strength": args.cfg_strength,
            "sampling_rate": seq_cfg.sampling_rate,
            "duration_sec": float(duration),
            "video_input": str(video_path) if video_path is not None else None,
            "wav_output": str(out_wav),
            "mp4_output": str(out_mp4) if out_mp4 is not None else None,
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        log.info(f"Manifest saved to {manifest_path}")
    except Exception as e:
        log.warning(f"Failed to write manifest: {e!r}")

    log.info("Memory usage: %.2f GB", torch.cuda.max_memory_allocated() / (2**30))

    # ---------- stdout ----------
    print(json.dumps({
        "wav": str(out_wav),
        "mp4": (str(out_mp4) if out_mp4 is not None else None),
        "manifest": str(manifest_path),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
