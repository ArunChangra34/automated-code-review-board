"""Structured logging setup for the Automated Code Review Board."""

from __future__ import annotations

import logging
import re
import sys

# Secret redaction patterns to ensure sensitive tokens never leak into logs
_SECRET_REDACT_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*['\"])([^'\"]{4})[^'\"]+(['\"])"),
    re.compile(r"(?i)(password\s*[:=]\s*['\"])([^'\"]{2})[^'\"]+(['\"])"),
    re.compile(r"(?i)(secret\s*[:=]\s*['\"])([^'\"]{4})[^'\"]+(['\"])"),
    re.compile(r"(?i)(token\s*[:=]\s*['\"])([^'\"]{4})[^'\"]+(['\"])"),
    re.compile(r"(AKIA[0-9A-Z]{4})[0-9A-Z]{12}"),
    re.compile(r"(ghp_[0-9a-zA-Z]{4})[0-9a-zA-Z]{32,}"),
]


def redact_secrets_in_text(text: str) -> str:
    """Mask secrets so they never appear in full in logs or reports."""
    redacted = text
    for pattern in _SECRET_REDACT_PATTERNS:
        # If pattern captures prefix, prefix-chars, suffix
        if pattern.groups == 3:
            redacted = pattern.sub(r"\g<1>\g<2>****\g<3>", redacted)
        elif pattern.groups == 1:
            redacted = pattern.sub(r"\g<1>****", redacted)
    return redacted


class SafeFormatter(logging.Formatter):
    """Custom logging formatter that applies secret redaction and formats correlation id."""

    def format(self, record: logging.LogRecord) -> str:
        orig_msg = record.getMessage()
        change_id = getattr(record, "change_id", "-")
        record.msg = f"[{change_id}] {redact_secrets_in_text(orig_msg)}"
        record.args = ()
        return super().format(record)


def setup_logger(name: str = "code_review_board", level: str = "INFO") -> logging.Logger:
    """Configure and return a structured logger."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers if already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        formatter = SafeFormatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def get_logger(name: str = "code_review_board") -> logging.Logger:
    """Get an existing logger or create one with default settings."""
    return logging.getLogger(name)


def configure_logging(level: str = "INFO") -> None:
    """Configure root/application loggers with safe formatting."""
    log_val = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_val)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(log_val)
        formatter = SafeFormatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
    else:
        for h in root.handlers:
            h.setLevel(log_val)
