"""Benchmark spatial index vs brute-force polygon queries."""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from region import load_config
from indexing.build_index import build_index, load_index, query_point


def _brute_query(x: float, y: float, gdf: gpd.GeoDataFrame) -> list[dict]:
    pt = Point(x, y)
    hits = []
    for i, row in gdf.iterrows():
        if row.geometry is not None and row.geometry.contains(pt):
            hits.append({"id": i, "layer": row.get("layer", "unknown")})
    return hits


def benchmark(config_path: str | Path | None = None, n_queries: int = 100, seed: int = 0) -> dict:
    cfg = load_config(config_path)
    build_index(config_path)
    spatial_idx, gdf = load_index(config_path)

    min_x, min_y, max_x, max_y = cfg.bbox_xy()
    rng = random.Random(seed)
    points = [(rng.uniform(min_x, max_x), rng.uniform(min_y, max_y)) for _ in range(n_queries)]

    t0 = time.perf_counter()
    indexed_results = [query_point(x, y, spatial_idx, gdf) for x, y in points]
    indexed_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    brute_results = [_brute_query(x, y, gdf) for x, y in points]
    brute_time = time.perf_counter() - t0

    # Verify agreement
    mismatches = sum(1 for a, b in zip(indexed_results, brute_results) if len(a) != len(b))
    speedup = brute_time / indexed_time if indexed_time > 0 else float("inf")

    report = {
        "n_queries": n_queries,
        "indexed_time_s": indexed_time,
        "brute_time_s": brute_time,
        "speedup": speedup,
        "mismatches": mismatches,
    }

    print(f"Spatial index benchmark ({n_queries} queries):")
    print(f"  Indexed:  {indexed_time:.4f}s")
    print(f"  Brute:    {brute_time:.4f}s")
    print(f"  Speedup:  {speedup:.1f}x")
    print(f"  Mismatches: {mismatches}")

    out = cfg.processed_dir / f"index_benchmark_{cfg.name}.txt"
    with open(out, "w") as f:
        for k, v in report.items():
            f.write(f"{k}: {v}\n")
    return report


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    benchmark(n_queries=n)
