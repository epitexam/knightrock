"""Backward-compatible path for :mod:`src.shared.events`.

The event vocabulary is shared kernel: the simulation publishes facts and the
application subscribes, so neither layer may own the bus's types. Importing
the old path keeps every caller working during the migration (ADR 0001).
"""

from src.shared.events import *  # noqa: F403
