"""
Data structures for parsed TMX level data.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import pygame
import pytmx

from src.core.settings import World

logger = logging.getLogger(__name__)

#: The object layer that carries a level's settings rather than its world. It
#: is hidden in Tiled as a matter of course, so it is read either way.
DATA_LAYER_NAME = "Data"


class LevelDataError(ValueError):
    """A map cannot be read as the level this game plays.

    A ``ValueError`` because it is a bad value in a file the game was handed,
    and because ``LevelManager`` re-raises pytmx's own failures under a
    ``ValueError`` for the same reason: the fatal screen already reports those.
    """


@dataclass
class TileLayerData:
    """Represents a single tile layer with its tiles."""

    name: str
    tiles: list[tuple[int, int, pygame.Surface]]


@dataclass
class ObjectData:
    """Represents a single object from an object layer.

    ``gid`` is the tile id the TMX object refers to, remapped by pytmx from
    the tileset's own numbering into global ids -- a ``gid="229"`` in the file
    arrives here as 92. It is carried through and not read: image objects are
    loaded by path, and nothing in the world builder resolves tiles by gid. It
    stays so the field is here when something does.
    """

    name: str
    x: float
    y: float
    width: float
    height: float
    gid: int | None
    image: pygame.Surface | None
    points: list[tuple[float, float]] | None
    properties: dict


@dataclass
class ObjectLayerData:
    """Represents an object layer containing multiple objects."""

    name: str
    objects: list[ObjectData]


@dataclass
class LevelConfig:
    """Configuration metadata extracted from the special 'Data' layer.

    The three limits are parsed from the TMX properties the level files
    actually carry (every one of them sets all three) and are not read yet:
    they are shaped for level bounds -- a kill plane at the bottom, a ceiling
    at the top, a horizon for the background -- which has no consumer yet.
    Their siblings are all read, which is what makes the absence visible:
    ``bg`` by the renderer, ``death_border_bottom`` by the respawn system,
    ``level_unlock`` by the notification system. The data stays because the
    data is deliberate; a dead field and an abandoned design look identical
    from here, and only the level files can tell them apart.
    """

    bg: str = ""
    top_limit: float = 0.0
    bottom_limit: float = 0.0
    horizon_line: float = 0.0
    death_border_bottom: float = 0.0
    level_unlock: int = 0


@dataclass
class LevelData:
    """
    Complete parsed representation of a TMX level.

    Contains tile layers, object layers, and configuration metadata.
    """

    width: int
    height: int
    tile_size: int
    tile_layers: dict[str, TileLayerData] = field(default_factory=dict)
    object_layers: dict[str, ObjectLayerData] = field(default_factory=dict)
    config: LevelConfig = field(default_factory=LevelConfig)

    @property
    def pixel_width(self) -> float:
        """Total width of the level in pixels."""
        return self.width * self.tile_size

    @property
    def pixel_height(self) -> float:
        """Total height of the level in pixels."""
        return self.height * self.tile_size

    @classmethod
    def from_tmx(cls, tmx_map: Any) -> LevelData:
        """
        Build a LevelData instance from a pytmx TiledMap.

        A layer the designer hid in Tiled is skipped, with one exception: the
        ``Data`` layer is the level's settings carrier and is routinely hidden
        to keep it out of the editor, so it is read either way. Dropping the
        config along with the visibility flag would silently take the level's
        kill plane and its unlock with it.

        Args:
            tmx_map: The loaded TMX map object.

        Returns:
            A fully populated LevelData object.
        """
        tile_layers: dict[str, TileLayerData] = {}
        object_layers: dict[str, ObjectLayerData] = {}
        config = LevelConfig()

        for layer in tmx_map.layers:
            if not getattr(layer, "visible", True) and layer.name != DATA_LAYER_NAME:
                logger.warning(
                    "'%s' is hidden in Tiled, so it is not built: it is neither "
                    "drawn nor collided with",
                    layer.name,
                )
                continue
            if isinstance(layer, pytmx.TiledTileLayer):
                tile_layers[layer.name] = TileLayerData(name=layer.name, tiles=list(layer.tiles()))
            elif isinstance(layer, pytmx.TiledObjectGroup):
                objects = [_object_from_tmx(obj) for obj in layer]
                object_layers[layer.name] = ObjectLayerData(name=layer.name, objects=objects)
                if layer.name == DATA_LAYER_NAME and objects:
                    config = _config_from_properties(objects[0].properties)

        tile_size = tmx_map.tilewidth
        if tile_size != World.TILE_SIZE:
            raise LevelDataError(
                f"map tiles are {tile_size}px, the world is built on "
                f"{World.TILE_SIZE}px. Every placement in the builder multiplies "
                "by the world's size, so the camera, the tile index and the "
                "sprites would disagree about where anything is."
            )

        return cls(
            width=tmx_map.width,
            height=tmx_map.height,
            tile_size=tile_size,
            tile_layers=tile_layers,
            object_layers=object_layers,
            config=config,
        )


def _object_from_tmx(obj: Any) -> ObjectData:
    """Convert a pytmx object to our ObjectData structure."""
    raw_points = getattr(obj, "points", None)
    points = [(float(px), float(py)) for px, py in raw_points] if raw_points else None
    return ObjectData(
        name=obj.name or "",
        x=obj.x,
        y=obj.y,
        width=obj.width or 0.0,
        height=obj.height or 0.0,
        gid=getattr(obj, "gid", None),
        image=getattr(obj, "image", None),
        points=points,
        properties=dict(obj.properties or {}),
    )


def _config_from_properties(props: dict) -> LevelConfig:
    """Extract LevelConfig from the properties of the first Data object."""
    # pytmx reads an empty ``<property value=""/>`` as None, so a designer who
    # clears the background gets ``str(None)`` -- the literal string "None" --
    # rather than the "" the field is documented to default to. Preserving the
    # sentinel here is what lets the renderer tell "no background" apart from
    # a colour somebody typed.
    bg = props.get("bg", "")
    return LevelConfig(
        bg="" if bg is None else str(bg),
        top_limit=float(props.get("top_limit", 0)),
        bottom_limit=float(props.get("bottom_limit", 0)),
        horizon_line=float(props.get("horizon_line", 0)),
        death_border_bottom=float(props.get("death_border_bottom", 0)),
        level_unlock=int(props.get("level_unlock", 0)),
    )
