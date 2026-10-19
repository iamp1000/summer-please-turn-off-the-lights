from __future__ import annotations
import logging
import os
import sys
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent.parent / "debug_log.txt"

def setup_logger(name: str = "tapo", level: int = logging.INFO) -> logging.Logger:
    """Configures structured logger with console and file output."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-5s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler (only when stdout is attached, not under pythonw)
    if sys.stdout is not None:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(formatter)
        logger.addHandler(console)

    # File Handler
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as ex:
        console.write(f"Failed to open log file {LOG_FILE}: {ex}\n")

    return logger

log = setup_logger()
