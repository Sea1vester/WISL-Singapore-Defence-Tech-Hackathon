import { elevationHeightAt } from './tabletop.mjs?v=stream-25';

export function observeImagery(provider, onStatus) {
  const requestImage=provider.requestImage;
  const tiles=new Map();
  const emit=()=>{
    const counts={pending:0,loaded:0,failed:0};
    for(const tile of tiles.values()) counts[tile.status]++;
    onStatus(counts);
  };
  provider.requestImage=function(x,y,level,request){
    const result=requestImage.call(this,x,y,level,request);
    if(!result)return result;
    const key=`${level}/${x}/${y}`,tile={status:'pending'};
    tiles.delete(key);tiles.set(key,tile);
    if(tiles.size>256)tiles.delete(tiles.keys().next().value);
    emit();
    return Promise.resolve(result).then(image=>{
      if(tiles.get(key)===tile){
        tile.status=image?.width===1&&image?.height===1?'failed':'loaded';emit();
      }
      return image;
    },error=>{
      if(tiles.get(key)===tile){
        if(request?.cancelled)tiles.delete(key);else tile.status='failed';
        emit();
      }
      throw error;
    });
  };
  return provider;
}

export function imageryStatusText(name, status) {
  if(status.failed)return `${name} imagery ${status.loaded?'partly unavailable':'unavailable'} — retry or use Tabletop. Check the WISL server's network.`;
  if(status.pending||!status.loaded)return `Loading ${name.toLowerCase()} imagery…`;
  return `${name} imagery loaded`;
}

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
export function constrainCameraAboveGround(viewer, atlas, C) {
  const camera=viewer.camera,position=camera.positionCartographic;
  const cached=atlasHeight(atlas,C.Math.toDegrees(position.longitude),C.Math.toDegrees(position.latitude));
  const rendered=viewer.scene.globe.getHeight(position);
  const floor=Math.max(cached,Number.isFinite(rendered)?rendered:cached)+3;
  if(position.height>=floor)return false;
  camera.worldToCameraCoordinatesPoint(C.Cartesian3.fromRadians(position.longitude,position.latitude,floor),camera.position);
  return true;
}

export function tabletopBounds(data, samples) {
  const lat = samples.reduce((sum,p)=>sum+p.lat,0)/samples.length;
  const dy=170/111320, dx=dy/Math.max(0.05,Math.cos(lat*Math.PI/180));
  // Three times the old width and height gives nine times its visible area.
  const west=Math.min(...samples.map(p=>p.lon))-dx, east=Math.max(...samples.map(p=>p.lon))+dx;
  const south=Math.min(...samples.map(p=>p.lat))-dy, north=Math.max(...samples.map(p=>p.lat))+dy;
  const cx=(west+east)/2, cy=(south+north)/2;
  return {
    west:Math.max(data.bounds.west,cx-(east-west)*1.5),
    east:Math.min(data.bounds.east,cx+(east-west)*1.5),
    south:Math.max(data.bounds.south,cy-(north-south)*1.5),
    north:Math.min(data.bounds.north,cy+(north-south)*1.5),
  };
}
export async function loadTabletopAtlas() {
  // Only the elevation/manifest is needed before replay; map geometry streams later.
  try {
    const response=await fetch('./assets/tabletop-atlas.json',{signal:AbortSignal.timeout(4500)});
    if(!response.ok) return [];
    const result=await response.json();
    return Array.isArray(result) ? result : result.regions || [];
  } catch { return []; }
}

export function configureDaytimeAtmosphere(viewer,C) {
  const scene=viewer.scene;
  scene.skyBox=undefined;
  scene.skyAtmosphere ||= new C.SkyAtmosphere(scene.globe.ellipsoid);
  scene.skyAtmosphere.setDynamicLighting(C.DynamicAtmosphereLightingType.NONE);
  scene.skyAtmosphere.saturationShift=-0.25;
  scene.skyAtmosphere.brightnessShift=-0.12;
  scene.skyAtmosphere.perFragmentAtmosphere=true;
  scene.globe.showGroundAtmosphere=true;
  scene.backgroundColor=C.Color.fromCssColorString('#9bafbf');
  if(scene.atmosphere){
    scene.atmosphere.dynamicLighting=C.DynamicAtmosphereLightingType.NONE;
    scene.atmosphere.saturationShift=-0.25;
    scene.atmosphere.brightnessShift=-0.12;
  }
}

export function createTabletopClip(viewer,bounds,C) {
  if(!C.ClippingPolygonCollection?.isSupported(viewer.scene))return null;
  return new C.ClippingPolygonCollection({enabled:false,inverse:false,polygons:[new C.ClippingPolygon({
    positions:C.Cartesian3.fromDegreesArray([bounds.west,bounds.south,bounds.east,bounds.south,bounds.east,bounds.north,bounds.west,bounds.north]),
  })]});
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
  // Soften empty horizon only. Aircraft and path pixels stay sharp because they
  // often sit over void depth and would otherwise be washed out with the mist.
  return viewer.scene.postProcessStages.add(new C.PostProcessStage({
    name:'wisl-tabletop-finish',
    uniforms:{
      pixel:()=>new C.Cartesian2(1/viewer.canvas.width,1/viewer.canvas.height),
      fogNear:()=>Math.max(2200,viewer.camera.positionCartographic.height*5.0),
    },
    fragmentShader:`uniform sampler2D colorTexture;
      uniform vec2 pixel;
      uniform sampler2D depthTexture;
      uniform float fogNear;
      in vec2 v_textureCoordinates;
      void main(){
        vec2 uv=v_textureCoordinates;
        vec3 sharp=texture(colorTexture,uv).rgb;
        float edge=smoothstep(0.20,0.49,abs(uv.y-0.48));
        float depth=czm_unpackDepth(texture(depthTexture,uv));
        vec4 eye=czm_windowToEyeCoordinates(gl_FragCoord.xy,depth);
        float distanceToScene=length(eye.xyz/max(abs(eye.w),0.00001));
        float empty=(depth<=0.0 || depth>=0.9999999) ? 1.0 : 0.0;
        if(empty>0.5){out_FragColor=vec4(sharp,1.0);return;}
        float far=empty>0.5 ? 1.0 : smoothstep(fogNear,fogNear*2.6,distanceToScene);
        float luma=dot(sharp,vec3(0.299,0.587,0.114));
        float chroma=length(sharp-vec3(luma));
        float mark=max(smoothstep(0.10,0.24,chroma),smoothstep(0.34,0.58,luma));
        float haze=mix(far*0.28,0.86,empty)*(1.0-mark);
        vec2 radius=pixel*(edge*2.0+empty*8.5+far*(1.0-empty)*1.6)*(1.0-mark);
        vec3 color=sharp*0.40;
        color+=texture(colorTexture,uv+vec2(radius.x,radius.y)).rgb*0.15;
        color+=texture(colorTexture,uv+vec2(-radius.x,radius.y)).rgb*0.15;
        color+=texture(colorTexture,uv+vec2(radius.x,-radius.y)).rgb*0.15;
        color+=texture(colorTexture,uv-radius).rgb*0.15;
        float grain=fract(sin(dot(gl_FragCoord.xy,vec2(12.9898,78.233)))*43758.5453)-0.5;
        float vignette=1.0-0.14*smoothstep(0.28,0.75,length(uv-0.5));
        vec3 mist=vec3(0.61,0.69,0.75);
        color=mix(mix(color,mist,haze),sharp,mark);
        out_FragColor=vec4(color*vignette+grain*0.006,1.0);
      }`,
  }));
}
