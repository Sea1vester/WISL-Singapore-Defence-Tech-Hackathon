// Offline map/terrain cache builder. Run with NODE_PATH pointing to a temporary
// `lerc@4.0.4` install. The input can be an Overpass `out geom` response or an
// existing tabletop cache; --bounds lets an existing map extract retain its OSM
// provenance while its elevation coverage is expanded.
const fs = require('node:fs');
const path = require('node:path');
const Lerc = require('lerc');
const endpoint = 'https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer';
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const name = process.argv[3] || 'stonehenge';
const boundsFlag = process.argv.indexOf('--bounds');
const parseBounds = value => {
  const [west,south,east,north] = String(value).split(',').map(Number);
  if (![west,south,east,north].every(Number.isFinite) || west >= east || south >= north) throw new Error('Invalid --bounds west,south,east,north');
  return {west,south,east,north};
};
const bounds = boundsFlag >= 0 ? parseBounds(process.argv[boundsFlag + 1]) : (input.bounds || {west:-1.833,south:51.175,east:-1.819,north:51.184});
const existingCache = Array.isArray(input.elements) && input.elevation;
const mapBounds = existingCache ? (input.source?.mapBounds || input.bounds) : input.bounds;
const level = 14;
const tiles = new Map();
async function heightAt(lon, lat) {
  const n = 2 ** level;
  const x = (lon + 180) / 360 * n;
  const y = (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * n;
  const tx = Math.floor(x), ty = Math.floor(y), key = `${tx}/${ty}`;
  if (!tiles.has(key)) tiles.set(key, (async () => {
    const response = await fetch(`${endpoint}/tile/${level}/${ty}/${tx}`, {signal: AbortSignal.timeout(20000)});
    if (!response.ok) throw new Error(`Elevation tile: ${response.status}`);
    return Lerc.decode(await response.arrayBuffer());
  })());
  const tile = await tiles.get(key);
  const px = (x-tx)*(tile.width-1), py = (y-ty)*(tile.height-1);
  const x0=Math.floor(px), y0=Math.floor(py), x1=Math.min(x0+1,tile.width-1), y1=Math.min(y0+1,tile.height-1);
  const values=[y0*tile.width+x0,y0*tile.width+x1,y1*tile.width+x0,y1*tile.width+x1].map(i=>{
    if (tile.mask && !tile.mask[i]) throw new Error('No-data elevation pixel');
    return tile.pixels[0][i];
  });
  const a=px-x0,b=py-y0;
  return Math.round(((values[0]*(1-a)+values[1]*a)*(1-b)+(values[2]*(1-a)+values[3]*a)*b)*100)/100;
}
(async()=>{
 await Lerc.load();
 const rows=49,columns=49,heights=[];
 for(let r=0;r<rows;r++) for(let c=0;c<columns;c++) heights.push(await heightAt(bounds.west+(bounds.east-bounds.west)*c/(columns-1), bounds.south+(bounds.north-bounds.south)*r/(rows-1)));
 const source={...(existingCache ? input.source : {}),map:'© OpenStreetMap contributors',mapUrl:'https://www.openstreetmap.org/copyright',mapBounds, mapBoundsProvenance: existingCache ? (input.source?.mapBoundsProvenance || 'Original bounded OpenStreetMap extract retained while elevation coverage was expanded.') : 'Bounded OpenStreetMap extract used for this cache.',elevation:'Esri World Elevation / Terrain3D',elevationUrl:endpoint,elevationTileLevel:level,retrievedAt:new Date().toISOString(),osmTimestamp:existingCache ? input.source?.osmTimestamp : input.osm3s?.timestamp_osm_base,notes:'Mapped footprints; illustrative vertical feature dimensions. Elevation grid sampled from Esri LERC tiles. Row 0 is south. No surveyed obstacle or clearance claims.'};
 const elements=existingCache ? input.elements : input.elements.map(e=>({type:e.type,id:e.id,tags:Object.fromEntries(Object.entries(e.tags||{}).filter(([k])=>!k.includes(':')||k==='building:levels')),geometry:e.geometry}));
 const data={bounds,source,elevation:{bounds,rows,columns,heights},elements};
 const out=path.resolve(__dirname,`../public/assets/tabletop-${name}.json`);fs.writeFileSync(out,JSON.stringify(data));
 console.log(out, 'elevation',Math.min(...heights),Math.max(...heights),'features',data.elements.length,'tiles',tiles.size);
})().catch(e=>{console.error(e);process.exit(1)});
