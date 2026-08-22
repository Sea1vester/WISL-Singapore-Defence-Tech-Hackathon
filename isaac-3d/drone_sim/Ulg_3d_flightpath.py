#!/usr/bin/env python3
"""
ulg_3d_flightpath.py

Read a PX4 .ulg (ULog) flight log and produce a 3D visualization of the
drone's flight path.

Usage:
    python3 ulg_3d_flightpath.py path/to/log.ulg [--out-prefix myflight]

Outputs (written next to the script unless --out-dir is given):
    <prefix>_3d_static.png   - static 3D matplotlib plot, colored by altitude
    <prefix>_3d_interactive.html - interactive plotly 3D plot (rotate/zoom in browser)

How it works
-------------
PX4 .ulg files are a binary log of every topic the flight controller
published during flight (attitude, position, battery, RC input, etc.).
This script uses the `pyulog` library to parse the file, then pulls the
best available position source:

  1. `vehicle_local_position` (preferred) - local NED (North-East-Down)
     position in meters, already estimator-fused and smooth. x=North,
     y=East, z=Down (so altitude = -z).

  2. `vehicle_gps_position` (fallback) - raw GPS lat/lon/alt, used if
     local position wasn't logged. Converted to a local East-North-Up
     (ENU) frame in meters using an equirectangular projection anchored
     at the first fix (fine for typical flight-area distances).

Install dependencies first if you haven't:
    pip install pyulog matplotlib plotly --break-system-packages
"""

import argparse
import math
import os
import sys

import numpy as np


def get_dataset(ulog, name, multi_instance=0):
    """Return the pyulog Data object for a given topic name, or None."""
    for d in ulog.data_list:
        if d.name == name and d.multi_id == multi_instance:
            return d
    return None


def load_local_position(ulog):
    """Try to extract a NED trajectory from vehicle_local_position."""
    d = get_dataset(ulog, "vehicle_local_position")
    if d is None:
        return None

    data = d.data
    if not all(k in data for k in ("x", "y", "z", "timestamp")):
        return None

    # Some logs mark validity of the local position estimate
    xy_valid = data.get("xy_valid")
    z_valid = data.get("z_valid")

    t = data["timestamp"]
    x = data["x"]  # North (m)
    y = data["y"]  # East (m)
    z = data["z"]  # Down (m)

    mask = np.ones(len(t), dtype=bool)
    if xy_valid is not None:
        mask &= xy_valid.astype(bool)
    if z_valid is not None:
        mask &= z_valid.astype(bool)

    t, x, y, z = t[mask], x[mask], y[mask], z[mask]
    if len(t) == 0:
        return None

    north = x
    east = y
    up = -z  # altitude above local origin

    return {
        "t": t,
        "north": north,
        "east": east,
        "up": up,
        "source": "vehicle_local_position (NED estimator)",
    }


def load_gps_position(ulog):
    """Fallback: extract a trajectory from vehicle_gps_position (lat/lon/alt)."""
    d = get_dataset(ulog, "vehicle_gps_position")
    if d is None:
        return None

    data = d.data
    required = ("lat", "lon", "alt", "timestamp")
    if not all(k in data for k in required):
        return None

    t = data["timestamp"]
    lat = data["lat"].astype(np.float64) / 1e7   # deg
    lon = data["lon"].astype(np.float64) / 1e7   # deg
    alt = data["alt"].astype(np.float64) / 1e3   # mm -> m (AMSL)

    fix_type = data.get("fix_type")
    mask = np.ones(len(t), dtype=bool)
    if fix_type is not None:
        mask &= fix_type >= 3  # require at least a 3D fix

    t, lat, lon, alt = t[mask], lat[mask], lon[mask], alt[mask]
    if len(t) == 0:
        return None

    lat0, lon0, alt0 = lat[0], lon[0], alt[0]
    lat0_rad = math.radians(lat0)

    R_EARTH = 6371000.0  # m
    east = np.radians(lon - lon0) * R_EARTH * math.cos(lat0_rad)
    north = np.radians(lat - lat0) * R_EARTH
    up = alt - alt0

    return {
        "t": t,
        "north": north,
        "east": east,
        "up": up,
        "source": "vehicle_gps_position (lat/lon/alt, local ENU projection)",
    }


def load_trajectory(ulg_path):
    from pyulog import ULog

    ulog = ULog(ulg_path)

    traj = load_local_position(ulog)
    if traj is None:
        traj = load_gps_position(ulog)
    if traj is None:
        available = sorted({d.name for d in ulog.data_list})
        raise RuntimeError(
            "Could not find usable position data (tried "
            "'vehicle_local_position' and 'vehicle_gps_position').\n"
            "Topics available in this log:\n  " + "\n  ".join(available)
        )

    # Time relative to start, in seconds
    t0 = traj["t"][0]
    traj["t_sec"] = (traj["t"] - t0) / 1e6  # ULog timestamps are in microseconds
    return traj, ulog


