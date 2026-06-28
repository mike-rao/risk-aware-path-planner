"""Terrain slope cost layer from elevation raster."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio

from region import load_config


def compute_slope_cost(
    dem_path: str | Path,
    output_path: str | Path | None = None,
    config_path: str | Path | None = None,
) -> Path:
    """Gradient magnitude → normalized terrain cost (steeper = higher)."""
    cfg = load_config(config_path)
    out = Path(output_path) if output_path else cfg.processed_dir / f"terrain_cost_{cfg.name}.tif"

    with rasterio.open(dem_path) as src:
        elev = src.read(1).astype(np.float64)
        transform = src.transform
        profile = src.profile.copy()

        # Pixel size in meters (assume square pixels in projected CRS)
        dx = abs(transform.a)
        dy = abs(transform.e)

        gy, gx = np.gradient(elev, dy, dx)
        slope_rad = np.arctan(np.sqrt(gx**2 + gy**2))
        slope_deg = np.degrees(slope_rad)

        # Normalize to [0, 1] with cap at 45°
        cost = np.clip(slope_deg / 45.0, 0.0, 1.0).astype(np.float32)

    profile.update(dtype="float32", nodata=-9999.0)
    cfg.processed_dir.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(cost, 1)

    print(f"Wrote terrain cost: {out}")
    return out
