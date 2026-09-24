#!/usr/bin/env node
// Pre-warms the local /tiles cache for every region in tabletop-atlas.json.
// Fetches OSM map tiles (z13-18) and Esri satellite tiles (z13-19) through the
// local proxy so both replay map modes work on a LAN-only demo.
const fs = require("node:fs");
const path = require("node:path");

const API_PORT = process.env.API_PORT || 8010;
const BASE = `http://127.0.0.1:${API_PORT}/tiles`;
const SOURCES = [
  { prefix: "", suffix: ".png", minZoom: 13, maxZoom: 18 },
  { prefix: "sat/", suffix: ".jpg", minZoom: 13, maxZoom: 19 },
];
const MAX_TILES = Number(process.env.WARM_MAX_TILES || 30000);
const DELAY_MS = Number(process.env.WARM_TILE_DELAY_MS || 60);

const atlasPath = path.join(__dirname, "..", "public", "assets", "tabletop-atlas.json");
const atlas = JSON.parse(fs.readFileSync(atlasPath, "utf8"));

function lonToX(lon, z) {
  return Math.floor(((lon + 180) / 360) * 2 ** z);
}
function latToY(lat, z) {
  const rad = (lat * Math.PI) / 180;
  return Math.floor(((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * 2 ** z);
}

const tiles = [];
for (const region of atlas.regions || []) {
  const b = region.bounds;
  for (const source of SOURCES) {
    for (let z = source.minZoom; z <= source.maxZoom; z++) {
      const x0 = lonToX(b.west, z);
      const x1 = lonToX(b.east, z);
      const y0 = latToY(b.north, z); // north edge has the smaller y
      const y1 = latToY(b.south, z);
      for (let x = Math.min(x0, x1); x <= Math.max(x0, x1); x++) {
        for (let y = Math.min(y0, y1); y <= Math.max(y0, y1); y++) {
          tiles.push([source, z, x, y]);
        }
      }
    }
  }
}

if (tiles.length > MAX_TILES) {
  console.error(`abort: ${tiles.length} tiles would exceed the ${MAX_TILES} cap`);
  process.exit(1);
}
console.log(`warming ${tiles.length} tiles across ${(atlas.regions || []).length} regions (osm z13-18, sat z13-19)`);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  let bytes = 0;
  let done = 0;
  for (const [source, z, x, y] of tiles) {
    const res = await fetch(`${BASE}/${source.prefix}${z}/${x}/${y}${source.suffix}`);
    if (!res.ok) {
      console.error(`abort: /tiles/${source.prefix}${z}/${x}/${y}${source.suffix} -> HTTP ${res.status}`);
      process.exit(1);
    }
    bytes += (await res.arrayBuffer()).byteLength;
    done += 1;
    if (done % 200 === 0) console.log(`${done}/${tiles.length}`);
    await sleep(DELAY_MS);
  }
  console.log(`done: ${done} tiles, ${(bytes / 1048576).toFixed(1)} MB transferred`);
}

main().catch((err) => {
  console.error(`abort: ${err.message}`);
  process.exit(1);
});
