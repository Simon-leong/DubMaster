import argparse, os, sys, shutil
from pathlib import Path

def add_repo(home: str):
    home = os.path.expanduser(home)
    if home not in sys.path:
        sys.path.insert(0, home)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=os.environ.get("INSPIREMUSIC_HOME", "/hpc2hdd/home/yrong854/jhaidata/music/InspireMusic"))
    ap.add_argument("--model_name", default="InspireMusic-1.5B-Long")
    ap.add_argument("--text", required=True)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--chorus", default=os.environ.get("INSPIREMUSIC_CHORUS", "verse"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    home = Path(args.home).expanduser()
    os.chdir(home)
    add_repo(str(home))

    from inspiremusic.cli.inference import InspireMusicModel, env_variables

    try:
        env_variables()
    except Exception:
        pass

    out_path = Path(args.out).expanduser().resolve()
    result_dir = out_path.parent

    model = InspireMusicModel(
        model_name=args.model_name,
        result_dir=str(result_dir),
    )

    output_fn = out_path.stem

    # sec >= 1
    time_start = 0.0
    time_end = max(float(args.seconds), 1.0)

    produced = model.inference(
        task="text-to-music",
        text=args.text,
        chorus=args.chorus,
        time_start=time_start,
        time_end=time_end,
        output_fn=output_fn,
        output_format="wav",
        trim=False,
        fade_out_mode=True,
        fade_out_duration=1.0,
    )

    if not produced:
        produced = str(result_dir / f"{output_fn}.wav")

    src = Path(produced)
    if not src.exists():
        candidates = sorted(
            [p for p in result_dir.glob(f"{output_fn}.*")] +
            [p for p in result_dir.glob("*.wav")],
            key=lambda p: p.stat().st_mtime, reverse=True
        )
        if candidates:
            src = candidates[0]

    if not src.exists():
        raise RuntimeError(f"InspireMusic fail to find the output：{produced}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() != out_path:
        shutil.copyfile(src, out_path)

if __name__ == "__main__":
    main()
