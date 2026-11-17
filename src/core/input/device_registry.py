"""One owner for connected joysticks, shared by the input provider and router."""

from __future__ import annotations

from pygame.joystick import JoystickType


class DeviceRegistry:
    """The connected pads, keyed by instance id.

    ``Game.joysticks`` is a view of this registry; the provider and the router
    both ask it instead of keeping their own dictionaries that could disagree
    after a hotplug.
    """

    def __init__(self) -> None:
        self._devices: dict[int, JoystickType] = {}

    def connect(self, joystick: JoystickType) -> None:
        self._devices[joystick.get_instance_id()] = joystick

    def disconnect(self, instance_id: int) -> None:
        self._devices.pop(instance_id, None)

    def replace(self, devices: dict[int, JoystickType]) -> None:
        self._devices = dict(devices)

    def as_dict(self) -> dict[int, JoystickType]:
        return dict(self._devices)

    def active(self) -> JoystickType | None:
        """The pad gameplay reads from: the first connected one."""
        return next(iter(self._devices.values()), None)

    def get(self, instance_id: int) -> JoystickType | None:
        return self._devices.get(instance_id)
