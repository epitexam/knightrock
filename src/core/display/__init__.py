"""The display subsystem: framing, letterbox, window and presentation.

Four objects with four jobs, kept apart on purpose:

``Framing``
    How much of the world is visible. Fixed, in world units. The only display
    quantity the simulation may read.
``Viewport``
    The surface everything is drawn into, at the window's own size.
``Stage``
    The OS window. Mode, position, DPI, vsync. It has no opinion about size.
``Presentation``
    Window and target, and the pointer back. The only place that reconciles
    them, and it does not scale: the picture is blitted 1:1.

Nothing is re-exported. ``game.py``, ``tools/display_acceptance.py`` and two
tests import the *module* ``detection`` (``from src.core.display import
detection``) because they want the whole detection pass, not one function; every
other name is imported from the module that defines it.
"""
