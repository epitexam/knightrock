"""Application bootstrap: logging setup (dictConfig) then Game."""

import logging.config
import os
import sys

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


def _run_from_argv(argv: list[str]) -> None:
    """Entry point for ``python main.py``.

    ``--debug`` exists because the overlay used to be reachable only by calling
    ``main_debug()`` from a REPL, and nothing said so. So ``python main.py``
    quietly started a game with no panels and no F-keys, which reads as the
    feature being broken rather than as a flag nobody was told about.
    """
    if "--debug" in argv[1:]:
        main_debug()
        return
    if any(arg in ("-h", "--help") for arg in argv[1:]):
        print(__doc__)
        print("usage: python main.py [--debug]")
        print("  --debug   draw the debug panels and enable F1-F11")
        return
    main()


if __name__ == "__main__":
    _run_from_argv(sys.argv)
