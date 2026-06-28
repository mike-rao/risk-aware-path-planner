"""Region configuration loader — single source of truth for coordinates and paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "configs" / "austin.yaml"


@dataclass(frozen=True)
class LonLat:
    lon: float
    lat: float
    name: str = ""

    def to_xy(self, crs: str) -> tuple[float, float]:
        transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        return transformer.transform(self.lon, self.lat)


@dataclass
class RegionConfig:
    name: str
    crs: str
    bbox: dict[str, float]
    origin: LonLat
    destination: LonLat
    dem: dict[str, Any]
    paths: dict[str, str]
    weights: dict[str, float]
    planning: dict[str, Any]
    validation: dict[str, float]
    description: str = ""

    @property
    def raw_dir(self) -> Path:
        return ROOT / self.paths["raw_dir"]

    @property
    def processed_dir(self) -> Path:
        return ROOT / self.paths["processed_dir"]

    def bbox_xy(self) -> tuple[float, float, float, float]:
        """Return bbox as (min_x, min_y, max_x, max_y) in project CRS."""
        transformer = Transformer.from_crs("EPSG:4326", self.crs, always_xy=True)
        xs = []
        ys = []
        for lon in (self.bbox["min_lon"], self.bbox["max_lon"]):
            for lat in (self.bbox["min_lat"], self.bbox["max_lat"]):
                x, y = transformer.transform(lon, lat)
                xs.append(x)
                ys.append(y)
        return min(xs), min(ys), max(xs), max(ys)

    def origin_xy(self) -> tuple[float, float]:
        return self.origin.to_xy(self.crs)

    def destination_xy(self) -> tuple[float, float]:
        return self.destination.to_xy(self.crs)

    def infinite_cost(self) -> float:
        return float(self.validation.get("infinite_cost", 1e9))


def load_config(path: str | Path | None = None) -> RegionConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    # origin/destination as LonLat
    origin = LonLat(**raw["origin"])
    destination = LonLat(**raw["destination"])

    return RegionConfig(
        name=raw["name"],
        description=raw.get("description", ""),
        crs=raw["crs"],
        bbox=raw["bbox"],
        origin=origin,
        destination=destination,
        dem=raw["dem"],
        paths=raw["paths"],
        weights=raw["weights"],
        planning=raw["planning"],
        validation=raw.get("validation", {}),
    )
