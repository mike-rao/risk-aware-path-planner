"""Sweep weight combinations to trace Pareto front."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from region import load_config
from costfield.combine import combine_costs
from planning.astar import run_astar, PlanResult
from validation.check_route import check_route


def _risk_cost_along_path(path_xy: list[tuple[float, float]], risk_raster: Path) -> float:
    import rasterio

    total = 0.0
    with rasterio.open(risk_raster) as src:
        risk = src.read(1)
        transform = src.transform
        for i in range(1, len(path_xy)):
            x0, y0 = path_xy[i - 1]
            x1, y1 = path_xy[i]
            seg = np.hypot(x1 - x0, y1 - y0)
            col, row = ~transform * ((x0 + x1) / 2, (y0 + y1) / 2)
            r, c = int(round(row)), int(round(col))
            if 0 <= r < risk.shape[0] and 0 <= c < risk.shape[1]:
                total += risk[r, c] * seg
    return total


def pareto_sweep(
    config_path: str | Path | None = None,
    n_points: int = 8,
) -> Path:
    cfg = load_config(config_path)
    risk_path = cfg.processed_dir / f"risk_cost_{cfg.name}.tif"

    # Ensure risk layer exists
    from costfield.combine import combine_costs as _combine
    from dem.build_composite import build_composite
    from dem.fetch_obstacles import fetch_obstacles
    from costfield.risk_cost import compute_risk_cost

    paths = build_composite(config_path)
    buildings_path, _ = fetch_obstacles(config_path)
    compute_risk_cost(buildings_path, paths["composite"], config_path=config_path)

    results = []
    for i in range(n_points):
        w_risk = i / max(1, n_points - 1)
        w_distance = 1.0 - w_risk
        weights = {"w_terrain": 0.5 * w_risk, "w_risk": w_risk, "w_distance": w_distance}
        cost_path = combine_costs(config_path, weights=weights)
        plan = run_astar(cost_path, config_path)

        if not plan.success:
            continue

        risk_cost = _risk_cost_along_path(plan.path_xy, risk_path)
        compliance = check_route(plan.path_xy, config_path, label=f"w_risk={w_risk:.2f}")

        results.append({
            "w_risk": w_risk,
            "w_distance": w_distance,
            "distance_m": plan.distance_m,
            "risk_cost": risk_cost,
            "total_cost": plan.total_cost,
            "planning_time_s": plan.planning_time_s,
            "compliance_pass": compliance.passed,
            "path_xy": plan.path_xy,
        })

    out_json = cfg.processed_dir / f"pareto_{cfg.name}.json"
    out_png = cfg.processed_dir / f"pareto_{cfg.name}.png"

    # Save routes for representative points
    if results:
        for tag, idx in [("efficient", 0), ("balanced", len(results) // 2), ("conservative", -1)]:
            r = results[idx]
            route_path = cfg.processed_dir / f"route_{tag}_{cfg.name}.json"
            with open(route_path, "w") as f:
                json.dump({"label": tag, "w_risk": r["w_risk"], "path_xy": r["path_xy"]}, f)

    serializable = [{k: v for k, v in r.items() if k != "path_xy"} for r in results]
    with open(out_json, "w") as f:
        json.dump(serializable, f, indent=2)

    if results:
        distances = [r["distance_m"] for r in results]
        risks = [r["risk_cost"] for r in results]
        plt.figure(figsize=(8, 6))
        plt.scatter(distances, risks, c=[r["w_risk"] for r in results], cmap="viridis", s=80)
        plt.colorbar(label="w_risk")
        for r in results:
            plt.annotate(f"{r['w_risk']:.1f}", (r["distance_m"], r["risk_cost"]), fontsize=8)
        plt.xlabel("Route distance (m)")
        plt.ylabel("Risk-weighted cost")
        plt.title("Pareto Front: Distance vs Risk")
        plt.tight_layout()
        plt.savefig(out_png, dpi=150)
        plt.close()
        print(f"Saved Pareto plot: {out_png}")

    print(f"Saved Pareto results: {out_json}")
    return out_json


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    pareto_sweep(n_points=n)
