"""The audio policy, and the degradation of its transport (audit UI, lot 5).

Two things are checked apart on purpose. :func:`cue_for` is a pure function
over :class:`UiEffect`, so "this interaction sounds like that" is provable
with no audio device at all. :class:`AudioBus` is exercised against the dummy
SDL driver to prove it degrades instead of raising — the state CI is in, since
``assets/`` is git-ignored.
"""

import os

import pygame
import pytest

from src.application.events import (
    EventBus,
    LevelCompleted,
    LevelStarted,
    PlayerDied,
    UiEffect,
    UiFeedback,
)
from src.core.audio import SOUNDS, AudioBus, AudioCategory, SoundId, SoundSpec, cue_for


@pytest.fixture(scope="module", autouse=True)
def _dummy_audio_driver() -> None:
    """A device-less mixer: the state CI is in, since ``assets/`` is ignored."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))


# --- the policy: one fact, one cue ---------------------------------------


@pytest.mark.parametrize(
    ("effect", "expected"),
    [
        (UiEffect.NAVIGATED, SoundId.NAVIGATE),
        (UiEffect.CONFIRMED, SoundId.CONFIRM),
        (UiEffect.DISMISSED, SoundId.BACK),
    ],
)
def test_every_interface_effect_has_its_cue(effect: UiEffect, expected: SoundId) -> None:
    assert cue_for(effect) is expected


def test_the_policy_covers_every_effect_with_a_real_cue() -> None:
    """No effect is left without an answer, and no answer is a dead cue."""
    for effect in UiEffect:
        sound_id = cue_for(effect)
        assert sound_id is not None
        assert sound_id in SOUNDS


def test_a_dismissal_is_not_a_confirmation() -> None:
    """They share a file today; the distinction must not depend on that."""
    assert cue_for(UiEffect.DISMISSED) is not cue_for(UiEffect.CONFIRMED)


# --- the table -----------------------------------------------------------


def test_every_cue_points_at_an_existing_ui_asset() -> None:
    """The shipped sounds are all accounted for, and none is orphaned.

    ``CONFIRM`` and ``BACK`` deliberately share ``click.mp3``: the three files
    in ``assets/sounds/ui`` are the three cues the interface needs, and a
    fourth file would be a behaviour invented to justify an asset.
    """
    assert {sound_id: spec.path for sound_id, spec in SOUNDS.items()} == {
        SoundId.NAVIGATE: "assets/sounds/ui/hover.mp3",
        SoundId.CONFIRM: "assets/sounds/ui/click.mp3",
        SoundId.BACK: "assets/sounds/ui/click.mp3",
        SoundId.DENIED: "assets/sounds/ui/errors_and_warnings.mp3",
    }
    assert all(spec.category is AudioCategory.UI for spec in SOUNDS.values())


# --- the transport -------------------------------------------------------


class _UnpluggedDeviceSound:
    """A decoded cue whose device disappeared before it could be played.

    ``pygame.mixer.Sound`` is a C type whose ``play`` cannot be patched, so the
    failure is injected at the factory instead.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.volume = 1.0

    def set_volume(self, volume: float) -> None:
        self.volume = volume

    def play(self) -> None:
        raise pygame.error("audio device disconnected")


def test_a_missing_asset_is_remembered_instead_of_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CI case: no ``assets/`` at all, and the press must not retry."""
    monkeypatch.setitem(
        SOUNDS, SoundId.NAVIGATE, SoundSpec(AudioCategory.UI, "assets/sounds/ui/absent.mp3")
    )
    bus = AudioBus()
    bus.initialize()

    bus.on_ui_feedback(UiFeedback(UiEffect.NAVIGATED))
    bus.on_ui_feedback(UiFeedback(UiEffect.NAVIGATED))

    assert bus.available is True
    assert SoundId.NAVIGATE not in bus._sounds
    assert SoundId.NAVIGATE in bus._unavailable


def test_a_bus_that_never_started_plays_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never initialized: silent, and still safe to call every frame."""

    def no_mixer() -> None:
        raise pygame.error("mixer not initialized")

    monkeypatch.setattr(pygame.mixer, "Sound", no_mixer)
    bus = AudioBus()

    bus.on_ui_feedback(UiFeedback(UiEffect.CONFIRMED))

    assert bus.available is False


def test_a_failing_playback_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """A device unplugged mid-game costs the cue, not the frame."""
    monkeypatch.setattr(pygame.mixer, "Sound", _UnpluggedDeviceSound)
    bus = AudioBus()
    bus.initialize()

    bus.on_ui_feedback(UiFeedback(UiEffect.CONFIRMED))

    assert SoundId.CONFIRM in bus._unavailable


# --- volumes -------------------------------------------------------------


def test_volumes_are_per_category_and_clamped() -> None:
    bus = AudioBus()
    bus.initialize()

    bus.set_volume(AudioCategory.UI, 0.25)
    bus.set_volume(AudioCategory.MUSIC, 2.0)
    bus.set_volume(AudioCategory.SFX, -1.0)

    assert bus.volume(AudioCategory.UI) == 0.25
    assert bus.volume(AudioCategory.MUSIC) == 1.0
    assert bus.volume(AudioCategory.SFX) == 0.0
    # One category is not another: muting the music must not mute the menus.
    assert bus.volume(AudioCategory.UI) == 0.25


def test_a_zero_volume_is_the_mute() -> None:
    bus = AudioBus()
    bus.initialize()
    bus.set_volume(AudioCategory.UI, 0.0)

    bus.play(SoundId.NAVIGATE)

    assert bus.volume(AudioCategory.UI) == 0.0


def test_initialize_is_idempotent() -> None:
    bus = AudioBus()

    bus.initialize()
    bus.initialize()

    assert bus.available is True


# --- the subscription ----------------------------------------------------


def test_the_bus_answers_the_interface_and_the_simulation() -> None:
    """One channel: the interface facts and the milestones it was built for."""
    bus = AudioBus()
    events = EventBus()
    bus.attach(events)
    bus.initialize()
    seen: list[SoundId] = []
    monkey = AudioBus()
    monkey.attach(events)
    monkey.play = seen.append  # type: ignore[method-assign]

    events.emit(UiFeedback(UiEffect.NAVIGATED))
    events.emit(UiFeedback(UiEffect.CONFIRMED))
    events.emit(UiFeedback(UiEffect.DISMISSED))
    events.emit(LevelStarted(level_id=0))
    events.emit(PlayerDied(entity_id="p", deaths=0))
    events.emit(LevelCompleted(level_id=0))

    assert seen == [SoundId.NAVIGATE, SoundId.CONFIRM, SoundId.BACK]


def test_attaching_twice_does_not_double_a_sound() -> None:
    """A second ``attach`` would play every cue twice; the bus is attached once.

    Cheap to state, expensive to discover: the duplicate is inaudible as a bug
    report and obvious as a doubled click.
    """
    bus = AudioBus()
    events = EventBus()
    bus.attach(events)
    bus.attach(events)
    bus.initialize()
    played: list[SoundId] = []
    bus.play = played.append  # type: ignore[method-assign]

    events.emit(UiFeedback(UiEffect.CONFIRMED))

    assert played == [SoundId.CONFIRM]
