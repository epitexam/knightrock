"""Application bootstrap: logging setup (dictConfig) then Game."""

import logging.config
import os
import sys
from dataclasses import replace

from src.application.game import Game
from src.application.runtime_config import RuntimeConfig

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
    Game(config=RuntimeConfig.from_environment()).run()


def main_debug() -> None:
    """Run the game with the debug overlay enabled."""
    # The overlay's leaf helpers still read DEBUG at call time; keep the env
    # write for them while the application layer uses the explicit config.
    os.environ["DEBUG"] = "1"
    _setup_logging()
    Game(config=replace(RuntimeConfig.from_environment(), debug=True)).run()


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
