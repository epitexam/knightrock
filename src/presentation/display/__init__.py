"""The display subsystem: framing, letterbox, window and presentation.

``Framing``
    How much of the world is visible, in world units. The only display
    quantity the simulation may read.
``Viewport``
    The surface everything is drawn into, at the letterbox's size.
``Stage``
    The OS window: size, position, fullscreen, vsync.
``Presentation``
    Reconciles window and target, and maps the pointer back. The picture is
    blitted 1:1, never scaled.

Nothing is re-exported: import each name from the module that defines it.
"""
