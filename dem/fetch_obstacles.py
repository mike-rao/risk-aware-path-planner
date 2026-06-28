"""Fetch building footprints and water bodies from OpenStreetMap via Overpass."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import shape

from region import load_config

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _overpass_query(bbox: dict[str, float]) -> str:
    south, west, north, east = (
        bbox["min_lat"],
        bbox["min_lon"],
        bbox["max_lat"],
        bbox["max_lon"],
    )
    return f"""
    [out:json][timeout:120];
    (
      way["building"]({south},{west},{north},{east});
      relation["building"]({south},{west},{north},{east});
      way["natural"="water"]({south},{west},{north},{east});
      relation["natural"="water"]({south},{west},{north},{east});
      way["water"]({south},{west},{north},{east});
      relation["water"]({south},{west},{north},{east});
    );
    out body;
    >;
    out skel qt;
    """


def _elements_to_geodataframe(elements: list[dict], geom_type: str) -> gpd.GeoDataFrame:
    """Convert Overpass elements with geometry into a GeoDataFrame."""
    nodes = {el["id"]: (el["lon"], el["lat"]) for el in elements if el["type"] == "node"}
    features = []

    for el in elements:
        if el["type"] == "way" and "nodes" in el:
            coords = [nodes[n] for n in el["nodes"] if n in nodes]
            if len(coords) >= 3:
                from shapely.geometry import Polygon

                try:
                    geom = Polygon(coords)
                    if geom.is_valid and not geom.is_empty:
                        features.append({"geometry": geom, "osm_id": el["id"], **el.get("tags", {})})
                except Exception:
                    pass
        elif el["type"] == "relation" and el.get("tags"):
            # Relations need member assembly; skip for minimal implementation
            if "members" in el:
                for mem in el.get("members", []):
                    if mem.get("role") == "outer" and mem.get("type") == "way":
                        pass  # handled via ways above in most cases

    if not features:
        return gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:4326")

    gdf = gpd.GeoDataFrame(features, crs="EPSG:4326")
    return gdf


def fetch_obstacles(config_path: str | Path | None = None, force: bool = False) -> tuple[Path, Path]:
    """Download buildings and water polygons; cache as GeoJSON in data/raw/."""
    cfg = load_config(config_path)
    buildings_path = cfg.raw_dir / f"buildings_{cfg.name}.geojson"
    water_path = cfg.raw_dir / f"water_{cfg.name}.geojson"

    if buildings_path.exists() and water_path.exists() and not force:
        print(f"Using cached obstacles: {buildings_path}, {water_path}")
        return buildings_path, water_path

    cfg.raw_dir.mkdir(parents=True, exist_ok=True)

    try:
        print("Querying Overpass API for buildings and water...")
        resp = requests.post(
            OVERPASS_URL,
            data={"data": _overpass_query(cfg.bbox)},
            timeout=30,
            headers={"User-Agent": "risk-aware-path-planner/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        elements = data.get("elements", [])
        buildings_path, water_path = _parse_overpass_elements(cfg, elements, buildings_path, water_path)
    except (requests.RequestException, json.JSONDecodeError, KeyError) as exc:
        print(f"Overpass fetch failed ({exc}) — using synthetic obstacles.")
        buildings_path, water_path = _write_synthetic_obstacles(cfg, buildings_path, water_path)

    return buildings_path, water_path


def _parse_overpass_elements(
    cfg, elements: list[dict], buildings_path: Path, water_path: Path
) -> tuple[Path, Path]:
    nodes = {el["id"]: (el["lon"], el["lat"]) for el in elements if el["type"] == "node"}
    building_features = []
    water_features = []

    for el in elements:
        if el["type"] != "way" or "nodes" not in el:
            continue
        coords = [nodes[n] for n in el["nodes"] if n in nodes]
        if len(coords) < 3:
            continue
        from shapely.geometry import Polygon

        try:
            geom = Polygon(coords)
            if not geom.is_valid or geom.is_empty:
                continue
        except Exception:
            continue

        tags = el.get("tags", {})
        feat = {"geometry": geom, "osm_id": el["id"], **tags}
        if "building" in tags:
            building_features.append(feat)
        elif tags.get("natural") == "water" or "water" in tags:
            water_features.append(feat)

    buildings = (
        gpd.GeoDataFrame(building_features, crs="EPSG:4326")
        if building_features
        else gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:4326")
    )
    water = (
        gpd.GeoDataFrame(water_features, crs="EPSG:4326")
        if water_features
        else _synthetic_lake_austin(cfg)
    )

    if water.empty:
        water = _synthetic_lake_austin(cfg)

    buildings.to_file(buildings_path, driver="GeoJSON")
    water.to_file(water_path, driver="GeoJSON")
    print(f"Saved {len(buildings)} buildings, {len(water)} water polygons")
    return buildings_path, water_path


def _write_synthetic_obstacles(cfg, buildings_path: Path, water_path: Path) -> tuple[Path, Path]:
    """Minimal synthetic obstacles for offline development."""
    from shapely.geometry import Polygon

    # Cluster of buildings near Domain
    ox, oy = cfg.origin.to_xy(cfg.crs)
    building_polys = []
    for dx, dy in [(-200, 100), (150, -80), (300, 200), (-100, -150)]:
        cx, cy = ox + dx, oy + dy
        building_polys.append(
            Polygon([
                (cx - 40, cy - 40), (cx + 40, cy - 40),
                (cx + 40, cy + 40), (cx - 40, cy + 40),
            ])
        )

    buildings = gpd.GeoDataFrame(
        [{"geometry": p} for p in building_polys], crs=cfg.crs
    ).to_crs("EPSG:4326")
    water = _synthetic_lake_austin(cfg)

    buildings.to_file(buildings_path, driver="GeoJSON")
    water.to_file(water_path, driver="GeoJSON")
    print(f"Saved synthetic obstacles: {len(buildings)} buildings, {len(water)} water polygons")
    return buildings_path, water_path


def _synthetic_lake_austin(cfg) -> gpd.GeoDataFrame:
    """Fallback Lake Austin polygon when OSM fetch is empty."""
    from shapely.geometry import Polygon
    from pyproj import Transformer

    dest_lon, dest_lat = cfg.destination.lon, cfg.destination.lat
    # Elongated lake polygon NW of Mount Bonnell
    offsets = [
        (-0.012, -0.003),
        (-0.008, -0.006),
        (-0.003, -0.007),
        (0.002, -0.005),
        (0.004, -0.002),
        (0.001, 0.001),
        (-0.005, 0.002),
        (-0.010, 0.000),
    ]
    coords = [(dest_lon + dlon, dest_lat + dlat) for dlon, dlat in offsets]
    poly = Polygon(coords)
    return gpd.GeoDataFrame([{"name": "Lake Austin (synthetic)", "geometry": poly}], crs="EPSG:4326")


if __name__ == "__main__":
    force = "--force" in sys.argv
    fetch_obstacles(force=force)
