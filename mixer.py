import os, math, subprocess, shutil
from typing import List, Dict, Any, Optional
from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip, ImageClip
from pydub import AudioSegment


def _to_ms(x: str) -> int:
    """turn time from s to ms"""
    try:
        return int(float(x) * 1000)
    except Exception:
        return 0


def _speedup_to_fit(audio: AudioSegment, target_ms: int) -> AudioSegment:
    """
    align the duration
    """
    if target_ms <= 0:
        return audio 
    
    actual_ms = len(audio) 

    if actual_ms < target_ms:
        silence_duration = target_ms - actual_ms
        silence = AudioSegment.silent(duration=silence_duration)
        audio = audio + silence
    elif actual_ms > target_ms:
        speed_factor = actual_ms / float(target_ms)
        audio = audio.speedup(playback_speed=speed_factor)

    return audio[:target_ms] 


def _adjust_volume(audio: AudioSegment, vol_db) -> AudioSegment:
    try:
        return audio + float(vol_db)
    except Exception:
        return audio 


def _ensure_parent_dir(path: Optional[str]) -> None:
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)


def mix_and_maybe_mux(
    *,
    video_path: Optional[str],
    image_path: Optional[str] = None,
    audio_segments: List[Dict],
    output_audio_path: str,
    output_video_path: Optional[str] = None
) -> Dict[str, str]:
    """
    mix the audio according to the timestamp
    """
    if not audio_segments:
        raise ValueError("audio_segments is empty")

    tracks = []
    max_end_ms = 0
    for seg in audio_segments:
        wav = seg.get("wav_file")
        if not wav or not os.path.exists(wav):
            continue
        try:
            audio = AudioSegment.from_wav(wav)
        except Exception:
            continue

        start_ms = _to_ms(seg.get("start_time", 0))
        end_ms   = _to_ms(seg.get("end_time", 0))
        dur_ms   = _to_ms(seg.get("duration", 0))

        # if dur_ms > 0:
        #     audio = _speedup_to_fit(audio, dur_ms)

        vol = seg.get("volume", seg.get("volume_db", 0.0))
        audio = _adjust_volume(audio, vol)

        tracks.append((start_ms, audio))
        max_end_ms = max(max_end_ms, end_ms)
        
    if not tracks or max_end_ms <= 0:
        raise ValueError("no valid audio segments to mix")

    mixed = AudioSegment.silent(duration=max_end_ms)
    for start_ms, audio in tracks:
        mixed = mixed.overlay(audio, position=start_ms)

    _ensure_parent_dir(output_audio_path)
    mixed.export(output_audio_path, format="wav")
    result = {"audio": output_audio_path}

    if video_path:
        out_mp4 = output_video_path or os.path.splitext(output_audio_path)[0] + ".mp4"
        _ensure_parent_dir(out_mp4)
        with VideoFileClip(video_path) as v:
            new_audio = AudioFileClip(output_audio_path)
            clips = []
            if v.audio:
                clips.append(v.audio)
            clips.append(new_audio)
            comp = CompositeAudioClip(clips)
            final = v.with_audio(comp)
            final.duration = v.duration
            final.write_videofile(out_mp4, codec="libx264", audio_codec="aac")
        result["video"] = out_mp4

    elif image_path and os.path.exists(image_path):
        out_mp4 = output_video_path or os.path.splitext(output_audio_path)[0] + ".mp4"
        _ensure_parent_dir(out_mp4)
        audio_clip = AudioFileClip(output_audio_path)
        img_clip = ImageClip(image_path).with_duration(audio_clip.duration).with_audio(audio_clip)
        img_clip.write_videofile(out_mp4, fps=1, codec="libx264", audio_codec="aac")
        audio_clip.close()
        result["video"] = out_mp4

    return result