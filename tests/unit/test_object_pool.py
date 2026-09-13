"""Tests du ObjectPool générique (Phase 3 #1, audit F6.3)."""

from src.core.object_pool import ObjectPool


class Projectile:
    def __init__(self) -> None:
        self.active = True
        self.velocity = 900.0
        self.resets = 0


def test_acquire_builds_through_the_factory_when_empty() -> None:
    pool: ObjectPool[Projectile] = ObjectPool(Projectile)

    first = pool.acquire()

    assert isinstance(first, Projectile)
    assert pool.created == 1
    assert pool.available == 0


def test_release_then_acquire_returns_the_same_instance() -> None:
    pool: ObjectPool[Projectile] = ObjectPool(Projectile)
    first = pool.acquire()
    pool.release(first)

    second = pool.acquire()

    assert second is first
    assert pool.created == 1  # aucune nouvelle construction


def test_reset_runs_on_recycled_instances_only() -> None:
    resets: list[Projectile] = []
    pool: ObjectPool[Projectile] = ObjectPool(Projectile, reset=resets.append)

    fresh = pool.acquire()
    assert resets == []  # l'instance neuve sort propre de la factory

    pool.release(fresh)
    recycled = pool.acquire()

    assert recycled is fresh
    assert resets == [fresh]


def test_available_reflects_the_free_list() -> None:
    pool: ObjectPool[Projectile] = ObjectPool(Projectile)
    a = pool.acquire()
    b = pool.acquire()

    assert pool.available == 0
    pool.release(a)
    pool.release(b)
    assert pool.available == 2

    pool.acquire()
    assert pool.available == 1


def test_clear_drops_parked_instances() -> None:
    pool: ObjectPool[Projectile] = ObjectPool(Projectile)
    instance = pool.acquire()
    pool.release(instance)

    pool.clear()

    assert pool.available == 0
    assert pool.acquire() is not instance


def test_pool_is_reusable_across_many_cycles() -> None:
    pool: ObjectPool[Projectile] = ObjectPool(Projectile)
    seen: list[int] = []
    for _ in range(50):
        instance = pool.acquire()
        seen.append(id(instance))
        pool.release(instance)

    assert len(set(seen)) == 1  # une seule instance recyclée 50 fois
    assert pool.created == 1


def test_release_allows_duplicates_but_is_not_policed() -> None:
    """Double-release documenté : le pool reste minimal (pas de bookkeeping)."""
    pool: ObjectPool[Projectile] = ObjectPool(Projectile)
    instance = pool.acquire()

    pool.release(instance)
    pool.release(instance)

    assert pool.available == 2  # comportement explicite, pas de magie
