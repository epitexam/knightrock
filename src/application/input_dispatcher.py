"""Route an input to the active scene, and publish what the scene did.

The dispatcher is the single seam between the input layer and the interface.
It owns no presentation state, reads no view, and knows nothing about audio:
it routes an event, hands it to the scene, and turns the scene's report into a
:class:`UiFeedback` fact on the bus. One input, one report, one fact — so an
interaction cannot be announced twice by two branches of two screens.

Publishing rather than calling also means the interface effects are not the
dispatcher's business to know: the audio system is one subscriber among
others, and the next one costs nothing here.
"""

import pygame

from src.application.events import EventBus, UiEffect, UiFeedback
from src.application.scene import Scene
from src.core.input.event_router import EventRouter, RoutedInput
from src.ui.menu_model import MenuAction

#: The report values that mean *the focus moved* rather than *an item fired*.
_NAVIGATION = frozenset({MenuAction.MOVE_UP, MenuAction.MOVE_DOWN, MenuAction.HOVER})

#: Routed inputs that are not a deliberate action, and that the screens
#: already refuse to act on: the extra event a stick/hat emits when it returns
#: to neutral (``MenuModel.is_release``), and a controller being unplugged.
#: They are filtered here, where the variant is known, rather than in each
#: screen.
_UNACTED_VARIANTS = frozenset({"release", "device_removed"})


class InputDispatcher:
    def __init__(self, router: EventRouter, events: EventBus) -> None:
        self._router = router
        self._events = events

    @property
    def router(self) -> EventRouter:
        return self._router

    def dispatch(self, scene: Scene, event: pygame.event.Event) -> None:
        scene.handle_event(event)
        routed = self._router.route(event)
        if routed is not None:
            self._apply(scene, routed)

    def poll_held_repeats(self, scene: Scene) -> None:
        for routed in self._router.poll_repeats():
            self._apply(scene, routed)

    def _apply(self, scene: Scene, routed: RoutedInput) -> None:
        """Let the scene act, then announce what it did.

        The report is read *after* the scene has handled the input, which is
        what makes the ordering of ``handle_event`` irrelevant here: a screen
        that swallows the raw event (the controls screen filling a binding)
        returns ``None`` and nothing is published, with no pre-reading of the
        scene's state to keep in sync.
        """
        performed = scene.handle_routed(routed)
        if performed is None or routed.variant in _UNACTED_VARIANTS:
            return
        self._events.emit(UiFeedback(effect=_effect_of(performed), action=performed))


def _effect_of(performed: str) -> UiEffect:
    """The interface effect a scene report stands for.

    The classification lives here, in the layer that already speaks both
    vocabularies: only the input/interface side knows what ``MenuAction`` means,
    and the audio side is left with a fact it can answer without knowing a
    single menu action.
    """
    if performed in _NAVIGATION:
        return UiEffect.NAVIGATED
    if performed == MenuAction.BACK:
        return UiEffect.DISMISSED
    return UiEffect.CONFIRMED
