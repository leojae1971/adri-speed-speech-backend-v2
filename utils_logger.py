"""Logger unificado del backend."""
import logging
import os

_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class Logger:
    @staticmethod
    def log(msg: str, tag: str = "ADRI"):
        logging.getLogger(tag).info(msg)

    @staticmethod
    def info(msg: str, tag: str = "ADRI"):
        logging.getLogger(tag).info(msg)

    @staticmethod
    def warning(msg: str, tag: str = "ADRI"):
        logging.getLogger(tag).warning(msg)

    @staticmethod
    def error(msg: str, tag: str = "ADRI", exc_info: bool = False):
        logging.getLogger(tag).error(msg, exc_info=exc_info)
