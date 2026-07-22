from __future__ import annotations

import logging
import os
import sys

RESET = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"

LEVEL_COLORS = {
    logging.DEBUG: "\x1b[38;5;245m",
    logging.INFO: "\x1b[38;5;39m",
    logging.WARNING: "\x1b[38;5;214m",
    logging.ERROR: "\x1b[38;5;203m",
    logging.CRITICAL: "\x1b[1;38;5;197m",
}

LEVEL_NAMES = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRIT",
}

NAME_COLOR = "\x1b[38;5;108m"
TIME_COLOR = "\x1b[38;5;244m"


def _supports_color(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(stream, "isatty") and stream.isatty()


class ColorFormatter(logging.Formatter):
    def __init__(self, color: bool):
        super().__init__(datefmt="%H:%M:%S")
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        level = LEVEL_NAMES.get(record.levelno, record.levelname)
        name = record.name
        if name.startswith("wwps."):
            name = name[5:]
        message = record.getMessage()
        stamp = self.formatTime(record, self.datefmt)

        if not self.color:
            line = f"{stamp} {level:<5} {name:<14} {message}"
        else:
            level_color = LEVEL_COLORS.get(record.levelno, "")
            line = (f"{TIME_COLOR}{stamp}{RESET} "
                    f"{level_color}{level:<5}{RESET} "
                    f"{NAME_COLOR}{name:<14}{RESET} "
                    f"{message}")

        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure(level: str = "INFO"):
    stream = sys.stdout
    handler = logging.StreamHandler(stream)
    handler.setFormatter(ColorFormatter(_supports_color(stream)))

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def get(name: str) -> logging.Logger:
    return logging.getLogger(name)


def banner(server_name: str, version: str, port: int, wibwob: bool):
    color = _supports_color(sys.stdout)
    title = f"{server_name} ({'Wibble Wobble' if wibwob else 'Puni Puni'})"
    line = f"{title} - version {version} - listening on :{port}"
    if color:
        print(f"{BOLD}\x1b[38;5;39m{line}{RESET}")
    else:
        print(line)
