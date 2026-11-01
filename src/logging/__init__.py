"""Logging package for Incubrix Engine."""

import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

try:
    from src.logging.logger import get_logger, setup_logging
except ImportError:
    from logger import get_logger, setup_logging  # type: ignore

__all__ = ["get_logger", "setup_logging"]
