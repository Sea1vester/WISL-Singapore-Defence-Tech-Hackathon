import { elevationHeightAt } from './tabletop.mjs?v=tabletop-3';

export function containsPoint(bounds, lon, lat) {
  return Number.isFinite(lon) && Number.isFinite(lat) && lon >= bounds.west && lon <= bounds.east && lat >= bounds.south && lat <= bounds.north;
}
export function routeContext(atlas, samples) {
  return atlas.find(data => samples.length && samples.every(p => containsPoint(data.bounds, p.lon, p.lat))) || null;
}
export function atlasHeight(atlas, lon, lat) {
  const data = atlas.find(item => containsPoint(item.bounds, lon, lat));
  return data ? elevationHeightAt(data.elevation, lon, lat) : 0;
}
export function tabletopBounds(data, samples) {
  const lat = samples.reduce((sum,p)=>sum+p.lat,0)/samples.length;
  const dy=170/111320, dx=dy/Math.max(0.05,Math.cos(lat*Math.PI/180));
  return {
    west:Math.max(data.bounds.west,Math.min(...samples.map(p=>p.lon))-dx),
    east:Math.min(data.bounds.east,Math.max(...samples.map(p=>p.lon))+dx),
    south:Math.max(data.bounds.south,Math.min(...samples.map(p=>p.lat))-dy),
    north:Math.min(data.bounds.north,Math.max(...samples.map(p=>p.lat))+dy),
  };
}
export async function loadTabletopAtlas() {
  const files=['stonehenge','shropshire','north-wales'];
  const results=await Promise.allSettled(files.map(async name=>{
    const response=await fetch(`./assets/tabletop-${name}.json`,{signal:AbortSignal.timeout(4500)});
    if(!response.ok) throw new Error('Map cache unavailable');
    return response.json();
  }));
  return results.filter(result=>result.status==='fulfilled').map(result=>result.value);
}

export function createCachedTerrain(C, atlas) {
  const tilingScheme=new C.GeographicTilingScheme();
  const size=32;
  return new C.CustomHeightmapTerrainProvider({
    tilingScheme,width:size,height:size,
    credit:new C.Credit('Terrain: Esri World Elevation'),
    callback(x,y,level){
      const rectangle=tilingScheme.tileXYToRectangle(x,y,level);
      const data=new Float32Array(size*size);
      for(let row=0;row<size;row++) for(let col=0;col<size;col++) {
        const lon=C.Math.toDegrees(rectangle.west+(rectangle.east-rectangle.west)*col/(size-1));
        const lat=C.Math.toDegrees(rectangle.north-(rectangle.north-rectangle.south)*row/(size-1));
        data[row*size+col]=atlasHeight(atlas,lon,lat);
      }
      return data;
    },
  });
}

export function createTabletopFinish(viewer,C) {
  // A restrained screen-space focus band applies only to the 3D scene, never text/UI.
  // Facet colors carry the lighting; this adds lens softness and fine painted-surface grain.
  return viewer.scene.postProcessStages.add(new C.PostProcessStage({
    name:'wisl-tabletop-finish',
    uniforms:{pixel:()=>new C.Cartesian2(1/viewer.canvas.width,1/viewer.canvas.height)},
    fragmentShader:`uniform sampler2D colorTexture;
      uniform vec2 pixel;
      in vec2 v_textureCoordinates;
      void main(){
        vec2 uv=v_textureCoordinates;
        float edge=smoothstep(0.20,0.49,abs(uv.y-0.48));
        vec2 radius=pixel*(edge*2.4);
        vec3 color=texture(colorTexture,uv).rgb*0.40;
        color+=texture(colorTexture,uv+vec2(radius.x,radius.y)).rgb*0.15;
        color+=texture(colorTexture,uv+vec2(-radius.x,radius.y)).rgb*0.15;
        color+=texture(colorTexture,uv+vec2(radius.x,-radius.y)).rgb*0.15;
        color+=texture(colorTexture,uv-radius).rgb*0.15;
        float grain=fract(sin(dot(gl_FragCoord.xy,vec2(12.9898,78.233)))*43758.5453)-0.5;
        float vignette=1.0-0.14*smoothstep(0.28,0.75,length(uv-0.5));
        out_FragColor=vec4(color*vignette+grain*0.006,1.0);
      }`,
  }));
}
