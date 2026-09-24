import pygame

from src.application.scene import Scene
from src.core.input.event_router import EventRouter


class InputDispatcher:
    def __init__(self, router: EventRouter) -> None:
        self._router = router

    def dispatch(self, scene: Scene, event: pygame.event.Event) -> None:
        scene.handle_event(event)
        routed = self._router.route(event)
        if routed is not None:
            scene.handle_routed(routed)
