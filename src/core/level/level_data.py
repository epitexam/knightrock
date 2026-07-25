"""
Data structures for parsed TMX level data.
"""

from dataclasses import dataclass, field
from typing import Optional

import pygame
import pytmx


@dataclass
class TileLayerData:
    """Represents a single tile layer with its tiles."""
    name: str
    tiles: list[tuple[int, int, pygame.Surface]]


@dataclass
class ObjectData:
    """Represents a single object from an object layer."""
    name: str
    x: float
    y: float
    width: float
    height: float
    gid: Optional[int]
    image: Optional[pygame.Surface]
    points: Optional[list[tuple[float, float]]]
    properties: dict


@dataclass
class ObjectLayerData:
    """Represents an object layer containing multiple objects."""
    name: str
    objects: list[ObjectData]


@dataclass
class LevelConfig:
    """Configuration metadata extracted from the special 'Data' layer."""
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
    def from_tmx(cls, tmx_map) -> "LevelData":
        """
        Build a LevelData instance from a pytmx TiledMap.

        Args:
            tmx_map: The loaded TMX map object.

        Returns:
            A fully populated LevelData object.
        """
        tile_layers: dict[str, TileLayerData] = {}
        object_layers: dict[str, ObjectLayerData] = {}
        config = LevelConfig()

        for layer in tmx_map.layers:
            if isinstance(layer, pytmx.TiledTileLayer):
                tile_layers[layer.name] = TileLayerData(
                    name=layer.name, tiles=list(layer.tiles())
                )
            elif isinstance(layer, pytmx.TiledObjectGroup):
                objects = [_object_from_tmx(obj) for obj in layer]
                object_layers[layer.name] = ObjectLayerData(
                    name=layer.name, objects=objects
                )
                if layer.name == "Data" and objects:
                    config = _config_from_properties(objects[0].properties)

        return cls(
            width=tmx_map.width,
            height=tmx_map.height,
            tile_size=tmx_map.tilewidth,
            tile_layers=tile_layers,
            object_layers=object_layers,
            config=config,
        )


def _object_from_tmx(obj) -> ObjectData:
    """Convert a pytmx object to our ObjectData structure."""
    raw_points = getattr(obj, "points", None)
    points = [(float(px), float(py))
              for px, py in raw_points] if raw_points else None
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
    return LevelConfig(
        bg=str(props.get("bg", "")),
        top_limit=float(props.get("top_limit", 0)),
        bottom_limit=float(props.get("bottom_limit", 0)),
        horizon_line=float(props.get("horizon_line", 0)),
        death_border_bottom=float(props.get("death_border_bottom", 0)),
        level_unlock=int(props.get("level_unlock", 0)),
    )
