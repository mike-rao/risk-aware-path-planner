"""Generate interactive folium map with routes and obstacles."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import folium
import geopandas as gpd
from pyproj import Transformer

from region import load_config
from dem.build_composite import build_composite
from dem.fetch_obstacles import fetch_obstacles


def _to_latlon(path_xy: list[tuple[float, float]], crs: str) -> list[list[float]]:
    transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    return [[lat, lon] for lon, lat in (transformer.transform(x, y) for x, y in path_xy)]


def make_map(config_path: str | Path | None = None, output: str | Path | None = None) -> Path:
    cfg = load_config(config_path)
    build_composite(config_path)
    buildings_path, water_path = fetch_obstacles(config_path)

    center = [cfg.origin.lat, cfg.origin.lon]
    m = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")

    # Obstacle overlays (geometry only — OSM attrs break folium JSON)
    if water_path.exists():
        water = gpd.read_file(water_path)[["geometry"]]
        if not water.empty:
            folium.GeoJson(
                json.loads(water.to_json()),
                name="Water (no-fly)",
                style_function=lambda _: {
                    "fillColor": "#1e88e5",
                    "color": "#0d47a1",
                    "weight": 1,
                    "fillOpacity": 0.5,
                },
            ).add_to(m)

    if buildings_path.exists():
        buildings = gpd.read_file(buildings_path)[["geometry"]]
        if not buildings.empty:
            # Downsample for map performance when OSM returns many footprints
            if len(buildings) > 2000:
                buildings = buildings.sample(2000, random_state=0)
            folium.GeoJson(
                json.loads(buildings.to_json()),
                name="Buildings",
                style_function=lambda _: {
                    "fillColor": "#795548",
                    "color": "#4e342e",
                    "weight": 0.5,
                    "fillOpacity": 0.4,
                },
            ).add_to(m)

    # Origin / destination markers
    folium.Marker(
        [cfg.origin.lat, cfg.origin.lon],
        popup=cfg.origin.name,
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(m)
    folium.Marker(
        [cfg.destination.lat, cfg.destination.lon],
        popup=cfg.destination.name,
        icon=folium.Icon(color="red", icon="flag"),
    ).add_to(m)

    # Route layers from processed data
    route_colors = {
        "baseline": "#ff9800",
        "risk_aware": "#4caf50",
        "efficient": "#2196f3",
        "balanced": "#9c27b0",
        "conservative": "#e91e63",
    }

    route_files = sorted(cfg.processed_dir.glob(f"route_*_{cfg.name}.json"))
    pareto_routes = []
    for rf in route_files:
        with open(rf) as f:
            data = json.load(f)
        label = data.get("label", rf.stem)
        path_xy = data.get("path_xy", [])
        if not path_xy:
            continue

        latlon = _to_latlon(path_xy, cfg.crs)
        color_key = label.split("/")[0] if "/" in label else label
        color = route_colors.get(color_key, "#333333")
        show = "baseline" in label or "risk_aware" in label
        layer_name = label

        fg = folium.FeatureGroup(name=layer_name, show=show)
        folium.PolyLine(latlon, color=color, weight=4, opacity=0.8, popup=layer_name).add_to(fg)
        fg.add_to(m)

        if any(tag in label for tag in ("efficient", "balanced", "conservative")):
            pareto_routes.append((label, latlon, color))

    if pareto_routes:
        pareto_fg = folium.FeatureGroup(name="Pareto candidates", show=False)
        for label, latlon, color in pareto_routes:
            folium.PolyLine(latlon, color=color, weight=3, opacity=0.6, dash_array="5", popup=label).add_to(pareto_fg)
        pareto_fg.add_to(m)

    folium.LayerControl().add_to(m)

    out = Path(output) if output else Path("outputs") / f"map_{cfg.name}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out))
    print(f"Saved map: {out}")
    return out


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else None
    make_map(output=out)
