"""Structured logging configuration for GarminSyncWeight.

Produces JSONL logs with redaction of sensitive fields.
Logs are written to separate files per subsystem:
  - backend.log  (general application)
  - withings.log (Withings API calls)
  - garmin.log   (Garmin MCP calls)
  - sync.log     (sync pipeline)
  - security.log (auth events, token operations)
"""

import json
import logging
import logging.handlers
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.utils.redact import redact_text

LOG_FORMAT_JSONL = "jsonl"
LOG_FORMAT_TEXT = "text"

_LOGGERS: dict[str, logging.Logger] = {}


class RedactingJsonFormatter(logging.Formatter):
    """JSONL formatter that redacts sensitive fields before serialization."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


class RedactingTextFormatter(logging.Formatter):
    """Plain-text formatter with redaction."""

    def format(self, record: logging.LogRecord) -> str:
        record.msg = redact_text(record.getMessage())
        return super().format(record)

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        ct = datetime.fromtimestamp(record.created, tz=UTC)
        return ct.isoformat() if datefmt is None else ct.strftime(datefmt)


_LOG_FILES: dict[str, str] = {
    "garminsync": "backend.log",
    "withings": "withings.log",
    "garmin": "garmin.log",
    "sync": "sync.log",
    "security": "security.log",
}


def setup_logging(log_dir: Path, level: str = "INFO", fmt: str = LOG_FORMAT_JSONL) -> None:
    """Configure all loggers with file + console handlers."""
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("garminsync")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter: logging.Formatter
    if fmt == LOG_FORMAT_JSONL:
        formatter = RedactingJsonFormatter()
    else:
        formatter = RedactingTextFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handlers per subsystem
    for logger_name, filename in _LOG_FILES.items():
        lgr = logging.getLogger(logger_name)
        lgr.setLevel(getattr(logging, level.upper(), logging.INFO))
        lgr.propagate = False
        handler = logging.handlers.RotatingFileHandler(
            log_dir / filename,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(formatter)
        lgr.addHandler(handler)
        _LOGGERS[logger_name] = lgr

    root.info("Logging initialized — dir=%s level=%s format=%s", log_dir, level, fmt)


def get_logger(name: str) -> logging.Logger:
    """Get a pre-configured subsystem logger (garminsync, withings, garmin, sync, security).

    Falls back to a general logger for unknown names.
    """
    lgr = _LOGGERS.get(name)
    if lgr is not None:
        return lgr
    return logging.getLogger(name)
