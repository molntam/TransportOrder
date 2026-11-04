import {tripLinks, forgetTrip} from './trip.mjs';
import config from './config.mjs';
import {escapeHtml as esc} from './domain.mjs';
const workspace='111fb839-a913-4c34-ae02-1c1228f35f9c';
const sessionKey = 'transportorder.tracking.session';
let session = null;
let results = [];
let query = '';
let working = false;

function saveSession(value) {
 session = value;
 try {
  if (value) localStorage.setItem(sessionKey, JSON.stringify(value));
  else localStorage.removeItem(sessionKey);
 } catch {}
}

function storeTokens(result) {
 saveSession({
  access_token: result.access_token,
  refresh_token: result.refresh_token,
  expires: Date.now() + result.expires_in * 1000
 });
}

async function refreshSession() {
 if (session.expires > Date.now() + 30000) return;
 const renew = async () => {
  const saved = JSON.parse(localStorage.getItem(sessionKey) || 'null');
  if (saved?.expires > Date.now() + 30000) {
   session = saved;
   return;
  }
  const result = await request('/auth/v1/token?grant_type=refresh_token',
   {refresh_token: saved?.refresh_token || session.refresh_token}, false);
  storeTokens(result);
 };
 if (navigator.locks) await navigator.locks.request(sessionKey, renew);
 else await renew();
}

