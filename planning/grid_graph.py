"""Convert cost raster to 8-connected grid graph."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np
import rasterio

from region import load_config


@dataclass
class GridGraph:
    graph: nx.Graph
    cost_array: np.ndarray
    transform: rasterio.Affine
    crs: str
    cell_size: float
    infinite_cost: float
    subsample: int = 1

    def cell_to_xy(self, row: int, col: int) -> tuple[float, float]:
        x, y = rasterio.transform.xy(self.transform, row, col, offset="center")
        return x, y

    def xy_to_cell(self, x: float, y: float) -> tuple[int, int]:
        col, row = ~self.transform * (x, y)
        return int(round(row / self.subsample)), int(round(col / self.subsample))

    def nearest_free_cell(self, x: float, y: float) -> tuple[int, int] | None:
        """Find nearest non-obstacle grid cell to a point."""
        row, col = self.xy_to_cell(x, y)
        h, w = self.cost_array.shape
        row = np.clip(row, 0, h - 1)
        col = np.clip(col, 0, w - 1)

        if self.cost_array[row, col] < self.infinite_cost * 0.5:
            return row, col

        # BFS spiral search
        for radius in range(1, max(h, w)):
            for dr in range(-radius, radius + 1):
                for dc in range(-radius, radius + 1):
                    if abs(dr) != radius and abs(dc) != radius:
                        continue
                    r, c = row + dr, col + dc
                    if 0 <= r < h and 0 <= c < w:
                        if self.cost_array[r, c] < self.infinite_cost * 0.5:
                            return r, c
        return None

    def path_to_xy(self, path: list[tuple[int, int]]) -> list[tuple[float, float]]:
        return [self.cell_to_xy(r, c) for r, c in path]


def build_grid_graph(
    cost_raster_path: str | Path,
    config_path: str | Path | None = None,
    subsample: int | None = None,
) -> GridGraph:
    """Build 8-connected graph from cost raster."""
    cfg = load_config(config_path)
    subsample = subsample or int(cfg.planning.get("astar_subsample", 2))
    inf = cfg.infinite_cost()

    with rasterio.open(cost_raster_path) as src:
        cost_full = src.read(1).astype(np.float64)
        transform = src.transform
        crs = str(src.crs)

    cost = cost_full[::subsample, ::subsample]
    cell_size = abs(transform.a) * subsample
    h, w = cost.shape

    # Scaled transform for subsampled grid
    sub_transform = rasterio.Affine(
        transform.a * subsample, transform.b, transform.c,
        transform.d, transform.e * subsample, transform.f,
    )

    g = nx.Graph()
    neighbors = [
        (-1, 0), (1, 0), (0, -1), (0, 1),
        (-1, -1), (-1, 1), (1, -1), (1, 1),
    ]

    for row in range(h):
        for col in range(w):
            if cost[row, col] >= inf * 0.5:
                continue
            node = (row, col)
            g.add_node(node, cost=cost[row, col])
            for dr, dc in neighbors:
                nr, nc = row + dr, col + dc
                if 0 <= nr < h and 0 <= nc < w:
                    if cost[nr, nc] >= inf * 0.5:
                        continue
                    dist = cell_size * (1.414 if dr != 0 and dc != 0 else 1.0)
                    edge_cost = 0.5 * (cost[row, col] + cost[nr, nc]) * dist
                    g.add_edge(node, (nr, nc), weight=edge_cost)

    return GridGraph(
        graph=g,
        cost_array=cost,
        transform=sub_transform,
        crs=crs,
        cell_size=cell_size,
        infinite_cost=inf,
        subsample=subsample,
    )
