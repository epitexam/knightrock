"""Display geometry and names, read from the SDL pygame already links.

pygame-ce answers ``get_desktop_sizes``: sizes, nothing else. It has no answer
for where a display sits on the virtual desktop, for the area a taskbar leaves
free, or for what the panel is called. Those three are what placing a window on
a chosen screen needs, and all three are available one layer down -- so this
module goes there, through ``ctypes``, into the libSDL2 the pygame extension
already depends on.

Verified on the development machine (pygame-ce 2.5.7, SDL 2.32.10, Wayland):

    pygame      SDL_GetDesktopSizes()      -> [(1920, 1080)]
    SDL_GetDisplayBounds(0)                -> (0, 0, 1920, 1080)
    SDL_GetDisplayUsableBounds(0)          -> (0, 32, 1920, 1048)
    SDL_GetDisplayName(0)                  -> b'eDP-1 17"'

Two guards make reaching for it safe.

The handle has to be the library pygame is *using*. ``find_library`` can hand
back a different libSDL2, and a second SDL's video subsystem is not initialised,
so it answers from nothing. So a probe is cross-checked against pygame's own
numbers -- same display count, same size on display 0 -- and a disagreement
throws the probe away instead of being reported.

Nothing here is required for the game to start. Every entry point answers an
empty tuple when the library cannot be reached, and the caller falls back to
what pygame can say.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pygame

logger = logging.getLogger(__name__)

#: DPI the platform calls 100%, which is the divisor for a display scale.
BASE_DPI = 96.0

#: Refused as implausible rather than trusted as a scale factor. SDL reports
#: garbage on some drivers instead of failing, and a scale of 0 or 300 would
#: either collapse the interface or multiply it into nothing.
MIN_PLAUSIBLE_DPI = 24.0
MAX_PLAUSIBLE_DPI = 960.0


class _SdlRect(ctypes.Structure):
    _fields_ = (
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("w", ctypes.c_int),
        ("h", ctypes.c_int),
    )


class _SdlDisplayMode(ctypes.Structure):
    # The layout SDL 2 has had since 2.0.0: format, width, height, refresh, and
    # a driver-private tail. The tail is what makes guessing wrong loudly.
    _fields_ = (
        ("format", ctypes.c_uint32),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("refresh_rate", ctypes.c_int),
        ("driverdata", ctypes.c_void_p),
    )


@dataclass(frozen=True)
class DisplayGeometry:
    """One display, as SDL describes it.

    ``bounds`` is the panel in virtual-desktop coordinates and may have a
    negative origin -- the leftmost monitor is not at x=0 on a Linux desktop
    whose primary is elsewhere. ``usable`` is ``bounds`` less whatever the
    desktop reserves for panels, and is what a borderless window should fill so
    it does not sit under a taskbar.
    """

    index: int
    name: str
    bounds: tuple[int, int, int, int]
    usable: tuple[int, int, int, int]
    refresh_rate: int
    scale: float

    @property
    def size(self) -> tuple[int, int]:
        return (self.bounds[2], self.bounds[3])

    @property
    def usable_size(self) -> tuple[int, int]:
        return (self.usable[2], self.usable[3])

    @property
    def origin(self) -> tuple[int, int]:
        return (self.bounds[0], self.bounds[1])


class _Bindings:
    """The five calls this module needs, with their signatures pinned."""

    def __init__(self, lib: ctypes.CDLL) -> None:
        lib.SDL_GetNumVideoDisplays.restype = ctypes.c_int
        lib.SDL_GetNumVideoDisplays.argtypes = []
        lib.SDL_GetDisplayBounds.restype = ctypes.c_int
        lib.SDL_GetDisplayBounds.argtypes = [ctypes.c_int, ctypes.POINTER(_SdlRect)]
        lib.SDL_GetDisplayUsableBounds.restype = ctypes.c_int
        lib.SDL_GetDisplayUsableBounds.argtypes = [ctypes.c_int, ctypes.POINTER(_SdlRect)]
        lib.SDL_GetDisplayName.restype = ctypes.c_char_p
        lib.SDL_GetDisplayName.argtypes = [ctypes.c_int]
        lib.SDL_GetDesktopDisplayMode.restype = ctypes.POINTER(_SdlDisplayMode)
        lib.SDL_GetDesktopDisplayMode.argtypes = [ctypes.c_int, ctypes.POINTER(_SdlDisplayMode)]
        # SDL_GetDisplayDPI reports 0 on success and -1 when the platform has no
        # answer, which on SDL 2 includes a Wayland session.
        lib.SDL_GetDisplayDPI.restype = ctypes.c_int
        lib.SDL_GetDisplayDPI.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
        ]
        self.lib = lib

    def display_geometry(self, index: int) -> DisplayGeometry | None:
        bounds, usable = _SdlRect(), _SdlRect()
        # SDL returns 0 on success here, unlike every call it documents as
        # returning a pointer. Testing it for truth reads success as failure.
        if self.lib.SDL_GetDisplayBounds(index, ctypes.byref(bounds)) != 0:
            return None
        self.lib.SDL_GetDisplayUsableBounds(index, ctypes.byref(usable))
        if usable.w <= 0 or usable.h <= 0:
            # A driver that cannot answer is worse than one that answers with
            # the panel: a zero-sized usable area would be what a borderless
            # window is sized from.
            usable = bounds
        name = self.lib.SDL_GetDisplayName(index)
        mode = _SdlDisplayMode()
        # The return value is not the test. SDL returns the pointer it was
        # handed, and ctypes pointer instances do not agree with truthiness --
        # measured here, a call that filled refresh_rate with 60 compared
        # false -- so the mode is checked by its contents instead.
        self.lib.SDL_GetDesktopDisplayMode(index, ctypes.byref(mode))
        refresh = max(0, int(mode.refresh_rate)) if mode.width > 0 and mode.height > 0 else 0
        return DisplayGeometry(
            index=index,
            name=_decode(name),
            bounds=(bounds.x, bounds.y, bounds.w, bounds.h),
            usable=(usable.x, usable.y, usable.w, usable.h),
            refresh_rate=refresh,
            scale=self._scale(index),
        )

    def _scale(self, index: int) -> float:
        """The desktop scale the compositor reports, or 1.0 when it reports none.

        A scale is a *system* preference, so it is worth reading when it exists
        and must never be guessed: SDL answering -1 on a platform that has no
        notion of it means 1.0, and inventing a number there would resize the
        interface on machines that need no resizing.
        """
        ddpi, hdpi, vdpi = ctypes.c_float(), ctypes.c_float(), ctypes.c_float()
        if self.lib.SDL_GetDisplayDPI(
            index, ctypes.byref(ddpi), ctypes.byref(hdpi), ctypes.byref(vdpi)
        ):
            return 1.0
        if not MIN_PLAUSIBLE_DPI <= hdpi.value <= MAX_PLAUSIBLE_DPI:
            return 1.0
        return round(hdpi.value / BASE_DPI, 3)


def _decode(raw: bytes | None) -> str:
    """A display name as text, or empty when SDL had none.

    SDL returns whatever the platform calls the panel, which is not always
    text: on some drivers it is empty, and on some it is a localised string.
    An empty name is carried through rather than invented here, because the
    caller decides what a nameless display is called and needs to know it was
    nameless.
    """
    if not raw:
        return ""
    return raw.decode("utf-8", errors="replace").strip()


#: The bound calls, resolved once. :func:`probe` is re-run on every topology
#: poll, and re-running the search costs ~56ms -- almost all of it the
#: ``ldconfig`` call inside ``find_library`` -- which is a fifth of a 60Hz frame
#: every three quarters of a second. The handle does not change; the displays do.
_bindings_cache: _Bindings | None = None
_bindings_searched = False


def _open(path: str | None) -> Iterator[ctypes.CDLL]:
    """One handle, or nothing.

    Every ``dlopen`` in this module goes through here rather than being called
    directly, and the reason is that any of them can raise for reasons that have
    nothing to do with whether the library is the right one: a file that is not a
    shared object, a pattern that matched something unexpected, a path the loader
    refuses. A generator that raised part way through the search would abort the
    whole search and take the probe down with it, when the only thing that went
    wrong is one candidate out of five.
    """
    if not path:
        return
    try:
        yield ctypes.CDLL(path)
    except OSError as error:
        logger.debug("Not a loadable library: %s (%s)", path, error)


def _libraries() -> Iterator[ctypes.CDLL]:
    """Handles to try, the one pygame uses first.

    Order is the trust order. A display is described by the SDL that owns the
    video subsystem, and only two of these can be that SDL: symbols already
    global in this process, and the library one of pygame's own extensions is
    linked against. The bundled copy is next because auditwheel puts it there.
    ``find_library`` is last and is the one that can find a *different* SDL,
    which is why its answer is cross-checked like any other.
    """
    yield from _open(None)

    for extension in (getattr(pygame, "base", None), pygame.display):
        yield from _open(getattr(extension, "__file__", None))

    root = Path(pygame.__file__).parent
    # Only the SDL2 patterns, and only inside pygame's own two directories. The
    # names are specific enough that nothing else matches, and the directories
    # are the ones the wheel places them in -- this walks the installation, never
    # the filesystem at large.
    for pattern in (
        "../pygame_ce.libs/libSDL2-*",
        "libSDL2*.dll",
        "libSDL2*.dylib",
        "libSDL2*.so*",
    ):
        for path in sorted(root.glob(pattern)):
            yield from _open(str(path.resolve()))

    yield from _open(ctypes.util.find_library("SDL2"))


def _agree_with_pygame(displays: tuple[DisplayGeometry, ...]) -> bool:
    """Whether the probe describes the same displays pygame does.

    The check that earns the whole module its place. A handle to a second
    libSDL2 answers from an uninitialised video subsystem, and what it returns
    is not an error -- it is numbers, plausible ones, describing nothing. Two
    facts catch that: how many displays there are, and how big display 0 is.
    Both come from pygame on the SDL the game is actually running on.
    """
    try:
        sizes = tuple((int(w), int(h)) for w, h in pygame.display.get_desktop_sizes())
    except pygame.error:
        # No video system to compare against. That is not evidence the probe
        # is wrong, and refusing it here would take the probe away from exactly
        # the callers that run before a display exists.
        return True
    if not sizes:
        return True
    return len(displays) == len(sizes) and displays[0].size == sizes[0]


def _bindings() -> _Bindings | None:
    """The bound calls, found on the first call and remembered.

    Cached on *the symbols binding*, not on a display being found. Those are two
    different failures and only one of them is permanent: a probe made before
    ``pygame.init()`` sees zero displays, and caching that as "no libSDL2" would
    leave the game without display geometry for the rest of the session -- the
    one time it can least afford it, because that is the moment it is deciding
    where to put the window.

    Returning ``None`` is cached too. Without that, a platform where the search
    finds nothing -- which is the case where the 56ms matters most, because
    there is no working handle to make it cheap -- pays the whole search on
    every poll.
    """
    global _bindings_cache, _bindings_searched
    if _bindings_searched:
        return _bindings_cache
    _bindings_searched = True
    for lib in _libraries():
        try:
            _bindings_cache = _Bindings(lib)
        except AttributeError as error:
            # The library loaded and is not the SDL we want: no display calls.
            logger.debug("Not an SDL2 with display calls: %s", error)
            continue
        except OSError as error:
            logger.debug("Could not read display calls: %s", error)
            continue
        return _bindings_cache
    logger.debug("No libSDL2 with display calls could be bound; geometry unavailable")
    return None


def probe() -> tuple[DisplayGeometry, ...]:
    """Every display SDL can describe, or empty when it cannot be reached.

    Empty is the honest answer and every caller treats it as "geometry is
    unavailable", which is a state the game already survives: display 0's size
    comes from pygame on its own.

    Needs pygame's video subsystem to be up. Before that SDL reports zero
    displays, which is a refusal rather than a wrong answer, so a caller that
    probes too early gets the degraded path and no exception.
    """
    bindings = _bindings()
    if bindings is None:
        return ()
    count = bindings.lib.SDL_GetNumVideoDisplays()
    if count <= 0:
        return ()
    found = tuple(
        geometry
        for geometry in (bindings.display_geometry(i) for i in range(count))
        if geometry is not None
    )
    if not found:
        return ()
    if not _agree_with_pygame(found):
        logger.warning("SDL reported displays that disagree with pygame; ignoring them")
        return ()
    return found


def is_available() -> bool:
    """Whether display geometry can be read at all.

    A capability question rather than a repeat of :func:`probe`, so the menu can
    say once whether the monitor list is real before it shows one.
    """
    return bool(probe())
