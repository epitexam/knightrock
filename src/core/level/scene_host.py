"""The one thing a debug panel may ask about the application.

``Level.draw`` used to take ``game: Any`` and pass it down to the debug SCENE
panel, which read a single attribute off it: ``game.scene_manager.current``.
Four signatures in between were typed ``Any`` to carry that one hop, and ``Any``
is a pass-through rather than a contract -- it says nothing about what the
panel is allowed to touch, so the next addition to it is invisible.

This is the narrowing. It is deliberately *one* member rather than the whole
application: the audit that asked for a six-member ``SceneHost`` (ui_scale,
clock, scene_manager, notice, render_alpha, surface) was describing a seam
that does not exist here, because the scenes reach the application through
``Scene.game`` and use a good deal more than six things. A Protocol that
under-describes its subject is a Protocol everything satisfies and nothing is
checked against, which is ``Any`` with better manners.

So this is the honest size: the debug panel needs to know which scene is on
top, and it gets a type that says exactly that. ``Game`` satisfies it
structurally and ``None`` means "nobody to ask", which is what a level drawn
outside the scene stack has always meant by it.
"""

from __future__ import annotations

from typing import Protocol

__all__ = ["SceneHost", "SceneStack"]


class SceneStack(Protocol):
    """The top of the scene stack."""

    @property
    def current(self) -> object | None:
        """The active scene, or None when the stack is empty."""


class SceneHost(Protocol):
    """Whoever can answer "which scene is on top right now".

    Implemented by :class:`~src.core.game.Game`. The SCENE debug panel reads
    the current scene's name, its ``level_id`` and its level's death count --
    the first two through the stack, the last through the scene, and both
    through ``getattr`` with a default, because a scene that has no level is a
    perfectly ordinary thing for the panel to be asked about.
    """

    @property
    def scene_manager(self) -> SceneStack:
        """The scene stack this host is driving."""
