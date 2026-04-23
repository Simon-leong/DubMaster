import subprocess, json

def probe_video_seconds(path: str) -> float:
    # ffprobe
    try:
        out = subprocess.check_output([
            "ffprobe","-v","error","-select_streams","v:0",
            "-show_entries","format=duration",
            "-of","json", path
        ], text=True)
        dur = float(json.loads(out)["format"]["duration"])
        return dur
    except Exception:
        pass
    # moviepy
    try:
        from moviepy.editor import VideoFileClip
        with VideoFileClip(path) as v:
            return float(v.duration)
    except Exception:
        return 0.0
