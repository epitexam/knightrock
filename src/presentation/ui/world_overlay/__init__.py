"""World-space debug overlay layers.

The submodules are imported directly by their callers; this package deliberately
does not import them at module scope, so a caller still using one of the old flat
paths cannot close a cycle through the package root.
"""

__all__ = [
    "bars",
    "cards",
    "geo",
    "metrics",
    "panels",
    "shapes",
    "shared",
    "velocity",
]
