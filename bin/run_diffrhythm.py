from __future__ import annotations
import argparse, os, sys, subprocess, shutil, re, wave

def _validate_lrc_has_timestamps(lrc_path: str):
    if not os.path.exists(lrc_path):
        raise FileNotFoundError(f"[DiffRhythm] lrc file not found: {lrc_path}")
    txt = open(lrc_path, "r", encoding="utf-8").read()
    if not re.search(r"\[\d{2}:\d{2}(?:\.\d{1,2})?\]", txt):
        raise ValueError("[DiffRhythm] LRC must contain timestamps like [mm:ss.xx].")

def _trim_wav(in_path: str, out_path: str, seconds: float) -> float:
    """
    cut the audio and save to out_path. 
    Return the original audio duration (in seconds) for logging
    """
    if seconds <= 0:
        raise ValueError(f"[DiffRhythm] real_seconds must be > 0, got {seconds}")

    with wave.open(in_path, "rb") as r:
        n_channels  = r.getnchannels()
        sampwidth   = r.getsampwidth()
        framerate   = r.getframerate()
        nframes     = r.getnframes()
        orig_dur    = nframes / float(framerate)

        # clip the audio
        frames_to_copy = min(nframes, int(seconds * framerate))

        if frames_to_copy >= nframes:
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            shutil.copy2(in_path, out_path)
            return orig_dur

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with wave.open(out_path, "wb") as w:
            w.setnchannels(n_channels)
            w.setsampwidth(sampwidth)
            w.setframerate(framerate)

            chunk_frames = 4096
            remaining = frames_to_copy
            while remaining > 0:
                to_read = min(remaining, chunk_frames)
                data = r.readframes(to_read)
                if not data:
                    break
                w.writeframes(data)
                remaining -= to_read

    return orig_dur

def main():
    ap = argparse.ArgumentParser(description="Wrapper for DiffRhythm infer")
    ap.add_argument("--lrc_path",         required=True)
    ap.add_argument("--ref_audio_path",   default="")
    ap.add_argument("--ref_prompt",       default="")
    ap.add_argument("--real_seconds",     type=float, required=True)
    ap.add_argument("--seconds",          default=95)
    ap.add_argument("--out",              required=True)
    ap.add_argument("--batch_infer_num",  type=int, default=5)
    ap.add_argument("--chunked",          action="store_true")
    ap.add_argument("--repo_root",        default="/hpc2hdd/home/yrong854/jhaidata/music/DiffRhythm")
    args = ap.parse_args()

    _validate_lrc_has_timestamps(args.lrc_path)

    # one of two ways
    use_ref_audio = bool(args.ref_audio_path)
    use_ref_prompt = bool(args.ref_prompt)
    if use_ref_audio == use_ref_prompt:
        raise ValueError("[DiffRhythm] Provide exactly one of --ref_audio_path OR --ref_prompt.")

    # seconds -> audio_length (95 / 96~285)
    length = int(round(float(args.seconds)))
    if length < 95: length = 95
    elif 95 < length < 96: length = 96
    elif length > 285: length = 285

    repo = args.repo_root
    infer_py = os.path.join(repo, "infer", "infer.py")

    # trim and write the final result to args.out
    out_dir = os.path.join(os.path.dirname(args.out), ".diffrhythm_tmp")
    os.makedirs(out_dir, exist_ok=True)

    cmd = [
        "python3", infer_py,
        "--lrc-path", args.lrc_path,
        "--audio-length", str(length),
        "--output-dir", out_dir,
        "--batch-infer-num", str(args.batch_infer_num),
    ]
    if args.chunked:
        cmd.append("--chunked")
    if use_ref_audio:
        cmd += ["--ref-audio-path", args.ref_audio_path]
    else:
        cmd += ["--ref-prompt", args.ref_prompt]

    env = os.environ.copy()
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") + (":" + repo)

    subprocess.run(cmd, check=True, cwd=repo, env=env)

    produced = os.path.join(out_dir, "output.wav")
    if not os.path.exists(produced):
        raise FileNotFoundError(f"[DiffRhythm] expected output not found: {produced}")

    orig_dur = _trim_wav(produced, args.out, args.real_seconds)
    print(f"[DiffRhythm] source duration = {orig_dur:.2f}s, wrote first {args.real_seconds:.2f}s to {args.out}")

if __name__ == "__main__":
    main()
