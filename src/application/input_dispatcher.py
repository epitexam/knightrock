import pygame

from src.application.scene import Scene
from src.core.input.event_router import EventRouter


class InputDispatcher:
    def __init__(self, router: EventRouter) -> None:
        self._router = router

    @property
    def router(self) -> EventRouter:
        return self._router

    def dispatch(self, scene: Scene, event: pygame.event.Event) -> None:
        scene.handle_event(event)
        routed = self._router.route(event)
        if routed is not None:
            scene.handle_routed(routed)

    def poll_held_repeats(self, scene: Scene) -> None:
        for routed in self._router.poll_repeats():
            scene.handle_routed(routed)
