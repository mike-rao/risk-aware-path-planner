"""Fetch bare-earth DEM via OpenTopography (USGS 3DEP / SRTM)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

from region import ROOT, load_config

OPENTOPO_URL = "https://portal.opentopography.org/API/globaldem"


def dem_cache_path(config_path: str | Path | None = None) -> Path:
    cfg = load_config(config_path)
    demtype = cfg.dem.get("opentopography_demtype", "USGS30m")
    return cfg.raw_dir / f"dem_{cfg.name}_{demtype}.tif"


def fetch_dem(config_path: str | Path | None = None, force: bool = False) -> Path:
    """Download DEM GeoTIFF for config bbox; cache in data/raw/."""
    cfg = load_config(config_path)
    out_path = dem_cache_path(config_path)

    if out_path.exists() and not force:
        print(f"Using cached DEM: {out_path}")
        return out_path

    api_key = os.environ.get("OPENTOPOGRAPHY_API_KEY")
    if not api_key:
        print(
            "OPENTOPOGRAPHY_API_KEY not set — generating synthetic DEM for development.",
            file=sys.stderr,
        )
        from dem.synthetic_dem import generate_synthetic_dem

        return generate_synthetic_dem(config_path)

    params = {
        "demtype": cfg.dem.get("opentopography_demtype", "USGS30m"),
        "south": cfg.bbox["min_lat"],
        "north": cfg.bbox["max_lat"],
        "west": cfg.bbox["min_lon"],
        "east": cfg.bbox["max_lon"],
        "outputFormat": "GTiff",
        "API_Key": api_key,
    }

    cfg.raw_dir.mkdir(parents=True, exist_ok=True)
    print(f"Fetching DEM from OpenTopography ({params['demtype']})...")
    resp = requests.get(OPENTOPO_URL, params=params, timeout=300)
    resp.raise_for_status()

    out_path.write_bytes(resp.content)
    print(f"Saved DEM to {out_path}")
    return out_path


if __name__ == "__main__":
    force = "--force" in sys.argv
    fetch_dem(force=force)
