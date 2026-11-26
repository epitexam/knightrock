"""PyTMX's private gid structures are read in exactly one place."""

from types import SimpleNamespace

from src.simulation.level.tmx_adapter import TmxAdapter


def _map(tiledgidmap: dict, gidmap: dict) -> SimpleNamespace:
    return SimpleNamespace(tiledgidmap=tiledgidmap, gidmap=gidmap)


def test_a_mirrored_tile_object_gets_its_flags() -> None:
    flags = SimpleNamespace(flipped_horizontally=True, flipped_vertically=False)
    adapter = TmxAdapter(_map({229: 92}, {92: [(229, flags)]}))

    assert adapter.flips(229) == (True, False)


def test_an_unmirrored_gid_and_a_missing_gid_are_both_false() -> None:
    adapter = TmxAdapter(_map({}, {}))

    assert adapter.flips(None) == (False, False)
    assert adapter.flips(0) == (False, False)
    assert adapter.flips(999) == (False, False)


def test_a_map_without_private_attributes_degrades_to_no_flips() -> None:
    """A PyTMX upgrade that drops the internals must not crash level loading."""
    adapter = TmxAdapter(SimpleNamespace())

    assert adapter.flips(42) == (False, False)
