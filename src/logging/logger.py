"""Structured and colorized logging setup for Incubrix Engine.

Writes logs to console and rotating log file under data/logs/incubrix.log.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from typing import Optional

from src.config import get_settings


class ColoredFormatter(logging.Formatter):
    """Custom formatter adding ANSI color codes for console readability."""

    GREY = "\x1b[38;20m"
    BLUE = "\x1b[34;20m"
    CYAN = "\x1b[36;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"

    FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"

    FORMATS = {
        logging.DEBUG: GREY + FORMAT + RESET,
        logging.INFO: CYAN + FORMAT + RESET,
        logging.WARNING: YELLOW + FORMAT + RESET,
        logging.ERROR: RED + FORMAT + RESET,
        logging.CRITICAL: BOLD_RED + FORMAT + RESET,
    }

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self.FORMATS.get(record.levelno, self.FORMAT)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


_initialized = False


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[Path] = None,
) -> None:
    """Initialize root logger with console and file handlers."""
    global _initialized
    if _initialized:
        return

    settings = get_settings()
    log_level_name = level or settings.log_level
    log_level = getattr(logging, log_level_name.upper(), logging.INFO)

    root_logger = logging.getLogger("incubrix")
    root_logger.setLevel(log_level)
    root_logger.propagate = False

    # Remove existing handlers to avoid duplicates
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ColoredFormatter())
    root_logger.addHandler(console_handler)

    # 2. Rotating File Handler
    logs_dir = settings.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)
    target_file = log_file or (logs_dir / "incubrix.log")

    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        filename=target_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Get a namespaced logger under 'incubrix'."""
    if not _initialized:
        setup_logging()
    clean_name = name.removeprefix("src.").removeprefix("incubrix.")
    return logging.getLogger(f"incubrix.{clean_name}")
