import logging
from pathlib import Path


def setup_logger(log_dir="logs"):

    Path(log_dir).mkdir(exist_ok=True)

    logger = logging.getLogger("HousingSocietyScraper")

    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    file_handler = logging.FileHandler(
        Path(log_dir) / "scraper.log",
        encoding="utf-8"
    )

    console_handler = logging.StreamHandler()

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
