"""Explicit compliance rules for planned routes."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
from shapely.geometry import Point

from region import load_config


@dataclass
class Violation:
    rule: str
    location_xy: tuple[float, float]
    detail: str


@dataclass
class ComplianceReport:
    passed: bool
    violations: list[Violation] = field(default_factory=list)

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"Compliance: {status} ({len(self.violations)} violations)"]
        for v in self.violations[:10]:
            lines.append(f"  [{v.rule}] ({v.location_xy[0]:.0f}, {v.location_xy[1]:.0f}): {v.detail}")
        if len(self.violations) > 10:
            lines.append(f"  ... and {len(self.violations) - 10} more")
        return "\n".join(lines)


def check_max_slope(
    path_xy: list[tuple[float, float]],
    dem_path: str,
    max_slope_deg: float,
) -> list[Violation]:
    violations = []
    with rasterio.open(dem_path) as src:
        elev_fn = lambda x, y: _sample_raster(src, x, y)
        for i in range(1, len(path_xy)):
            x0, y0 = path_xy[i - 1]
            x1, y1 = path_xy[i]
            seg_len = math.hypot(x1 - x0, y1 - y0)
            if seg_len < 1:
                continue
            e0, e1 = elev_fn(x0, y0), elev_fn(x1, y1)
            slope_deg = math.degrees(math.atan(abs(e1 - e0) / seg_len))
            if slope_deg > max_slope_deg:
                mid = ((x0 + x1) / 2, (y0 + y1) / 2)
                violations.append(
                    Violation("max_slope", mid, f"slope {slope_deg:.1f}° > {max_slope_deg}°")
                )
    return violations


def check_obstacle_clearance(
    path_xy: list[tuple[float, float]],
    water_mask_path: str,
    min_clearance_m: float,
    config_path: str | Path | None = None,
) -> list[Violation]:
    """Minimum clearance from water/no-fly zones only."""
    violations = []
    with rasterio.open(water_mask_path) as src:
        transform = src.transform
        mask = src.read(1)
        cell_size = abs(transform.a)

        for x, y in path_xy:
            col, row = ~transform * (x, y)
            row, col = int(round(row)), int(round(col))
            if 0 <= row < mask.shape[0] and 0 <= col < mask.shape[1]:
                if mask[row, col] > 0:
                    violations.append(
                        Violation("obstacle_intersection", (x, y), "route intersects no-fly zone")
                    )
                    continue

            clearance_cells = int(math.ceil(min_clearance_m / cell_size))
            r0 = max(0, row - clearance_cells)
            r1 = min(mask.shape[0], row + clearance_cells + 1)
            c0 = max(0, col - clearance_cells)
            c1 = min(mask.shape[1], col + clearance_cells + 1)
            if mask[r0:r1, c0:c1].any():
                violations.append(
                    Violation("min_clearance", (x, y), f"within {min_clearance_m}m of no-fly zone")
                )
    return violations


def check_no_fly_zones(
    path_xy: list[tuple[float, float]],
    water_mask_path: str,
) -> list[Violation]:
    """Zero intersection with water / no-fly polygons."""
    violations = []
    with rasterio.open(water_mask_path) as src:
        mask = src.read(1)
        transform = src.transform
        for x, y in path_xy:
            col, row = ~transform * (x, y)
            row, col = int(round(row)), int(round(col))
            if 0 <= row < mask.shape[0] and 0 <= col < mask.shape[1] and mask[row, col] > 0:
                violations.append(
                    Violation("no_fly_zone", (x, y), "route enters no-fly zone (water)")
                )
    return violations


def _sample_raster(src, x: float, y: float) -> float:
    row, col = src.index(x, y)
    if 0 <= row < src.height and 0 <= col < src.width:
        val = src.read(1)[row, col]
        if val != src.nodata:
            return float(val)
    return 0.0
