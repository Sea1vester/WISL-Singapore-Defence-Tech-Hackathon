import { createTabletop } from './tabletop.mjs?v=stream-25';

export function intersects(a,b) {
  return a.west<=b.east&&a.east>=b.west&&a.south<=b.north&&a.north>=b.south;
}
export function terrainChunks(bounds) {
  const chunks=[];
  for(let row=0;row<3;row++) for(let col=0;col<3;col++) {
    chunks.push({row,col,distance:Math.hypot(row-1,col-1),bounds:{
      west:bounds.west+(bounds.east-bounds.west)*col/3,
      east:bounds.west+(bounds.east-bounds.west)*(col+1)/3,
      south:bounds.south+(bounds.north-bounds.south)*row/3,
      north:bounds.south+(bounds.north-bounds.south)*(row+1)/3,
    }});
  }
  return chunks.sort((a,b)=>a.distance-b.distance);
}
export function nearbyMapChunks(chunks,bounds) {
  const cx=(bounds.west+bounds.east)/2,cy=(bounds.south+bounds.north)/2;
  const distance=c=>Math.hypot(((c.bounds.west+c.bounds.east)/2-cx)*Math.cos(cy*Math.PI/180),(c.bounds.south+c.bounds.north)/2-cy);
  return chunks.filter(c=>intersects(c.bounds,bounds)).sort((a,b)=>distance(a)-distance(b));
}
export function createTabletopCache(viewer,options={}) {
  const entries=new Map(),create=options.create||createStreamingTabletop;
  let active=null,notify=null;
  const dispose=key=>{
    const entry=entries.get(key);
    if(!entry)return;
    if(active===entry)active=null;
    entry.part.destroy();entries.delete(key);
  };
  return {
    get size(){return entries.size;},
    activate(data,onProgress){
      const key=JSON.stringify([data.name,data.bounds]);
      if(active&&active.key!==key){
        if(!active.progress?.complete||active.progress.failed)dispose(active.key);
        else active.part.setVisible(false);
      }
      if(entries.get(key)?.progress?.failed)dispose(key);
      notify=onProgress;
      let entry=entries.get(key);
      if(!entry){
        entry={key,progress:null,part:null};entries.set(key,entry);active=entry;
        entry.part=create(viewer,data,{bounds:data.bounds,onProgress:progress=>{
          entry.progress=progress;if(active===entry)notify?.(progress);
        }});
      }
      active=entry;entries.delete(key);entries.set(key,entry);
      entry.part.setVisible(true);
      if(entry.progress)notify?.(entry.progress);
      while(entries.size>2)dispose(entries.keys().next().value);
      return entry.part;
    },
    deactivate(){
      if(!active)return;
      if(!active.progress?.complete||active.progress.failed)dispose(active.key);
      else{active.part.setVisible(false);active=null;}
    },
    destroy(){for(const key of entries.keys())dispose(key);},
  };
}

const yieldFrame=()=>new Promise(resolve=>requestAnimationFrame(()=>setTimeout(resolve,0)));

/** A low-resolution base is immediate; cancellable work streams around it. */
export function createStreamingTabletop(viewer,data,options={}) {
  const render=options.render||createTabletop;
  const pause=options.yieldFrame||yieldFrame;
  const fetchChunk=options.fetchChunk|| (async (chunk,signal)=>{
    const response=await fetch(chunk.url,{signal});
    if(!response.ok) throw new Error(`Map chunk ${response.status}`);
    return response.json();
  });
  const bounds=options.bounds||data.bounds;
  const controller=new AbortController(),parts=[];
  let destroyed=false,visible=options.show!==false,mapOverlay=false;
  const terrain=terrainChunks(bounds),maps=nearbyMapChunks(data.chunks||[],bounds);
  const progress={terrain:0,terrainTotal:terrain.length,map:0,mapTotal:maps.length,failed:0,complete:false};
  const update=()=>{if(!destroyed) options.onProgress?.({...progress});};
  const add=(source,config)=>{
    if(destroyed)return;
    const part=render(viewer,source,{...config,show:visible,mapOverlay});
    part.setMapOverlay?.(mapOverlay);
    parts.push(part);
    viewer.scene.requestRender();
    return part;
  };
  // The low-detail underlay sits just below the detailed surface to avoid z-fighting.
  const heights=(data.elevation?.heights||[]).filter(Number.isFinite);
  const baseHeight=(heights.length?Math.min(...heights):0)-8;
  add(data,{bounds,features:false,seams:false,edges:false,resolution:2,
    heightAt:()=>baseHeight});
  async function loadTerrain() {
    const pending=[];
    for(const chunk of terrain){
      await pause();
      if(destroyed)return;
      const part=add(data,{bounds:chunk.bounds,features:false,seams:false,edges:false,resolution:chunk.distance===0?32:18});
      pending.push(Promise.resolve(part.ready).then(rendered=>{
        if(destroyed)return;
        if(rendered===false)progress.failed++;
        progress.terrain++;update();
      }));
    }
    await Promise.all(pending);
  }
  async function loadMap() {
    const pending=[];
    for(const chunk of maps) {
      await pause();
      if(destroyed)return;
      let timeout;
      const timed=new AbortController();
      const abort=()=>timed.abort();
      controller.signal.addEventListener('abort',abort,{once:true});
      timeout=setTimeout(abort,5000);
      try{
        const content=await fetchChunk(chunk,timed.signal);
        if(destroyed)return;
        const part=add({...data,elements:content.elements},{bounds,terrain:false,seams:false,edges:false});
        pending.push(Promise.resolve(part.ready).then(rendered=>{
          if(destroyed)return;
          if(rendered===false)progress.failed++;
          progress.map++;update();
        }));
      }catch(error){if(destroyed)return;progress.failed++;update();}
      finally {clearTimeout(timeout);controller.signal.removeEventListener('abort',abort);}
    }
    await Promise.all(pending);
  }
  const terrainReady=loadTerrain();
  const ready=Promise.allSettled([terrainReady,terrainReady.then(()=>{if(!destroyed)return loadMap();})]).then(results=>{
    if(!destroyed){
      progress.failed+=results.filter(r=>r.status==='rejected').length;
      progress.complete=true;update();
    }
  });
  return {
    ready,
    get show(){return visible;},
    set show(value){this.setVisible(value);},
    setVisible(value){visible=Boolean(value);for(const part of parts)part.setVisible(visible);},
    setMapOverlay(value){mapOverlay=Boolean(value);for(const part of parts)part.setMapOverlay?.(mapOverlay);},
    destroy(){
      if(destroyed)return;
      destroyed=true;controller.abort();for(const part of parts)part.destroy();parts.length=0;
    },
  };
}
