import { createTabletop, elevationHeightAt } from './tabletop.mjs?v=stream-17';

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
    const part=render(viewer,source,{...config,show:visible});
    part.setMapOverlay?.(mapOverlay);
    parts.push(part);
    viewer.scene.requestRender();
  };
  // The low-detail underlay sits just below the detailed surface to avoid z-fighting.
  add(data,{bounds,features:false,seams:false,edges:false,resolution:10,
    heightAt:(lon,lat)=>elevationHeightAt(data.elevation,lon,lat)-1.5});
  async function loadTerrain() {
    for(const chunk of terrain){
      await pause();
      if(destroyed)return;
      add(data,{bounds:chunk.bounds,features:false,seams:false,edges:false,resolution:chunk.distance===0?32:18});
      progress.terrain++;update();
    }
  }
  async function loadMap() {
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
        add({...data,elements:content.elements},{bounds,terrain:false,seams:false,edges:false});
        progress.map++;
      }catch(error){if(destroyed)return;progress.failed++;}
      finally {clearTimeout(timeout);controller.signal.removeEventListener('abort',abort);}
      update();
    }
  }
  const ready=Promise.allSettled([loadTerrain(),loadMap()]).then(results=>{
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
