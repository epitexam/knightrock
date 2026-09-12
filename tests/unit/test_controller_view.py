"""Tests du mixin ControllerView (audit F1.1, Phase 2 #3)."""

from types import SimpleNamespace

import pytest

from src.entities.controller_view import ControllerView


class Dummy(ControllerView):
    """Agrégat minimal mimant Player + ses controllers."""

    CONTROLLER_VIEWS = {
        "flat": ("ctrl", "real"),
        "renamed": ("ctrl", "other"),
        "read_only": ("ctrl", "constant"),
    }

    def __init__(self) -> None:
        self.ctrl = SimpleNamespace(real=1, other=2, constant=9)
        self.plain = 3


def test_read_forwards_to_controller() -> None:
    dummy = Dummy()

    assert dummy.flat == 1
    assert dummy.renamed == 2


def test_write_forwards_to_controller() -> None:
    dummy = Dummy()

    dummy.flat = 42

    assert dummy.ctrl.real == 42


def test_plain_attribute_has_priority() -> None:
    dummy = Dummy()

    dummy.plain = 7

    assert dummy.plain == 7
    assert dummy.plain != dummy.ctrl.real


def test_unknown_attribute_raises() -> None:
    dummy = Dummy()

    with pytest.raises(AttributeError):
        _ = dummy.missing


def test_read_only_view_has_no_setter_effect() -> None:
    dummy = Dummy()

    # Toute écriture d'une vue plate est relayée : ici on documente que
    # "read_only" écrit bien l'attribut du controller (pas de blocage).
    dummy.read_only = 5

    assert dummy.ctrl.constant == 5


def test_missing_controller_falls_back_to_instance_attribute() -> None:
    class Partial(ControllerView):
        CONTROLLER_VIEWS = {"flat": ("absent_ctrl", "real")}

        def __init__(self) -> None:
            self.flat = 12

    partial = Partial()

    # Le controller n'existe pas encore : l'attribut d'instance prime.
    assert partial.flat == 12
    partial.flat = 13
    assert partial.flat == 13
