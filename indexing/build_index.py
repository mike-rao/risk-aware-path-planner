"""Build rtree spatial index over obstacle and building polygons."""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from rtree import index
from shapely.geometry import Point

from region import load_config
from dem.fetch_obstacles import fetch_obstacles


def _index_base(config_path: str | Path | None = None) -> Path:
    cfg = load_config(config_path)
    return cfg.processed_dir / f"spatial_index_{cfg.name}"


def build_index(config_path: str | Path | None = None, force: bool = False) -> Path:
    """Index building + water polygons for fast point-in-polygon queries."""
    cfg = load_config(config_path)
    idx_base = _index_base(config_path)
    meta_path = Path(str(idx_base) + "_meta.pkl")

    if meta_path.exists() and Path(str(idx_base) + ".idx").exists() and not force:
        print(f"Using cached spatial index: {idx_base}")
        return idx_base

    buildings_path, water_path = fetch_obstacles(config_path)
    buildings = gpd.read_file(buildings_path).to_crs(cfg.crs)
    water = gpd.read_file(water_path).to_crs(cfg.crs)

    frames = []
    if not buildings.empty:
        frames.append(buildings[["geometry"]].assign(layer="building"))
    if not water.empty:
        frames.append(water[["geometry"]].assign(layer="water"))
    combined = (
        gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=cfg.crs)
        if frames
        else gpd.GeoDataFrame(columns=["geometry", "layer"], crs=cfg.crs)
    )

    cfg.processed_dir.mkdir(parents=True, exist_ok=True)
    props = index.Property()
    props.overwrite = True
    spatial_idx = index.Index(str(idx_base), properties=props)

    for i, row in combined.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        spatial_idx.insert(i, geom.bounds)

    spatial_idx.close()

    with open(meta_path, "wb") as f:
        pickle.dump(combined, f)

    print(f"Built spatial index with {len(combined)} features: {idx_base}")
    return idx_base


def load_index(config_path: str | Path | None = None) -> tuple[index.Index, gpd.GeoDataFrame]:
    idx_base = _index_base(config_path)
    meta_path = Path(str(idx_base) + "_meta.pkl")

    if not meta_path.exists():
        build_index(config_path)

    with open(meta_path, "rb") as f:
        gdf = pickle.load(f)

    spatial_idx = index.Index(str(idx_base))
    return spatial_idx, gdf


def query_point(
    x: float, y: float, spatial_idx: index.Index, gdf: gpd.GeoDataFrame
) -> list[dict]:
    """Return features containing point (x, y)."""
    pt = Point(x, y)
    hits = []
    for i in spatial_idx.intersection((x, y, x, y)):
        geom = gdf.iloc[i].geometry
        if geom is not None and geom.contains(pt):
            hits.append({"id": i, "layer": gdf.iloc[i].get("layer", "unknown")})
    return hits


if __name__ == "__main__":
    force = "--force" in sys.argv
    build_index(force=force)
