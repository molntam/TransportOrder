import {tripLinks, forgetTrip} from './trip.mjs';
import config from './config.mjs';
import {escapeHtml as esc} from './domain.mjs';
import {buildings, stages, route, routeSearch, documentDestination, documentStats} from './portal-domain.mjs';
const workspace = '111fb839-a913-4c34-ae02-1c1228f35f9c';
const sessionKey = 'transportorder.tracking.session';
const app = document.querySelector('#app');
const date = value => value ? new Date(value).toLocaleString('en-GB',{timeZone:'Europe/Amsterdam',hourCycle:'h23',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'}) : 'Pending';
let session = null, state = route(location.search), records = [], counts = {}, total = 0, hasMore = false;
let working = false, loading = false, error = '', generation = 0;
function saveSession(value) {
 session = value;
 try {if(value)localStorage.setItem(sessionKey,JSON.stringify(value));else localStorage.removeItem(sessionKey);} catch {}
}
function storeTokens(result) {
 saveSession({access_token:result.access_token,refresh_token:result.refresh_token,expires:Date.now() + result.expires_in * 1000});
}
async function refreshSession(force = false) {
 if(!session)throw new Error('Sign in to search shipments.');
 if(!force && session.expires > Date.now() + 30000)return;
 const renew = async () => {
  let saved;
  try {saved=JSON.parse(localStorage.getItem(sessionKey) || 'null');} catch {}
  if(saved?.expires > Date.now() + 30000 && (!force || saved.access_token !== session.access_token)) {session=saved;return;}
  const response = await fetch(config.url+'/auth/v1/token?grant_type=refresh_token',{method:'POST',headers:{apikey:config.publishableKey,'Content-Type':'application/json'},body:JSON.stringify({refresh_token:saved?.refresh_token || session.refresh_token}),credentials:'omit',referrerPolicy:'no-referrer',signal:AbortSignal.timeout(30000)});
  const result = await response.json();
  if(!response.ok) {
   if([400,401,403].includes(response.status))saveSession(null);
   throw new Error(session ? 'Sign-in could not be renewed. Try again.' : 'Your sign-in has expired. Please sign in again.');
  }
  storeTokens(result);
 };
 if(navigator.locks)await navigator.locks.request(sessionKey,renew);else await renew();
}
async function request(path,body,auth=true,retry=true) {
 if(auth)await refreshSession();
 let response;
 try {
  response=await fetch(config.url+path,{method:'POST',headers:{apikey:config.publishableKey,'Content-Type':'application/json',...(auth ? {Authorization:'Bearer '+session.access_token} : {})},body:JSON.stringify(body),credentials:'omit',referrerPolicy:'no-referrer',cache:'no-store',signal:AbortSignal.timeout(30000)});
 } catch {throw new Error('Connection interrupted. Your sign-in and current view are kept. Try again.');}
 const result=await response.json().catch(()=>null);
 if(response.status===401 && auth && retry){await refreshSession(true);return request(path,body,auth,false);}
 if(!response.ok)throw new Error(response.status===400 && !auth ? 'Email or password was not accepted.' : response.status===403 ? 'This account does not have access to this workspace.' : 'The request could not be completed. Please try again.');
 return result;
}
function navigate(changes,replace=false) {
 state={...state,...changes};
 const url=location.pathname+routeSearch(state);
 if(url!==location.pathname+location.search)history[replace ? 'replaceState' : 'pushState']({},'',url);
}
function renderCard(record) {
 const dest=documentDestination(record), c=documentStats(record), delivered=record.stage==='delivered';
 const status=record.shipment_status?.startsWith('At ') ? record.shipment_status : stages.find(([key])=>key===record.stage)?.[1] || 'In process';
 const type={load:'Loading manifest',pallet:'Pallet consolidation',form:'Transport order'}[record.kind] || 'Document';
 const source=record.snapshot?.sourceDepartment?.name;
 return `<article class="card portal-result" id="record-${esc(record.id)}"><div class="tracking-card-top"><div><span class="eyebrow">${type}</span><h2>${esc(dest.building)}</h2><p class="destination-department">${esc(dest.departments || source || 'Internal transport')}</p></div><span class="status-pill ${delivered?'delivered':record.stage==='collected'?'transit':record.stage==='ready'?'ready':'processing'}">${esc(status)}</span></div>
  <div class="tracking-reference"><b>${esc(record.id)}</b><span>Revision ${record.revision}</span><time>${date(record.created_at)}</time></div>
  <div class="tracking-counts">${c.pallets?`<span><b>${c.pallets}</b> ${c.pallets===1?'pallet':'pallets'}</span>`:''}<span><b>${c.dns}</b> DNs</span><span><b>${c.hus}</b> HUs</span>${dest.shipTos?`<span class="tracking-shipto">${esc(dest.shipTos)}</span>`:''}</div>
  ${record.reason?`<div class="tracking-comment"><b>${record.left_behind ? `${record.left_behind} ${record.left_behind===1?'pallet':'pallets'} left for another truck` : 'Dispatch comment'}</b><p>${esc(record.reason)}</p></div>`:''}
  ${(record.collected_at || record.delivered_at || record.driver_name)?`<div class="tracking-milestones"><div><small>Collected</small><strong>${date(record.collected_at)}</strong>${record.driver_name?`<span>${esc(record.driver_name)}${record.vehicle?' · '+esc(record.vehicle):''}</span>`:''}</div><div><small>Delivered</small><strong>${date(record.delivered_at)}</strong>${record.receiver_name?`<span>Received by <b>${esc(record.receiver_name)}</b></span>`:''}</div></div>`:''}
  <details data-record="${esc(record.id)}" ${state.document===record.id?'open':''}><summary>View DNs, HUs and activity <span>${c.lines.length} material ${c.lines.length===1?'line':'lines'}</span></summary><div class="portal-table"><table><thead><tr><th>Delivery number</th><th>Handling unit</th><th>Qty</th></tr></thead><tbody>${c.lines.map(l=>`<tr><td>${esc(l.dn || '—')}</td><td>${esc(l.hu || '—')}</td><td>${esc(l.qty || '—')}</td></tr>`).join('')}</tbody></table></div><ol class="tracking-activity">${(record.events || []).map(e=>`<li><div><b>${esc(e.action)}</b><time>${date(e.at)}</time></div>${e.detail?.receiver?`<p>Received by ${esc(e.detail.receiver)}</p>`:''}${e.detail?.reason?`<p>${esc(e.detail.reason)}</p>`:''}${e.detail?.fromDepartment?`<p>From ${esc(e.detail.fromDepartment)} → ${esc(e.detail.palletId)}</p>`:''}</li>`).join('') || '<li>Document prepared. Awaiting the next handling event.</li>'}</ol></details></article>`;
}
function render() {
 app.setAttribute('aria-busy',String(loading));
 app.classList.add('tracking-app');
 document.title=(state.building?buildings.find(([key])=>key===state.building)?.[1]+' · ':'')+'Shipment tracking · TransportOrder';
 if(!session) {
  app.innerHTML=`${tripLinks()}<section class="tracking-login"><div class="login-intro"><span class="eyebrow">DELIVERY OPERATIONS</span><h1>Every shipment.<br>A clearer journey.</h1><p>Find materials by delivery number, handling unit or document. Follow their progress from preparation to delivery.</p><div class="login-assurance">Authorized shipment tracking · Netherlands</div></div><div class="card login-card"><h2>Sign in to tracking</h2><p>Use your authorized operator or tracking account.</p><form id="tracking-login" class="portal-login"><label>Email address<input name="email" type="email" autocomplete="username" required></label><label>Password<input name="password" type="password" autocomplete="current-password" required></label><button class="btn primary wide" type="submit" ${working?'disabled':''}>Sign in</button></form><p class="portal-error" id="portal-error" role="alert">${esc(error)}</p><p class="helper">Drivers can open their shipment QR without signing in.</p></div></section>`;
  return;
 }
 const active=Boolean(state.query || state.building), label=buildings.find(([key])=>key===state.building);
 app.innerHTML=`<div class="tracking-toolbar"><a href="${esc(location.pathname)}" data-portal="home" class="tracking-home">Shipment tracking</a><div><span class="timezone-note">Europe/Amsterdam · 24h</span><button class="btn secondary small" data-portal="logout">Sign out</button></div></div>
  <nav class="building-tabs" aria-label="Destination buildings">${buildings.map(([key,name,sub])=>`<button data-portal="building" data-building="${key}" class="${state.building===key?'active':''}" ${state.building===key?'aria-current="page"':''}><b>${esc(name)}</b>${sub?`<small>${esc(sub)}</small>`:''}</button>`).join('')}</nav>
  ${tripLinks()}<section class="tracking-search-area ${active?'':'home-search'}"><form id="tracking-search" class="portal-search"><label class="search"><span class="search-label">Search all shipments</span><input aria-label="Search DN, HU or document" name="query" value="${esc(state.query)}" placeholder="Search DN, HU, form, pallet or manifest" maxlength="200" autocomplete="off" type="search"></label><button class="btn primary" type="submit">Search</button></form></section>
  <p class="portal-error" id="portal-error" role="alert" ${error?'':'hidden'}>${esc(error)} ${error?'<button class="text-link" data-portal="retry">Try again</button>':''}</p>
  ${active?`<section class="tracking-results-area"><div class="tracking-results-heading"><div><span class="eyebrow">${state.query?'SEARCH RESULTS':'DESTINATION OVERVIEW'}</span><h1>${state.query ? `Results for “${esc(state.query)}”` : esc(label?.[1] || '')}${!state.query && label?.[2]?` <span>${esc(label[2])}</span>`:''}</h1></div><button class="text-link" data-portal="retry" ${loading?'disabled':''}>Refresh status</button></div>
  <nav class="status-tabs" aria-label="Shipment status"><button data-portal="stage" data-stage="" class="${!state.stage?'active':''}">All <span>${Object.values(counts).reduce((sum,n)=>sum+n,0)}</span></button>${stages.map(([key,name])=>`<button data-portal="stage" data-stage="${key}" class="${state.stage===key?'active':''}" aria-pressed="${state.stage===key}">${name}<span>${counts[key] || 0}</span></button>`).join('')}</nav>
  <div class="results-caption" role="status">${loading?'Checking the latest shipment status…':`${total} ${total===1?'document':'documents'} · Showing the highest document for each shipment`}</div>
  <div class="portal-results ${loading?'is-loading':''}">${records.map(renderCard).join('') || (loading?'<div class="tracking-empty"><div class="loader"></div><h2>Loading shipments</h2></div>':error?'':'<div class="tracking-empty"><div class="empty-icon">—</div><h2>No shipments here yet</h2><p>Try another status, building or reference.</p></div>')}</div>
  ${state.page || hasMore?`<div class="tracking-pagination"><button class="btn secondary" data-portal="previous" ${state.page && !loading?'':'disabled'}>Previous</button><span>Page ${state.page+1}</span><button class="btn secondary" data-portal="next" ${hasMore && !loading?'':'disabled'}>Next</button></div>`:''}</section>`:''}`;
}
async function search() {
 const current=++generation;
 error='';
 if(!state.query && !state.building){records=[];counts={};total=0;loading=false;render();return;}
 loading=true;render();
 try {
  const result=await request('/rest/v1/rpc/transport_tracking_page',{p_workspace:workspace,p_query:state.query,p_building:state.building,p_stage:state.stage,p_offset:state.page*50});
  if(current!==generation)return;
  if(!result.authorized)throw new Error('This account has no tracking access. Ask a workspace administrator.');
  records=result.records;counts=result.counts;total=result.total;hasMore=result.hasMore;
 } catch(e){if(current===generation)error=e.message;}
 finally {if(current===generation){loading=false;render();}}
}
export async function startPortal() {
 try {session=JSON.parse(localStorage.getItem(sessionKey) || 'null');} catch {}
 if(!session?.access_token || !session?.refresh_token)session=null;
 render();
 app.addEventListener('submit',async event=>{
  if(!['tracking-login','tracking-search'].includes(event.target.id))return;
  event.preventDefault();if(working)return;
  const values=Object.fromEntries(new FormData(event.target)), login=event.target.id==='tracking-login';
  working=true;error='';
  if(login){event.target.elements.password.value='';event.target.querySelector('button').disabled=true;}
  try {
   if(login){storeTokens(await request('/auth/v1/token?grant_type=password',values,false));const access=await request('/rest/v1/rpc/transport_tracking_page',{p_workspace:workspace,p_query:'',p_building:'',p_stage:'',p_offset:0});if(!access.authorized){saveSession(null);throw new Error('This account has no tracking access. Ask a workspace administrator.');}}
   else navigate({query:values.query.trim(),building:'',stage:'',page:0,document:''});
   await search();
  } catch(e){error=e.message;render();}
  finally {working=false;const b=document.querySelector('#tracking-login button');if(b)b.disabled=false;}
 });
 app.addEventListener('click',async event=>{
  const button=event.target.closest('[data-portal]');if(!button || button.disabled || working)return;
  event.preventDefault();const action=button.dataset.portal;
  if(action==='forget-trip'){forgetTrip();render();return;}
  if(action==='logout') {
   working=true;
   try {await request('/auth/v1/logout?scope=local',{});} catch {}
   saveSession(null);records=[];working=false;error='';render();return;
  }
  if(action==='home')navigate({query:'',building:'',stage:'',page:0,document:''});
  if(action==='building')navigate({query:'',building:button.dataset.building,stage:'',page:0,document:''});
  if(action==='stage')navigate({stage:button.dataset.stage,page:0,document:''});
  if(action==='previous')navigate({page:Math.max(0,state.page-1),document:''});
  if(action==='next')navigate({page:state.page+1,document:''});
  await search();
 });
 app.addEventListener('toggle',event=>{
  if(!event.target.matches('details[data-record]'))return;
  const id=event.target.dataset.record;
  if(event.target.open && state.document!==id)navigate({document:id},true);
  else if(!event.target.open && state.document===id)navigate({document:''},true);
 },true);
 window.addEventListener('popstate',()=>{state=route(location.search);search();});
 window.addEventListener('storage',event=>{if(event.key===sessionKey){try{session=JSON.parse(event.newValue);}catch{session=null;}render();}});
 if(session) {
  try {await refreshSession();await search();}catch(e){error=e.message;render();}
 }
 setInterval(()=>{if(session && !document.hidden && !working && !loading && (state.query || state.building) && !app.querySelector('details[open]') && !app.contains(document.activeElement))search();},30000);
}
