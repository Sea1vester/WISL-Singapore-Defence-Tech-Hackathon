import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {routeContext,atlasHeight,tabletopBounds,observeImagery,imageryStatusText,constrainCameraAboveGround} from '../public/tabletop-context.mjs';
const atlas=await Promise.all(['stonehenge','shropshire','north-wales'].map(async name=>JSON.parse(await readFile(new URL(`../public/assets/tabletop-${name}.json`,import.meta.url),'utf8'))));

test('imagery distinguishes loading, blank placeholders and real tiles',async()=>{
  const updates=[];
  let image={width:1,height:1};
  const provider=observeImagery({requestImage(){return Promise.resolve(image);}},s=>updates.push(s));
  await provider.requestImage(0,0,0);
  assert.deepEqual(updates[0],{pending:1,loaded:0,failed:0});
  assert.deepEqual(updates.at(-1),{pending:0,loaded:0,failed:1});
  assert.match(imageryStatusText('Map',updates.at(-1)),/unavailable/);
  image={width:256,height:256};
  await provider.requestImage(0,0,0);
  assert.deepEqual(updates.at(-1),{pending:0,loaded:1,failed:0});
  assert.match(imageryStatusText('Map',updates.at(-1)),/loaded/);
});

test('imagery preserves Cesium throttling and reports errors but not cancellations',async()=>{
  const updates=[];
  let requestImage=()=>undefined;
  const provider=observeImagery({requestImage(...args){return requestImage(...args);}},s=>updates.push(s));
  assert.equal(provider.requestImage(0,0,0),undefined);
  assert.equal(updates.length,0);
  requestImage=()=>Promise.reject(new Error('offline'));
  await assert.rejects(provider.requestImage(0,0,0),/offline/);
  assert.equal(updates.at(-1).failed,1);
  await assert.rejects(provider.requestImage(0,0,0,{cancelled:true}),/offline/);
  assert.deepEqual(updates.at(-1),{pending:0,loaded:0,failed:0});
  assert.match(imageryStatusText('Satellite',{pending:1,loaded:0,failed:0}),/Loading/);
  assert.match(imageryStatusText('Map',{pending:0,loaded:2,failed:1}),/partly unavailable/);
});

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

test('camera clearance uses cached hills before globe tiles arrive, then the higher rendered terrain',()=>{
 const bounds={west:0,south:0,east:1,north:1};
 const atlas=[{bounds,elevation:{bounds,columns:2,rows:2,heights:[40,40,40,40]}}];
 const position={longitude:0.5,latitude:0.5,height:-10};
 const camera={position:{},positionCartographic:position,worldToCameraCoordinatesPoint(world,local){Object.assign(local,world);position.height=world.height;}};
 let rendered;
 const viewer={camera,scene:{globe:{getHeight:()=>rendered}}};
 const C={Math:{toDegrees:v=>v},Cartesian3:{fromRadians:(longitude,latitude,height)=>({longitude,latitude,height})}};
 assert.equal(constrainCameraAboveGround(viewer,atlas,C),true);
 assert.equal(camera.position.height,43);
 assert.equal(constrainCameraAboveGround(viewer,atlas,C),false);
 rendered=50;
 assert.equal(constrainCameraAboveGround(viewer,atlas,C),true);
 assert.equal(camera.position.height,53);
 position.longitude=5;position.latitude=5;position.height=-20;rendered=undefined;
 assert.equal(constrainCameraAboveGround(viewer,atlas,C),true);
 assert.equal(camera.position.height,3);
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
