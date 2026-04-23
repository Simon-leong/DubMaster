"""Soft test for InspireMusicTool.

Rules:
- No real LLM calls.
- Exactly ONE real API call to xscdvfaaqqq/InspireMusic /demo_inspiremusic_t2m (guarded by RUN_LIVE=1).
- All other paths exercised with lightweight mocking.

Run unit tests only:
    python tests/test_inspiremusic.py

Run including the single live API call:
    RUN_LIVE=1 python tests/test_inspiremusic.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
import wave
from pathlib import Path
from unittest.mock import patch

# Allow imports from project root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from tool.base import ToolRunError
from tools_v2 import ToolLibrary

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = os.path.join(ROOT, "template/config_template.yaml")


def _write_silent_wav(path: str, duration_sec: float = 1.0, sample_rate: int = 24000) -> None:
    nframes = int(max(duration_sec, 0.1) * sample_rate)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * nframes)


def _find_inspiremusic_tool_name(tool_lib: ToolLibrary) -> str:
    """Auto-discover the InspireMusic tool key from ToolLibrary."""
    first_candidate = ""
    for name, spec in getattr(tool_lib, "tools", {}).items():
        name_l = str(name).lower()
        model_l = str(getattr(spec, "default_model", "")).lower()
        task_l = str(getattr(spec, "task", "")).lower()
        if "inspiremusic" in name_l or "inspiremusic" in model_l:
            if task_l in ("music", "music_gen", "song", "song_gen"):
                return name
            if not first_candidate:
                first_candidate = name
    if first_candidate:
        return first_candidate
    raise RuntimeError("No InspireMusic-like tool found in tool library.")


# Load tool from ToolLibrary with mocked Gradio client.
with patch("gradio_client.Client"):
    _TOOL_LIB = ToolLibrary(CONFIG_PATH)
    _TOOL_NAME = _find_inspiremusic_tool_name(_TOOL_LIB)
    _TOOL_SPEC = _TOOL_LIB.get(_TOOL_NAME)


def _make_tool():
    """Get InspireMusicTool from library with mocked Gradio client (no network)."""
    with patch("gradio_client.Client"):
        tool_lib = ToolLibrary(CONFIG_PATH)
        tool_name = _find_inspiremusic_tool_name(tool_lib)
        spec = tool_lib.get(tool_name)
    return spec.runtime


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


def test_model_name_default():
    tool = _make_tool()
    assert tool._model_name({}) == "InspireMusic-1.5B-Long"


def test_model_name_invalid_falls_back():
    tool = _make_tool()
    assert tool._model_name({"model_name": "unknown-model"}) == "InspireMusic-1.5B-Long"


def test_model_name_valid_kept():
    tool = _make_tool()
    assert tool._model_name({"model_name": "InspireMusic-Base"}) == "InspireMusic-Base"


def test_chorus_default():
    tool = _make_tool()
    assert tool._chorus({}) == "intro"


def test_chorus_invalid_falls_back():
    tool = _make_tool()
    assert tool._chorus({"chorus": "bridge"}) == "intro"


def test_output_sample_rate_default():
    tool = _make_tool()
    assert tool._output_sample_rate({}) == 48000


def test_output_sample_rate_invalid_falls_back():
    tool = _make_tool()
    assert tool._output_sample_rate({"output_sample_rate": "16000"}) == 48000


def test_seconds_alias_for_max_generate_audio_seconds():
    tool = _make_tool()
    assert tool._max_generate_audio_seconds({"seconds": 12}) == 12.0


def test_max_generate_audio_seconds_invalid_falls_back():
    tool = _make_tool()
    assert tool._max_generate_audio_seconds({"max_generate_audio_seconds": "bad"}) == 30.0


def test_missing_text_raises():
    tool = _make_tool()
    try:
        tool.run({"chorus": "verse"})
        raise AssertionError("Expected ToolRunError not raised")
    except ToolRunError:
        pass


def test_run_calls_t2m_api_with_expected_kwargs():
    tool = _make_tool()
    fake_output = "/tmp/_inspiremusic_test_out.wav"
    _write_silent_wav(fake_output, duration_sec=20.0)
    try:
        with patch.object(tool, "_predict", return_value=fake_output) as mock_predict:
            result = tool.run({"text": "calm piano", "seconds": 9, "chorus": "verse"})
        kwargs = mock_predict.call_args.kwargs
        assert kwargs["api_name"] == "/demo_inspiremusic_t2m"
        assert kwargs["text"] == "calm piano"
        assert kwargs["chorus"] == "verse"
        assert kwargs["max_generate_audio_seconds"] == 9.0
        assert result == fake_output
    finally:
        Path(fake_output).unlink(missing_ok=True)


def test_run_accepts_tuple_result_and_copies_to_output_wav():
    tool = _make_tool()
    fake_src = "/tmp/_inspiremusic_test_src.wav"
    Path(fake_src).touch()
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = os.path.join(tmpdir, "out.wav")
        try:
            with patch.object(tool, "_predict", return_value=(fake_src,)):
                result = tool.run({"text": "ambient pad"}, output_wav=dest)
            assert result == dest
            assert Path(dest).exists()
        finally:
            Path(fake_src).unlink(missing_ok=True)


def test_nested_args_unwrapped():
    tool = _make_tool()
    fake_output = "/tmp/_inspiremusic_test_nested.wav"
    _write_silent_wav(fake_output, duration_sec=20.0)
    nested = {_TOOL_SPEC.name: {"text": "soft lo-fi", "chorus": "chorus", "seconds": 6}}
    try:
        with patch.object(tool, "_predict", return_value=fake_output):
            result = tool.run(nested)
        assert result == fake_output
    finally:
        Path(fake_output).unlink(missing_ok=True)


def test_live_demo_inspiremusic_t2m():
    """Single live call with endpoint discovered from ToolLibrary runtime metadata."""
    from gradio_client import Client

    endpoint = str(getattr(_TOOL_SPEC.runtime, "space", "") or _TOOL_SPEC.default_model or "").strip()
    tool_name = _TOOL_SPEC.name

    if not endpoint:
        raise RuntimeError(f"Tool '{tool_name}' has neither default_model nor space")

    client = Client(endpoint)
    result = client.predict(
        text="Soft ambient piano for a peaceful night.",
        model_name="InspireMusic-1.5B-Long",
        chorus="intro",
        output_sample_rate=48000,
        max_generate_audio_seconds=10,
        api_name="/demo_inspiremusic_t2m",
    )
    print(f"\n[DEBUG] Raw API result: {result}")
    print(f"[DEBUG] Result type: {type(result)}")
    assert result, "API returned empty result"
    print(f"\n[live] tool={tool_name} endpoint={endpoint} returned: {result}")


UNIT_TESTS = [
    test_model_name_default,
    test_model_name_invalid_falls_back,
    test_model_name_valid_kept,
    test_chorus_default,
    test_chorus_invalid_falls_back,
    test_output_sample_rate_default,
    test_output_sample_rate_invalid_falls_back,
    test_seconds_alias_for_max_generate_audio_seconds,
    test_max_generate_audio_seconds_invalid_falls_back,
    test_missing_text_raises,
    test_run_calls_t2m_api_with_expected_kwargs,
    test_run_accepts_tuple_result_and_copies_to_output_wav,
    test_nested_args_unwrapped,
]


if __name__ == "__main__":
    print("=== InspireMusicTool unit tests ===")
    for fn in UNIT_TESTS:
        run_test(fn.__name__, fn)

    if os.environ.get("RUN_LIVE") == "1":
        print("\n=== Live API test (1 real call) ===")
        run_test(test_live_demo_inspiremusic_t2m.__name__, test_live_demo_inspiremusic_t2m)

    total = len(_PASS) + len(_FAIL)
    print(f"\n{len(_PASS)}/{total} passed", "" if not _FAIL else f"  FAILED: {_FAIL}")
    sys.exit(0 if not _FAIL else 1)
