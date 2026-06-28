"""Population-density-proxy risk layer from building density."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features
from scipy.ndimage import distance_transform_edt

from region import load_config


def compute_risk_cost(
    buildings_path: str | Path,
    reference_raster: str | Path,
    output_path: str | Path | None = None,
    config_path: str | Path | None = None,
    falloff_m: float = 500.0,
) -> Path:
    """
    Distance-based falloff from building clusters.
    Denser buildings → higher baseline risk; cost decays with distance.
    """
    cfg = load_config(config_path)
    out = Path(output_path) if output_path else cfg.processed_dir / f"risk_cost_{cfg.name}.tif"

    with rasterio.open(reference_raster) as ref:
        shape = (ref.height, ref.width)
        transform = ref.transform
        profile = ref.profile.copy()

    buildings = gpd.read_file(buildings_path).to_crs(cfg.crs) if Path(buildings_path).exists() else gpd.GeoDataFrame(columns=["geometry"], crs=cfg.crs)

    if buildings.empty:
        risk = np.zeros(shape, dtype=np.float32)
    else:
        building_density = np.zeros(shape, dtype=np.float32)
        shapes = [(geom, 1) for geom in buildings.geometry if geom is not None and not geom.is_empty]
        building_density = features.rasterize(
            shapes, out_shape=shape, transform=transform, fill=0, dtype=np.float32,
        )
        # Smooth density with distance transform from building cells
        inv = 1.0 - np.clip(building_density, 0, 1)
        dist_px = distance_transform_edt(inv)
        pixel_size = abs(transform.a)
        dist_m = dist_px * pixel_size
        risk = np.exp(-dist_m / falloff_m).astype(np.float32)
        # Boost near actual building footprints
        risk = np.maximum(risk, building_density * 0.8)

    # Normalize to [0, 1]
    if risk.max() > 0:
        risk = risk / risk.max()

    profile.update(dtype="float32", nodata=-9999.0)
    cfg.processed_dir.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(risk.astype(np.float32), 1)

    print(f"Wrote risk cost: {out}")
    return out
