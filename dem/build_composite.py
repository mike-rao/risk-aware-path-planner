"""Merge DEM with building heights and water obstacle mask."""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features
from rasterio.warp import calculate_default_transform, reproject, Resampling

from region import load_config
from dem.fetch_dem import fetch_dem
from dem.fetch_obstacles import fetch_obstacles


def build_composite(config_path: str | Path | None = None, force: bool = False) -> dict[str, Path]:
    """Reproject DEM, add building heights, rasterize water mask."""
    cfg = load_config(config_path)
    cfg.processed_dir.mkdir(parents=True, exist_ok=True)

    composite_path = cfg.processed_dir / f"composite_dem_{cfg.name}.tif"
    obstacle_path = cfg.processed_dir / f"obstacle_mask_{cfg.name}.tif"
    water_raster_path = cfg.processed_dir / f"water_mask_{cfg.name}.tif"

    if composite_path.exists() and obstacle_path.exists() and water_raster_path.exists() and not force:
        print(f"Using cached composite: {composite_path}")
        return {
            "composite": composite_path,
            "obstacle_mask": obstacle_path,
            "water_mask": water_raster_path,
        }

    dem_path = fetch_dem(config_path, force=force)
    buildings_path, water_geojson_path = fetch_obstacles(config_path, force=force)

    building_height = float(cfg.dem.get("building_height_m", 15.0))

    with rasterio.open(dem_path) as src:
        dem_data = src.read(1).astype(np.float32)
        src_crs = src.crs
        src_transform = src.transform
        src_nodata = src.nodata

        if src_crs and str(src_crs) != cfg.crs:
            min_x, min_y, max_x, max_y = cfg.bbox_xy()
            dst_transform, width, height = calculate_default_transform(
                src_crs, cfg.crs, src.width, src.height,
                left=min_x, bottom=min_y, right=max_x, top=max_y,
            )
            dem_reproj = np.empty((height, width), dtype=np.float32)
            reproject(
                source=dem_data,
                destination=dem_reproj,
                src_transform=src_transform,
                src_crs=src_crs,
                dst_transform=dst_transform,
                dst_crs=cfg.crs,
                resampling=Resampling.bilinear,
                src_nodata=src_nodata,
                dst_nodata=-9999.0,
            )
            dem_data = dem_reproj
            transform = dst_transform
        else:
            transform = src_transform
            height, width = dem_data.shape

    # Load and reproject vector layers
    buildings = gpd.read_file(buildings_path).to_crs(cfg.crs) if buildings_path.exists() else gpd.GeoDataFrame(columns=["geometry"], crs=cfg.crs)
    water = gpd.read_file(water_geojson_path).to_crs(cfg.crs) if water_geojson_path.exists() else gpd.GeoDataFrame(columns=["geometry"], crs=cfg.crs)

    # Rasterize building footprints as height additions
    if not buildings.empty:
        building_shapes = [(geom, 1) for geom in buildings.geometry if geom is not None and not geom.is_empty]
        building_mask = features.rasterize(
            building_shapes,
            out_shape=dem_data.shape,
            transform=transform,
            fill=0,
            dtype=np.uint8,
        )
        dem_data = dem_data + building_mask.astype(np.float32) * building_height

    # Water-only mask for no-fly validation
    water_mask = np.zeros(dem_data.shape, dtype=np.uint8)
    if not water.empty:
        water_shapes = [(geom, 1) for geom in water.geometry if geom is not None and not geom.is_empty]
        water_mask = features.rasterize(
            water_shapes,
            out_shape=dem_data.shape,
            transform=transform,
            fill=0,
            dtype=np.uint8,
        )
        from scipy.ndimage import binary_dilation
        water_mask = binary_dilation(water_mask, iterations=2).astype(np.uint8)

    # Combined obstacle mask (water + buildings) for planning
    obstacle_mask = water_mask.copy()

    # Also mark building footprints as hard obstacles at ground level
    if not buildings.empty:
        building_shapes = [(geom, 1) for geom in buildings.geometry if geom is not None and not geom.is_empty]
        building_obstacle = features.rasterize(
            building_shapes,
            out_shape=dem_data.shape,
            transform=transform,
            fill=0,
            dtype=np.uint8,
        )
        obstacle_mask = np.maximum(obstacle_mask, building_obstacle)

    dem_data = np.where(dem_data == -9999.0, np.nan, dem_data)
    dem_data = np.nan_to_num(dem_data, nan=np.nanmean(dem_data))

    profile = {
        "driver": "GTiff",
        "height": dem_data.shape[0],
        "width": dem_data.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": cfg.crs,
        "transform": transform,
        "nodata": -9999.0,
    }

    with rasterio.open(composite_path, "w", **profile) as dst:
        dst.write(dem_data.astype(np.float32), 1)

    with rasterio.open(obstacle_path, "w", **profile) as dst:
        dst.write(obstacle_mask.astype(np.uint8), 1)

    with rasterio.open(water_raster_path, "w", **profile) as dst:
        dst.write(water_mask.astype(np.uint8), 1)

    print(f"Wrote composite DEM: {composite_path}")
    print(f"Wrote obstacle mask: {obstacle_path}")
    print(f"Wrote water mask: {water_raster_path}")
    return {
        "composite": composite_path,
        "obstacle_mask": obstacle_path,
        "water_mask": water_raster_path,
    }


def plot_hillshade(config_path: str | Path | None = None, output: str | Path | None = None) -> Path:
    """Sanity-check hillshade visualization."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource

    cfg = load_config(config_path)
    paths = build_composite(config_path)
    out = Path(output) if output else cfg.processed_dir / f"hillshade_{cfg.name}.png"

    with rasterio.open(paths["composite"]) as src:
        elev = src.read(1)
        obstacle = rasterio.open(paths["obstacle_mask"]).read(1)

    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.shade(elev, cmap=plt.cm.terrain, vert_exag=2, blend_mode="overlay")

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    axes[0].imshow(rgb, extent=_extent_from_raster(paths["composite"]))
    axes[0].set_title("Composite DEM Hillshade")
    axes[1].imshow(obstacle, cmap="Reds", extent=_extent_from_raster(paths["obstacle_mask"]))
    axes[1].set_title("Obstacle Mask (Lake + Buildings)")
    for ax in axes:
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
    plt.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved hillshade to {out}")
    return out


def _extent_from_raster(path: Path) -> list[float]:
    with rasterio.open(path) as src:
        b = src.bounds
        return [b.left, b.right, b.bottom, b.top]


if __name__ == "__main__":
    force = "--force" in sys.argv
    build_composite(force=force)
    if "--plot" in sys.argv:
        plot_hillshade()
