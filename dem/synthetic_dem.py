"""Synthetic DEM for offline development when no API key is available."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from pyproj import Transformer

from region import load_config


def generate_synthetic_dem(config_path: str | Path | None = None) -> Path:
    """Build a plausible elevation surface with Mount Bonnell peak and Lake Austin low area."""
    cfg = load_config(config_path)
    min_x, min_y, max_x, max_y = cfg.bbox_xy()
    res = float(cfg.dem.get("resolution_m", 30))

    width = max(2, int((max_x - min_x) / res))
    height = max(2, int((max_y - min_y) / res))
    transform = from_bounds(min_x, min_y, max_x, max_y, width, height)

    xs = np.linspace(min_x, max_x, width)
    ys = np.linspace(min_y, max_y, height)
    xx, yy = np.meshgrid(xs, ys)

    dest_x, dest_y = cfg.destination_xy()
    origin_x, origin_y = cfg.origin_xy()

    # Base rolling terrain ~150–220 m AMSL
    elev = 170.0 + 25.0 * np.sin(xx / 2000) * np.cos(yy / 1500)

    # Mount Bonnell prominence near destination
    bonnell = 120.0 * np.exp(-((xx - dest_x) ** 2 + (yy - dest_y) ** 2) / (800.0**2))
    elev += bonnell

    # Lake Austin trough (elongated NW–SE)
    lake_center_x, lake_center_y = cfg.destination.to_xy(cfg.crs)
    lake_center_x += 400
    lake_center_y -= 300
    lake = 40.0 * np.exp(
        -(((xx - lake_center_x) / 1200) ** 2 + ((yy - lake_center_y) / 400) ** 2)
    )
    elev -= lake

    # Gentle rise near Domain (origin)
    domain_bump = 15.0 * np.exp(
        -((xx - origin_x) ** 2 + (yy - origin_y) ** 2) / (1500.0**2)
    )
    elev += domain_bump

    elev = elev.astype(np.float32)

    out_path = cfg.raw_dir / f"dem_{cfg.name}_synthetic.tif"
    cfg.raw_dir.mkdir(parents=True, exist_ok=True)

    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=elev.dtype,
        crs=cfg.crs,
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(elev, 1)

    print(f"Wrote synthetic DEM to {out_path}")
    return out_path


if __name__ == "__main__":
    generate_synthetic_dem()
