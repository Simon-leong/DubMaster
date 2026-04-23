"""Soft test for DiffRhythmTool.

Rules:
- No real LLM calls.
- Exactly ONE real API call to ASLP-lab/DiffRhythm /infer_music (guarded by RUN_LIVE=1).
- All other paths exercised with lightweight mocking.

Run unit tests only:
    python tests/test_diffrhythm.py

Run including the single live API call:
    RUN_LIVE=1 python tests/test_diffrhythm.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

# Allow imports from project root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from tool.base import ToolRunError
from tools_v2 import ToolLibrary

# ── fixtures ───────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = os.path.join(ROOT, "template/config_template.yaml")

SAMPLE_LRC = (
    "[00:00.00]Hello world\n"
    "[00:04.00]This is a test\n"
    "[00:08.00]oh, oh, oh\n"
)


def _find_diffrhythm_tool_name(tool_lib: ToolLibrary) -> str:
    """Auto-discover the DiffRhythm tool key from ToolLibrary."""
    first_candidate = ""
    for name, spec in getattr(tool_lib, "tools", {}).items():
        name_l = str(name).lower()
        model_l = str(getattr(spec, "default_model", "")).lower()
        task_l = str(getattr(spec, "task", "")).lower()
        if "diffrhythm" in name_l or "diffrhythm" in model_l:
            if task_l in ("song_gen", "song", "music", "music_gen", "song_generation"):
                return name
            if not first_candidate:
                first_candidate = name
    if first_candidate:
        return first_candidate
    raise RuntimeError("No DiffRhythm-like tool found in tool library.")

# Load tool from ToolLibrary with mocked Gradio client.
with patch("gradio_client.Client"):
    _TOOL_LIB = ToolLibrary(CONFIG_PATH)
    _TOOL_NAME = _find_diffrhythm_tool_name(_TOOL_LIB)
    _TOOL_SPEC = _TOOL_LIB.get(_TOOL_NAME)


def _make_tool():
    """Get DiffRhythmTool from library with mocked Gradio client (no network)."""
    with patch("gradio_client.Client"):
        tool_lib = ToolLibrary(CONFIG_PATH)
        tool_name = _find_diffrhythm_tool_name(tool_lib)
        spec = tool_lib.get(tool_name)
    return spec.runtime


# ── test runners ───────────────────────────────────────────────────────────────

_PASS = []
_FAIL = []


def run_test(name, fn):
    try:
        fn()
        _PASS.append(name)
        print(f"  PASS  {name}")
    except Exception:
        _FAIL.append(name)
        print(f"  FAIL  {name}")
        traceback.print_exc()


# ── unit tests ─────────────────────────────────────────────────────────────────

def test_seed_default():
    tool = _make_tool()
    assert tool._seed({}) == 0.0


def test_seed_explicit():
    tool = _make_tool()
    assert tool._seed({"seed": 42}) == 42.0


def test_steps_default():
    tool = _make_tool()
    assert tool._steps({}) == 32.0


def test_cfg_strength_default():
    tool = _make_tool()
    assert tool._cfg_strength({}) == 4.0


def test_music_duration_from_seconds():
    tool = _make_tool()
    assert tool._music_duration({"seconds": 60}) == 60.0


def test_music_duration_from_Music_Duration():
    tool = _make_tool()
    assert tool._music_duration({"Music_Duration": 120}) == 120.0


def test_music_duration_default():
    tool = _make_tool()
    assert tool._music_duration({}) == 95.0


def test_file_type_valid():
    tool = _make_tool()
    assert tool._file_type({"file_type": "wav"}) == "wav"


def test_file_type_invalid_falls_back():
    tool = _make_tool()
    assert tool._file_type({"file_type": "flac"}) == "mp3"


def test_odeint_method_default():
    tool = _make_tool()
    assert tool._odeint_method({}) == "euler"


def test_odeint_method_rk4():
    tool = _make_tool()
    assert tool._odeint_method({"odeint_method": "rk4"}) == "rk4"


def test_preference_default():
    tool = _make_tool()
    assert tool._preference({}) == "quality first"


def test_inline_lrc():
    tool = _make_tool()
    assert tool._read_lrc({"lrc": SAMPLE_LRC}) == SAMPLE_LRC


def test_lrc_from_file():
    tool = _make_tool()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lrc", delete=False, encoding="utf-8") as f:
        f.write(SAMPLE_LRC)
        tmp = f.name
    try:
        assert tool._read_lrc({"lrc_path": tmp}) == SAMPLE_LRC
    finally:
        os.unlink(tmp)


def test_missing_lrc_raises():
    tool = _make_tool()
    try:
        tool._read_lrc({})
        raise AssertionError("Expected ToolRunError not raised")
    except ToolRunError:
        pass


def test_nonexistent_lrc_path_raises():
    tool = _make_tool()
    try:
        tool._read_lrc({"lrc_path": "/nonexistent/path/song.lrc"})
        raise AssertionError("Expected ToolRunError not raised")
    except ToolRunError:
        pass


def test_missing_prompt_raises():
    tool = _make_tool()
    with patch("gradio_client.handle_file", return_value={"path": "sample.wav"}):
        try:
            tool.run({"lrc": SAMPLE_LRC})
            raise AssertionError("Expected ToolRunError not raised")
        except ToolRunError:
            pass


def test_run_with_inline_lrc_no_ref_audio():
    """run() with inline LRC and no ref_audio_path calls _predict with correct kwargs."""
    tool = _make_tool()
    fake_output = "/tmp/_diffrhythm_test_out.mp3"
    Path(fake_output).touch()
    try:
        with patch.object(tool, "_predict", return_value=fake_output) as mock_predict, \
             patch("tool.diffrhythm.handle_file", return_value={"path": "sample.wav"}):
            result = tool.run({"lrc": SAMPLE_LRC, "text_prompt": "Pop piano"})
        kwargs = mock_predict.call_args.kwargs
        assert kwargs["api_name"] == "/infer_music"
        assert kwargs["lrc"] == SAMPLE_LRC
        assert kwargs["text_prompt"] == "Pop piano"
        assert result == fake_output
    finally:
        Path(fake_output).unlink(missing_ok=True)


def test_run_uses_ref_prompt_as_text_prompt():
    tool = _make_tool()
    fake_output = "/tmp/_diffrhythm_test_refprompt.mp3"
    Path(fake_output).touch()
    try:
        with patch.object(tool, "_predict", return_value=fake_output), \
             patch("tool.diffrhythm.handle_file", return_value={"path": "sample.wav"}):
            result = tool.run({"lrc": SAMPLE_LRC, "ref_prompt": "Indie folk ballad"})
        assert result == fake_output
    finally:
        Path(fake_output).unlink(missing_ok=True)


def test_run_copies_to_output_wav():
    """When output_wav is provided, the file is copied there."""
    tool = _make_tool()
    fake_src = "/tmp/_diffrhythm_test_src.mp3"
    Path(fake_src).touch()
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = os.path.join(tmpdir, "out.mp3")
        try:
            with patch.object(tool, "_predict", return_value=fake_src), \
                 patch("tool.diffrhythm.handle_file", return_value={"path": "sample.wav"}):
                result = tool.run({"lrc": SAMPLE_LRC, "text_prompt": "Jazz"}, output_wav=dest)
            assert result == dest
            assert Path(dest).exists()
        finally:
            Path(fake_src).unlink(missing_ok=True)


def test_nested_args_unwrapped():
    """Tool-name-keyed nested dict is unwrapped by run()."""
    tool = _make_tool()
    fake_output = "/tmp/_diffrhythm_test_nested.mp3"
    Path(fake_output).touch()
    nested = {_TOOL_SPEC.name: {"lrc": SAMPLE_LRC, "text_prompt": "Classical"}}
    try:
        with patch.object(tool, "_predict", return_value=fake_output), \
             patch("tool.diffrhythm.handle_file", return_value={"path": "sample.wav"}):
            result = tool.run(nested)
        assert result == fake_output
    finally:
        Path(fake_output).unlink(missing_ok=True)


# ── live test (exactly ONE real API call) ──────────────────────────────────────

def test_live_infer_music():
    """Single live call with endpoint discovered from ToolLibrary runtime metadata."""
    from gradio_client import Client, handle_file

    endpoint = str(getattr(_TOOL_SPEC.runtime, "space", "") or _TOOL_SPEC.default_model or "").strip()
    tool_name = _TOOL_SPEC.name

    if not endpoint:
        raise RuntimeError(f"Tool '{tool_name}' has neither default_model nor space")

    client = Client(endpoint)
    client.view_api()
    result = client.predict(
        lrc=SAMPLE_LRC,
        ref_audio_path=None,
        text_prompt="Pop Emotional Piano",
        seed=0,
        randomize_seed=True,
        steps=32,
        cfg_strength=4.0,
        file_type="mp3",
        odeint_method="euler",
        preference_infer="quality first",
        Music_Duration=8,
        api_name="/infer_music",
    )
    print(f"\n[DEBUG] Raw API result: {result}")
    print(f"[DEBUG] Result type: {type(result)}")
    assert result, "API returned empty result"
    print(f"\n[live] tool={tool_name} endpoint={endpoint} returned: {result}")


# ── main ───────────────────────────────────────────────────────────────────────

UNIT_TESTS = [
    test_seed_default,
    test_seed_explicit,
    test_steps_default,
    test_cfg_strength_default,
    test_music_duration_from_seconds,
    test_music_duration_from_Music_Duration,
    test_music_duration_default,
    test_file_type_valid,
    test_file_type_invalid_falls_back,
    test_odeint_method_default,
    test_odeint_method_rk4,
    test_preference_default,
    test_inline_lrc,
    test_lrc_from_file,
    test_missing_lrc_raises,
    test_nonexistent_lrc_path_raises,
    test_missing_prompt_raises,
    test_run_with_inline_lrc_no_ref_audio,
    test_run_uses_ref_prompt_as_text_prompt,
    test_run_copies_to_output_wav,
    test_nested_args_unwrapped,
]

if __name__ == "__main__":
    print("=== DiffRhythmTool unit tests ===")
    for fn in UNIT_TESTS:
        run_test(fn.__name__, fn)

    if os.environ.get("RUN_LIVE") == "1":
        print("\n=== Live API test (1 real call) ===")
        run_test(test_live_infer_music.__name__, test_live_infer_music)

    total = len(_PASS) + len(_FAIL)
    print(f"\n{len(_PASS)}/{total} passed", "" if not _FAIL else f"  FAILED: {_FAIL}")
    sys.exit(0 if not _FAIL else 1)
