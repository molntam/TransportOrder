export const buildings = [
 ['weert1a', 'RE-USE', 'Weert-1A'], ['weert1b', 'RPH', 'Weert-1B'],
 ['building21', 'Building 21', ''], ['building9', 'Building 9', ''],
 ['building17', 'Building 17', ''], ['building30', 'Building 30', ''],
 ['weert2', 'SPL', 'Weert-2'], ['building58', 'Building 58', ''],
 ['dc8', 'DC8', ''], ['hqpack', 'HQ-PACK', 'RTM']
];
export const stages = [['in_process','In process'],['ready','Ready for Pick-up'],['collected','Collected'],['delivered','Delivered']];
export function route(search) {
 const params = new URLSearchParams(search);
 const building = buildings.some(([id]) => id === params.get('building')) ? params.get('building') : '';
 const stage = stages.some(([id]) => id === params.get('stage')) ? params.get('stage') : '';
 return {query:(params.get('q') || '').slice(0,200), building, stage,
  page:Math.min(2000,Math.max(0,Number.parseInt(params.get('page') || '0',10) || 0)), document:params.get('document') || ''};
}
export function routeSearch(value) {
 const params = new URLSearchParams();
 if(value.query)params.set('q',value.query);
 if(value.building)params.set('building',value.building);
 if(value.stage)params.set('stage',value.stage);
 if(value.page)params.set('page',String(value.page));
 if(value.document)params.set('document',value.document);
 return params.size ? '?' + params.toString() : '';
}
export function materialLines(snapshot) {
 const found = [];
 function walk(value) {
  if(Array.isArray(value))value.forEach(walk);
  else if(value && typeof value === 'object') {
   if(value.hu || value.dn || value.part || value.description)found.push(value);
   else for(const [key,item] of Object.entries(value))if(!['events','versions','releasedPallets','sourceImports'].includes(key))walk(item);
  }
 }
 walk(snapshot);
 return [...new Map(found.map(line => [`${line.dn || ''}|${line.hu || ''}|${line.qty || ''}|${line.part || ''}|${line.description || ''}`,line])).values()];
}
export function documentDestination(record) {
 const s = record.snapshot || {};
 const pallets = s.pallets || [];
 const destinations = s.destination ? [s.destination] : pallets.map(p => (p.snapshot || p).destination).filter(Boolean);
 return {building:record.building || s.building || destinations[0]?.building || 'Destination not specified',
  departments:[...new Set(destinations.map(d => d.department).filter(Boolean))].join(' · '),
  shipTos:[...new Set(destinations.map(d => d.shipTo).filter(Boolean))].join(' · ')};
}
export function documentStats(record) {
 const lines = materialLines(record.snapshot);
 return {lines, dns:new Set(lines.map(l=>l.dn).filter(Boolean)).size, hus:new Set(lines.map(l=>l.hu).filter(Boolean)).size,
  pallets:record.kind === 'load' ? record.snapshot.pallets.length : record.kind === 'pallet' ? 1 : 0};
}
