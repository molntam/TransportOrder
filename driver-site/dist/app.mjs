import config from './config.mjs';
import {escapeHtml as esc,parseToken,normalizeScan,totals,filterPallets,validatePickup,friendlyError,createClient,createDemo} from './domain.mjs';
const $=s=>document.querySelector(s);
const paths={box:'M12 3 3 8l9 5 9-5-9-5ZM3 8v10l9 5 9-5V8M12 13v10',truck:'M1 5h13v12H1ZM14 9h5l4 5v3h-9M8 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM21 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',check:'m5 12 4 4L19 6',scan:'M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5M7 12h10',arrow:'M4 12h16m-6-6 6 6-6 6',chevron:'m9 5 7 7-7 7',close:'m6 6 12 12M6 18 18 6',refresh:'M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 2l1 4M4 12l1 4a8 8 0 0 0 13 2',search:'M15 15 21 21M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z',info:'M12 11v6M12 7h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',alert:'m12 3 10 18H2L12 3ZM12 9v5M12 17h.01',pin:'M19 10c0 5-7 12-7 12S5 15 5 10a7 7 0 0 1 14 0ZM15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z'};
const icon=name=>`<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]||paths.box}"/></svg>`;
const formatDate=value=>value?new Date(value).toLocaleString('en-GB',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',timeZone:'Europe/Amsterdam'}):'Pending';
const token=parseToken(location.hash);
const demo=!token&&new URLSearchParams(location.search).get('demo')==='1';
const client=demo?createDemo():token?createClient(config,token):null;
let shipment=null,query='',filter='all',view='overview',busy=false,errorMessage='',lastRefresh=null;
let cameraStream=null,cameraRun=0,cameraStarting=false,scanBusy=false,scanMessage='',scanError=false;
let confirming=false,confirmationKind=null,confirmationPallet=null,driverName='',vehicle='',receiver='';
let expanded=new Set();
const app=$('#app');
function noShipment(title,text,retry=false) {
  app.setAttribute('aria-busy','false');
  app.innerHTML=`<section class="empty-state"><div class="empty-icon">${icon(retry?'alert':'scan')}</div><span class="eyebrow">DRIVER SHIPMENTS</span><h1>${esc(title)}</h1><p>${esc(text)}</p>${retry?`<button class="btn primary" data-action="refresh">${icon('refresh')}Try again</button>`:`<div class="empty-note">${icon('info')}Your shipment opens from the QR on the loading manifest.</div>`}<a class="text-link" href="?demo=1">Explore a demonstration ${icon('arrow')}</a></section>`;
}
function statusLabel() {return {ready:'Ready for loading',collected:'In transit',partial:'Partial pickup · in transit',delivered:'Delivered',cancelled:'Cancelled'}[shipment.status]||'Shipment';}
function render() {
  if(!shipment)return;
  const c=totals(shipment),ready=shipment.status==='ready',delivered=shipment.status==='delivered';
  const progress=ready?c.scanned:delivered?c.delivered:c.collected;
  app.setAttribute('aria-busy','false');
  app.innerHTML=`<div class="page-top"><div class="breadcrumb">Driver portal <span>/</span> Shipment</div><button class="text-link refresh-link" data-action="refresh" ${busy?'disabled':''}>${icon('refresh')}Refresh status</button></div>
    <div class="heading"><div><span class="eyebrow">SHIPMENT MANIFEST</span><h1>Your shipment</h1><p class="reference">${esc(shipment.id)} <span>·</span> Revision ${shipment.revision}</p></div><span class="status-pill ${ready?'ready':delivered?'delivered':'transit'}"><span class="status-dot"></span>${statusLabel()}</span></div>
    ${errorMessage?`<div class="notice error" role="alert">${icon('alert')}<span>${esc(errorMessage)}</span></div>`:''}
    <div class="workspace-grid"><div class="main-column"><section class="destination-card"><div class="destination-copy"><span class="eyebrow">DESTINATION</span><h2>${esc(shipment.building)}</h2><p>${esc([...new Set(shipment.pallets.map(p=>p.destination?.shipTo).filter(Boolean))].join(' · '))}</p></div><div class="destination-symbol">${icon('pin')}</div><div class="destination-bottom"><span>${icon('truck')}Internal transport</span><span>${c.planned} ${c.planned===1?'pallet':'pallets'} planned</span></div></section>
    <section class="numbers" aria-label="Shipment totals">${[[c.planned,'Pallets','box'],[c.dns,'Deliveries','truck'],[c.hus,'Handling units','scan']].map(([n,label,i])=>`<div><span class="number-icon">${icon(i)}</span><strong>${n}</strong><span>${label}</span></div>`).join('')}</section>
    <section class="card journey"><div class="section-heading"><h2>Shipment journey</h2><span>Netherlands time</span></div><ol class="timeline">${[['Prepared',shipment.createdAt,true],['Picked up',shipment.collectedAt,Boolean(shipment.collectedAt)],['Delivered',shipment.deliveredAt,delivered]].map(([title,at,done],i)=>`<li class="${done?'done':''}"><span class="step-circle">${done?icon('check'):i+1}</span><div><b>${title}</b><small>${formatDate(at)}</small></div></li>`).join('')}</ol></section>
    <section class="card contents"><div class="section-heading contents-heading"><div><h2>Pallets & deliveries</h2><p>Check the DN and HU on each pallet.</p></div><button class="text-link" data-action="toggle-view">${view==='contents'?'Compact view':'View all details'} ${icon('chevron')}</button></div><label class="search"><span class="sr-only">Search pallet, DN or HU</span>${icon('search')}<input id="pallet-search" value="${esc(query)}" placeholder="Search pallet, DN or HU" autocomplete="off"></label><div class="filters" role="group" aria-label="Pallet filter">${[['all',`All (${c.planned})`],['scanned',`${ready?'Scanned':'Collected'} (${c.scanned})`],['remaining',`${ready?'Remaining':'Not collected'} (${c.planned-c.scanned})`]].map(([key,label])=>`<button data-action="filter" data-filter="${key}" class="${filter===key?'active':''}">${label}</button>`).join('')}</div><div id="pallet-list">${renderPallets()}</div></section></div>
    <aside class="side-column"><section class="card action-card"><span class="eyebrow">${ready?'LOADING CHECK':delivered?'DELIVERY COMPLETE':'NEXT STEP'}</span><h2>${ready?'Scan before you load':delivered?'Shipment delivered':'Confirm arrival'}</h2><p>${ready?'Scan every pallet going onto your truck. You can leave pallets behind if they don’t fit.':delivered?'The collected pallets are confirmed delivered. The warehouse can see the updated status.':'At the destination, confirm the building and who received the pallets.'}</p><div class="progress-number"><strong>${progress}</strong><span>/ ${ready?c.planned:c.collected}</span><small>${ready?'pallets scanned':delivered?'pallets delivered':'pallets collected'}</small></div><progress value="${progress}" max="${Math.max(1,ready?c.planned:c.collected)}" aria-label="${ready?'Scanning':'Shipment'} progress"></progress>
    ${ready?`<button class="btn primary wide scan-button" data-action="open-scanner">${icon('scan')}${c.scanned?'Continue scanning':'Scan pallets'}${icon('arrow')}</button><button class="btn secondary wide" data-action="pickup" ${!c.scanned?'disabled':''}>Confirm pickup · ${c.scanned} pallets</button><div class="helper">${icon('info')}Only scanned pallets will be marked collected.</div>`:delivered?`<div class="success-note">${icon('check')}Delivery recorded ${formatDate(shipment.deliveredAt)}</div>`:`<button class="btn primary wide" data-action="delivery">${icon('pin')}Confirm delivery${icon('arrow')}</button><div class="helper">${icon('info')}Confirm only when the pallets have arrived at ${esc(shipment.building)}.</div>`}
    ${!ready&&c.collected<c.planned?`<div class="partial-note"><b>${c.planned-c.collected} pallets stayed behind</b><span>They remain available for another truck.</span></div>`:''}</section><section class="support-card">${icon('info')}<div><b>Something doesn’t match?</b><p>Check with warehouse dispatch before moving the pallet.</p></div></section><p class="last-updated">Status checked ${lastRefresh?lastRefresh.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}):'just now'}</p></aside></div>`;
}
function renderPallets() {
  const ps=filterPallets(shipment,query,filter),ready=shipment.status==='ready';
  if(!ps.length)return '<div class="list-empty">No pallets match this search.</div>';
  return ps.map(p=>{
    const lines=(p.forms||[]).flatMap(f=>f.lines||[]),dns=[...new Set(lines.map(l=>l.dn).filter(Boolean))];
    const open=view==='contents'||expanded.has(p.id),done=ready?p.scannedAt:p.collectedAt;
    const label=p.deliveredAt?'Delivered':p.collectedAt?'Collected':p.scannedAt?'Scanned':ready?'Awaiting scan':'Not collected';
    return `<article class="pallet-item ${done?'is-scanned':''}"><button class="pallet-summary" data-action="expand" data-id="${esc(p.id)}" aria-expanded="${open}"><span class="pallet-icon">${icon(done?'check':'box')}</span><span class="pallet-name"><b>${esc(p.id)}</b><small>${esc(p.destination?.shipTo||shipment.building)} · ${dns.length} ${dns.length===1?'DN':'DNs'} · ${lines.filter(l=>l.hu).length} HUs</small></span><span class="pallet-status ${done?'ok':''}">${label}</span><span class="expand-icon ${open?'expanded':''}">${icon('chevron')}</span></button>${open?`<div class="pallet-details"><div class="table-scroll"><table><thead><tr><th>Delivery number</th><th>Handling unit</th><th>Qty</th></tr></thead><tbody>${lines.map(l=>`<tr><td>${esc(l.dn)||'—'}</td><td>${esc(l.hu)||'—'}</td><td>${esc(l.qty)||'—'}</td></tr>`).join('')}</tbody></table></div><div class="pallet-detail-footer"><span>Document revision ${p.revision}${p.scannedAt?' · Scanned '+formatDate(p.scannedAt):''}</span>${ready&&p.scannedAt?`<button class="text-link danger-text" data-action="unscan" data-id="${esc(p.id)}">Remove from truck</button>`:''}</div></div>`:''}</article>`;
  }).join('');
}
function linkUnavailable(error) {
  if(error?.code!=='42501'&&!/Invalid or expired driver link|Superseded manifest/i.test(error?.message||''))return false;
  shipment=null;stopCamera();$('#scanner').close();$('#confirmation').close();noShipment('Shipment link unavailable',friendlyError(error),true);return true;
}
function toast(text) {$('#toast').textContent=text;$('#toast').classList.add('visible');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').classList.remove('visible'),4500);}
async function refresh(quiet=false) {
  if(!client||busy)return;
  try {shipment=await client();lastRefresh=new Date();errorMessage='';render();if($('#scanner').open)updateScanner();if(!quiet)toast('Shipment status updated.');}
  catch(error){errorMessage=friendlyError(error);if(linkUnavailable(error))return;if(shipment)render();else noShipment('Shipment unavailable',errorMessage,true);}
}
async function mutate(action,payload) {
  if(busy)throw Object.assign(new Error('An update is already in progress. Please wait.'),{local:true});
  busy=true;
  try {shipment=await client(action,payload);lastRefresh=new Date();errorMessage='';render();return shipment;}
  catch(error){
    if(linkUnavailable(error))throw error;
    try {shipment=await client();lastRefresh=new Date();render();}catch(refreshError){linkUnavailable(refreshError);}
    throw error;
  } finally {busy=false;const refreshButton=$('[data-action="refresh"]');if(refreshButton)refreshButton.disabled=false;}
}
function feedback(message,isError=false) {
  scanMessage=message;scanError=isError;
  const el=$('#scan-feedback');if(el){el.className='scanner-feedback '+(isError?'bad':'good');el.innerHTML=icon(isError?'alert':'check')+`<span>${esc(message)}</span>`;el.setAttribute('role',isError?'alert':'status');}
}
function updateScanner() {
  if(!shipment||!$('#scan-count'))return;
  const c=totals(shipment);$('#scan-count').textContent=c.scanned;$('#scan-total').textContent='/ '+c.planned;
  $('#scan-progress').value=c.scanned;$('#scan-progress').max=c.planned;
  $('#scanner-pickup').textContent=`Confirm pickup · ${c.scanned} pallets`;$('#scanner-pickup').disabled=!c.scanned||shipment.status!=='ready'||busy;
  if(shipment.status!=='ready'){stopCamera();feedback('This pickup has been confirmed. Close the scanner to view the current status.');}
  if(demo&&$('#demo-next'))$('#demo-next').disabled=c.scanned===c.planned;
}
function openScanner() {
  if(shipment.status!=='ready')return;
  stopCamera();scanMessage='Ready to scan. Start the camera or use a connected QR scanner.';scanError=false;
  const el=$('#scanner');el.innerHTML=`<div class="modal-head"><div><span class="eyebrow">${esc(shipment.building)}</span><h2 id="scanner-title">Scan your pallets</h2></div><button class="icon-button" data-action="close-scanner" aria-label="Close scanner">${icon('close')}</button></div><div class="scanner-body"><div class="scanner-tally"><div><strong id="scan-count">0</strong><span id="scan-total"></span><small>pallets scanned</small></div><span class="scanner-tag">${icon('box')}Loading check</span></div><progress id="scan-progress" value="0" max="1" aria-label="Pallet scan progress"></progress><div class="camera-viewport"><video id="camera" playsinline muted></video><div class="camera-placeholder" id="camera-placeholder">${icon('scan')}<b>Camera ready when you are</b><span>Keep each QR steady inside the frame.</span></div><div class="camera-guide" hidden id="camera-guide"></div></div><div class="camera-actions"><button class="btn primary" id="start-camera" data-action="start-camera">${icon('scan')}Start camera</button><button class="btn secondary" data-action="stop-camera">Stop camera</button></div><div id="scan-feedback" class="scanner-feedback" aria-live="polite"></div><details class="manual-entry" ${demo?'open':''}><summary>Use a QR scanner or enter a code</summary><form id="scan-form"><label for="scan-input">Pallet QR code</label><div class="input-button"><input id="scan-input" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Scan a pallet QR, then press Enter"><button class="btn secondary" type="submit">Check</button></div></form></details>${demo?`<div class="demo-tools"><b>Demonstration controls</b><div><button class="btn secondary" id="demo-next" data-action="demo-scan">Scan next demo pallet</button><button class="text-link" data-action="demo-wrong">Try a wrong destination</button></div></div>`:''}</div><div class="modal-foot"><button class="btn secondary" data-action="close-scanner">Close scanner</button><button class="btn primary" id="scanner-pickup" data-action="pickup">Confirm pickup</button></div>`;
  el.showModal();updateScanner();feedback(scanMessage);if(demo)$('#scan-input').focus();
}
async function scan(value) {
  if(scanBusy||busy)return;
  scanBusy=true;
  try {const code=normalizeScan(value);const result=await mutate('scan',{code});updateScanner();const c=totals(result);feedback(result.duplicate?'Already scanned. This pallet is counted once.':`${c.scanned} of ${c.planned} pallets accepted.${c.scanned===c.planned?' All pallets scanned. Confirm pickup when loaded.':''}`);if(!result.duplicate)navigator.vibrate?.(70);if($('#scan-input'))$('#scan-input').value='';}
  catch(error){feedback(error.message?.startsWith('Scan a pallet QR')?error.message:friendlyError(error),true);updateScanner();}
  finally {scanBusy=false;updateScanner();}
}
function stopCamera() {
  cameraRun++;cameraStarting=false;cameraStream?.getTracks().forEach(t=>t.stop());cameraStream=null;
  if($('#camera'))$('#camera').srcObject=null;
  if($('#camera-placeholder'))$('#camera-placeholder').hidden=false;
  if($('#camera-guide'))$('#camera-guide').hidden=true;
  if($('#start-camera')){$('#start-camera').disabled=false;$('#start-camera').innerHTML=icon('scan')+'Start camera';}
}
async function startCamera() {
  if(cameraStarting)return;
  stopCamera();cameraStarting=true;const run=cameraRun;
  $('#start-camera').disabled=true;
  try {
    if(!navigator.mediaDevices?.getUserMedia)throw new Error('Camera access is unavailable. Open this page in your phone’s browser, or use a QR scanner.');
    const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280}},audio:false});
    if(run!==cameraRun||!$('#scanner').open){stream.getTracks().forEach(t=>t.stop());return;}
    cameraStream=stream;const video=$('#camera');video.srcObject=stream;await video.play();
    if(run!==cameraRun)return;
    $('#camera-placeholder').hidden=true;$('#camera-guide').hidden=false;
    const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d',{willReadFrequently:true});
    let lastCode='',lastAt=0,lastFrame=0;
    feedback('Camera is on. Scan each pallet QR; there’s no need to restart between scans.');
    const frame=async now=>{
      if(run!==cameraRun)return;
      if(now-lastFrame>180&&video.readyState>=2&&!scanBusy&&!busy){
        lastFrame=now;
        try {
          canvas.width=Math.min(video.videoWidth,720);canvas.height=Math.round(video.videoHeight*canvas.width/video.videoWidth);ctx.drawImage(video,0,0,canvas.width,canvas.height);
          const data=ctx.getImageData(0,0,canvas.width,canvas.height),result=window.jsQR(data.data,data.width,data.height,{inversionAttempts:'dontInvert'});
          if(result&&(result.data!==lastCode||now-lastAt>2500)){lastCode=result.data;lastAt=now;await scan(result.data);}
          if(!result)lastCode='';
        }catch{feedback('The camera could not read this frame. Hold the QR steady or enter its code below.',true);}
      }
      if(run===cameraRun)requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }catch(error){if(run!==cameraRun)return;stopCamera();const msg=error.name==='NotAllowedError'?'Camera permission was denied. Allow camera access in your browser settings, or use a QR scanner below.':error.name==='NotFoundError'?'No camera was found. Use a connected QR scanner or enter its code below.':error.message;feedback(msg,true);}
  finally {if(run===cameraRun){cameraStarting=false;if($('#start-camera')){$('#start-camera').disabled=false;$('#start-camera').innerHTML=icon('scan')+(cameraStream?'Restart camera':'Start camera');}}}
}
function openConfirmation(kind,palletId=null) {
  stopCamera();$('#scanner').close();confirmationKind=kind;confirmationPallet=palletId;
  const c=totals(shipment),partial=c.scanned<c.planned;
  const title=kind==='pickup'?(partial?'Confirm partial pickup':'Confirm pickup'):kind==='delivery'?'Confirm delivery':'Remove pallet from truck';
  const body=kind==='pickup'?`<div class="confirmation-count">${c.scanned}<span> / ${c.planned} pallets</span></div><p>${partial?`Only the ${c.scanned} scanned pallets will be collected. The other ${c.planned-c.scanned} pallets stay ready for another truck.`:'Confirm all scanned pallets are physically on your truck.'}</p><div class="two-fields"><label>Your name<input name="driver" maxlength="200" value="${esc(driverName)}" autocomplete="name" required></label><label>Vehicle registration<input name="vehicle" maxlength="200" value="${esc(vehicle)}" autocomplete="off" required></label></div>${partial?'<label>Why are pallets staying behind?<textarea name="reason" maxlength="1000" rows="3" placeholder="For example: no space on the truck" required></textarea></label>':''}`:kind==='delivery'?`<p>Confirm the collected pallets have arrived at <b>${esc(shipment.building)}</b>.</p><label>Destination building<select name="building" required><option value="">Confirm the destination</option><option value="${esc(shipment.building)}">${esc(shipment.building)}</option></select></label><label>Received by<input name="receiver" maxlength="200" value="${esc(receiver)}" autocomplete="name" placeholder="Receiver’s name" required></label><label class="checkbox-label"><input name="arrival" type="checkbox" required>I confirm the pallets have arrived at this building.</label>`:`<p>Physically remove <b>${esc(palletId)}</b> from the truck before removing its scan.</p><label>Reason<textarea name="reason" maxlength="1000" rows="3" required></textarea></label>`;
  $('#confirmation').innerHTML=`<form id="confirm-form"><div class="modal-head"><h2 id="confirmation-title">${title}</h2><button class="icon-button" data-action="cancel-confirm" type="button" aria-label="Close confirmation">${icon('close')}</button></div><div class="confirmation-body">${body}<div id="confirmation-error" class="notice error" role="alert" hidden></div></div><div class="modal-foot"><button class="btn secondary" data-action="cancel-confirm" type="button">Cancel</button><button class="btn primary" id="confirm-submit" type="submit">${kind==='pickup'?'Confirm pickup':kind==='delivery'?'Confirm delivery':'Remove scan'}${icon('check')}</button></div></form>`;
  $('#confirmation').showModal();
}
async function confirm(form) {
  if(busy||confirming||!form.reportValidity())return;
  confirming=true;
  const values=Object.fromEntries(new FormData(form));
  const button=$('#confirm-submit');button.disabled=true;
  try {
    const previous=structuredClone(shipment);await refresh(true);
    if(!shipment||errorMessage)throw Object.assign(new Error(errorMessage),{local:true});
    if(shipment.rowVersion!==previous.rowVersion){render();throw Object.assign(new Error('This shipment changed while the form was open. Close this form, review the current pallets and confirm again.'),{local:true});}
    if(confirmationKind==='pickup'){
      driverName=values.driver;vehicle=values.vehicle;const payload=validatePickup(shipment,{driver:driverName,vehicle,reason:values.reason||''});await mutate('confirm_pickup',payload);
    }else if(confirmationKind==='delivery'){
      receiver=values.receiver;await mutate('confirm_delivery',{building:values.building,receiver,expectedRowVersion:shipment.rowVersion});
    }else await mutate('unscan',{palletId:confirmationPallet,reason:values.reason,expectedRowVersion:shipment.rowVersion});
    $('#confirmation').close();toast(confirmationKind==='pickup'?'Pickup recorded. Safe journey.':confirmationKind==='delivery'?'Delivery recorded. Thank you.':'Pallet removed from this pickup.');
  }catch(error){$('#confirmation-error').hidden=false;$('#confirmation-error').textContent=friendlyError(Object.assign(error,{local:error.local||/Scan at least one|Enter your name|Tell the warehouse|already been confirmed/.test(error.message)}));}
  finally {confirming=false;button.disabled=false;}
}
document.addEventListener('click',async event=>{
  const b=event.target.closest('[data-action]');if(!b||b.disabled)return;
  try {
    const action=b.dataset.action;
    if(action==='refresh')await refresh();
    if(action==='filter'){filter=b.dataset.filter;render();}
    if(action==='expand'){expanded.has(b.dataset.id)?expanded.delete(b.dataset.id):expanded.add(b.dataset.id);$('#pallet-list').innerHTML=renderPallets();}
    if(action==='toggle-view'){view=view==='contents'?'overview':'contents';render();}
    if(action==='open-scanner')openScanner();
    if(action==='close-scanner'){$('#scanner').close();stopCamera();}
    if(action==='start-camera')await startCamera();
    if(action==='stop-camera'){stopCamera();feedback('Camera stopped. You can still use the code field below.');}
    if(action==='pickup'){if(!totals(shipment).scanned){toast('Scan at least one pallet first.');return;}openConfirmation('pickup');}
    if(action==='delivery')openConfirmation('delivery');
    if(action==='unscan')openConfirmation('unscan',b.dataset.id);
    if(action==='cancel-confirm')$('#confirmation').close();
    if(action==='demo-scan'){const p=shipment.pallets.find(p=>!p.scannedAt);if(p)await scan(`TO:PALLET:${p.id}:${p.revision}`);}
    if(action==='demo-wrong')await scan('TO:PALLET:P-DEMO-WRONG:1');
  }catch(error){toast(friendlyError(error));}
});
document.addEventListener('submit',event=>{if(event.target.id==='scan-form'){event.preventDefault();scan($('#scan-input').value);}if(event.target.id==='confirm-form'){event.preventDefault();confirm(event.target);}});
document.addEventListener('input',event=>{if(event.target.id==='pallet-search'){query=event.target.value;$('#pallet-list').innerHTML=renderPallets();}});
$('#scanner').addEventListener('close',stopCamera);$('#scanner').addEventListener('cancel',stopCamera);
window.addEventListener('pagehide',stopCamera);
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopCamera();});
window.addEventListener('hashchange',()=>{stopCamera();location.reload();});
if(demo){$('#demo-banner').hidden=false;$('#demo-banner').textContent='DEMONSTRATION · Fictional shipment. Nothing is saved.';}
if(!client)noShipment(location.hash?'This shipment link isn’t valid':'Open your shipment QR',location.hash?'Ask warehouse dispatch for the current loading manifest QR.':'Scan the QR on your loading manifest to view the shipment and start loading.');
else await refresh(true);
setInterval(()=>{if(client&&!document.hidden&&!$('#confirmation').open&&!busy&&!scanBusy)refresh(true);},30000);
