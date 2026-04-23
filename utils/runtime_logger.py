import logging
import os
import sys
import time
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, Optional

_RESET = "\033[0m"
_STEP_COLOR = "\033[36m"
_LLM_COLOR = "\033[33m"
_TOOL_COLOR = "\033[32m"
_UPLOAD_COLOR = "\033[34m"


def _use_log_truncation() -> bool:
    """Default to full logs; enable truncation only when explicitly requested."""
    val = str(os.environ.get("LOG_TRUNCATE", "")).strip().lower()
    return val in {"1", "true", "yes", "on"}


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _colored_prefix(tag: str, color: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = f"[{now}] [{tag}]"
    if _supports_color():
        return f"{color}{prefix}{_RESET}"
    return prefix


def _logger() -> logging.Logger:
    logger = logging.getLogger("dubmaster")
    if logger.handlers:
        return logger

    level_name = os.environ.get("DUBMASTER_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_runtime_logger() -> logging.Logger:
    """Return the shared DubMaster runtime logger instance."""
    return _logger()


def log_step(message: str) -> None:
    _logger().info("%s %s", _colored_prefix("STEP", _STEP_COLOR), message)


def _shorten(text: Any, max_len: int = 220) -> str:
    s = "" if text is None else str(text)
    s = s.replace("\n", "\\n")
    if not _use_log_truncation():
        return s
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _sanitize_mapping(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    redacted = {}
    for k, v in data.items():
        lk = str(k).lower()
        if any(token in lk for token in ("key", "token", "secret", "password")):
            redacted[k] = "***"
            continue
        if isinstance(v, bytes):
            redacted[k] = f"<bytes:{len(v)}>"
            continue
        redacted[k] = v
    return redacted


def _media_summary(media: Optional[Dict[str, Any]]) -> str:
    if not media:
        return "none"

    items = []
    for k in ("texts", "images", "videos", "audio"):
        if k not in media or media.get(k) is None:
            continue
        v = media.get(k)
        if isinstance(v, list):
            items.append(f"{k}[{len(v)}]")
        elif isinstance(v, str):
            items.append(f"{k}=path:{_shorten(v, 80)}")
        elif isinstance(v, bytes):
            items.append(f"{k}=bytes:{len(v)}")
        else:
            items.append(f"{k}={type(v).__name__}")
    return ", ".join(items) if items else "none"


def decorate_chat(chat_fn: Callable[..., str], model_label: str) -> Callable[..., str]:
    @wraps(chat_fn)
    def wrapper(*args, **kwargs):
        system = kwargs.get("system")
        user = kwargs.get("user")

        if system is None and len(args) >= 1:
            system = args[0]
        if user is None and len(args) >= 2:
            user = args[1]

        media = kwargs.get("media")

        _logger().info(
            "%s request model=%s system=%s user=%s media=%s",
            _colored_prefix("LLM", _LLM_COLOR),
            model_label,
            _shorten(system, 120),
            _shorten(user, 160),
            _media_summary(media),
        )

        start = time.perf_counter()
        try:
            result = chat_fn(*args, **kwargs)
            elapsed = time.perf_counter() - start
            _logger().info(
                "%s response model=%s elapsed=%.2fs chars=%d body=%s",
                _colored_prefix("LLM", _LLM_COLOR),
                model_label,
                elapsed,
                len(result or ""),
                _shorten(result, 260),
            )
            return result
        except Exception as exc:
            elapsed = time.perf_counter() - start
            _logger().exception(
                "%s error model=%s elapsed=%.2fs error=%s",
                _colored_prefix("LLM", _LLM_COLOR),
                model_label,
                elapsed,
                exc,
            )
            raise

    setattr(wrapper, "_logged", True)
    return wrapper


def instrument_llm_chat(llm_obj: Any) -> Any:
    chat_fn = getattr(llm_obj, "chat", None)
    if chat_fn is None:
        return llm_obj

    if getattr(chat_fn, "_logged", False):
        return llm_obj

    model_name = getattr(llm_obj, "model", llm_obj.__class__.__name__)
    label = f"{llm_obj.__class__.__name__}({model_name})"
    llm_obj.chat = decorate_chat(chat_fn, label)
    return llm_obj


def decorate_tool_run(run_fn: Callable[..., str], tool_label: str) -> Callable[..., str]:
    @wraps(run_fn)
    def wrapper(*args, **kwargs):
        run_args = kwargs.get("args")
        output_wav = kwargs.get("output_wav")

        if run_args is None and len(args) >= 1:
            run_args = args[0]
        if output_wav is None and len(args) >= 2:
            output_wav = args[1]

        safe_args = _sanitize_mapping(run_args)

        _logger().info(
            "%s request tool=%s args=%s output=%s",
            _colored_prefix("TOOL", _TOOL_COLOR),
            tool_label,
            _shorten(safe_args, 260),
            _shorten(output_wav, 120),
        )

        start = time.perf_counter()
        try:
            result = run_fn(*args, **kwargs)
            elapsed = time.perf_counter() - start
            _logger().info(
                "%s response tool=%s elapsed=%.2fs result=%s",
                _colored_prefix("TOOL", _TOOL_COLOR),
                tool_label,
                elapsed,
                _shorten(result, 200),
            )
            return result
        except Exception as exc:
            elapsed = time.perf_counter() - start
            _logger().exception(
                "%s error tool=%s elapsed=%.2fs error=%s",
                _colored_prefix("TOOL", _TOOL_COLOR),
                tool_label,
                elapsed,
                exc,
            )
            raise

    setattr(wrapper, "_logged", True)
    return wrapper


def instrument_tool_run(tool_runtime: Any) -> Any:
    run_fn = getattr(tool_runtime, "run", None)
    if run_fn is None:
        return tool_runtime

    if getattr(run_fn, "_logged", False):
        return tool_runtime

    spec = getattr(tool_runtime, "spec", None)
    tool_name = getattr(spec, "name", None) or tool_runtime.__class__.__name__
    label = f"{tool_runtime.__class__.__name__}({tool_name})"
    tool_runtime.run = decorate_tool_run(run_fn, label)
    return tool_runtime


def _upload_result_summary(result: Any) -> str:
    if result is None:
        return "none"

    if hasattr(result, "provider") and hasattr(result, "url"):
        provider = getattr(result, "provider", "")
        url = getattr(result, "url", "")
        remote_id = getattr(result, "remote_id", "")
        remote_path = getattr(result, "remote_path", "")
        return _shorten(
            f"provider={provider} url={url} remote_id={remote_id} remote_path={remote_path}",
            260,
        )

    if isinstance(result, list):
        return f"list[{len(result)}]"

    return _shorten(result, 260)


def decorate_upload_action(action: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for media upload methods with dedicated UPLOAD logs."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if getattr(fn, "_logged", False):
            return fn

        @wraps(fn)
        def wrapper(*args, **kwargs):
            uploader = args[0] if args else None
            label = uploader.__class__.__name__ if uploader is not None else "Uploader"
            call_args = args[1:] if len(args) >= 1 else args

            _logger().info(
                "%s request uploader=%s action=%s args=%s kwargs=%s",
                _colored_prefix("UPLOAD", _UPLOAD_COLOR),
                label,
                action,
                _shorten(call_args, 220),
                _shorten(_sanitize_mapping(kwargs), 220),
            )

            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                elapsed = time.perf_counter() - start
                _logger().info(
                    "%s response uploader=%s action=%s elapsed=%.2fs result=%s",
                    _colored_prefix("UPLOAD", _UPLOAD_COLOR),
                    label,
                    action,
                    elapsed,
                    _upload_result_summary(result),
                )
                return result
            except Exception as exc:
                elapsed = time.perf_counter() - start
                _logger().exception(
                    "%s error uploader=%s action=%s elapsed=%.2fs error=%s",
                    _colored_prefix("UPLOAD", _UPLOAD_COLOR),
                    label,
                    action,
                    elapsed,
                    exc,
                )
                raise

        setattr(wrapper, "_logged", True)
        return wrapper

    return decorator
