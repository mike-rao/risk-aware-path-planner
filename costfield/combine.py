"""Weighted combination of cost layers."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import rasterio
import matplotlib.pyplot as plt

from region import load_config
from dem.build_composite import build_composite
from dem.fetch_obstacles import fetch_obstacles
from costfield.terrain_cost import compute_slope_cost
from costfield.obstacle_cost import compute_obstacle_cost
from costfield.risk_cost import compute_risk_cost


def combine_costs(
    config_path: str | Path | None = None,
    weights: dict[str, float] | None = None,
    force: bool = False,
) -> Path:
    """Weighted sum of terrain + risk + distance baseline; hard obstacles override."""
    cfg = load_config(config_path)
    w = weights or cfg.weights
    w_terrain = float(w.get("w_terrain", 1.0))
    w_risk = float(w.get("w_risk", 1.0))
    w_distance = float(w.get("w_distance", 1.0))
    inf_cost = cfg.infinite_cost()

    out = cfg.processed_dir / f"combined_cost_{cfg.name}.tif"
    suffix = f"_w{w_terrain}_{w_risk}_{w_distance}".replace(".", "p")
    out_weighted = cfg.processed_dir / f"combined_cost_{cfg.name}{suffix}.tif"

    paths = build_composite(config_path, force=force)
    buildings_path, _ = fetch_obstacles(config_path)

    terrain_path = compute_slope_cost(paths["composite"], config_path=config_path)
    obstacle_path = compute_obstacle_cost(paths["obstacle_mask"], config_path=config_path)
    risk_path = compute_risk_cost(buildings_path, paths["composite"], config_path=config_path)

    with rasterio.open(terrain_path) as t_src, rasterio.open(risk_path) as r_src, rasterio.open(obstacle_path) as o_src:
        terrain = t_src.read(1)
        risk = r_src.read(1)
        obstacle = o_src.read(1)
        profile = t_src.profile.copy()

    # Distance baseline: uniform unit cost per cell (normalized later)
    distance = np.ones_like(terrain, dtype=np.float32)

    combined = (
        w_distance * distance
        + w_terrain * terrain
        + w_risk * risk
    ).astype(np.float32)

    # Hard obstacles
    combined = np.where(obstacle >= inf_cost * 0.5, inf_cost, combined)

    profile.update(dtype="float32", nodata=-9999.0)
    cfg.processed_dir.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_weighted, "w", **profile) as dst:
        dst.write(combined, 1)

    # Also write default-named file for downstream scripts
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(combined, 1)

    print(f"Wrote combined cost: {out_weighted}")
    return out_weighted


def plot_cost_heatmap(config_path: str | Path | None = None, output: str | Path | None = None) -> Path:
    cfg = load_config(config_path)
    cost_path = combine_costs(config_path)
    out = Path(output) if output else cfg.processed_dir / f"cost_heatmap_{cfg.name}.png"

    with rasterio.open(cost_path) as src:
        cost = src.read(1)
        cost = np.where(cost >= cfg.infinite_cost() * 0.5, np.nan, cost)
        extent = [src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top]

    plt.figure(figsize=(10, 8))
    plt.imshow(cost, extent=extent, origin="upper", cmap="YlOrRd")
    plt.colorbar(label="Combined cost")
    plt.title("Combined Cost Field")
    plt.xlabel("Easting (m)")
    plt.ylabel("Northing (m)")
    plt.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved cost heatmap: {out}")
    return out


if __name__ == "__main__":
    force = "--force" in sys.argv
    combine_costs(force=force)
    if "--plot" in sys.argv:
        plot_cost_heatmap()
