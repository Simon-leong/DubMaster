from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from gradio_client import handle_file

from .base import GradioTool


class DiffRhythmTool(GradioTool):
    """DiffRhythm song generation tool backed by the ASLP-lab/DiffRhythm Gradio space."""

    SPACE = "ASLP-lab/DiffRhythm"

    # ── parameter helpers ──────────────────────────────────────────────────────

    def _seed(self, args: Dict[str, Any]) -> float:
        try:
            return float(args.get("seed", self.config.get("parameters", {}).get("seed", 0)))
        except Exception:
            return 0.0

    def _steps(self, args: Dict[str, Any]) -> float:
        try:
            return float(args.get("steps", self.config.get("parameters", {}).get("steps", 32)))
        except Exception:
            return 32.0

    def _cfg_strength(self, args: Dict[str, Any]) -> float:
        try:
            return float(args.get("cfg_strength", self.config.get("parameters", {}).get("cfg_strength", 4.0)))
        except Exception:
            return 4.0

    def _music_duration(self, args: Dict[str, Any]) -> float:
        """Resolve music duration in seconds from args."""
        dur = args.get("seconds") or args.get("Music_Duration") or self.config.get("parameters", {}).get("Music_Duration", 95)
        try:
            return float(dur)
        except Exception:
            return 95.0

    def _trim_seconds(self, args: Dict[str, Any]) -> Optional[float]:
        """Resolve target output duration for explicit post-generation trim."""
        for key in ("trim_seconds", "real_seconds", "duration", "seconds", "target_seconds"):
            if key in args and args.get(key) not in (None, ""):
                return self._positive_seconds_or_none(args.get(key))
        return None

    def _api_music_duration(self, args: Dict[str, Any], trim_seconds: Optional[float]) -> float:
        """Resolve API Music_Duration with independent min/max constraints."""
        api_raw = (
            args.get("api_music_duration")
            or args.get("api_seconds")
            or args.get("Music_Duration")
            or args.get("seconds")
            or trim_seconds
            or self.config.get("parameters", {}).get("Music_Duration", 95)
        )
        try:
            api_seconds = float(api_raw)
        except Exception:
            api_seconds = 95.0

        # Legacy DiffRhythm length constraints from the old script.
        min_api = self._positive_seconds_or_none(
            args.get("api_min_seconds", self.config.get("parameters", {}).get("api_min_seconds", 95))
        )
        max_api = self._positive_seconds_or_none(
            args.get("api_max_seconds", self.config.get("parameters", {}).get("api_max_seconds", 285))
        )

        if min_api is not None and max_api is not None and min_api > max_api:
            min_api, max_api = max_api, min_api

        if min_api is not None and api_seconds < min_api:
            api_seconds = min_api
        if max_api is not None and api_seconds > max_api:
            api_seconds = max_api

        # Keep parity with legacy normalization: 95 < x < 96 -> 96.
        if min_api is not None and min_api >= 95.0 and 95.0 < api_seconds < 96.0:
            api_seconds = 96.0

        return float(api_seconds)

    def _file_type(self, args: Dict[str, Any]) -> str:
        ft = args.get("file_type", self.config.get("parameters", {}).get("file_type", "mp3"))
        if ft in ("wav", "mp3", "ogg"):
            return ft
        return "mp3"

    def _odeint_method(self, args: Dict[str, Any]) -> str:
        m = args.get("odeint_method", self.config.get("parameters", {}).get("odeint_method", "euler"))
        if m in ("euler", "midpoint", "rk4", "implicit_adams"):
            return m
        return "euler"

    def _preference(self, args: Dict[str, Any]) -> str:
        p = args.get("preference_infer", self.config.get("parameters", {}).get("preference_infer", "quality first"))
        if p in ("quality first", "speed first"):
            return p
        return "quality first"

    def _read_lrc(self, args: Dict[str, Any]) -> str:
        """Return LRC text from a file path or inline string."""
        lrc_path = args.get("lrc_path")
        if lrc_path:
            p = Path(str(lrc_path)).expanduser()
            if p.is_file():
                return p.read_text(encoding="utf-8")
            raise self._tool_error(f"lrc_path does not exist: {p}")
        lrc = args.get("lrc", "")
        if not lrc:
            raise self._tool_error("Missing required argument: lrc_path or lrc")
        return str(lrc)

    def _ref_audio_payload(self, ref_audio_path: str) -> Any:
        """Build a handle_file payload for the ref audio input."""
        path = Path(str(ref_audio_path)).expanduser().resolve()
        if not path.exists():
            raise self._tool_error(f"ref_audio_path does not exist: {path}")
        return handle_file(str(path))

    # ── main entry point ───────────────────────────────────────────────────────

    def run(self, args: Dict[str, Any], output_wav: Optional[str] = None) -> str:
        """Call /infer_music and return the local output audio path."""
        args = dict(args or {})

        # Unwrap nested args keyed by tool name (pipeline convention).
        tool_args = args.get(self.spec.name)
        if isinstance(tool_args, dict):
            args = {k: v for k, v in args.items() if k != self.spec.name}
            args.update(tool_args)

        started = self._log_start(args, output_wav)
        trim_seconds = self._trim_seconds(args)
        api_music_duration = self._api_music_duration(args, trim_seconds)

        lrc = self._read_lrc(args)
        text_prompt = str(args.get("ref_prompt") or args.get("text_prompt") or "")
        if not text_prompt:
            raise self._tool_error("Missing required argument: ref_prompt or text_prompt")

        ref_audio_path = str(args.get("ref_audio_path") or "").strip()
        if ref_audio_path:
            ref_audio = self._ref_audio_payload(ref_audio_path)
        else:
            # Use the API default sample when no reference audio is provided.
            ref_audio = None
            
        result = self._predict(
            lrc=lrc,
            ref_audio_path=ref_audio,
            text_prompt=text_prompt,
            seed=self._seed(args),
            randomize_seed=bool(args.get("randomize_seed", True)),
            steps=self._steps(args),
            cfg_strength=self._cfg_strength(args),
            file_type=self._file_type(args),
            odeint_method=self._odeint_method(args),
            preference_infer=self._preference(args),
            Music_Duration=api_music_duration,
            api_name="/infer_music",
        )

        if isinstance(result, (list, tuple)):
            result_path = str(result[0]) if result else ""
        else:
            result_path = str(result)

        final_path = self._materialize_output(result_path, output_wav)
        final_path = self._trim_audio_to_seconds(final_path, trim_seconds)
        self._log_success(started, final_path)
        return final_path


__all__ = ["DiffRhythmTool"]
