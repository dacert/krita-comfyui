
from logging import Logger
import logging.config
from pathlib import Path

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "standard": {
            "()": "logging.Formatter",
            "fmt": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        }
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "standard"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(Path(__file__).resolve().parent / "krita_comfyui.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 4,
            "encoding": "utf-8",
            "formatter": "standard"
        }
    },

    "root": {
        "level": "DEBUG",
        "handlers": ["console", "file"]
    }
}


def init_logging() -> None:
    logging.config.dictConfig(LOGGING_CONFIG)


def getLogger(name: str) -> Logger:
    return logging.getLogger("krita_comfyui").getChild(name)