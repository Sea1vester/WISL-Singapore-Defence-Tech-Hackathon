# Drone Flight Simulator / Log Visualizer (C++/OpenGL)

A lightweight C++ 3D environment for visualizing UAV flight paths (from PX4
`.ulg` logs) over terrain, with a free-fly camera and GPS-anchored world
coordinates.

## What's here

| Requirement                          | Where it's implemented |
|---------------------------------------|--------------------------|
| C++ rendering environment             | `CMakeLists.txt`, GLFW (window/input) + GLEW (OpenGL loader) + GLM (math) |
| Lightweight 3D world + camera controls| `src/Camera.h/.cpp` — free-fly WASD+mouse camera, plus an orbit "follow" mode |
| Terrain / topo map import             | `src/Terrain.h/.cpp` — loads a grayscale PGM heightmap, or falls back to procedural terrain |
| UAV model + coordinate system         | `src/UAV.h/.cpp` — procedural quadcopter mesh, pose = position + yaw/pitch/roll |
| GPS → 3D mapping                      | `src/GeoUtils.h/.cpp` — WGS84 lat/lon/alt → local ENU meters → OpenGL world space |

`src/FlightPath.h/.cpp` ties it together: it loads a CSV trajectory (the
kind you can export from the earlier Python `.ulg` parser) and plays it back,
moving the UAV model and drawing its trail.

## Build

Dependencies (Ubuntu/Debian):
```bash
sudo apt install cmake libglfw3-dev libglew-dev libglm-dev libgl-dev
```
macOS: `brew install cmake glfw glew glm`
Windows: use vcpkg (`vcpkg install glfw3 glew glm`) and point CMake at the toolchain file.

Build:
```bash
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j
./drone_sim [flightpath.csv] [heightmap.pgm]
```
Both arguments are optional — with none given it looks for
`assets/flightpath.csv` and `assets/heightmap.pgm`, and falls back to a
demo circular orbit / procedural terrain if either is missing. This repo
ships small example files for both so `./drone_sim` works out of the box.

This was built and compiled successfully in a headless Linux container
(g++ 13, CMake 3.28) but **hasn't been run visually** since that container
has no display/GPU — you'll need a machine with a windowing system and
OpenGL 3.3+ to actually see it render. If anything doesn't compile on your
setup, it's most likely a dependency version/path issue — the code itself
built clean here.

## Controls

- `W A S D` — move camera
- `Space` / `Left Ctrl` — up / down
- Mouse — look around (click into the window; `Esc` toggles cursor capture)
- Scroll — zoom (FOV)
- `F` — toggle follow-cam (auto-orbits the UAV)
- `P` — play/pause flight path playback
- `R` — restart playback
- `Q` — quit

## Getting real data in

### 1. Flight path (from a `.ulg` log)
Use the earlier `ulg_3d_flightpath.py` script's `load_trajectory()` output
and export it to CSV:
```python
import numpy as np
traj, _ = load_trajectory("your_log.ulg")
np.savetxt("assets/flightpath.csv",
           np.column_stack([traj["t_sec"], traj["north"], traj["east"], traj["up"]]),
           header="t_sec,north,east,up", delimiter=",", comments="")
```
(A `lat,lon,alt` CSV header form is also supported — see `FlightPath.h`.)

### 2. Terrain (from a real DEM / topo map)
Convert a GeoTIFF/DEM (e.g. SRTM) to a grayscale PGM heightmap:
```bash
gdal_translate -of PGM -ot Byte -scale input_dem.tif assets/heightmap.pgm
```
or in Python:
```python
from PIL import Image
Image.fromarray(dem_array).convert("L").save("assets/heightmap.pgm")
```
Set `g_geoOrigin` in `main.cpp` to the lat/lon/alt that should map to world
`(0,0,0)` — typically the DEM tile's center or the flight's takeoff point —
so the terrain and flight path line up correctly.

## Coordinate system notes

- GPS (WGS84) → local East-North-Up (ENU) meters via an equirectangular
  projection anchored at `GeoOrigin` (accurate to well under 1% for
  flight areas up to tens of km across — see `GeoUtils.cpp`).
- ENU → OpenGL world space: `X = East, Y = Up, Z = -North` (right-handed,
  Y-up). This is a convention choice — flip it if you'd rather match a
  different tool's axes.

## Known limitations / natural next steps

- Terrain uses a single fixed LOD grid (no chunking/streaming) — fine up to
  a few hundred meters/side at high res, but a real topo dataset covering
  many km would want tiling.
- UAV orientation composition (yaw→pitch→roll) is a simplified Euler chain,
  fine for visualization but not flight-dynamics-accurate; swap in
  quaternions from the log's `vehicle_attitude` topic for exact orientation.
- No shadows/skybox/atmospheric scattering yet — flat directional lighting only.
- PGM is intentionally simple (no external image lib needed); swap in
  `stb_image.h` if you want direct PNG/JPG heightmap loading.
