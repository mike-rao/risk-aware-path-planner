# TODO: Multi-Objective Risk-Aware Route Planner (Austin, TX)

> Region: Austin, TX. Route pair: The Domain (~30.402, -97.725) → Mount Bonnell / Lake Austin area (~30.329, -97.772).
> Lake Austin is treated as a hard no-fly obstacle; the route crosses real elevation gain toward Mount Bonnell.
> Build order matters — each phase produces something visible/runnable before the next.

---

## Phase 0 — Project Setup

- [ ] Create repo structure:
  ```
  route-planner/
  ├── data/
  │   ├── raw/              # downloaded DEM tiles, OSM extracts
  │   └── processed/        # merged DEM, cost rasters, indices
  ├── dem/                  # DEM fetch + merge tooling
  ├── costfield/            # cost layer construction (terrain, risk, obstacles)
  ├── planning/             # A*, RRT* implementations
  ├── indexing/             # spatial index (rtree/quadtree) + benchmarks
  ├── validation/           # compliance checker
  ├── eval/                 # batch comparison + metrics + Pareto front
  ├── viz/                  # folium/kepler.gl map generation
  ├── configs/              # region configs (bbox, OD pairs, weights)
  └── README.md
  ```
- [ ] Set up Python env: `rasterio`, `geopandas`, `shapely`, `networkx`, `rtree`, `numpy`, `folium`, `requests`, `pyproj`
- [ ] Define `configs/austin.yaml`: bounding box covering Domain → Mount Bonnell corridor, origin/destination coordinates, CRS to standardize on (recommend UTM Zone 14N / EPSG:32614 for accurate distance math, not raw lat/lon)
- [ ] Write a tiny `region.py` config loader so nothing downstream hardcodes Austin's coordinates directly — every script reads from config

---

## Phase 1 — Composite DEM Tool