def plot_static_3d(traj, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

    north, east, up, t_sec = traj["north"], traj["east"], traj["up"], traj["t_sec"]

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")

    sc = ax.scatter(east, north, up, c=up, cmap="viridis", s=4)
    ax.plot(east, north, up, color="gray", linewidth=0.5, alpha=0.6)

    ax.scatter(east[0], north[0], up[0], color="green", s=80, marker="o", label="Start")
    ax.scatter(east[-1], north[-1], up[-1], color="red", s=80, marker="X", label="End")

    ax.set_xlabel("East (m)")
    ax.set_ylabel("North (m)")
    ax.set_zlabel("Altitude (m)")
    ax.set_title(f"Drone Flight Path (3D)\nSource: {traj['source']}")
    ax.legend()

    cbar = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.1)
    cbar.set_label("Altitude (m)")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_interactive_3d(traj, out_path):
    import plotly.graph_objects as go

    north, east, up, t_sec = traj["north"], traj["east"], traj["up"], traj["t_sec"]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter3d(
            x=east,
            y=north,
            z=up,
            mode="lines+markers",
            marker=dict(size=2, color=t_sec, colorscale="Viridis",
                        colorbar=dict(title="Time (s)")),
            line=dict(color="rgba(100,100,100,0.6)", width=2),
            name="Flight path",
            hovertemplate=(
                "East: %{x:.1f} m<br>"
                "North: %{y:.1f} m<br>"
                "Alt: %{z:.1f} m<br>"
                "t=%{marker.color:.1f}s<extra></extra>"
            ),
        )
    )

    fig.add_trace(
        go.Scatter3d(
            x=[east[0]], y=[north[0]], z=[up[0]],
            mode="markers", marker=dict(size=6, color="green"), name="Start",
        )
    )
    fig.add_trace(
        go.Scatter3d(
            x=[east[-1]], y=[north[-1]], z=[up[-1]],
            mode="markers", marker=dict(size=6, color="red", symbol="x"), name="End",
        )
    )

    fig.update_layout(
        title=f"Drone Flight Path (3D) — Source: {traj['source']}",
        scene=dict(
            xaxis_title="East (m)",
            yaxis_title="North (m)",
            zaxis_title="Altitude (m)",
            aspectmode="data",
        ),
        legend=dict(x=0.02, y=0.98),
        margin=dict(l=0, r=0, t=40, b=0),
    )

    fig.write_html(out_path)


def export_csv(traj, out_path):
    """
    Write a CSV in the exact format drone_sim's FlightPath.h expects:
        t_sec,north,east,up
    Drop the resulting file at drone_sim/assets/flightpath.csv (or pass its
    path as the first CLI arg to the drone_sim executable) to replay this
    real flight in the C++ 3D simulation.
    """
    arr = np.column_stack([traj["t_sec"], traj["north"], traj["east"], traj["up"]])
    np.savetxt(out_path, arr, header="t_sec,north,east,up", delimiter=",", comments="")


def main():
    parser = argparse.ArgumentParser(description="Visualize a PX4 .ulg flight log in 3D.")
    parser.add_argument("ulg_file", help="Path to the .ulg log file")
    parser.add_argument("--out-prefix", default=None,
                         help="Prefix for output files (default: derived from input filename)")
    parser.add_argument("--out-dir", default=".", help="Directory to write output files to")
    parser.add_argument("--csv", action="store_true",
                         help="Also export a flightpath.csv for use with the C++ drone_sim viewer "
                              "(format: t_sec,north,east,up)")
    parser.add_argument("--csv-name", default="flightpath.csv",
                         help="Filename for the CSV export (default: flightpath.csv, matching "
                              "drone_sim's default asset name)")
    args = parser.parse_args()

    if not os.path.isfile(args.ulg_file):
        sys.exit(f"Error: file not found: {args.ulg_file}")

    prefix = args.out_prefix or os.path.splitext(os.path.basename(args.ulg_file))[0]
    os.makedirs(args.out_dir, exist_ok=True)

    print(f"Loading {args.ulg_file} ...")
    traj, ulog = load_trajectory(args.ulg_file)
    print(f"Using position source: {traj['source']}")
    print(f"Number of points: {len(traj['t_sec'])}")
    print(f"Flight duration: {traj['t_sec'][-1]:.1f} s")
    print(f"Max altitude: {traj['up'].max():.1f} m")

    static_path = os.path.join(args.out_dir, f"{prefix}_3d_static.png")
    interactive_path = os.path.join(args.out_dir, f"{prefix}_3d_interactive.html")

    plot_static_3d(traj, static_path)
    print(f"Saved static plot to: {static_path}")

    plot_interactive_3d(traj, interactive_path)
    print(f"Saved interactive plot to: {interactive_path}")

    if args.csv:
        csv_path = os.path.join(args.out_dir, args.csv_name)
        export_csv(traj, csv_path)
        print(f"Saved drone_sim-compatible CSV to: {csv_path}")
        print("Copy/rename this to drone_sim/assets/flightpath.csv to replay it in the 3D sim.")


if __name__ == "__main__":
    main()