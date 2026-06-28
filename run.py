#!/usr/bin/env python3
"""End-to-end pipeline runner — one command per phase."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def phase_fetch(args):
    from dem.fetch_dem import fetch_dem
    from dem.fetch_obstacles import fetch_obstacles

    fetch_dem(args.config, force=args.force)
    fetch_obstacles(args.config, force=args.force)


def phase_composite(args):
    from dem.build_composite import build_composite, plot_hillshade

    build_composite(args.config, force=args.force)
    if args.plot:
        plot_hillshade(args.config)


def phase_cost(args):
    from costfield.combine import combine_costs, plot_cost_heatmap

    combine_costs(args.config, force=args.force)
    if args.plot:
        plot_cost_heatmap(args.config)


def phase_plan(args):
    from costfield.combine import combine_costs
    from planning.astar import run_astar
    from planning.rrt_star import run_rrt_star

    cost_path = combine_costs(args.config)
    for name, runner in [("A*", run_astar), ("RRT*", run_rrt_star)]:
        result = runner(cost_path, args.config)
        print(f"{name}: success={result.success}, dist={result.distance_m:.0f}m, time={result.planning_time_s:.2f}s")


def phase_pareto(args):
    from eval.pareto_sweep import pareto_sweep

    pareto_sweep(args.config, n_points=args.points)


def phase_index(args):
    from indexing.build_index import build_index
    from indexing.benchmark import benchmark

    build_index(args.config, force=args.force)
    benchmark(args.config, n_queries=args.queries)


def phase_eval(args):
    from eval.run_comparison import run_comparison

    run_comparison(args.config)


def phase_viz(args):
    from viz.make_map import make_map

    make_map(args.config, output=args.output)


def phase_all(args):
    phase_fetch(args)
    phase_composite(args)
    phase_cost(args)
    phase_plan(args)
    phase_pareto(args)
    phase_index(args)
    phase_eval(args)
    phase_viz(args)


def main():
    parser = argparse.ArgumentParser(description="Risk-aware path planner pipeline")
    parser.add_argument("--config", default=None, help="Path to region config YAML")
    parser.add_argument("--force", action="store_true", help="Re-fetch / rebuild cached data")
    parser.add_argument("--plot", action="store_true", help="Generate plots where applicable")
    parser.add_argument("--points", type=int, default=8, help="Pareto sweep points")
    parser.add_argument("--queries", type=int, default=100, help="Index benchmark queries")
    parser.add_argument("--output", default=None, help="Map output path")

    sub = parser.add_subparsers(dest="phase", required=True)
    for name, fn in [
        ("fetch", phase_fetch),
        ("composite", phase_composite),
        ("cost", phase_cost),
        ("plan", phase_plan),
        ("pareto", phase_pareto),
        ("index", phase_index),
        ("eval", phase_eval),
        ("viz", phase_viz),
        ("all", phase_all),
    ]:
        sub.add_parser(name).set_defaults(func=fn)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
