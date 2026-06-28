"""Hard obstacle mask as infinite-cost layer."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio

from region import load_config


def compute_obstacle_cost(
    obstacle_mask_path: str | Path,
    output_path: str | Path | None = None,
    config_path: str | Path | None = None,
) -> Path:
    """Binary obstacle mask: 1 = impassable (infinite cost), 0 = free."""
    cfg = load_config(config_path)
    out = Path(output_path) if output_path else cfg.processed_dir / f"obstacle_cost_{cfg.name}.tif"
    inf_cost = cfg.infinite_cost()

    with rasterio.open(obstacle_mask_path) as src:
        mask = src.read(1)
        profile = src.profile.copy()

    cost = np.where(mask > 0, inf_cost, 0.0).astype(np.float32)
    profile.update(dtype="float32", nodata=-9999.0)

    cfg.processed_dir.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(cost, 1)

    print(f"Wrote obstacle cost: {out}")
    return out
