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
        "level": "ERROR",
        "handlers": ["console", "file"]
    }
}


def init_logging(is_debug_level: bool = False) -> None:
    config = LOGGING_CONFIG
    if is_debug_level:
        config["root"]["level"] = "DEBUG"
    else:
        config["root"]["level"] = "ERROR"
    logging.config.dictConfig(config)


def getLogger(name: str) -> Logger:
    return logging.getLogger("krita_comfyui").getChild(name)
