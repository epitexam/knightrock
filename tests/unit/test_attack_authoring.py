"""Editor export round-trip and destination tests."""

import pytest

from src.application.attack_authoring import export_attack
from src.data.attacks import read_attacks_file
from tests.unit.helpers import make_attack, make_phase


def test_export_attack_is_loadable_and_restricted_to_one_attack(tmp_path) -> None:
    definition = make_attack(make_phase())
    destination = export_attack({"player": {"kick": definition}}, "kick", tmp_path)
    loaded = read_attacks_file(destination)
    assert loaded == {"player": {"kick": definition}}


def test_export_attack_rejects_unknown_name(tmp_path) -> None:
    with pytest.raises(KeyError, match="Unknown attack"):
        export_attack({"player": {}}, "missing", tmp_path)
