// Split retained tabletop OSM geometry into small spatial chunks and write the
// terrain-only manifest. Feature ownership is based on its geometry midpoint so
// a feature is emitted once, while chunk bounds are the true geometry extent.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../public/assets');
const names = ['stonehenge', 'shropshire', 'north-wales'];
const cellMeters = 400;
const bbox = geometry => {
  const points = (geometry || []).filter(p => Number.isFinite(p?.lon) && Number.isFinite(p?.lat));
  if (!points.length) return null;
  return {west:Math.min(...points.map(p=>p.lon)), south:Math.min(...points.map(p=>p.lat)), east:Math.max(...points.map(p=>p.lon)), north:Math.max(...points.map(p=>p.lat))};
};
const union = boxes => ({west:Math.min(...boxes.map(b=>b.west)),south:Math.min(...boxes.map(b=>b.south)),east:Math.max(...boxes.map(b=>b.east)),north:Math.max(...boxes.map(b=>b.north))});
fs.mkdirSync(path.join(root, 'tabletop-chunks'), {recursive:true});
const regions = names.map(name => {
  const asset = JSON.parse(fs.readFileSync(path.join(root, `tabletop-${name}.json`), 'utf8'));
  const bounds = asset.elevation.bounds;
  const latMeters = 110574;
  const lonMeters = 111320 * Math.cos((bounds.south + bounds.north) / 2 * Math.PI / 180);
  const cols = Math.max(1, Math.ceil((bounds.east - bounds.west) * lonMeters / cellMeters));
  const rows = Math.max(1, Math.ceil((bounds.north - bounds.south) * latMeters / cellMeters));
  const buckets = new Map();
  for (const element of asset.elements) {
    const box = bbox(element.geometry); if (!box) continue;
    const lon = (box.west + box.east) / 2, lat = (box.south + box.north) / 2;
    const col = Math.max(0, Math.min(cols - 1, Math.floor((lon - bounds.west) / (bounds.east - bounds.west) * cols)));
    const row = Math.max(0, Math.min(rows - 1, Math.floor((lat - bounds.south) / (bounds.north - bounds.south) * rows)));
    const key = `${col}-${row}`;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push({element, box});
  }
  const chunks = [];
  for (const [key, entries] of buckets) {
    const id = `${name}-${key}`, file = `tabletop-chunks/${id}.json`;
    fs.writeFileSync(path.join(root, file), JSON.stringify({elements:entries.map(x=>x.element)}));
    chunks.push({id, url:`./assets/${file}`, bounds:union(entries.map(x=>x.box))});
  }
  chunks.sort((a,b)=>a.id.localeCompare(b.id, undefined, {numeric:true}));
  return {name,bounds,elevation:asset.elevation,source:asset.source,chunks};
});
fs.writeFileSync(path.join(root, 'tabletop-atlas.json'), JSON.stringify({regions}));
console.log(`wrote tabletop-atlas.json with ${regions.reduce((n,r)=>n+r.chunks.length,0)} chunks`);
