"""
Console logging with a timestamp, a level, and an emoji.

Every log line looks like this:

    2026-11-27 20:45:12 INFO    [VectorStore] Loading re-ranker model: cross-encoder/...
    2026-11-27 20:45:13 SUCCESS ✅ [FolderWatcher] Started watching /app/my-docs
    2026-11-27 20:45:14 WARN    ⚠️ [FolderWatcher] No supported documents in /app/my-docs
    2026-11-27 20:45:15 ERROR   ❌ [VectorStore] The vector database could not be opened

Lines go to stderr and, once :func:`app.log_config.setup_logging` ran, also to
the rotating file ``<LOG_DIR>/server.log``. stdout carries the MCP protocol and
the CLI reports (`--help`, `--show-config`, scan reports), so stdout stays clean.

Detail records (queries, chunks, scans) go to ``<LOG_DIR>/detail.jsonl`` through
:func:`app.log_config.log_detail`.

Use:

    log_info("Loading model", component="Embeddings")
    log_success("Started watching /app/my-docs", component="FolderWatcher")
    log_warn("No supported documents in /app/my-docs", component="FolderWatcher")
    log_error(explain(exc), component="VectorStore")
"""

import logging
from datetime import datetime
from typing import Optional

from .log_config import SERVER_LOGGER, setup_logging

LEVEL_INFO = "INFO"
LEVEL_SUCCESS = "SUCCESS"
LEVEL_WARN = "WARN"
LEVEL_ERROR = "ERROR"

# INFO stays plain: an emoji on every line makes scanning the log harder.
EMOJI = {
    LEVEL_INFO: "",
    LEVEL_SUCCESS: "✅",
    LEVEL_WARN: "⚠️",
    LEVEL_ERROR: "❌",
}

_LEVEL_WIDTH = len(LEVEL_SUCCESS)


def _level_number(level: str) -> int:
    return {
        LEVEL_INFO: logging.INFO,
        LEVEL_SUCCESS: logging.INFO,
        LEVEL_WARN: logging.WARNING,
        LEVEL_ERROR: logging.ERROR,
    }.get(level, logging.INFO)


def log(level: str, message: str, component: Optional[str] = None) -> None:
    """Write one log line: timestamp, level, emoji, component, message."""
    setup_logging()  # idempotent; keeps CLI callers working without extra setup

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag = f"[{component}] " if component else ""
    emoji = EMOJI.get(level, "")
    emoji_field = f"{emoji} " if emoji else ""

    # Multi-line messages keep their own layout, indented under the first line
    lines = str(message).splitlines() or [""]
    first = f"{stamp} {level:<{_LEVEL_WIDTH}} {emoji_field}{tag}{lines[0]}"
    if len(lines) == 1:
        text = first
    else:
        padding = " " * (len(stamp) + 1 + _LEVEL_WIDTH + 1 + (len(emoji_field) + len(tag)))
        text = "\n".join([first] + [f"{padding}{line}" for line in lines[1:]])

    logging.getLogger(SERVER_LOGGER).log(_level_number(level), text)


def log_info(message: str, component: Optional[str] = None) -> None:
    """Normal progress message."""
    log(LEVEL_INFO, message, component)


def log_success(message: str, component: Optional[str] = None) -> None:
    """Something worked: model loaded, folder watched, chunks added."""
    log(LEVEL_SUCCESS, message, component)


def log_warn(message: str, component: Optional[str] = None) -> None:
    """Something is off but the work continues."""
    log(LEVEL_WARN, message, component)


def log_error(message: str, component: Optional[str] = None) -> None:
    """Something failed."""
    log(LEVEL_ERROR, message, component)
