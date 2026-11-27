"""
Console logging with a timestamp, a level, and an emoji.

Every log line looks like this:

    2026-11-27 20:45:12 INFO    [VectorStore] Loading re-ranker model: cross-encoder/...
    2026-11-27 20:45:13 SUCCESS ✅ [FolderWatcher] Started watching /app/my-docs
    2026-11-27 20:45:14 WARN    ⚠️ [FolderWatcher] No supported documents in /app/my-docs
    2026-11-27 20:45:15 ERROR   ❌ [VectorStore] The vector database could not be opened

All output goes to stderr. stdout carries the MCP protocol and the CLI reports
(`--help`, `--show-config`, scan reports), so stdout must stay clean.

Use:

    log_info("Loading model", component="Embeddings")
    log_success("Started watching /app/my-docs", component="FolderWatcher")
    log_warn("No supported documents in /app/my-docs", component="FolderWatcher")
    log_error(explain(exc), component="VectorStore")
"""

import sys
from datetime import datetime
from typing import Optional

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


def log(level: str, message: str, component: Optional[str] = None) -> None:
    """Write one log line to stderr: timestamp, level, emoji, component, message."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag = f"[{component}] " if component else ""
    emoji = EMOJI.get(level, "")
    emoji_field = f"{emoji} " if emoji else ""

    # Multi-line messages keep their own layout, indented under the first line
    lines = str(message).splitlines() or [""]
    first = f"{stamp} {level:<{_LEVEL_WIDTH}} {emoji_field}{tag}{lines[0]}"
    if len(lines) == 1:
        print(first, file=sys.stderr, flush=True)
        return

    print(first, file=sys.stderr)
    padding = " " * (len(stamp) + 1 + _LEVEL_WIDTH + 1 + (len(emoji_field) + len(tag)))
    for line in lines[1:]:
        print(f"{padding}{line}", file=sys.stderr, flush=True)


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
