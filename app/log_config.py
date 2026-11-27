"""
Production logging setup: console, rotating server log, structured detail log.

Two files live in ``LOG_DIR`` (``logs/`` next to the project, ``/app/logs`` in
Docker, bind-mounted so they survive the container):

* ``server.log`` - everything the server does, one line per event, rotated by
  size (``LOG_MAX_BYTES``, ``LOG_BACKUP_COUNT`` backups: ``server.log.1`` ...).
* ``detail.jsonl`` - one JSON object per line for the events that need detail:
  MCP tool calls, search queries with every candidate and every returned chunk,
  document scans, watcher batches. Rotated the same way.

Both files use the same timestamped, levelled format the console uses, so a line
copied from the console can be found in ``server.log`` verbatim.

Call :func:`setup_logging` once at process start. Every other module keeps using
:mod:`app.logging_utils`; nothing writes to the files directly.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .config import (
    LOG_BACKUP_COUNT,
    LOG_CONSOLE,
    LOG_DETAIL_ENABLED,
    LOG_DIR,
    LOG_LEVEL,
    LOG_MAX_BYTES,
)

SERVER_LOG_NAME = "server.log"
DETAIL_LOG_NAME = "detail.jsonl"

SERVER_LOGGER = "docs2ai.server"
DETAIL_LOGGER = "docs2ai.detail"

_configured = False


def _level_number(level: str) -> int:
    return {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }.get((level or "INFO").upper(), logging.INFO)


class _PlainFormatter(logging.Formatter):
    """Keep the line exactly as logging_utils built it."""

    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()


def _rotating_handler(path: Path, level: int) -> logging.Handler:
    handler = logging.handlers.RotatingFileHandler(
        filename=str(path),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    handler.setLevel(level)
    handler.setFormatter(_PlainFormatter())
    return handler


def setup_logging() -> None:
    """Install the console and file handlers once per process."""
    global _configured
    if _configured:
        return
    _configured = True

    level = _level_number(LOG_LEVEL)

    server_logger = logging.getLogger(SERVER_LOGGER)
    server_logger.setLevel(level)
    server_logger.propagate = False
    if not server_logger.handlers:
        try:
            server_logger.addHandler(_rotating_handler(LOG_DIR / SERVER_LOG_NAME, level))
        except OSError as exc:  # read-only or missing folder must not kill the server
            print(f"Could not open {LOG_DIR / SERVER_LOG_NAME}: {exc}", file=sys.stderr)
        if LOG_CONSOLE:
            console = logging.StreamHandler(stream=sys.stderr)
            console.setLevel(level)
            console.setFormatter(_PlainFormatter())
            server_logger.addHandler(console)

    detail_logger = logging.getLogger(DETAIL_LOGGER)
    detail_logger.setLevel(logging.INFO)
    detail_logger.propagate = False
    if LOG_DETAIL_ENABLED and not detail_logger.handlers:
        try:
            detail_logger.addHandler(_rotating_handler(LOG_DIR / DETAIL_LOG_NAME, logging.INFO))
        except OSError as exc:
            print(f"Could not open {LOG_DIR / DETAIL_LOG_NAME}: {exc}", file=sys.stderr)


def log_detail(event: str, **fields: Any) -> None:
    """Append one structured record to detail.jsonl (no-op when disabled)."""
    if not LOG_DETAIL_ENABLED:
        return
    record: Dict[str, Any] = {
        "ts": datetime.now().isoformat(timespec="milliseconds"),
        "event": event,
    }
    record.update(fields)
    try:
        line = json.dumps(record, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:  # never break a request because of logging
        line = json.dumps({"ts": record["ts"], "event": event, "log_error": str(exc)}, ensure_ascii=False)
    logging.getLogger(DETAIL_LOGGER).info(line)


def truncate(text: Optional[str], limit_chars: int) -> Optional[str]:
    """Cut long chunk text for the detail log, and mark that it was cut."""
    if text is None:
        return None
    if limit_chars <= 0:
        return None
    if len(text) <= limit_chars:
        return text
    return text[:limit_chars] + f"...[{len(text) - limit_chars} chars cut]"
