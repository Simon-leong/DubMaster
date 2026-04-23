from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .base import GradioTool


class CosyVoice3Tool(GradioTool):
	"""CosyVoice3 TTS wrapper backed by the Gradio API.

	Supports two modes:
	- zero_shot: voice cloning from a reference wav (requires a valid local
	  file path or URL in prompt_wav).
	- instruct: no reference audio needed; voice style is driven by
	  instruct_text.  This is the automatic fallback when prompt_wav is
	  missing or points to a file that does not exist.
	"""

	def _mode_value(self, args: Dict[str, Any]) -> str:
		return str(args.get("mode_value") or args.get("mode") or "zero_shot")

	def _instruct_text(self, args: Dict[str, Any]) -> str:
		return str(
			args.get("instruct_text")
			or self.config.get("parameters", {}).get("instruct_text")
			or "You are a helpful assistant. Please say a sentence as loudly as possible.<|endofprompt|>"
		)

	def _ui_lang(self, args: Dict[str, Any]) -> str:
		return str(args.get("ui_lang") or self.config.get("parameters", {}).get("ui_lang") or "Zh")

	def _seed_value(self, args: Dict[str, Any]) -> float:
		seed = args.get("seed", self.config.get("parameters", {}).get("seed", 0))
		try:
			return float(seed)
		except Exception:
			return 0.0

	def _prompt_wav_upload(self, prompt_wav: str):
		from gradio_client import handle_file
		return handle_file(prompt_wav)

	def recognize_prompt_wav(self, prompt_wav: str) -> str:
		"""Recognize transcript text from a prompt wav via `/prompt_wav_recognition`."""
		if not prompt_wav:
			raise self._tool_error("Missing required argument: prompt_wav")

		started = self._log_start(
			{"prompt_wav": prompt_wav, "api_name": "/prompt_wav_recognition"},
			output_wav=None,
		)
		result = self._predict(
			prompt_wav=self._prompt_wav_upload(prompt_wav),
			api_name="/prompt_wav_recognition",
		)
		transcript = result[0] if isinstance(result, (list, tuple)) else result
		transcript = str(transcript or "").strip()
		if not transcript:
			raise self._tool_error("Prompt wav recognition returned an empty transcript.")
		self._log_success(started, transcript)
		return transcript

	def run(self, args: Dict[str, Any], output_wav: Optional[str] = None) -> str:
		"""Map project-side TTS args to CosyVoice3's /generate_audio API."""
		args = dict(args or {})

		# Defensive compatibility: callers may pass nested args as
		# {"tool_name": {...}, "out": "..."}.
		tool_args = args.get(self.spec.name)
		if isinstance(tool_args, dict):
			args = {k: v for k, v in args.items() if k != self.spec.name}
			args.update(tool_args)

		started = self._log_start(args, output_wav)

		target_text = args.get("target_text") or args.get("text") or args.get("tts_text")
		if not target_text:
			raise self._tool_error("Missing required argument: target_text/text/tts_text")

		prompt_wav = str(args.get("prompt_wav") or "")
		if not prompt_wav or (
			not prompt_wav.startswith("http://")
			and not prompt_wav.startswith("https://")
			and not os.path.isfile(prompt_wav)
		):
			raise self._tool_error(
				"CosyVoice3 requires a reference audio file (prompt_wav). "
				"Please upload a short WAV/MP3 clip as the voice reference."
			)

		prompt_text = str(args.get("prompt_text") or args.get("prompt_transcript") or "")

		result = self._predict(
			tts_text=str(target_text),
			mode_value="zero_shot",
			prompt_text=prompt_text,
			prompt_wav_upload=self._prompt_wav_upload(prompt_wav),
			prompt_wav_record=None,
			instruct_text=self._instruct_text(args),
			ui_lang=self._ui_lang(args),
			api_name=self.api_name or "/generate_audio",
		)

		if isinstance(result, (list, tuple)):
			result_path = result[0] if result else ""
		else:
			result_path = result
		final_path = self._materialize_output(str(result_path), output_wav)
		self._log_success(started, final_path)
		return final_path


__all__ = ["CosyVoice3Tool"]
