"""A* path planner on grid graph."""

from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass
from pathlib import Path

from region import load_config
from planning.grid_graph import GridGraph, build_grid_graph


@dataclass
class PlanResult:
    algorithm: str
    path_xy: list[tuple[float, float]]
    path_cells: list[tuple[int, int]]
    total_cost: float
    distance_m: float
    planning_time_s: float
    success: bool
    message: str = ""


def _heuristic(a: tuple[int, int], b: tuple[int, int], cell_size: float) -> float:
    dr, dc = a[0] - b[0], a[1] - b[1]
    return cell_size * math.sqrt(dr * dr + dc * dc)


def astar(
    grid: GridGraph,
    start_xy: tuple[float, float],
    goal_xy: tuple[float, float],
) -> PlanResult:
    t0 = time.perf_counter()
    start = grid.nearest_free_cell(*start_xy)
    goal = grid.nearest_free_cell(*goal_xy)

    if start is None or goal is None:
        return PlanResult("astar", [], [], float("inf"), 0.0, time.perf_counter() - t0, False, "No free start/goal cell")

    g_score: dict[tuple[int, int], float] = {start: 0.0}
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    open_set: list[tuple[float, tuple[int, int]]] = [(0.0, start)]
    closed: set[tuple[int, int]] = set()

    while open_set:
        _, current = heapq.heappop(open_set)
        if current in closed:
            continue
        if current == goal:
            path_cells = _reconstruct(came_from, current)
            path_xy = grid.path_to_xy(path_cells)
            total_cost = g_score[goal]
            dist = _path_distance(path_xy)
            return PlanResult(
                "astar", path_xy, path_cells, total_cost, dist,
                time.perf_counter() - t0, True,
            )
        closed.add(current)

        for neighbor in grid.graph.neighbors(current):
            if neighbor in closed:
                continue
            edge_w = grid.graph[current][neighbor]["weight"]
            tentative = g_score[current] + edge_w
            if tentative < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                f = tentative + _heuristic(neighbor, goal, grid.cell_size)
                heapq.heappush(open_set, (f, neighbor))

    return PlanResult("astar", [], [], float("inf"), 0.0, time.perf_counter() - t0, False, "No path found")


def _reconstruct(came_from: dict, current: tuple[int, int]) -> list[tuple[int, int]]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def _path_distance(path_xy: list[tuple[float, float]]) -> float:
    dist = 0.0
    for i in range(1, len(path_xy)):
        dx = path_xy[i][0] - path_xy[i - 1][0]
        dy = path_xy[i][1] - path_xy[i - 1][1]
        dist += math.hypot(dx, dy)
    return dist


def run_astar(
    cost_raster_path: str | Path,
    config_path: str | Path | None = None,
) -> PlanResult:
    cfg = load_config(config_path)
    grid = build_grid_graph(cost_raster_path, config_path)
    return astar(grid, cfg.origin_xy(), cfg.destination_xy())
