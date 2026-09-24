# Tabletop scene data and rendering

The bundled Stonehenge, Shropshire and North Wales caches contain map geometry and ground elevation for the current demo flights. They are map context, independent of the recorded telemetry and detector conclusions.

- **Map footprints:** © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL. Downloaded through the [Overpass API](https://overpass-api.de/api/interpreter), using `out geom` for building, highway, landuse, natural, historic and leisure ways. Each JSON preserves OSM way IDs and its source timestamp. Regional extracts retain ODbL attribution; the extracted database is available in the adjacent JSON files.
- **Elevation:** [Esri World Elevation / Terrain3D](https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer), level 14 LERC tiles (roughly 9.55 projected metres per source pixel). Decoded and resampled to a geographic grid per region (49×49 for the UK caches, 97×97 for the Singapore caches). These are orthometric source heights, not a survey or a precise vertical datum transformation. Exact download timestamps and bounds are stored in each JSON's `source` and `bounds` fields.
- **Display:** Actual horizontal footprints are retained. Structures and stones are extruded at tag-derived heights (explicit `height`, else `building:levels` × 3.0 m plus a 1.5 m roof, else 8 m); building heights are capped at 200 m and stone heights at 6 m. Large or incomplete footprints can be omitted. Roads have illustrative widths. No new obstacles, cities or hills are generated. Aircraft position follows the existing replay convention of recorded altitude rebased above local ground, while telemetry labels continue to show the recorded altitude unchanged. This is not an obstacle-clearance or geodetic measurement tool.
- **Materials:** Cesium primitives use baked face colours for soft, consistent material shading. A screen-space finish adds restrained edge defocus and fine surface grain. Cast shadows are disabled. This is a stylized material treatment, not a full metallic/roughness PBR material stack. The finite slab and modular seams are decorative presentation elements.
- **Coverage:** Region bounds must cover the flight bounds plus at least 700 m on every side so the slab edge stays out of the default camera framing. Flights outside all bundled regional bounds display a clearly labelled flat globe. Cached terrain/map geometry needs no runtime external request; Cesium and the standard OSM raster layer still use network resources. Map providers' attribution remains visible in both modes.

## Regenerate a cache

Install `lerc@4.0.4` in a temporary tool directory (no new application dependency). Save an Overpass `out geom` response as JSON and add a `bounds` object with `west`, `south`, `east`, `north` in WGS84 degrees. Then run from the repository root:

```sh
npm install --prefix /tmp/wisl-terrain-tools lerc@4.0.4 --no-audit --no-fund
NODE_PATH=/tmp/wisl-terrain-tools/node_modules node sdth-replay/scripts/cache-tabletop.cjs /path/to/osm-region.json stonehenge
```

The final argument selects `tabletop-<name>.json`. New names must also be added to `loadTabletopAtlas` in `tabletop-context.mjs`. Keep extracts bounded to the flight areas and verify coverage before replacing the submission caches.

Implementation references: [Cesium custom heightmap terrain](https://cesium.com/learn/cesiumjs/ref-doc/CustomHeightmapTerrainProvider.html), [Cesium post-processing](https://cesium.com/learn/cesiumjs/ref-doc/PostProcessStageLibrary.html).
