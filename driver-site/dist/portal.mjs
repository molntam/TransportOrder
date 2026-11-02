import config from './config.mjs';
import {escapeHtml as esc} from './domain.mjs';
const workspace='111fb839-a913-4c34-ae02-1c1228f35f9c';
let session=null,results=[],devices=[],pairing=null,query='',working=false;
const app=document.querySelector('#app');
async function request(path,body,auth=true){
 const response=await fetch(config.url+path,{method:'POST',headers:{apikey:config.publishableKey,'Content-Type':'application/json',...(auth?{Authorization:'Bearer '+session.access_token}:{})},body:JSON.stringify(body),credentials:'omit',referrerPolicy:'no-referrer',cache:'no-store',signal:AbortSignal.timeout(30000)});
 const result=await response.json();
 if(!response.ok)throw Error(response.status===401?'Your session expired. Sign out and log in again.':'Access denied or request failed. Check your credentials and workspace membership.');
 return result;
}
const rpc=(name,payload)=>request('/rest/v1/rpc/'+name,payload);
function lines(snapshot){
 const found=[];const walk=value=>{if(Array.isArray(value))value.forEach(walk);else if(value&&typeof value==='object'){if(value.hu||value.dn)found.push(value);else Object.values(value).forEach(walk);}};walk(snapshot);
 return [...new Map(found.map(l=>[`${l.dn}|${l.hu}|${l.qty}`,l])).values()];
}
function render(){
 app.setAttribute('aria-busy','false');
 if(!session){app.innerHTML=`<section class="empty-state"><span class="eyebrow">SHIPMENT TRACKING</span><h1>Follow every shipment</h1><p>Authorized users can search delivery numbers, handling units, forms, pallets and loading manifests.</p><form id="tracking-login" class="portal-login"><label>Email<input name="email" type="email" autocomplete="username" required></label><label>Password<input name="password" type="password" autocomplete="current-password" required></label><button class="btn primary wide" type="submit">Log in</button></form><p id="portal-error" role="alert"></p><a class="text-link" href="?demo=1">Explore the driver demonstration</a><p class="helper">Drivers open their shipment QR directly and do not need an account.</p></section>`;return;}
 app.innerHTML=`<div class="page-top"><span>Shipment tracking</span><button class="btn secondary" data-portal="logout">Sign out</button></div><div class="heading"><div><span class="eyebrow">DELIVERY OPERATIONS</span><h1>Find a shipment</h1></div><button class="btn secondary" data-portal="devices">Pair a workstation</button></div><form id="tracking-search" class="portal-search"><label class="search">DN, HU, form, pallet or manifest<input name="query" value="${esc(query)}" placeholder="Enter any shipment reference" maxlength="200"></label><button class="btn primary" type="submit">Search</button></form><p id="portal-error" role="alert"></p><p class="helper">${results.length} results · Latest 200 matches. Narrow your search for older records. Times shown in Netherlands time.</p><div class="portal-results">${results.map(r=>{const ls=lines(r.snapshot);const dest=r.snapshot.destination||r.snapshot.pallets?.[0]?.destination||{};return `<article class="card portal-result"><div class="section-heading"><div><span class="eyebrow">${esc(r.kind)} · REV ${r.revision}</span><h2>${esc(r.id)}</h2></div><span class="status-pill ${r.shipment_status==='delivered'?'delivered':r.collected_at?'transit':'ready'}">${esc(r.shipment_status||'Prepared')}</span></div><p>${esc(dest.building||r.snapshot.building||'')} · ${esc(dest.department||'')} · ${new Date(r.created_at).toLocaleString('en-GB',{timeZone:'Europe/Amsterdam'})}</p>${r.manifest_id?`<p>Manifest ${esc(r.manifest_id)}</p>`:''}<div class="portal-milestones"><span>Pickup: <b>${r.collected_at?new Date(r.collected_at).toLocaleString('en-GB',{timeZone:'Europe/Amsterdam'}):'Pending'}</b></span><span>Delivery: <b>${r.delivered_at?new Date(r.delivered_at).toLocaleString('en-GB',{timeZone:'Europe/Amsterdam'}):'Pending'}</b></span></div>${r.driver_name?`<p>${esc(r.driver_name)} · ${esc(r.vehicle)}</p>`:''}<details><summary>Delivery contents · ${ls.length} lines</summary><div class="portal-table"><table><thead><tr><th>DN</th><th>HU</th><th>Qty</th></tr></thead><tbody>${ls.map(l=>`<tr><td>${esc(l.dn||'—')}</td><td>${esc(l.hu||'—')}</td><td>${esc(l.qty||'—')}</td></tr>`).join('')}</tbody></table></div>${(r.events||[]).map(e=>`<p class="helper">${esc(e.action)} · ${new Date(e.at).toLocaleString('en-GB',{timeZone:'Europe/Amsterdam'})}</p>`).join('')}</details></article>`;}).join('')||'<section class="card portal-result"><h2>No matching documents</h2><p>Completed documents appear after a paired workstation uploads them. Try a different reference.</p></section>'}</div><section id="pair-panel" class="card portal-result" hidden><h2>Authorize a workstation</h2><p>Generate a code here, then paste it once into desktop Settings → Pair workstation. Keep the code private. It permits publishing and archiving for this workspace for one year.</p><form id="pair-form"><label>Workstation name<input name="label" maxlength="120" placeholder="For example: Shipping dock 1" required></label><button class="btn primary" type="submit">Generate pairing code</button></form>${pairing?`<div class="notice"><div><b>Copy this code now; it is shown once.</b><label>Pairing code<input value="${esc(pairing.token)}" readonly autocomplete="off"></label></div></div>`:''}<div>${devices.map(d=>`<div class="portal-device"><span>${esc(d.label)} · ${d.revokedAt?'Revoked':'Expires '+new Date(d.expiresAt).toLocaleDateString('en-GB')}</span>${!d.revokedAt?`<button class="btn secondary" data-portal="revoke" data-id="${esc(d.id)}">Revoke</button>`:''}</div>`).join('')}</div><button class="text-link" data-portal="close-pair">Close pairing</button></section>`;
}
async function search(){results=await rpc('transport_tracking',{p_workspace:workspace,p_query:query});render();}
async function deviceList(){devices=await rpc('transport_pair_device',{p_workspace:workspace,p_label:''});render();document.querySelector('#pair-panel').hidden=false;document.querySelector('#pair-panel').scrollIntoView({block:'start'});}
export function startPortal(){
 render();
 app.addEventListener('submit',async event=>{
  if(!['tracking-login','tracking-search','pair-form'].includes(event.target.id))return;
  event.preventDefault();if(working)return;working=true;
  const values=Object.fromEntries(new FormData(event.target));const kind=event.target.id;
  if(kind==='tracking-login')event.target.elements.password.value='';
  try{
   if(kind==='tracking-login'){
    const result=await request('/auth/v1/token?grant_type=password',values,false);session={access_token:result.access_token};
    const response=await fetch(config.url+'/rest/v1/to_workspaces?id=eq.'+workspace,{headers:{apikey:config.publishableKey,Authorization:'Bearer '+session.access_token},credentials:'omit',cache:'no-store',referrerPolicy:'no-referrer'});
    if(!response.ok||(await response.json()).length!==1){session=null;throw Error('This account has no shipment tracking access. Ask a workspace administrator.');}
    await search();
   }else if(kind==='tracking-search'){query=values.query.trim();await search();}
   else{pairing=await rpc('transport_pair_device',{p_workspace:workspace,p_label:values.label});await deviceList();}
  }catch(error){document.querySelector('#portal-error').textContent=error.message;}finally{working=false;}
 });
 app.addEventListener('click',async event=>{
  const b=event.target.closest('[data-portal]');if(!b||working)return;working=true;
  try{
   if(b.dataset.portal==='logout'){try{await request('/auth/v1/logout?scope=local',{});}catch{}session=null;results=[];devices=[];pairing=null;render();}
   else if(b.dataset.portal==='devices')await deviceList();
   else if(b.dataset.portal==='close-pair'){pairing=null;render();}
   else if(b.dataset.portal==='revoke'){await rpc('transport_pair_device',{p_workspace:workspace,p_label:'',p_revoke_id:b.dataset.id});await deviceList();}
  }catch(error){document.querySelector('#portal-error').textContent=error.message;}finally{working=false;}
 });
}
