"""Dense table identity: recycled slots must not resurrect stale handles."""

from src.simulation.ecs.table import DenseTable
from src.simulation.entities.id_factory import IdFactory


def test_a_released_handle_never_resolves_again() -> None:
    table = DenseTable()
    slot = table.acquire(("p1", 0))
    assert table.slot_of(("p1", 0)) == slot

    assert table.release(slot) == ("p1", 0)
    assert table.slot_of(("p1", 0)) is None
    assert table.handle_at(slot) == ("p1", 1)


def test_a_recycled_slot_keeps_the_same_id_but_a_new_generation() -> None:
    table = DenseTable()
    first = table.acquire(("p1", 0))
    table.release(first)
    second = table.acquire(("p1", 1))

    assert second == first
    assert table.slot_of(("p1", 0)) is None
    assert table.slot_of(("p1", 1)) == second
    assert table.release(second) == ("p1", 1)
    assert table.handle_at(second) == ("p1", 2)


def test_columns_stay_aligned_acquire_and_release() -> None:
    table = DenseTable(["life", "vx"])
    table.add_column("vy", 0.0)
    first = table.acquire(("p1", 0))
    second = table.acquire(("p2", 0))
    table.column("life")[first] = 1.25
    table.column("life")[second] = 0.5

    table.release(first)
    third = table.acquire(("p3", 0))

    assert third == first
    assert table.column("life")[third] is None
    assert table.column("life")[second] == 0.5
    assert len(table.column("vy")) == len(table._handle_at)


def test_id_factory_hands_out_handles_with_generation_zero() -> None:
    factory = IdFactory()
    entity = factory.entity_handle()
    shot = factory.projectile_handle()

    assert entity == ("e0", 0)
    assert shot == ("p0", 0)
    assert factory.entity_id() == "e1"
    assert factory.projectile_id() == "p1"
