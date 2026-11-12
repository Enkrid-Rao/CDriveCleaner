"""运行日志：按天落盘，供 GUI 查看与问题排查。"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import sys
from pathlib import Path

from .. import paths

_logger: logging.Logger | None = None
_handler: logging.FileHandler | None = None
_current_day: str = ""


def _logfile() -> Path:
    day = _dt.date.today().isoformat()
    return paths.logs_dir() / f"CDriveCleaner-{day}.log"


def _ensure() -> logging.Logger | None:
    global _logger, _handler, _current_day
    day = _dt.date.today().isoformat()
    if _logger is not None and _handler is not None and day == _current_day:
        return _logger
    try:
        if _handler is not None:
            _logger.removeHandler(_handler)
            _handler.close()
        handler = logging.FileHandler(_logfile(), encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S"))
        logger = logging.getLogger("cdrivecleaner")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.addHandler(handler)
        _logger, _handler, _current_day = logger, handler, day
        return logger
    except OSError:
        return None


def log(level: str, message: str) -> None:
    logger = _ensure()
    if logger is None:
        return
    level = level.upper()
    try:
        if level == "ERROR":
            logger.error(message)
        elif level == "WARN":
            logger.warning(message)
        else:
            logger.info(message)
    except Exception:
        pass


def tail(lines: int = 200) -> str:
    path = _logfile()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            rows = f.readlines()
        return "".join(rows[-max(1, lines):])
    except OSError:
        return ""


def log_path() -> str:
    return str(_logfile())
