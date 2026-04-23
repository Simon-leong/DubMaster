from __future__ import annotations

import mimetypes
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from .base import GradioTool


class MMAudioTool(GradioTool):
	"""MMAudio wrapper that supports both video-conditioned and text-only generation."""

	def _seed_value(self, args: Dict[str, Any]) -> int:
		seed = args.get("seed", self.config.get("parameters", {}).get("seed", -1))
		try:
			return int(seed)
		except Exception:
			return -1

	def _num_steps(self, args: Dict[str, Any]) -> int:
		steps = args.get("num_steps", self.config.get("parameters", {}).get("num_steps", 25))
		try:
			return int(steps)
		except Exception:
			return 25

	def _cfg_strength(self, args: Dict[str, Any]) -> float:
		cfg = args.get("cfg_strength", self.config.get("parameters", {}).get("cfg_strength", 4.5))
		try:
			return float(cfg)
		except Exception:
			return 4.5

	def _duration(self, args: Dict[str, Any]) -> float:
		dur = args.get("duration", args.get("seconds", self.config.get("parameters", {}).get("duration", 8)))
		try:
			return float(dur)
		except Exception:
			return 8.0

	def _negative_prompt(self, args: Dict[str, Any]) -> str:
		return str(args.get("negative_prompt") or self.config.get("parameters", {}).get("negative_prompt") or "music")

	def _video_from_video_arg(self, video_arg: Any) -> str:
		raw = str(video_arg or "").strip()
		if not raw:
			return ""
		try:
			parts = shlex.split(raw)
		except Exception:
			parts = raw.split()
		for i, token in enumerate(parts):
			if token == "--video" and i + 1 < len(parts):
				return str(parts[i + 1]).strip()
		return ""

	def _resolve_video_path(self, args: Dict[str, Any]) -> str:
		video = args.get("video")
		if isinstance(video, str) and video.strip():
			return video.strip()
		return self._video_from_video_arg(args.get("video_arg"))

	def _video_filedata_payload(self, video_path: str) -> Dict[str, Any]:
		"""Build a FileData payload and preserve gradio upload semantics."""
		from gradio_client import handle_file

		p = Path(video_path).expanduser().resolve()
		if not p.exists():
			raise self._tool_error(f"Video path does not exist: {p}")
		if not p.is_file():
			raise self._tool_error(f"Video path is not a file: {p}")

		mime, _ = mimetypes.guess_type(str(p))
		payload_raw = handle_file(str(p))
		payload = dict(payload_raw) if isinstance(payload_raw, dict) else {"path": str(p)}
		payload.setdefault("path", str(p))
		payload.setdefault("url", p.as_uri())
		payload.setdefault("size", int(os.path.getsize(p)))
		payload.setdefault("orig_name", p.name)
		payload.setdefault("mime_type", mime or "video/mp4")
		payload.setdefault("is_stream", False)
		payload.setdefault("meta", {"_type": "gradio.FileData"})
		return payload

	def _prompt(self, args: Dict[str, Any]) -> str:
		return str(args.get("prompt") or args.get("text") or "").strip()

	def _default_video_prompt(self, args: Dict[str, Any]) -> str:
		return str(
			args.get("default_video_prompt")
			or self.config.get("parameters", {}).get("default_video_prompt")
			or "Generate natural, synchronized sound effects that match the visual actions in the video."
		)

	def _extract_wav_from_mp4(self, mp4_path: str, wav_path: str) -> None:
		cmd = [
			"ffmpeg",
			"-y",
			"-i",
			mp4_path,
			"-vn",
			"-acodec",
			"pcm_s16le",
			"-ar",
			"16000",
			"-ac",
			"1",
			wav_path,
		]
		proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
		if proc.returncode == 0 and Path(wav_path).exists():
			return

		# Fallback when ffmpeg cli is unavailable in PATH.
		try:
			from moviepy import VideoFileClip

			with VideoFileClip(mp4_path) as clip:
				if clip.audio is None:
					raise self._tool_error(f"No audio track found in video output: {mp4_path}")
				clip.audio.write_audiofile(
					wav_path,
					codec="pcm_s16le",
					fps=16000,
					ffmpeg_params=["-ac", "1"],
					logger=None,
				)
		except Exception as e:
			stderr = (proc.stderr or "") if proc.returncode != 0 else ""
			raise self._tool_error(
				f"Failed to extract wav from video output: {type(e).__name__}: {e}",
				stderr=stderr,
			) from e

		if not Path(wav_path).exists():
			raise self._tool_error(f"WAV output was not created: {wav_path}")

	def run(self, args: Dict[str, Any], output_wav: Optional[str] = None) -> str:
		"""Route to /video_to_audio when video is provided, else /text_to_audio."""
		args = dict(args or {})

		tool_args = args.get(self.spec.name)
		if isinstance(tool_args, dict):
			args = {k: v for k, v in args.items() if k != self.spec.name}
			args.update(tool_args)

		started = self._log_start(args, output_wav)

		negative_prompt = self._negative_prompt(args)
		seed = self._seed_value(args)
		num_steps = self._num_steps(args)
		cfg_strength = self._cfg_strength(args)
		duration = self._duration(args)
		video_path = self._resolve_video_path(args)
		prompt = self._prompt(args)
		if not prompt:
			if video_path:
				prompt = self._default_video_prompt(args)
			else:
				raise self._tool_error("Missing required argument: prompt/text")

		if video_path:
			result = self._predict(
				video=self._video_filedata_payload(video_path),
				prompt=prompt,
				negative_prompt=negative_prompt,
				seed=seed,
				num_steps=num_steps,
				cfg_strength=cfg_strength,
				duration=duration,
				api_name="/video_to_audio",
			)
		else:
			result = self._predict(
				prompt=prompt,
				negative_prompt=negative_prompt,
				seed=seed,
				num_steps=num_steps,
				cfg_strength=cfg_strength,
				duration=duration,
				api_name="/text_to_audio",
			)

		if isinstance(result, (list, tuple)):
			result_path = str(result[0]) if result else ""
		else:
			result_path = str(result)

		if not video_path:
			final_path = self._materialize_output(result_path, output_wav)
			self._log_success(started, final_path)
			return final_path

		# video endpoint returns MP4; keep MP4 and extract WAV for downstream pipeline.
		src_mp4 = Path(result_path).expanduser()
		if not src_mp4.exists():
			raise self._tool_error(f"API output path does not exist: {src_mp4}")

		if not output_wav:
			self._log_success(started, str(src_mp4))
			return str(src_mp4)

		wav_dst = Path(output_wav).expanduser()
		wav_dst.parent.mkdir(parents=True, exist_ok=True)
		mp4_dst = wav_dst.with_suffix(".mp4")
		if src_mp4.resolve() != mp4_dst.resolve():
			shutil.copyfile(src_mp4, mp4_dst)
		self._extract_wav_from_mp4(str(mp4_dst), str(wav_dst))

		self._log_success(started, str(wav_dst))
		return str(wav_dst)


__all__ = ["MMAudioTool"]
