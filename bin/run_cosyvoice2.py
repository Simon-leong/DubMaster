import argparse, os, sys
from pathlib import Path

def add_repo(home: str):
    home = os.path.expanduser(home)
    if home not in sys.path:
        sys.path.insert(0, home)

def main():
    script_dir = Path(__file__).resolve().parent
    workspace_root = script_dir.parent

    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=os.environ.get("COSYVOICE_HOME", str(script_dir / "cosyvoice")))
    ap.add_argument("--model", default="FunAudioLLM/CosyVoice2-0.5B")
    ap.add_argument("--target_text", default="大家好啊，我是你的专属数字人朵拉，今天你的心情怎么样呀")
    ap.add_argument("--prompt_transcript", default="希望你以后能够做的比我还好呦。")
    ap.add_argument("--prompt_wav", default=os.environ.get("COSYVOICE_PROMPT_WAV", "asset/zero_shot_prompt.wav"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    prompt_wav = Path(args.prompt_wav).expanduser().resolve()
    home = Path(args.home).expanduser().resolve()
    os.chdir(home)
    matcha_path = str(home / "third_party/Matcha-TTS")
    os.environ["PYTHONPATH"] = matcha_path + os.pathsep + os.environ.get("PYTHONPATH", "")
    if matcha_path not in sys.path:
        sys.path.insert(0, matcha_path)

    add_repo(str(home))

    from cosyvoice.cli.cosyvoice import CosyVoice2
    import torchaudio

    cosyvoice = CosyVoice2(args.model, load_jit=False, load_trt=False)

    if not prompt_wav.exists():
        raise FileNotFoundError(
            "prompt wav not found. "
            f"arg={args.prompt_wav}, resolved={prompt_wav}, "
            f"home={home}, workspace_root={workspace_root}"
        )

    gen = None
    for item in cosyvoice.inference_zero_shot(args.target_text, args.prompt_transcript, str(prompt_wav), stream=False):
        gen = item
    wav = gen['tts_speech']
    sr = cosyvoice.sample_rate

    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(out, wav, sr)

if __name__ == "__main__":
    main()
