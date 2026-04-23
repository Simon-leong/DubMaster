from __future__ import annotations

from typing import Any, Dict, Optional

from .base import GradioTool


class CosyVoice2Tool(GradioTool):
	"""CosyVoice2 zero-shot/instruct TTS wrapper backed by the Gradio API."""

	def _seed_value(self, args: Dict[str, Any]) -> float:
		seed = args.get("seed", self.config.get("parameters", {}).get("seed", 0))
		try:
			return float(seed)
		except Exception:
			return 0.0

	def _stream_value(self, args: Dict[str, Any]) -> str:
		stream = args.get("stream", self.config.get("parameters", {}).get("stream", "false"))
		return str(stream).lower()

	def _instruct_text(self, args: Dict[str, Any]) -> str:
		# Keep instruct_text input-driven: prefer explicit arg, fall back to style if provided.
		return str(args.get("instruct_text") or args.get("style") or "")

	def _mode_value(self, args: Dict[str, Any]) -> str:
		mode = args.get("mode_checkbox_group") or args.get("mode") or self.config.get("parameters", {}).get("mode_checkbox_group")
		if mode:
			mode_s = str(mode).strip()
			if mode_s in ("zero_shot", "3s极速复刻"):
				return "3s极速复刻"
			if mode_s in ("instruct", "自然语言控制"):
				return "自然语言控制"
			return mode_s
		return "3s极速复刻"

	def _prompt_wav_file(self, prompt_wav: str):
		from gradio_client import handle_file

		return handle_file(prompt_wav)

	def run(self, args: Dict[str, Any], output_wav: Optional[str] = None) -> str:
		"""Map project-side TTS args to CosyVoice2's `/generate_audio` API."""
		args = dict(args or {})

		tool_args = args.get(self.spec.name)
		if isinstance(tool_args, dict):
			args = {k: v for k, v in args.items() if k != self.spec.name}
			args.update(tool_args)

		started = self._log_start(args, output_wav)

		target_text = args.get("target_text") or args.get("text") or args.get("tts_text")
		if not target_text:
			raise self._tool_error("Missing required argument: target_text/text/tts_text")

		prompt_wav = str(self._require(args, "prompt_wav"))
		prompt_text = str(args.get("prompt_text") or args.get("prompt_transcript") or "")
		prompt_wav_file = self._prompt_wav_file(prompt_wav)

		result = self._predict(
			tts_text=str(target_text),
			mode_checkbox_group=self._mode_value(args),
			prompt_text=prompt_text,
			prompt_wav_upload=prompt_wav_file,
			prompt_wav_record=prompt_wav_file,
			instruct_text=self._instruct_text(args),
			seed=self._seed_value(args),
			stream=self._stream_value(args),
			api_name=self.api_name or "/generate_audio",
		)

		if isinstance(result, (list, tuple)):
			result_path = result[0] if result else ""
		else:
			result_path = result
		final_path = self._materialize_output(str(result_path), output_wav)
		self._log_success(started, final_path)
		return final_path


__all__ = ["CosyVoice2Tool"]
