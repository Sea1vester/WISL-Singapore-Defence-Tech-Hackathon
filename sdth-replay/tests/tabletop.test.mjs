import test from "node:test";
import assert from "node:assert/strict";
import { elevationHeightAt, featureKind, illustrativeBuildingHeight, illustrativeStoneHeight, lineFromGeometry, lineSegmentsFromGeometry, normalizeBounds, ringFromGeometry } from "../public/tabletop.mjs";

test("normalizes only finite non-wrapping geographic bounds", () => {
  assert.deepEqual(normalizeBounds({ west: 103.8, south: 1.3, east: 103.9, north: 1.4 }), { west: 103.8, south: 1.3, east: 103.9, north: 1.4 });
  assert.equal(normalizeBounds({ west: 2, south: 1, east: 1, north: 3 }), null);
  assert.equal(normalizeBounds({ west: 1, south: 1, east: Infinity, north: 3 }), null);
});

test("rings discard closing duplicate and reject open/invalid polygons", () => {
  const square = [{ lat: 1, lon: 2 }, { lat: 1, lon: 3 }, { lat: 2, lon: 3 }, { lat: 1, lon: 2 }];
  assert.deepEqual(ringFromGeometry(square), [{ lon: 2, lat: 1 }, { lon: 3, lat: 1 }, { lon: 3, lat: 2 }]);
  assert.equal(ringFromGeometry([{ lat: 1, lon: 2 }, { lat: 1, lon: 3 }]), null);
  assert.equal(ringFromGeometry([{ lat: 1, lon: 2 }, { lat: 1, lon: 3 }, { lat: "no", lon: 3 }]), null);
});

test("line geometry requires two real points and respects finite tabletop bounds", () => {
  const bounds = normalizeBounds({ west: 0, south: 0, east: 2, north: 2 });
  assert.deepEqual(lineFromGeometry([{ lon: 0, lat: 0 }, { lon: 1, lat: 1 }, { lon: 9, lat: 9 }], bounds), [{ lon: 0, lat: 0 }, { lon: 1, lat: 1 }, { lon: 2, lat: 2 }]);
  assert.deepEqual(lineSegmentsFromGeometry([{ lon: -2, lat: 1 }, { lon: -1, lat: 1 }, { lon: 1, lat: 1 }, { lon: 4, lat: 1 }, { lon: 1, lat: 1 }], bounds), [[{ lon: 0, lat: 1 }, { lon: 1, lat: 1 }, { lon: 2, lat: 1 }], [{ lon: 2, lat: 1 }, { lon: 1, lat: 1 }]]);
  assert.equal(lineFromGeometry([{ lon: 0, lat: 0 }]), null);
});

test("OSM tags are classified without inventing a feature type", () => {
  assert.equal(featureKind({ building: "yes" }), "building");
  assert.equal(featureKind({ highway: "residential" }), "road");
  assert.equal(featureKind({ natural: "water" }), "water");
  assert.equal(featureKind({ leisure: "park" }), "park");
  assert.equal(featureKind({ natural: "stone" }), "stone");
  assert.equal(featureKind({ historic: "archaeological_site" }), "site");
  assert.equal(featureKind({ amenity: "bench" }), null);
});

test("sampled elevation is bilinear and is safe for malformed grids", () => {
  const grid = { bounds: { west: 0, south: 0, east: 1, north: 1 }, columns: 2, rows: 2, heights: [10, 20, 30, 50] };
  assert.equal(elevationHeightAt(grid, 0.5, 0.5), 27.5);
  assert.equal(elevationHeightAt(grid, 2, 2), 50);
  assert.equal(elevationHeightAt({ columns: 1 }, 0, 0), 0);
  assert.equal(illustrativeStoneHeight({}, 11), 6);
  assert.equal(illustrativeStoneHeight({ height: "30m" }, 1), 6);
});

test("building heights are illustrative, tag-sensitive, and capped for visual scale", () => {
  assert.equal(illustrativeBuildingHeight({ height: "100 m" }), 24);
  assert.equal(illustrativeBuildingHeight({ height: "10 ft" }), 4);
  assert.equal(illustrativeBuildingHeight({ "building:levels": "5" }), 15.5);
  assert.equal(illustrativeBuildingHeight({}), 8);
});
