from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

import yaml

from tool.base import BaseTool, ToolSpec
from tool.cosyvoice2 import CosyVoice2Tool
from tool.cosyvoice3 import CosyVoice3Tool
from tool.diffrhythm import DiffRhythmTool
from tool.inspiremusic import InspireMusicTool
from tool.mmaudio import MMAudioTool
from utils.runtime_logger import instrument_tool_run

log = logging.getLogger(__name__)


def _expand_env_vars(obj):
    """Recursively expand ${VAR_NAME} placeholders using environment variables.

    Allows config.yaml to store secrets as ${HF_TOKEN} etc. rather than
    hardcoded values. On Fly.io secrets are env vars; locally use a .env file.
    """
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(i) for i in obj]
    if isinstance(obj, str):
        return re.sub(
            r"\$\{([^}]+)\}",
            lambda m: os.environ.get(m.group(1), ""),
            obj,
        )
    return obj


class ToolLibrary:
    """Config-driven registry that binds ToolSpec records to runtime tool objects."""

    def __init__(self, config_path: Optional[str] = None):
        self.tools: Dict[str, ToolSpec] = {}
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), "config.yaml")
        self._load_from_config(self.config_path)

    def _load_from_config(self, config_path: str) -> None:
        """Load tool definitions from the top-level `tools` section in config.yaml."""
        if not os.path.exists(config_path):
            return
        with open(config_path, "r", encoding="utf-8") as f:
            config = _expand_env_vars(yaml.safe_load(f) or {})
        basic_cfg = dict(config.get("basic") or config.get("basic_config") or {})
        basic_hf_token = str(basic_cfg.get("hf_token") or "").strip()

        for name, tool_config in (config.get("tools") or {}).items():
            merged_tool_config = dict(tool_config or {})
            tool_hf_token = str(merged_tool_config.get("hf_token") or "").strip()
            if not tool_hf_token and basic_hf_token:
                merged_tool_config["hf_token"] = basic_hf_token

            provider = merged_tool_config.get("provider")
            spec = ToolSpec(
                name=name,
                task=merged_tool_config.get("task", ""),
                command=merged_tool_config.get("command", ""),
                inputs=list(merged_tool_config.get("inputs", []) or []),
                conda_env=merged_tool_config.get("conda_env", ""),
                notes=merged_tool_config.get("notes", ""),
                provider=provider or "",
                default_model=merged_tool_config.get("default_model", ""),
                parameters=dict(merged_tool_config.get("parameters", {}) or {}),
            )
            try:
                spec.runtime = self._build_runtime(spec, merged_tool_config)
            except Exception as e:
                # Don't let one dead/slow Gradio Space take down the whole ToolLibrary.
                # The tool will be absent from the registry; attempts to use it will
                # raise KeyError in `get()` and be caught by the ToT error path.
                log.warning("Skipping tool %s: %s: %s", name, type(e).__name__, e)
                continue
            self.tools[name] = spec

    def _build_runtime(self, spec: ToolSpec, tool_config: Dict[str, Any]) -> BaseTool:
        """Select the concrete tool implementation from tool name/model identity."""
        name = (spec.name or "").lower()
        model = (spec.default_model or "").lower()
        identity = f"{name} {model}"

        if "mmaudio" in identity:
            return instrument_tool_run(MMAudioTool(spec, **tool_config))
        if "diffrhythm" in identity:
            return instrument_tool_run(DiffRhythmTool(spec, **tool_config))
        if "inspiremusic" in identity:
            return instrument_tool_run(InspireMusicTool(spec, **tool_config))
        if "cosyvoice2" in identity:
            return instrument_tool_run(CosyVoice2Tool(spec, **tool_config))
        if "cosyvoice3" in identity or "cosyvoice" in identity:
            return instrument_tool_run(CosyVoice3Tool(spec, **tool_config))

        raise ValueError(
            "Unsupported tool name/model for runtime binding: "
            f"name={spec.name!r}, default_model={spec.default_model!r}"
        )

    def has(self, name: str) -> bool:
        return name in self.tools

    def get(self, name: str) -> ToolSpec:
        if name not in self.tools:
            raise KeyError(f"Tool {name} not found")
        return self.tools[name]


def run_tool(tool: ToolSpec, args: Dict[str, Any], output_wav: Optional[str] = None) -> str:
    """Compatibility entrypoint that dispatches through the bound runtime object."""
    runtime = getattr(tool, "runtime", None)
    if runtime is None:
        raise RuntimeError(f"Tool '{tool.name}' has no runtime bound in tools_v2")
    if not getattr(getattr(runtime, "run", None), "_logged", False):
        runtime = instrument_tool_run(runtime)
        tool.runtime = runtime

    normalized_args = dict(args or {})

    # Backward compatibility: ToT passes refined_inputs as
    # {"tool_name": {...tool args...}, "out": "..."}. Flatten tool args.
    tool_specific_args = normalized_args.get(tool.name)
    if isinstance(tool_specific_args, dict):
        normalized_args = {k: v for k, v in normalized_args.items() if k != tool.name}
        normalized_args.update(tool_specific_args)

    # Accept legacy `out`/`output` when caller doesn't pass output_wav explicitly.
    if output_wav is None:
        out = normalized_args.get("out") or normalized_args.get("output")
        if isinstance(out, str) and out.strip():
            output_wav = out

    return runtime.run(normalized_args, output_wav=output_wav)


__all__ = ["ToolLibrary", "run_tool", "ToolSpec"]
