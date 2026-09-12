"""Application bootstrap: logging setup (dictConfig) then Game."""

import logging.config
import os

from src.core.game import Game


LOGGING_CONFIG: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stderr",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}


def _setup_logging() -> None:
    """Configure logging once at the application entry point (audit F7.3)."""
    logging.config.dictConfig(LOGGING_CONFIG)


def main() -> None:
    """Run the game with INFO console logging."""
    _setup_logging()
    Game().run()


def main_debug() -> None:
    """Run the game with the debug overlay enabled."""
    os.environ["DEBUG"] = "1"
    _setup_logging()
    Game().run()


if __name__ == "__main__":
    main()