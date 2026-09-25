import test from 'node:test';
import assert from 'node:assert/strict';
import {createStreamingTabletop,terrainChunks,nearbyMapChunks} from '../public/tabletop-stream.mjs';
import {tabletopBounds} from '../public/tabletop-context.mjs';
const bounds={west:0,south:0,east:3,north:3};
const region={bounds,elevation:{bounds,columns:2,rows:2,heights:[10,11,12,13]},chunks:[{id:'center',url:'center',bounds:{west:1,south:1,east:2,north:2}},{id:'outside',url:'outside',bounds:{west:4,south:4,east:5,north:5}}]};
const viewer={scene:{requestRender(){}}};
const pause=()=>Promise.resolve();

test('terrain partitions cover the expanded view once, with the central chunk first',()=>{
 const chunks=terrainChunks(bounds);
 assert.equal(chunks.length,9);
 assert.deepEqual(chunks[0].bounds,{west:1,south:1,east:2,north:2});
 assert.equal(new Set(chunks.map(c=>`${c.row}/${c.col}`)).size,9);
 assert.equal(chunks.reduce((sum,c)=>sum+(c.bounds.east-c.bounds.west)*(c.bounds.north-c.bounds.south),0),9);
 assert.deepEqual(nearbyMapChunks(region.chunks,bounds).map(c=>c.id),['center']);
 const data={bounds:{west:-10,east:10,south:-10,north:10}};
 const point={lon:0,lat:0}, expanded=tabletopBounds(data,[point]);
 const oldWidth=340/111320;
 assert.ok(Math.abs((expanded.east-expanded.west)*(expanded.north-expanded.south)/oldWidth**2-9)<1e-8);
});

test('replay gets an immediate base while unavailable map chunks leave usable terrain',async()=>{
 const configs=[],progress=[];
 const stream=createStreamingTabletop(viewer,region,{yieldFrame:pause,fetchChunk:async()=>{throw new Error('offline');},render(v,d,o){configs.push(o);return {setVisible(){},destroy(){}};},onProgress:p=>progress.push(p)});
 assert.equal(configs.length,1);
 assert.equal(configs[0].resolution,2);
 assert.ok(configs[0].heightAt(1.5,1.5)<Math.min(...region.elevation.heights));
 await stream.ready;
 assert.equal(configs.length,10);
 assert.equal(progress.at(-1).terrain,9);
 assert.equal(progress.at(-1).failed,1);
 assert.equal(progress.at(-1).complete,true);
 stream.destroy();
});

test('switching missions cancels pending work and prevents stale geometry or progress',async()=>{
 let release;
 const gate=new Promise(resolve=>{release=resolve;});
 let renders=0,disposals=0,updates=0;
 const stream=createStreamingTabletop(viewer,region,{yieldFrame:()=>gate,render(){renders++;return {setVisible(){},destroy(){disposals++;}};},onProgress(){updates++;}});
 stream.destroy();stream.destroy();release();await stream.ready;
 assert.equal(renders,1);assert.equal(disposals,1);assert.equal(updates,0);
});

test('map details wait for terrain GPU readiness rather than geometry submission',async()=>{
 const releases=[];
 let fetched=0;
 const stream=createStreamingTabletop(viewer,region,{yieldFrame:pause,fetchChunk:async()=>{fetched++;return {elements:[]};},render(v,d,o){
  return {ready:o.features===false&&o.resolution!==2?new Promise(resolve=>releases.push(resolve)):Promise.resolve(true),setVisible(){},destroy(){}};
 }});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(releases.length,9);
 assert.equal(fetched,0);
 releases.forEach(resolve=>resolve(true));
 await stream.ready;
 assert.equal(fetched,1);
 stream.destroy();
});

test('mode visibility applies to later arriving chunks as well as the base',async()=>{
 const configs=[],visibility=[];
 const stream=createStreamingTabletop(viewer,region,{yieldFrame:pause,fetchChunk:async()=>({elements:[]}),render(v,d,o){configs.push(o);return {setVisible:value=>visibility.push(value),destroy(){}};}});
 stream.setVisible(false);await stream.ready;
 assert.deepEqual(visibility,[false]);
 assert.ok(configs.slice(1).every(o=>o.show===false));
 assert.equal(configs.filter(o=>o.terrain===false).length,1);
 stream.destroy();
});
