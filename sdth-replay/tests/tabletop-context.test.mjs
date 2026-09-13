import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {routeContext,atlasHeight,tabletopBounds} from '../public/tabletop-context.mjs';
const atlas=await Promise.all(['stonehenge','shropshire','north-wales'].map(async name=>JSON.parse(await readFile(new URL(`../public/assets/tabletop-${name}.json`,import.meta.url),'utf8'))));

test('cached terrain grids contain finite real elevations and preserve source attribution',()=>{
  for(const data of atlas){
    const {rows,columns,heights}=data.elevation;
    assert.equal(heights.length,rows*columns);
    assert.ok(heights.every(Number.isFinite));
    assert.ok(Math.max(...heights)-Math.min(...heights)>10);
    assert.match(data.source.map,/OpenStreetMap/);
    assert.match(data.source.elevation,/Esri/);
    assert.ok(data.elements.every(e=>Number.isSafeInteger(e.id)&&Array.isArray(e.geometry)));
  }
});

test('a route crossing cache bounds does not claim full terrain coverage',()=>{
  const data=atlas[0],{west,east,south,north}=data.bounds;
  const center={lon:(west+east)/2,lat:(south+north)/2};
  assert.equal(routeContext(atlas,[center]),data);
  assert.equal(routeContext(atlas,[center,{lon:0,lat:0}]),null);
  assert.equal(routeContext(atlas,[]),null);
  assert.equal(atlasHeight(atlas,0,0),0);
  assert.ok(atlasHeight(atlas,center.lon,center.lat)>70);
  const table=tabletopBounds(data,[center]);
  assert.ok(table.west>=west&&table.east<=east&&table.south>=south&&table.north<=north);
  assert.ok(table.west<center.lon&&table.east>center.lon);
});
