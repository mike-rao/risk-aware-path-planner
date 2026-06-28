"""RRT* sampling-based path planner over cost field."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from region import load_config
from planning.grid_graph import GridGraph, build_grid_graph
from planning.astar import PlanResult, _path_distance


@dataclass
class Node:
    x: float
    y: float
    cost_from_root: float = 0.0
    parent: int | None = None


@dataclass
class RRTStar:
    grid: GridGraph
    step_size: float
    max_iter: int
    goal_sample_rate: float
    neighbor_radius: float
    rng: random.Random = field(default_factory=random.Random)

    def _sample(self, goal: tuple[float, float]) -> tuple[float, float]:
        if self.rng.random() < self.goal_sample_rate:
            return goal
        min_x, min_y, max_x, max_y = self._bounds()
        return self.rng.uniform(min_x, max_x), self.rng.uniform(min_y, max_y)

    def _bounds(self) -> tuple[float, float, float, float]:
        t = self.grid.transform
        w, h = self.grid.cost_array.shape[1], self.grid.cost_array.shape[0]
        corners_x = [t.c, t.c + t.a * w, t.c + t.a * w + t.b * h, t.c + t.b * h]
        corners_y = [t.f, t.f + t.e * h, t.f + t.e * h + t.d * w, t.f + t.d * w]
        return min(corners_x), min(corners_y), max(corners_x), max(corners_y)

    def _nearest(self, nodes: list[Node], point: tuple[float, float]) -> int:
        best_i, best_d = 0, float("inf")
        for i, n in enumerate(nodes):
            d = math.hypot(n.x - point[0], n.y - point[1])
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    def _steer(self, from_xy: tuple[float, float], to_xy: tuple[float, float]) -> tuple[float, float]:
        dx, dy = to_xy[0] - from_xy[0], to_xy[1] - from_xy[1]
        dist = math.hypot(dx, dy)
        if dist <= self.step_size:
            return to_xy
        scale = self.step_size / dist
        return from_xy[0] + dx * scale, from_xy[1] + dy * scale

    def _edge_cost(self, a: tuple[float, float], b: tuple[float, float]) -> float:
        """Integrate cost along straight segment by sampling grid."""
        samples = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / (self.grid.cell_size * 0.5)))
        total = 0.0
        for i in range(samples):
            t = i / (samples - 1)
            x = a[0] + t * (b[0] - a[0])
            y = a[1] + t * (b[1] - a[1])
            row, col = self.grid.xy_to_cell(x, y)
            h, w = self.grid.cost_array.shape
            if row < 0 or col < 0 or row >= h or col >= w:
                return self.grid.infinite_cost
            c = self.grid.cost_array[row, col]
            if c >= self.grid.infinite_cost * 0.5:
                return self.grid.infinite_cost
            seg_len = math.hypot(b[0] - a[0], b[1] - a[1]) / samples
            total += c * seg_len
        return total

    def _near(self, nodes: list[Node], point: tuple[float, float]) -> list[int]:
        indices = []
        for i, n in enumerate(nodes):
            if math.hypot(n.x - point[0], n.y - point[1]) <= self.neighbor_radius:
                indices.append(i)
        return indices

    def plan(self, start_xy: tuple[float, float], goal_xy: tuple[float, float]) -> PlanResult:
        t0 = time.perf_counter()
        start_cell = self.grid.nearest_free_cell(*start_xy)
        goal_cell = self.grid.nearest_free_cell(*goal_xy)
        if start_cell is None or goal_cell is None:
            return PlanResult("rrt_star", [], [], float("inf"), 0.0, time.perf_counter() - t0, False, "No free start/goal")

        sx, sy = self.grid.cell_to_xy(*start_cell)
        gx, gy = self.grid.cell_to_xy(*goal_cell)
        nodes = [Node(sx, sy, 0.0, None)]
        goal_threshold = self.step_size * 1.5
        best_goal_idx: int | None = None

        for _ in range(self.max_iter):
            sample = self._sample((gx, gy))
            nearest_i = self._nearest(nodes, sample)
            nearest = nodes[nearest_i]
            new_xy = self._steer((nearest.x, nearest.y), sample)
            edge = self._edge_cost((nearest.x, nearest.y), new_xy)
            if edge >= self.grid.infinite_cost * 0.5:
                continue

            new_cost = nearest.cost_from_root + edge
            new_node = Node(new_xy[0], new_xy[1], new_cost, nearest_i)
            nodes.append(new_node)
            new_i = len(nodes) - 1

            # Rewire neighbors
            for ni in self._near(nodes, new_xy):
                if ni == new_i:
                    continue
                n = nodes[ni]
                alt_edge = self._edge_cost((new_xy[0], new_xy[1]), (n.x, n.y))
                if alt_edge >= self.grid.infinite_cost * 0.5:
                    continue
                alt_cost = new_cost + alt_edge
                if alt_cost < n.cost_from_root:
                    n.parent = new_i
                    n.cost_from_root = alt_cost

            if math.hypot(new_xy[0] - gx, new_xy[1] - gy) < goal_threshold:
                if best_goal_idx is None or new_cost < nodes[best_goal_idx].cost_from_root:
                    best_goal_idx = new_i

        if best_goal_idx is None:
            return PlanResult("rrt_star", [], [], float("inf"), 0.0, time.perf_counter() - t0, False, "No path found")

        path_xy = self._extract_path(nodes, best_goal_idx)
        # Append exact goal
        path_xy.append((gx, gy))
        total_cost = nodes[best_goal_idx].cost_from_root + self._edge_cost(path_xy[-2], path_xy[-1])
        return PlanResult(
            "rrt_star", path_xy, [], total_cost, _path_distance(path_xy),
            time.perf_counter() - t0, True,
        )

    def _extract_path(self, nodes: list[Node], idx: int) -> list[tuple[float, float]]:
        path = []
        while idx is not None:
            n = nodes[idx]
            path.append((n.x, n.y))
            idx = n.parent
        path.reverse()
        return path


def run_rrt_star(
    cost_raster_path: str | Path,
    config_path: str | Path | None = None,
    seed: int = 42,
) -> PlanResult:
    cfg = load_config(config_path)
    grid = build_grid_graph(cost_raster_path, config_path)
    params = cfg.planning.get("rrt_star", {})
    planner = RRTStar(
        grid=grid,
        step_size=float(params.get("step_size_m", 80.0)),
        max_iter=int(params.get("max_iter", 3000)),
        goal_sample_rate=float(params.get("goal_sample_rate", 0.1)),
        neighbor_radius=float(params.get("neighbor_radius_m", 150.0)),
        rng=random.Random(seed),
    )
    return planner.plan(cfg.origin_xy(), cfg.destination_xy())
