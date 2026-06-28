"""Run all compliance rules on a planned route."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from region import load_config
from dem.build_composite import build_composite
from validation.rules import (
    ComplianceReport,
    check_max_slope,
    check_no_fly_zones,
    check_obstacle_clearance,
)


def check_route(
    path_xy: list[tuple[float, float]],
    config_path: str | Path | None = None,
    label: str = "route",
) -> ComplianceReport:
    cfg = load_config(config_path)
    paths = build_composite(config_path)
    max_slope = float(cfg.planning.get("max_slope_deg", 25.0))
    min_clearance = float(cfg.planning.get("min_clearance_m", 50.0))

    violations = []
    violations.extend(check_no_fly_zones(path_xy, paths["water_mask"]))
    violations.extend(check_obstacle_clearance(path_xy, paths["water_mask"], min_clearance, config_path))
    violations.extend(check_max_slope(path_xy, paths["composite"], max_slope))

    report = ComplianceReport(passed=len(violations) == 0, violations=violations)
    print(f"\n{label}: {report.summary()}")
    return report


def check_route_file(route_path: str | Path, config_path: str | Path | None = None) -> ComplianceReport:
    with open(route_path) as f:
        data = json.load(f)
    return check_route(data["path_xy"], config_path, label=data.get("label", route_path))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m validation.check_route <route.json>")
        sys.exit(1)
    check_route_file(sys.argv[1])
