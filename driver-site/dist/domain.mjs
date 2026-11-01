export const escapeHtml = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function parseToken(hash) {
  const value=hash.replace(/^#/,'');
  const token=value.includes('=')?new URLSearchParams(value).get('token'):value;
  return /^[a-f0-9]{64}$/i.test(token||'')?token.toLowerCase():null;
}
export function normalizeScan(value) {
  const code=String(value||'').trim();
  if(!/^TO:PALLET:P-[A-Z0-9-]{1,64}:[0-9]{1,9}$/.test(code))throw new Error('Scan a pallet QR from its transport document.');
  return code;
}
export function totals(shipment) {
  const pallets=shipment.pallets||[];
  const lines=pallets.flatMap(p=>(p.forms||[]).flatMap(f=>f.lines||[]));
  return {planned:pallets.length,scanned:pallets.filter(p=>p.scannedAt).length,
    collected:pallets.filter(p=>p.collectedAt).length,delivered:pallets.filter(p=>p.deliveredAt).length,
    hus:new Set(lines.map(l=>l.hu).filter(Boolean)).size,dns:new Set(lines.map(l=>l.dn).filter(Boolean)).size};
}
export function filterPallets(shipment,query='',filter='all') {
  const q=query.trim().toLowerCase();
  return shipment.pallets.filter(p=>(filter==='all'||(filter==='scanned'?Boolean(p.scannedAt):!p.scannedAt))&&JSON.stringify(p).toLowerCase().includes(q));
}
export function validatePickup(shipment,{driver,vehicle,reason}) {
  if(shipment.status!=='ready')throw new Error('This pickup has already been confirmed. Refresh the shipment.');
  const c=totals(shipment);
  if(!c.scanned)throw new Error('Scan at least one pallet before confirming pickup.');
  if(!driver.trim()||!vehicle.trim())throw new Error('Enter your name and vehicle registration.');
  if(driver.trim().length>200||vehicle.trim().length>200)throw new Error('Use at most 200 characters for your name and vehicle registration.');
  if(c.scanned<c.planned&&!reason.trim())throw new Error('Tell the warehouse why the remaining pallets are not being collected.');
  return {driver:driver.trim(),vehicle:vehicle.trim(),reason:reason.trim(),expectedRowVersion:shipment.rowVersion};
}
export function friendlyError(error) {
  const message=String(error?.message||'');
  if(/Invalid or expired driver link|Superseded manifest/i.test(message))return 'This shipment link has expired or been replaced. Ask the warehouse for a new QR.';
  if(/Wrong destination|Pallet is not on this manifest|Superseded or already collected pallet|Pickup is already closed|Choose a scanned pallet|Confirm pickup before delivery|matching destination|Driver name and vehicle|partial pickup|Scan at least one|Pallet changed|Manifest changed/i.test(message))return message;
  if(/Failed to fetch|NetworkError|network|timeout|aborted/i.test(message))return 'Connection interrupted. Your last action may have reached the system. Refresh the status before trying again.';
  return message&&error?.local?message:'The shipment could not be updated. Refresh its status and try again.';
}
export function createClient(config,token,request=fetch) {
  return async (action='get',payload={})=>{
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),20000);
    try {
      const response=await request(config.url+'/rest/v1/rpc/transport_driver',{method:'POST',headers:{apikey:config.publishableKey,'Content-Type':'application/json'},body:JSON.stringify({p_token:token,p_action:action,p_payload:payload}),signal:controller.signal,credentials:'omit',cache:'no-store',referrerPolicy:'no-referrer'});
      const data=await response.json().catch(()=>null);
      if(!response.ok){const error=new Error(data?.message||'Request failed');error.code=data?.code;throw error;}
      if(!data?.id||!Array.isArray(data.pallets))throw new Error('Invalid shipment response');
      return data;
    } finally {clearTimeout(timer);}
  };
}
export function createDemo() {
  let shipment={id:'LOAD-DEMO-2101',revision:1,rowVersion:1,building:'Building 21',status:'ready',createdAt:'2026-11-01T08:40:00Z',collectedAt:null,deliveredAt:null,duplicate:false,pallets:Array.from({length:20},(_,i)=>({id:'P-DEMO-'+String(i+1).padStart(2,'0'),revision:1,scannedAt:null,collectedAt:null,deliveredAt:null,destination:{building:'Building 21',department:i%3===0?'Field Service Hub':'Motion',shipTo:i%3===0?'NL15C':'B21-MOASSY'},forms:[{id:'TO-DEMO-'+String(i+1).padStart(2,'0'),lines:[{hu:'80002100'+String(i+1).padStart(4,'0'),dn:'008100'+String(i+1).padStart(4,'0'),qty:String(i%5+1)}]}]}))};
  return async(action='get',payload={})=>{
    shipment.duplicate=false;
    const at=new Date().toISOString();const c=totals(shipment);
    if(action==='scan'){
      if(shipment.status!=='ready')throw new Error('Pickup is already closed');
      if(payload.code==='TO:PALLET:P-DEMO-WRONG:1')throw new Error('Wrong destination: pallet is for Building 17, not Building 21.');
      const code=normalizeScan(payload.code),match=code.match(/^TO:PALLET:(.*):(\d+)$/),p=shipment.pallets.find(p=>p.id===match[1]);
      if(!p)throw new Error('Pallet is not on this manifest');
      if(p.revision!==Number(match[2]))throw new Error('Superseded or already collected pallet');
      shipment.duplicate=Boolean(p.scannedAt);p.scannedAt ||= at;
    } else if(action==='unscan'){
      if(shipment.status!=='ready')throw new Error('Pickup is already closed');
      const p=shipment.pallets.find(p=>p.id===payload.palletId&&p.scannedAt);
      if(!p||!payload.reason?.trim())throw new Error('Choose a scanned pallet and give a reason.');p.scannedAt=null;
    } else if(action==='confirm_pickup'){
      validatePickup(shipment,payload);
      shipment.status=c.scanned===c.planned?'collected':'partial';shipment.collectedAt=at;
      shipment.pallets.forEach(p=>{if(p.scannedAt)p.collectedAt=at;});
    } else if(action==='confirm_delivery'){
      if(!['collected','partial'].includes(shipment.status))throw new Error('Confirm pickup before delivery');
      if(payload.building!==shipment.building||!payload.receiver?.trim())throw new Error('Confirm the matching destination building and receiver name');
      shipment.status='delivered';shipment.deliveredAt=at;shipment.pallets.forEach(p=>{if(p.collectedAt)p.deliveredAt=at;});
    }
    if(action!=='get'&&!shipment.duplicate)shipment.rowVersion++;
    return structuredClone(shipment);
  };
}
