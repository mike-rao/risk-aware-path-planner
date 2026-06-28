"""Headline comparison: baseline vs risk-aware planners."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

from region import load_config
from costfield.combine import combine_costs
from planning.astar import run_astar
from planning.rrt_star import run_rrt_star
from validation.check_route import check_route
from eval.pareto_sweep import _risk_cost_along_path


def run_comparison(config_path: str | Path | None = None) -> pd.DataFrame:
    cfg = load_config(config_path)
    risk_path = cfg.processed_dir / f"risk_cost_{cfg.name}.tif"

    scenarios = [
        ("baseline_distance", {"w_terrain": 0.0, "w_risk": 0.0, "w_distance": 1.0}),
        ("risk_aware", {"w_terrain": 0.5, "w_risk": 1.0, "w_distance": 0.5}),
    ]

    rows = []
    for label, weights in scenarios:
        cost_path = combine_costs(config_path, weights=weights)

        for algo, runner in [("astar", run_astar), ("rrt_star", run_rrt_star)]:
            plan = runner(cost_path, config_path)
            compliance = check_route(plan.path_xy, config_path, label=f"{label}/{algo}") if plan.success else None
            risk_cost = _risk_cost_along_path(plan.path_xy, risk_path) if plan.success else float("nan")

            row = {
                "scenario": label,
                "algorithm": algo,
                "success": plan.success,
                "distance_m": round(plan.distance_m, 1),
                "risk_cost": round(risk_cost, 2),
                "total_cost": round(plan.total_cost, 2),
                "planning_time_s": round(plan.planning_time_s, 3),
                "compliance": "PASS" if compliance and compliance.passed else "FAIL",
                "violations": len(compliance.violations) if compliance else -1,
            }
            rows.append(row)

            if plan.success:
                route_path = cfg.processed_dir / f"route_{label}_{algo}_{cfg.name}.json"
                with open(route_path, "w") as f:
                    json.dump({"label": f"{label}/{algo}", "path_xy": plan.path_xy, **row}, f)

    df = pd.DataFrame(rows)
    out_csv = cfg.processed_dir / f"comparison_{cfg.name}.csv"
    out_txt = cfg.processed_dir / f"comparison_{cfg.name}.txt"
    df.to_csv(out_csv, index=False)

    with open(out_txt, "w") as f:
        f.write(df.to_string(index=False))
        f.write("\n")

    print("\n=== Comparison Table ===")
    print(df.to_string(index=False))
    print(f"\nSaved: {out_csv}")
    return df


if __name__ == "__main__":
    run_comparison()
