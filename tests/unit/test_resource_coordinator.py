"""One invalidation call drops every display-format-derived cache."""

from src.platform.resource_coordinator import ResourceCoordinator


def test_invalidation_reaches_every_cache() -> None:
    calls: list[str] = []
    coordinator = ResourceCoordinator(
        lambda: calls.append("assets"),
        lambda: calls.append("levels"),
        fx=lambda: calls.append("fx"),
        renderer=lambda: calls.append("renderer"),
    )

    coordinator.invalidate_display_format()

    assert calls == ["assets", "levels", "fx", "renderer"]


def test_a_coordinator_with_no_extra_hooks_is_still_valid() -> None:
    calls: list[str] = []

    ResourceCoordinator(
        lambda: calls.append("assets"), lambda: calls.append("levels")
    ).invalidate_display_format()

    assert calls == ["assets", "levels"]