function highestDocuments(records) {
 const sorted = [...records].sort((a, b) => b.revision - a.revision ||
  Number(Boolean(b.snapshot.online)) - Number(Boolean(a.snapshot.online)));
 const unique = new Map();
 for (const record of sorted) {
  const id = record.kind === 'load' ? record.manifest_id || record.id : record.id;
  const key = record.kind + ':' + id;
  if (!unique.has(key)) unique.set(key, record);
 }
 const manifests = [...unique.values()].filter(record => record.kind === 'load');
 const palletIds = new Set();
 const formIds = new Set();
 function collectForms(pallet) {
  for (const form of pallet.forms || []) formIds.add(form.id);
 }
 for (const manifest of manifests) {
  for (const pallet of manifest.snapshot.pallets || []) {
   palletIds.add(pallet.id);
   collectForms(pallet.snapshot || pallet);
  }
 }
 for (const record of unique.values()) {
  if (record.kind === 'pallet') collectForms(record.snapshot);
 }
 return [...unique.values()].filter(record => {
  if (record.kind === 'pallet') return !palletIds.has(record.id);
  if (record.kind === 'form') return !formIds.has(record.id) && !palletIds.has(record.snapshot.palletId);
  return true;
 }).sort((a, b) => b.created_at.localeCompare(a.created_at));
}
const app=document.querySelector('#app');
async function request(path,body,auth=true){
 if (auth) await refreshSession();
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
 if(!session){app.innerHTML=`${tripLinks()}<section class="empty-state"><span class="eyebrow">SHIPMENT TRACKING</span><h1>Follow every shipment</h1><p>Authorized users can search delivery numbers, handling units, forms, pallets and loading manifests.</p><form id="tracking-login" class="portal-login"><label>Email<input name="email" type="email" autocomplete="username" required></label><label>Password<input name="password" type="password" autocomplete="current-password" required></label><button class="btn primary wide" type="submit">Log in</button></form><p id="portal-error" role="alert"></p><a class="text-link" href="?demo=1">Explore the driver demonstration</a><p class="helper">Drivers open their shipment QR directly and do not need an account.</p></section>`;return;}
 app.innerHTML=`${tripLinks()}<div class="page-top"><span>Shipment tracking</span><button class="btn secondary" data-portal="logout">Sign out</button></div><div class="heading"><div><span class="eyebrow">DELIVERY OPERATIONS</span><h1>Find a shipment</h1></div></div><form id="tracking-search" class="portal-search"><label class="search">DN, HU, form, pallet or manifest<input name="query" value="${esc(query)}" placeholder="Enter any shipment reference" maxlength="200"></label><button class="btn primary" type="submit">Search</button></form><p id="portal-error" role="alert"></p><p class="helper">${results.length} results · Highest matching documents. Narrow your search for older records. Times shown in Netherlands time.</p><div class="portal-results">${results.map(r=>{const ls=lines(r.snapshot);const dest=r.snapshot.destination||r.snapshot.pallets?.[0]?.destination||{};return `<article class="card portal-result"><div class="section-heading"><div><span class="eyebrow">${esc(r.kind)} · REV ${r.revision}</span><h2>${esc(r.id)}</h2></div><span class="status-pill ${r.shipment_status==='delivered'?'delivered':r.collected_at?'transit':'ready'}">${esc(r.shipment_status||'Prepared')}</span></div><p>${esc(dest.building||r.snapshot.building||'')} · ${esc(dest.department||'')} · ${new Date(r.created_at).toLocaleString('en-GB',{timeZone:'Europe/Amsterdam'})}</p>${r.manifest_id?`<p>Manifest ${esc(r.manifest_id)}</p>`:''}<div class="portal-milestones"><span>Pickup: <b>${r.collected_at?new Date(r.collected_at).toLocaleString('en-GB',{timeZone:'Europe/Amsterdam'}):'Pending'}</b></span><span>Delivery: <b>${r.delivered_at?new Date(r.delivered_at).toLocaleString('en-GB',{timeZone:'Europe/Amsterdam'}):'Pending'}</b></span></div>${r.driver_name?`<p>${esc(r.driver_name)} · ${esc(r.vehicle)}</p>`:''}<details><summary>Delivery contents · ${ls.length} lines</summary><div class="portal-table"><table><thead><tr><th>DN</th><th>HU</th><th>Qty</th></tr></thead><tbody>${ls.map(l=>`<tr><td>${esc(l.dn||'—')}</td><td>${esc(l.hu||'—')}</td><td>${esc(l.qty||'—')}</td></tr>`).join('')}</tbody></table></div>${(r.events||[]).map(e=>`<p class="helper">${esc(e.action)} · ${new Date(e.at).toLocaleString('en-GB',{timeZone:'Europe/Amsterdam'})}</p>`).join('')}</details></article>`;}).join('')||'<section class="card portal-result"><h2>No matching documents</h2><p>Completed documents appear after an authorized workstation uploads them. Try a different reference.</p></section>'}</div>`;
}
async function search() {
 const matches = await rpc('transport_tracking', {p_workspace:workspace, p_query:query});
 results = highestDocuments(matches);
 render();
}
export async function startPortal(){
 try {
  session = JSON.parse(localStorage.getItem(sessionKey) || 'null');
  if (session) await search();
 } catch {
  saveSession(null);
 }
 render();
 app.addEventListener('submit',async event=>{
  if(!['tracking-login','tracking-search'].includes(event.target.id))return;
  event.preventDefault();if(working)return;working=true;
  const values=Object.fromEntries(new FormData(event.target));const kind=event.target.id;
  if(kind==='tracking-login')event.target.elements.password.value='';
  try{
   if(kind==='tracking-login'){
    const result=await request('/auth/v1/token?grant_type=password',values,false);storeTokens(result);
    const response=await fetch(config.url+'/rest/v1/to_workspaces?id=eq.'+workspace,{headers:{apikey:config.publishableKey,Authorization:'Bearer '+session.access_token},credentials:'omit',cache:'no-store',referrerPolicy:'no-referrer'});
    if(!response.ok||(await response.json()).length!==1){saveSession(null);throw Error('This account has no shipment tracking access. Ask a workspace administrator.');}
    await search();
   }else if(kind==='tracking-search'){query=values.query.trim();await search();}
  }catch(error){document.querySelector('#portal-error').textContent=error.message;}finally{working=false;}
 });
 app.addEventListener('click',async event=>{
  const b=event.target.closest('[data-portal]');if(!b||working)return;working=true;
  try{
   if(b.dataset.portal==='logout'){
    try { await request('/auth/v1/logout?scope=local',{}); } catch {}
    saveSession(null);
    results=[];
    render();
   } else if (b.dataset.portal==='forget-trip') {
    forgetTrip();
    render();
   }
  }catch(error){document.querySelector('#portal-error').textContent=error.message;}finally{working=false;}
 });
}
