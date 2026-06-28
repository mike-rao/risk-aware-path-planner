# Multi-Objective Risk-Aware Route Planner (Austin, TX)

Plan routes from **The Domain** to **Mount Bonnell** over real terrain, balancing distance, terrain difficulty, and population-density-proxy risk — while treating Lake Austin as a hard no-fly obstacle.

## Architecture

```
configs/austin.yaml  →  region.py (config loader)
        ↓
dem/ (fetch DEM + OSM obstacles → composite raster)
        ↓
costfield/ (terrain + risk + obstacle layers → combined cost)
        ↓
planning/ (A* and RRT* on grid graph)
        ↓
eval/ (Pareto sweep + comparison table)
indexing/ (rtree spatial index + benchmark)
validation/ (compliance rules)
        ↓
viz/ (interactive folium map)
```

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run full pipeline (uses synthetic DEM if no API key)
python run.py all

# Or step by step:
python run.py fetch       # DEM + OSM obstacles
python run.py composite   # merge + hillshade
python run.py cost        # combined cost field
python run.py plan        # A* + RRT*
python run.py pareto      # multi-objective sweep
python run.py index       # spatial index benchmark
python run.py eval        # comparison table
python run.py viz         # outputs/map_austin.html
```

## OpenTopography API Key (optional)

For real USGS 3DEP elevation data instead of the synthetic fallback:

```bash
export OPENTOPOGRAPHY_API_KEY=your_key_here   # free at portal.opentopography.org
python run.py fetch --force
```

## Configuration

All coordinates and weights live in `configs/austin.yaml` — nothing downstream hardcodes Austin. Key settings:

| Setting | Purpose |
|---------|---------|
| `crs: EPSG:32614` | UTM 14N for accurate distance math |
| `weights.w_*` | Terrain / risk / distance tradeoffs |
| `planning.max_slope_deg` | Compliance rule |
| `planning.min_clearance_m` | Minimum distance from obstacles |

## Outputs

| File | Description |
|------|-------------|
| `data/processed/comparison_austin.csv` | Headline results table |
| `data/processed/pareto_austin.png` | Distance vs risk tradeoff curve |
| `outputs/map_austin.html` | Interactive demo map |

## Limitations & Next Steps

- Risk layer is a building-density proxy, not census population data
- Real-time replanning not implemented
- Single Austin corridor tested; config system supports additional regions
- FAA airspace layer not yet integrated (stretch goal in TODO)

## License

MIT