- [ ] Get OpenTopography API key (free) for USGS 3DEP access
- [ ] Write `dem/fetch_dem.py`: given a bbox from config, request a seamless DEM raster (GeoTIFF) covering the area via OpenTopography's 3DEP endpoint
- [ ] Cache the downloaded raster to `data/raw/` (don't re-fetch on every run)
- [ ] Write `dem/fetch_obstacles.py`: pull building footprints + water bodies (Lake Austin!) for the same bbox via Overpass API (OpenStreetMap)
- [ ] Write `dem/build_composite.py`: reproject DEM to your standard CRS, rasterize building footprints as height additions on top of bare-earth elevation, rasterize water bodies as a separate "hard obstacle" mask
- [ ] Sanity check: load the composite DEM and plot a hillshade — confirm you can visually see Mount Bonnell as a high point and Lake Austin as a flat/masked region
- [ ] Confirm raster resolution is reasonable for your area size (don't pull 1m resolution over a huge bbox — start coarser, e.g. 10-30m, for faster iteration)

---

## Phase 2 — Multi-Dimensional Cost Field

- [ ] Write `costfield/terrain_cost.py`: compute slope from the elevation raster (gradient magnitude), normalize into a cost layer (steeper = more expensive)
- [ ] Write `costfield/obstacle_cost.py`: convert Lake Austin polygon + building footprints into a binary hard-obstacle mask (infinite cost / impassable)
- [ ] Write `costfield/risk_cost.py`: build a population-density-proxy risk layer — simplest version: distance-based falloff from building density (denser building clusters = higher risk if something fails overhead); `[STRETCH]` pull real census block data for population density
- [ ] `[STRETCH]` Write `costfield/airspace_cost.py`: pull FAA airspace data near KAUS, rasterize controlled airspace as a no-fly/high-cost zone if any overlaps your bbox
- [ ] Write `costfield/combine.py`: weighted sum of terrain + risk (+ airspace) layers into one combined cost raster, with hard obstacles (lake, buildings) as infinite cost regardless of weights
- [ ] Make the weights configurable (`w_terrain`, `w_risk`, etc.) via config — this is what Phase 4's Pareto front will sweep over
- [ ] Visualize the combined cost raster as a heatmap — confirm Lake Austin shows as impassable and hilly areas show elevated cost

---

## Phase 3 — Path Planning Algorithms

- [ ] Write `planning/grid_graph.py`: convert the cost raster into a graph (8-connected grid, edge weight = cost between adjacent cells)
- [ ] Implement **A\*** in `planning/astar.py` using `networkx` or hand-rolled with a priority queue — use Euclidean distance as the heuristic
- [ ] Implement **RRT\*** in `planning/rrt_star.py` — sampling-based, operating directly over the cost field (sample points, connect via local cost-aware steering, rewire for optimality)
- [ ] Run both planners on the Domain → Mount Bonnell pair with cost weights all set to "distance only" (terrain/risk weights = 0) — confirm both produce a sane, roughly-shortest route avoiding the lake
- [ ] Re-run with realistic weights — confirm the route now visibly bends around the hill/risk zones rather than charging straight through
- [ ] Benchmark planning time and path cost for both planners on this pair — note tradeoffs (A* likely faster/optimal on a grid; RRT* may explore better in continuous space but less deterministic)
- [ ] `[STRETCH]` Add a third planner (e.g., Dijkstra without heuristic, as a baseline-of-baselines) just to round out the comparison

---

## Phase 4 — Multi-Objective Optimization (Pareto Front)

- [ ] Write `eval/pareto_sweep.py`: run the planner repeatedly across a range of `w_risk` vs `w_distance` weight combinations (e.g., 8-10 points spanning "pure shortest path" to "pure risk avoidance")
- [ ] Log resulting (distance, risk-weighted cost) for each weight setting
- [ ] Plot the Pareto front: distance on X, risk cost on Y, one point per weight setting — should show a clear tradeoff curve, not a single dominant point
- [ ] Pick 2-3 representative points (e.g., "efficient," "balanced," "conservative") and save their routes for the demo map

---

## Phase 5 — Spatial Indexing & Query Layer

- [ ] Write `indexing/build_index.py`: load obstacle/risk polygons into an `rtree` spatial index instead of querying raster/vector data with brute force
- [ ] Write `indexing/benchmark.py`: time obstacle/risk lookups with vs. without the index across a batch of random query points in the bbox
- [ ] Report speedup numbers (this is a small but concrete "I understand spatial data structures" artifact)
- [ ] `[STRETCH]` Hand-roll a simple quadtree as an alternative to `rtree` and compare — better resume signal than just calling a library, since it shows you understand the underlying structure

---

## Phase 6 — Compliance Validation

- [ ] Write `validation/rules.py`: define explicit rules — e.g., max slope/climb-rate along any segment, minimum clearance from hard obstacles, zero intersection with no-fly polygons
- [ ] Write `validation/check_route.py`: given a planned route + the cost/obstacle layers, run every rule and produce a pass/fail report with specific violation locations if any
- [ ] Run the validator against routes from Phase 3 (sanity check: the "pure shortest path, weights=0" route should likely FAIL — e.g., clips the lake or an excessive slope — proving the validator actually catches something)
- [ ] Confirm the risk-aware planned routes from Phase 4 pass cleanly

---

## Phase 7 — Evaluation Harness

- [ ] Write `eval/run_comparison.py`: run shortest-path baseline vs. risk-aware planner on the Domain → Mount Bonnell pair, collect:
  - [ ] Route distance
  - [ ] Risk-weighted cost
  - [ ] Compliance pass/fail (+ violation list)
  - [ ] Planning time
- [ ] Output a clean comparison table (this is your headline result table)
- [ ] `[STRETCH]` Add 1-2 more origin/destination pairs within the same Austin bbox to show the pipeline generalizes beyond one hardcoded route
- [ ] `[STRETCH]` Run the whole pipeline against a second region (e.g., a different bbox) purely to confirm nothing is hardcoded to Austin's specific coordinates

---

## Phase 8 — Visualization

- [ ] Write `viz/make_map.py`: render an interactive `folium` map with — terrain hillshade or elevation tint, Lake Austin + buildings as obstacle overlays, the baseline route and risk-aware route as two distinctly colored lines
- [ ] Add the Pareto-front candidate routes (Phase 4) as a toggle-able layer so you can show the tradeoff family, not just one route
- [ ] Save as a standalone HTML file you can open and demo without rerunning code

---

## Phase 9 — Polish & Writeup

- [ ] README.md: problem framing, architecture diagram, headline comparison table, screenshot of the map, how to reproduce
- [ ] Clean configs so the whole pipeline reruns end-to-end with one command per phase (fetch → cost field → plan → validate → eval → viz)
- [ ] Short "limitations & next steps" section (e.g., real-time replanning not implemented, risk layer is a proxy not real population data, single fixed region tested)

---

## Order-of-Operations Summary (if short on time, cut here)

1. Phases 0–2 (DEM + cost field) are the foundation — can't skip.
2. Phase 3 (planners) is the core deliverable — protect this above all else.
3. Phase 4 (Pareto front) is what makes it "multi-objective" rather than single-path — don't cut, but can be small (5 weight points instead of 10).
4. Phase 5 (spatial indexing) can be minimal — even just `rtree` with a benchmark script is enough; skip the hand-rolled quadtree under time pressure.
5. Phase 6 (compliance) is cheap to build and directly mirrors the JD's language — keep it.
6. Phase 7 (eval table) and Phase 8 (map) are your demo — never cut these.
7. Phase 9 is presentation — do a minimal version even if rushed.
