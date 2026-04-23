import argparse, os, sys
from pathlib import Path


def add_repo(home: str):
    home = os.path.expanduser(home)
    if home not in sys.path:
        sys.path.insert(0, home)


def main():
    script_dir = Path(__file__).resolve().parent

    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=os.environ.get("COSYVOICE_HOME", str(script_dir / "cosyvoice")))
    ap.add_argument("--model", default="FunAudioLLM/Fun-CosyVoice3-0.5B-2512")
    ap.add_argument("--target_text", default="Hello, this is a CosyVoice3 zero-shot demo.")
    ap.add_argument("--prompt_transcript", default="希望你以后能够做的比我还好呦。")
    ap.add_argument("--system_prompt", default="You are a helpful assistant.")
    ap.add_argument(
        "--prompt_wav",
        default=os.environ.get(
            "COSYVOICE_PROMPT_WAV",
            "asset/zero_shot_prompt.wav",
        ),
    )
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    home = Path(args.home).expanduser().resolve()
    os.chdir(home)
    matcha_path = str(home / "third_party/Matcha-TTS")
    os.environ["PYTHONPATH"] = matcha_path + os.pathsep + os.environ.get("PYTHONPATH", "")
    if matcha_path not in sys.path:
        sys.path.insert(0, matcha_path)

    add_repo(str(home))

    from cosyvoice.cli.cosyvoice import AutoModel
    import torchaudio

    cosyvoice = AutoModel(model_dir=args.model)

    # CosyVoice3 zero-shot prompt format follows the official example.
    prompt_text = f"{args.system_prompt}<|endofprompt|>{args.prompt_transcript}"

    gen = None
    prompt_wav = Path(args.prompt_wav).expanduser()
    if not prompt_wav.is_absolute():
        prompt_wav = home / prompt_wav
    for item in cosyvoice.inference_zero_shot(
        args.target_text,
        prompt_text,
        str(prompt_wav),
        stream=False,
    ):
        gen = item

    if gen is None:
        raise RuntimeError("CosyVoice3 returned no waveform output.")

    wav = gen["tts_speech"]
    sr = cosyvoice.sample_rate

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(out, wav, sr)


if __name__ == "__main__":
    main()
