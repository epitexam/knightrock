"""The provider and the router read the same set of connected pads."""

from unittest.mock import Mock

from src.core.input.device_registry import DeviceRegistry
from src.core.input.event_router import EventRouter
from src.core.input.input_provider import LocalInputProvider


def _pad(instance_id: int) -> Mock:
    pad = Mock()
    pad.get_instance_id.return_value = instance_id
    return pad


def test_the_first_pad_is_active_and_the_next_one_does_not_steal_input() -> None:
    registry = DeviceRegistry()
    first, second = _pad(1), _pad(2)

    registry.connect(first)
    registry.connect(second)

    assert registry.active() is first
    assert registry.as_dict() == {1: first, 2: second}


def test_disconnecting_the_active_pad_promotes_the_next_one() -> None:
    registry = DeviceRegistry()
    first, second = _pad(1), _pad(2)
    registry.connect(first)
    registry.connect(second)

    registry.disconnect(1)

    assert registry.active() is second


def test_provider_and_router_share_one_registry() -> None:
    registry = DeviceRegistry()
    provider = LocalInputProvider(devices=registry)
    router = EventRouter(devices=registry)
    pad = _pad(7)

    provider.connect_joystick(pad)

    assert router._resolve_joystick(7) is pad  # noqa: SLF001 - the seam under test
