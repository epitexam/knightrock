"""Sound loading and playback: the only module that touches ``pygame.mixer``.

This system is a **consumer, and nothing else**. It never asks *who* did
something, never imports the input router, the menu model, the scenes or the
views, and holds no UI state. It is handed facts on the
:class:`~src.application.events.EventBus` and answers them with a sound:

* :class:`UiFeedback` — an interface interaction a screen actually performed;
* ``LevelStarted`` / ``PlayerDied`` / ``LevelCompleted`` — the simulation
  milestones the bus was built for, and which this bus was the fourth intended
  subscriber of.

``cue_for`` is the whole policy, as a pure function of the effect alone. That
is the only place a fact becomes a sound, so a cue cannot depend on *how* the
player did it, and the input layer cannot grow a second opinion about it.

Degradation is a feature, not a fallback. ``assets/`` is git-ignored, so a
checkout without assets, a CI runner, and a machine with no sound card all land
here: the mixer may refuse to start and a file may be missing or undecodable.
Neither raises. The cue is dropped, a warning is logged once, and the game runs
silent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

import pygame

from src.application.events import (
    EventBus,
    LevelCompleted,
    LevelStarted,
    PlayerDied,
    UiEffect,
    UiFeedback,
)
from src.core.paths import resource_path
from src.core.settings import Audio as AudioSettings

logger = logging.getLogger(__name__)

__all__ = [
    "SOUNDS",
    "AudioBus",
    "AudioCategory",
    "SoundId",
    "SoundSpec",
    "cue_for",
]


class AudioCategory(StrEnum):
    """Volume buckets.

    Only ``UI`` carries sounds for now. ``SFX`` and ``MUSIC`` exist because a
    cue is routed through a category anyway, so adding those sounds later is a
    table entry rather than an API change.
    """

    UI = "ui"
    SFX = "sfx"
    MUSIC = "music"


class SoundId(StrEnum):
    """What a sound *means*, never which file it is.

    Naming the cue rather than the asset is what lets ``hover.mp3`` become the
    navigation sound without a single producer learning about it.
    """

    NAVIGATE = "navigate"
    CONFIRM = "confirm"
    BACK = "back"
    #: Reserved for a refused action (a locked level, a rejected value). It has
    #: no trigger yet: wiring it to the locked levels of the level select needs
    #: ``MenuModel.activate`` to tell "refused" from "no target", and a cue with
    #: no trigger is cheaper than a guess at the wrong moment.
    DENIED = "denied"


@dataclass(frozen=True)
class SoundSpec:
    """Where a cue lives and which volume bucket it answers to."""

    category: AudioCategory
    path: str


#: The single home of the cue -> file mapping. ``assets/sounds/ui`` holds the
#: interface sounds; ``assets/sounds/music`` is the (still empty) home of the
#: per-scene tracks.
SOUNDS: dict[SoundId, SoundSpec] = {
    SoundId.NAVIGATE: SoundSpec(AudioCategory.UI, "assets/sounds/ui/hover.mp3"),
    SoundId.CONFIRM: SoundSpec(AudioCategory.UI, "assets/sounds/ui/click.mp3"),
    SoundId.BACK: SoundSpec(AudioCategory.UI, "assets/sounds/ui/click.mp3"),
    SoundId.DENIED: SoundSpec(AudioCategory.UI, "assets/sounds/ui/errors_and_warnings.mp3"),
}

#: The interface policy: what an interaction sounds like. Three branches, and
#: the ``DENIED`` cue is deliberately absent — nothing publishes a refusal yet.
_INTERFACE_CUES: dict[UiEffect, SoundId] = {
    UiEffect.NAVIGATED: SoundId.NAVIGATE,
    UiEffect.CONFIRMED: SoundId.CONFIRM,
    UiEffect.DISMISSED: SoundId.BACK,
}


def cue_for(effect: UiEffect) -> SoundId | None:
    """The cue an interface effect sounds like, or None to stay silent.

    Pure, total over :class:`UiEffect`, and unreachable from anything but an
    event: the audio system has no other entry point, which is what keeps a cue
    from depending on which device, which scene or which key produced it.
    """
    return _INTERFACE_CUES.get(effect)


class AudioBus:
    """Loads, caches and plays the game sounds.

    A bus that never raises: a mixer that will not start, an absent asset, an
    undecodable file and a device unplugged mid-game all end with a cue marked
    unavailable and a warning on the logger.

    The instance is owned by ``Game`` and passed to nothing: it subscribes to
    the event bus itself, so the only line that knows it exists is the one that
    owns it. That is also what lets a test swap in a recording bus.
    """

    def __init__(self) -> None:
        self._sounds: dict[SoundId, pygame.mixer.Sound] = {}
        self._unavailable: set[SoundId] = set()
        self._volumes: dict[AudioCategory, float] = dict.fromkeys(
            AudioCategory, AudioSettings.DEFAULT_VOLUME
        )
        self._mixer_ready = False

    @property
    def available(self) -> bool:
        """Whether the mixer is running and cues can be played."""
        return self._mixer_ready

    def attach(self, events: EventBus) -> None:
        """Subscribe to the facts this bus answers to.

        The gameplay milestones are subscribed as soon as they exist, though no
        sound plays for them yet: ``assets/sounds/`` carries the interface
        sounds only. Wiring the subscription now means the day a ``SFX`` cue
        lands in the table, nothing outside this module changes.
        """
        events.subscribe(UiFeedback, self.on_ui_feedback)
        events.subscribe(LevelStarted, self._on_level_started)
        events.subscribe(PlayerDied, self._on_player_died)
        events.subscribe(LevelCompleted, self._on_level_completed)

    def initialize(self) -> None:
        """Start the mixer and warm the cue cache. Idempotent, never raises.

        Called once from ``Game._initialize`` after ``pygame.init()``, which has
        already opened the mixer with SDL's defaults: there is nothing to
        configure, only to check. The cues are decoded here rather than on the
        first press, because decoding an MP3 during a menu navigation would
        hitch the frame that triggered it.
        """
        if self._mixer_ready:
            return
        if pygame.mixer.get_init() is None:
            try:
                pygame.mixer.init()
            except pygame.error as error:
                logger.warning("Audio mixer unavailable, the game runs silent: %s", error)
                return
        self._mixer_ready = True
        for sound_id in SOUNDS:
            self._load(sound_id)

    def play(self, sound_id: SoundId) -> None:
        """Play a cue, loading it on first use. Silent if it cannot be played."""
        if not self._mixer_ready or sound_id in self._unavailable:
            return
        sound = self._sounds.get(sound_id)
        if sound is None:
            sound = self._load(sound_id)
        if sound is None:
            return
        try:
            sound.play()
        except pygame.error as error:
            logger.warning("Cannot play the %s sound: %s", sound_id.value, error)
            self._unavailable.add(sound_id)

    def set_volume(self, category: AudioCategory, volume: float) -> None:
        """Set a category volume (0..1) and apply it to the cached cues."""
        self._volumes[category] = min(1.0, max(0.0, volume))
        for sound_id, sound in self._sounds.items():
            if SOUNDS[sound_id].category is category:
                sound.set_volume(self._volumes[category])

    def volume(self, category: AudioCategory) -> float:
        """The current volume of a category."""
        return self._volumes[category]

    def on_ui_feedback(self, event: UiFeedback) -> None:
        """Answer an interface interaction the screens actually performed."""
        sound_id = cue_for(event.effect)
        if sound_id is not None:
            self.play(sound_id)

    def _on_level_started(self, event: LevelStarted) -> None:
        """Subscribed for the music of a level; no cue is assigned yet."""

    def _on_player_died(self, event: PlayerDied) -> None:
        """Subscribed for the death cue; no cue is assigned yet."""

    def _on_level_completed(self, event: LevelCompleted) -> None:
        """Subscribed for the completion cue; no cue is assigned yet."""

    def _load(self, sound_id: SoundId) -> pygame.mixer.Sound | None:
        """Decode a cue once, or record it as unavailable and return None.

        A cue that failed is remembered, so a missing file is not re-read (and
        re-logged) on every press of the key that triggers it.
        """
        if sound_id in self._unavailable:
            return None
        spec = SOUNDS[sound_id]
        try:
            sound = pygame.mixer.Sound(resource_path(spec.path))
        except (pygame.error, OSError) as error:
            logger.warning("Sound %s unavailable (%s): %s", spec.path, sound_id.value, error)
            self._unavailable.add(sound_id)
            return None
        sound.set_volume(self._volumes[spec.category])
        self._sounds[sound_id] = sound
        return sound
