from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
import os
import shlex
import subprocess
import logging
import shutil

log = logging.getLogger(__name__)


def _tail_text(text: Optional[str], max_chars: int = 4000) -> str:
    s = (text or "").strip()
    if len(s) <= max_chars:
        return s
    return s[-max_chars:]

class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class ToolRunError(RuntimeError):
    def __init__(self, message: str, *, cmd: str, returncode: int, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@dataclass
class ToolSpec:
    name: str
    task: str
    command: str
    inputs: List[str] = field(default_factory=list)
    conda_env: str = ""
    notes: str = ""


class ToolLibrary:
    def __init__(self):
        bin_dir = os.path.join(os.path.dirname(__file__), "bin")
        self.tools: Dict[str, ToolSpec] = {
            "MMAudio": ToolSpec(
                name="MMAudio", task="sfx",
                command=("{conda_exec} run -n {conda_env} "
                         "python {bin_dir}/run_mmaudio.py --variant {variant} {video_arg} --prompt \"{text}\" "
                         "--duration {seconds} --cfg_strength {cfg_strength} --num_steps {num_steps} "
                         "--output_dir \"{output_dir}\" --seed {seed} --out \"{output}\""),
                inputs=["text", "seconds", "seed", "num_steps", "cfg_strength", "variant", "output_dir", "video_arg"],
                conda_env=os.environ.get("MMAUDIO_CONDA", "mmaudio"),
                notes="Video/Text-to-SFX via MMAudio."
            ),
            "CosyVoice2": ToolSpec(
                name="CosyVoice2", task="tts",
                command=("{conda_exec} run -n {conda_env} "
                         "python {bin_dir}/run_cosyvoice2.py --target_text \"{text}\" "
                         "--prompt_transcript \"{prompt_transcript}\" --prompt_wav \"{prompt_wav}\" --out \"{output}\""),
                inputs=["target_text", "prompt_transcript", "prompt_wav"],
                conda_env=os.environ.get("COSYVOICE_CONDA", "cosyvoice"),
                notes="CosyVoice2 zero-shot."
            ),
            "InspireMusic": ToolSpec(
                name="InspireMusic", task="music",
                command=("{conda_exec} run -n {conda_env} "
                         "python {bin_dir}/run_inspiremusic.py --text \"{text}\" "
                         "--seconds {seconds} --chorus {chorus} --out \"{output}\""),
                inputs=["text", "seconds", "chorus"],
                conda_env=os.environ.get("INSPIREMUSIC_CONDA", "inspiremusic"),
                notes="Text-to-music via InspireMusic."
            ),
            "DiffRhythm": ToolSpec(
                name="DiffRhythm", task="song_gen",
                command=(
                    "{conda_exec} run -n {conda_env} "
                    "python {bin_dir}/run_diffrhythm.py "
                    "--lrc_path \"{lrc_path}\" "
                    "--ref_audio_path \"{ref_audio_path}\" "
                    "--ref_prompt \"{ref_prompt}\" "
                    "--real_seconds {seconds} "
                    "--out \"{output}\" "
                    "--batch_infer_num {batch_infer_num} "
                    "--chunked"
                ),
                inputs=["lrc_path", "ref_audio_path", "ref_prompt", "real_seconds", "batch_infer_num"],
                conda_env=os.environ.get("DIFFRHYTHM_CONDA", "diffrhythm"),
                notes="DiffRhythm wrapper. lrc_path required; exactly one of ref_audio_path/ref_prompt must be non-empty."
            ),
        }

    def has(self, name: str) -> bool:
        return name in self.tools

    def get(self, name: str) -> ToolSpec:
        if name not in self.tools:
            raise KeyError(f"Tool {name} not found")
        return self.tools[name]


def run_tool(tool: ToolSpec, args: Dict[str, Any], output_wav: Optional[str] = None) -> str:
    args = dict(args or {})
    bin_dir_default = os.path.join(os.path.dirname(__file__), "bin")
    args.setdefault("bin_dir", bin_dir_default)
    args.setdefault("conda_env", tool.conda_env or "")
    conda_exec = os.environ.get("CONDA_EXE") or shutil.which("conda")
    if not conda_exec:
        raise RuntimeError("Conda executable not found. Please ensure Conda is installed and CONDA_EXE environment variable is set if conda is not in PATH.")
    args.setdefault("conda_exec", conda_exec or "conda")
    if output_wav:
        args.setdefault("output", output_wav)
        if ("output_dir" in getattr(tool, "inputs", [])) or ("{output_dir}" in tool.command):
            args.setdefault("output_dir", os.path.dirname(output_wav))

    if "video_arg" in tool.command:
        if "video_arg" not in args:
            v = args.get("video")
            args["video_arg"] = (f'--video "{v}"' if v else "")

    cleaned_args = {k: ("" if v is None else v) for k, v in args.items()}
    tool_specific_args = cleaned_args.get(tool.name, {})
    flat_args = {k: v for k, v in cleaned_args.items() if not isinstance(v, dict)}
    flat_args.update(tool_specific_args)

    cmd = tool.command.format_map(_SafeDict(**flat_args)).strip()
    log.info("Running tool %s (%s): %s", tool.name, tool.task, cmd)

    proc = subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        out_tail = _tail_text(proc.stdout)
        err_tail = _tail_text(proc.stderr)
        msg = (
            f"Tool '{tool.name}' failed with exit code {proc.returncode}.\n"
            f"cmd: {cmd}\n"
            f"stdout:\n{out_tail or '<empty>'}\n"
            f"stderr:\n{err_tail or '<empty>'}"
        )
        log.error(msg)
        raise ToolRunError(
            msg,
            cmd=cmd,
            returncode=proc.returncode,
            stdout=out_tail,
            stderr=err_tail,
        )
    return cleaned_args.get("output", "")
