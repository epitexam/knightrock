"""Axe G reception: per-tick HitCandidate dump (hitbox_amelioration.md).

- désactivé par défaut : aucun écriture, buffer vide ;
- anneau borné (maxlen) : les plus vieux candidats tombent ;
- drain JSONL : une ligne JSON par candidat, puis le buffer est vidé ;
- le compteur de tick avance via begin_tick (aligné sur le game loop).
"""

from __future__ import annotations

import json
from pathlib import Path

from src.core.level.systems.combat_trace import CombatTrace, HitCandidate


def _candidate(tick: int = 0) -> HitCandidate:
    return HitCandidate(
        tick=tick,
        kind="melee",
        owner_id="attacker",
        target_id="target",
        box_count=1,
        zone_index=0,
        zone_mult=1.2,
        pairs_tested=1,
        overlaps=1,
        contacts=1,
        guarded=False,
        damage=10.0,
    )


def test_disabled_trace_writes_nothing(tmp_path: Path) -> None:
    trace = CombatTrace(enabled=False)
    trace.record(_candidate())
    assert len(trace) == 0
    out = tmp_path / "dump.jsonl"
    trace.drain_jsonl(out)
    assert not out.exists()


def test_enabled_trace_records_and_ring_is_bounded() -> None:
    trace = CombatTrace(enabled=True, maxlen=3)
    for i in range(5):
        trace.record(_candidate(tick=i))
    assert len(trace) == 3
    # Ring keeps the most recent entries (deque maxlen semantics).
    buffered = list(trace._buffer)  # noqa: SLF001 - test asserts ring order
    assert [c.tick for c in buffered] == [2, 3, 4]


def test_drain_jsonl_writes_one_line_per_candidate(tmp_path: Path) -> None:
    trace = CombatTrace(enabled=True)
    trace.record(_candidate(tick=0))
    trace.record(_candidate(tick=1))
    out = tmp_path / "nested" / "combat_trace.jsonl"

    returned = trace.drain_jsonl(out)

    assert returned == out
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["tick"] == 0
    assert first["zone_mult"] == 1.2
    assert first["kind"] == "melee"
    assert len(trace) == 0  # buffer drained


def test_begin_tick_advances_counter() -> None:
    trace = CombatTrace(enabled=True)
    assert trace.tick == 0
    trace.begin_tick()
    trace.begin_tick()
    assert trace.tick == 2


def test_is_enabled_requires_debug_and_dump_env(monkeypatch) -> None:
    from src.core.level.systems.combat_trace import CombatTrace as CT

    monkeypatch.setenv("DEBUG", "1")
    monkeypatch.setenv("DEBUG_COMBAT_DUMP", "1")
    assert CT.is_enabled() is True

    monkeypatch.setenv("DEBUG_COMBAT_DUMP", "0")
    assert CT.is_enabled() is False

    monkeypatch.delenv("DEBUG_COMBAT_DUMP", raising=False)
    assert CT.is_enabled() is False
