"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const esc = escapeHtml;
const paths = {
  sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1 1M18 18l1 1M5 19l1-1M18 6l1-1"/>',
  moon:'<path d="M20 14A9 9 0 0 1 10 3a9 9 0 1 0 10 11Z"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  form:'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
  database:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
  box:'<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="M3 8v10l9 5 9-5V8M12 13v10M7 5.8l9 5"/>',
  history:'<path d="M3 12a9 9 0 1 0 2.7-6.4L3 8M3 3v5h5M12 7v5l3 2"/>',
  settings:'<path d="m9 3-.7 3-2 .9L3.5 6l-2 3.5 2.3 2.1v2.3l-2 2.1 2 3.5 2.8-.9 2 .9.7 3h4l.7-3 2-.9 2.8.9 2-3.5-2.3-2.1v-2.3l2.3-2.1-2-3.5-2.8.9-2-.9-.7-3Z"/><circle cx="11" cy="12" r="3"/>',
  arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  refresh:'<path d="M20 7v5h-5M4 17v-5h5M6.1 6.1A8 8 0 0 1 19 8l1 4M4 12l1 4a8 8 0 0 0 12.9 1.9"/>',
  print:'<path d="M6 8V3h12v5M6 17H3V9h18v8h-3M6 14h12v7H6Z"/><path d="M17 11h1"/>',
  save:'<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2ZM7 3v6h10V3M7 21v-8h10v8"/>',
  trash:'<path d="M3 6h18M8 6V3h8v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/>',
  upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  download:'<path d="M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  alert:'<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5M12 17h.01"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  chevron:'<path d="m8 5 7 7-7 7"/>',
  edit:'<path d="m16 3 5 5-12 12-6 1 1-6L16 3ZM13 6l5 5"/>',
  power:'<path d="M12 2v10M6 5a9 9 0 1 0 12 0"/>',
  truck:'<path d="M1 5h13v12H1ZM14 9h5l4 5v3h-9"/><circle cx="5" cy="18" r="3"/><circle cx="18" cy="18" r="3"/>',
  link:'<path d="m10 13 4-4M8 15l-2 2a4 4 0 0 1-5-5l5-5a4 4 0 0 1 6 0m0 2 2-2a4 4 0 0 1 5 5l-5 5a4 4 0 0 1-6 0"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.form}</svg>`;
const formatDate = value => value ? new Date(value).toLocaleString("en-GB", {day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}) : "Not imported";
const nfmt = value => new Intl.NumberFormat("en-GB", {maximumFractionDigits:6}).format(Number(value || 0));
const emptyLocation = () => ({building:"",department:"",shipTo:""});
const emptyLine = () => ({part:"",description:"",qty:"",hu:"",dn:""});
const activeForms = palletId => state.forms.filter(f => !f.removedAt && (!palletId || f.palletId === palletId));
const palletForms = id => state.forms.filter(f => f.palletId === id && !f.removedAt);
const counts = forms => ({hus:new Set(forms.flatMap(f=>f.lines.map(l=>l.hu).filter(Boolean))).size, dns:new Set(forms.flatMap(f=>f.lines.map(l=>l.dn).filter(Boolean))).size});
const statusPill = (status, removed=false) => `<span class="pill ${removed ? "removed" : status === "open" ? "open" : status === "draft" ? "draft" : ""}">${removed ? "Removed" : ({open:"Open pallet",finalised:"Ready for pick-up",draft:"Draft",complete:"Complete"}[status] || esc(status))}</span>`;

let token = new URLSearchParams(location.hash.slice(1)).get("session") || sessionStorage.getItem("transport-order.token") || "";
if (token) sessionStorage.setItem("transport-order.token", token);
if (location.hash.includes("session=")) history.replaceState(null, "", "/");
let state, directory, diagnostics, providers, view = "create", selectedPallet = null, editor, dirty = false, busy = false;
let originExpanded = false, receiverExpanded = false, bulkExpanded = false, resolving = 0, resolveResult = null;
let filter = "all", historyTab = "forms", search = "", dialogCallback = null, previewDocument = null;
const GRID_HEADERS = {
  shipto:["Outbound Delivery Order","ERP Document","Handling Unit","Number of Items","Ship-To","Storage Bin","Number of Handling Units","Shipping Condition","Changed On","Changed At","Storage Type","External Delivery ID"],
  quantities:["Document","Handling Unit","Quantity"]
};
const gridDraft = kind => ({text:"",decimalMark:".",grid:[[...GRID_HEADERS[kind]]],gridPage:0});
const imports = {shipto:gridDraft("shipto"),quantities:gridDraft("quantities")};
let printerInfo = {supported:null,printers:[],defaultPrinter:"",error:""}, pendingPrint = null, printingBusy = false;

function applyTheme(theme = state?.settings.theme || "light") {
  const dark = theme === "dark" || (theme === "system" && window.matchMedia?.("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  const button = $("#theme-button");
  if(button) { button.innerHTML=icon(dark?"sun":"moon");button.title=dark?"Switch to light mode":"Switch to dark mode";button.setAttribute("aria-label",button.title); }
}

async function loadPrinters() {
  try { printerInfo={...await api("printers"),error:""}; }
  catch(error) { printerInfo={supported:true,printers:[],defaultPrinter:"",error:error.message}; }
}

function parseGridClipboard(text) {
  text=text.replace(/^\uFEFF/,"");
  const first=text.split(/\r?\n/)[0];
  const delimiter=!/[\n\r\t]/.test(text)?"\t":text.includes("\t")?"\t":first.includes(";")?";":first.includes("|")?"|":",";
  const rows=[];let row=[],value="",quoted=false;
  for(let i=0;i<text.length;i++) {
    const c=text[i];
    if(c==='"'&&(quoted||!value)) { if(quoted&&text[i+1]==='"'){value+='"';i++;}else quoted=!quoted; }
    else if(c===delimiter&&!quoted){row.push(value);value="";}
    else if((c==="\n"||c==="\r")&&!quoted){if(c==="\r"&&text[i+1]==="\n")i++;row.push(value);rows.push(row);row=[];value="";}
    else value+=c;
  }
  if(value||row.length){row.push(value);rows.push(row);}
  return rows.map(row=>delimiter==="|"?row.slice(!row[0]?.trim()?1:0,!row.at(-1)?.trim()?-1:undefined):row).filter(row=>row.some(v=>v.trim())&&!row.every(v=>/^[-+ =]*$/.test(v)));
}

function isGridHeader(row) {
  const cells=row.map(v=>v.toLowerCase().replace(/[^a-z0-9]/g,""));
  return cells.some(v=>["handlingunit","hu"].includes(v)) && cells.some(v=>["document","outbounddeliveryorder","erpdocument","doc"].includes(v));
}

function gridText(rows) {
  return rows.filter(row=>row.some(v=>String(v).trim())).map(row=>row.map(v=>/[\t\n\r"]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v).join("\t")).join("\n");
}

function pasteGrid(kind,text,row=1,column=0) {
  const values=parseGridClipboard(text), draft=imports[kind];
  if(!values.length)return;
  if(column===0&&isGridHeader(values[0])){row=0;draft.grid=[];}
  else if(row===0&&column===0)row=1;
  if(row+values.length>50001||column+Math.max(...values.map(r=>r.length))>100)throw new Error("Use at most 50,000 data rows and 100 columns.");
  for(let r=0;r<values.length;r++) {
    draft.grid[row+r] ||= [];
    for(let c=0;c<values[r].length;c++)draft.grid[row+r][column+c]=values[r][c];
  }
  delete draft.fileBase64;delete draft.filename;draft.text="";draft.gridPage=Math.floor(Math.max(row-1,0)/50);
}

function columnLetter(index) {
  let result="";for(index++;index;index=Math.floor((index-1)/26))result=String.fromCharCode(65+(index-1)%26)+result;return result;
}

function sourceGrid(kind) {
  const draft=imports[kind], grid=draft.grid, columns=Math.max(GRID_HEADERS[kind].length,...Array.from(grid,row=>row?.length||0)), page=draft.gridPage||0;
  const total=Math.max(12,grid.length-1), start=page*50+1, end=Math.min(start+50,total+1);
  const cell=(row,col)=>`<td><input data-grid="${kind}" data-grid-row="${row}" data-grid-column="${col}" aria-label="${kind} cell ${columnLetter(col)}${row+1}" value="${esc(grid[row]?.[col]||"")}" autocomplete="off" spellcheck="false"></td>`;
  return `<div class="sap-grid-wrap"><table class="sap-grid" aria-label="${kind} SAP input cells"><thead><tr><th></th>${Array.from({length:columns},(_,c)=>`<th>${columnLetter(c)}</th>`).join("")}</tr><tr class="sap-headers"><th>1</th>${Array.from({length:columns},(_,c)=>cell(0,c)).join("")}</tr></thead><tbody>${Array.from({length:Math.max(0,end-start)},(_,i)=>{const r=start+i;return `<tr><th>${r+1}</th>${Array.from({length:columns},(_,c)=>cell(r,c)).join("")}</tr>`;}).join("")}</tbody></table></div><div class="grid-toolbar"><span>${grid.slice(1).filter(r=>r.some(v=>String(v).trim())).length} pasted rows · click a cell and press Ctrl+V</span><div class="inline-actions"><button class="btn small" data-action="grid-page" data-kind="${kind}" data-step="-1" ${page===0?"disabled":""}>Previous</button><span>${page+1} / ${Math.ceil(total/50)}</span><button class="btn small" data-action="grid-page" data-kind="${kind}" data-step="1" ${end>total?"disabled":""}>Next</button><button class="btn small" data-action="clear-grid" data-kind="${kind}">Clear cells</button></div></div>`;
}

function newEditor(palletId = selectedPallet) {
  const pallet = state.pallets.find(p=>p.id===palletId && p.status==="open");
  const existing = pallet ? palletForms(pallet.id)[0] : null;
  return {id:null,palletId:pallet?.id || null,mode:"automatic",origin:structuredClone(existing?.origin || state.settings.origin),destination:structuredClone(pallet?.destination || emptyLocation()),preparedBy:state.settings.preparedBy,lines:Array.from({length:5},emptyLine),remarks:"",receiverPhone:"",receiverEmail:"",manualEmergency:false,specialPickup:false,automaticEmergency:false,overrideReason:"",destinationOverride:false};
}

async function api(path, payload, raw=false) {
  const response = await fetch("/api/" + path, {method:payload === undefined ? "GET" : "POST",headers:{"X-Session-Token":token,...(payload === undefined ? {} : {"Content-Type":"application/json"})},...(payload === undefined ? {} : {body:JSON.stringify(payload)})});
  if (!response.ok) {
    const body = await response.json().catch(()=>({error:"The local application is unavailable."}));
    throw new Error(body.error || "The operation failed.");
  }
  return raw ? response.text() : response.json();
}

async function loadState() {
  const result = await api("state");
  state = result.state; directory = result.locations; diagnostics = result.diagnostics; providers = result.providers;
  $("#app-version").textContent = "TransportOrder " + result.version;
  updateShell();
}

function updateShell() {
  applyTheme();
  const items = [["create","form","Create order"],["infeed","database","Data infeed"],["open-orders","truck","Open orders"],["pallets","box","Pallets"],["history","history","History"],["settings","settings","Settings"]];
  $("#navigation").innerHTML = items.map(([id,ico,label])=>`<button class="nav-item ${view===id?"active":""}" data-action="navigate" data-view="${id}" title="${label}" ${view===id?'aria-current="page"':''}>${icon(ico)}<span>${label}</span>${id==="pallets"&&state.pallets.some(p=>p.status==="open")?`<b class="nav-count">${state.pallets.filter(p=>p.status==="open").length}</b>`:""}</button>`).join("");
  $("#page-label").textContent = items.find(i=>i[0]===view)?.[2] || "Create order";
  const ready = state.sources.shipto && state.sources.quantities;
  $("#source-health").className = "health-chip" + (ready ? "" : " warning");
  $("#source-health").innerHTML = icon(ready?"check":"database") + (ready ? "SAP tables loaded" : "SAP data needed");
  const name = state.settings.preparedBy || "Shipping user";
  $("#user-label").innerHTML = esc(name) + "<small>Delivery Operations</small>";
  $("#avatar").textContent = state.settings.preparedBy ? name.slice(0,2).toUpperCase() : "DO";
}

function heading(eyebrow, title, subtitle, action="") {
  return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${subtitle}</p></div>${action || `<span class="date-label">${icon("calendar")}${new Date().toLocaleDateString("en-GB",{day:"2-digit",month:"short",year:"numeric"})}</span>`}</div>`;
}

function stats() {
  const forms = activeForms(), c = counts(forms);
  return `<div class="stats">${[
    ["Open pallets",state.pallets.filter(p=>p.status==="open").length,"Consolidations in preparation","box",true],
    ["Ready for pick-up",state.pallets.filter(p=>p.status==="finalised").length,"Finalised in this workspace","truck"],
    ["Transport forms",forms.filter(f=>f.status==="complete").length,`${forms.filter(f=>f.status==="draft").length} drafts saved for later`,"form"],
    ["Handling units",c.hus,`${c.dns} unique delivery numbers`,"grid"]
  ].map(([label,value,note,ico,featured])=>`<div class="stat ${featured?"stat-featured":""}"><div class="stat-label">${label}${icon(ico)}</div><div class="stat-value">${String(value).padStart(2,"0")}</div><div class="stat-note">${note}</div></div>`).join("")}</div>`;
}

function locationFields(prefix, value, source="toLocations") {
  const locations = directory[source];
  const options = key => [...new Set(locations.filter(l=>(key==="building" || !value.building || l.building===value.building) && (key!=="shipTo" || !value.department || l.department===value.department)).map(l=>l[key]))].sort().map(v=>`<option value="${esc(v)}"></option>`).join("");
  return `<div class="fields">${[["building","Building","Select or type a building"],["department","Department","Select or type a department"],["shipTo",prefix==="origin"?"Ship-from":"Ship-to","SAP code or location"]].map(([key,label,placeholder])=>`<label>${prefix==="origin"?"From":"To"} ${label.toLowerCase()} <span class="required">*</span><input name="${prefix}.${key}" data-field="${prefix}.${key}" value="${esc(value[key])}" list="${prefix}-${key}" placeholder="${placeholder}" autocomplete="off"><datalist id="${prefix}-${key}">${options(key)}</datalist></label>`).join("")}</div>`;
}

function rowHtml(line, index) {
  const errors = line.issues?.filter(i=>i.code==="error") || [];
  const readonly = editor.mode==="automatic";
  return `<tr><td class="row-num">${String(index+1).padStart(2,"0")}</td>${["part","description","qty","hu","dn"].map(field=>`<td><input aria-label="${{part:"12NC",description:"Description",qty:"Quantity",hu:"HU",dn:"DN"}[field]} row ${index+1}" data-line="${index}" data-line-field="${field}" value="${esc(line[field])}" placeholder="${{part:"Part number",description:"Material description",qty:"0",hu:"Enter HU",dn:"Delivery nr."}[field]}" ${readonly&&["qty","dn"].includes(field)?"readonly":""} ${field==="qty"?'inputmode="decimal"':''} class="${errors.length&&field==="hu"?"invalid":""}" autocomplete="off">${field==="hu"&&line.sourceShipTo?`<span class="row-source ${line.emergency?"emergency":""}">${esc(line.sourceShipTo)}${line.emergency?" · Emergency":""}</span>`:""}${field==="qty"&&line.quantityRecords>1?`<span class="row-source">${line.quantityRecords} items summed</span>`:""}</td>`).join("")}<td><button class="icon-button row-delete" data-action="remove-line" data-index="${index}" title="Remove row ${index+1}" aria-label="Remove row ${index+1}">${icon("close")}</button></td></tr>${errors.length?`<tr class="row-error"><td colspan="7">${[...new Set(errors.map(i=>i.message))].map(esc).join("<br>")}</td></tr>`:""}`;
}

function renderCreate() {
  const pallet = state.pallets.find(p=>p.id===selectedPallet);
  const missingData = !state.sources.shipto || !state.sources.quantities;
  return heading("Shipment workspace",editor.id?"Edit transport order":"Prepare a transport order","Build the order, check its destination and keep your pallet moving.") + stats() +
    `<div class="work-grid"><div class="form-column">${editor.id?`<div class="banner">${icon("edit")}Editing ${esc(editor.id)} · ${editor.mode==="automatic"?"SAP lookups will be checked again when saved.":"Manual values are preserved."}<button class="subtle-button" data-action="new-form">New form</button></div>`:""}
    ${missingData&&editor.mode==="automatic"?`<div class="banner warn">${icon("database")}Load the two SAP tables to fill destination, quantity and DN automatically.<button class="subtle-button" data-action="navigate" data-view="infeed">Data infeed ${icon("arrow")}</button></div>`:""}
    <section class="card"><div class="card-head"><div class="card-title"><span class="card-number">01</span><h2>Shipment details</h2></div><div class="segmented" aria-label="Entry mode"><button data-action="mode" data-mode="automatic" class="${editor.mode==="automatic"?"selected":""}" aria-pressed="${editor.mode==="automatic"}">Automatic</button><button data-action="mode" data-mode="manual" class="${editor.mode==="manual"?"selected":""}" aria-pressed="${editor.mode==="manual"}">Manual</button></div></div>
    <div class="card-body"><div class="route-strip"><div class="route-end"><small>SHIP FROM</small><strong id="route-from">${esc(editor.origin.building || "Select origin")}</strong><span>${esc(editor.origin.department || "Origin department")}</span></div><div class="route-track">${icon("truck")}</div><div class="route-end"><small>SHIP TO</small><strong id="route-to">${esc(editor.destination.building || "Awaiting HUs")}</strong><span>${esc(editor.destination.department || (editor.mode==="automatic"?"Filled from SAP data":"Select a destination"))}</span></div></div>
    ${locationFields("destination",editor.destination)}
    <div class="quick-routes"><span>Quick select</span>${[["Weert 1A","Weert 1A"],["Weert 2","Weert 2"],["BLD 21","Building 21"],["BLD 30","Building 30"],["BLD 58","Building 58"],["Other","all"]].map(([text,building])=>`<button class="route-chip" data-action="presets" data-building="${building}">${text}</button>`).join("")}</div>
    <button class="subtle-button origin-toggle" data-action="origin">${icon("edit")}${originExpanded?"Hide":"Edit"} origin &amp; prepared by</button>
    ${originExpanded?`<div class="origin-fields">${locationFields("origin",editor.origin,"fromLocations")}<label class="mt">Prepared by<input data-field="preparedBy" value="${esc(editor.preparedBy)}" placeholder="Your username"></label></div>`:""}
    ${editor.mode==="automatic"&&editor.destinationOverride?`<label class="override">Destination override reason<input data-field="overrideReason" value="${esc(editor.overrideReason)}" placeholder="Required if changing or manually resolving a SAP route"><span class="field-hint">The original SAP ship-to is retained on each HU.</span></label>`:""}
    </div></section>
    <section class="card"><div class="card-head"><div class="card-title"><span class="card-number">02</span><h2>Materials &amp; handling units</h2></div><button class="subtle-button" data-action="bulk">${icon("plus")}Paste HUs</button></div>
    ${bulkExpanded?`<div class="paste-panel"><label>Paste one or more HU numbers<textarea id="bulk-hus" placeholder="One HU per line, or separated by spaces, commas or semicolons"></textarea></label><div class="inline-actions"><button class="btn primary small" data-action="add-hus">Add &amp; look up</button><span class="field-hint">Each HU becomes one row. Quantities are summed automatically.</span></div></div>`:""}
    <div class="table-wrap"><table class="material-table"><thead><tr><th>#</th><th>12NC / Part nr.</th><th>Description</th><th>Qty</th><th>Handling unit</th><th>DN</th><th></th></tr></thead><tbody id="material-rows">${editor.lines.map(rowHtml).join("")}</tbody></table></div>
    <div class="table-bottom"><button class="subtle-button" data-action="add-line">${icon("plus")}Add material row</button><span class="table-totals" id="line-totals">${lineTotals()}</span></div>
    ${editor.mode==="automatic"?`<div class="card-body" style="padding-top:0;padding-bottom:14px"><button class="btn small" data-action="resolve">${icon("refresh")}Check HUs &amp; refresh fields</button><span class="field-hint">12NC and descriptions are entered manually. They are not in these SAP exports.</span></div>`:""}
    ${resolveResult?.issues.some(i=>i.code==="error")?`<div class="banner error" style="margin:0 18px 16px">${icon("alert")}Resolve the highlighted HU errors before completing this order.</div>`:""}
    </section>
    <section class="card"><div class="card-body"><div class="remarks-row"><label>Remarks &amp; handling</label><div class="inline-actions"><label class="check-label"><input type="checkbox" data-field="manualEmergency" ${editor.manualEmergency?"checked":""}>Emergency</label><label class="check-label"><input type="checkbox" data-field="specialPickup" ${editor.specialPickup?"checked":""}>Special pick-up</label></div></div>
    ${editor.automaticEmergency?`<div class="banner warn">${icon("alert")}Emergency detected from shipping condition S4 / I2. It will print alongside your remarks.</div>`:""}
    <textarea class="remarks-text" data-field="remarks" placeholder="Extra instructions or information for this transport…">${esc(editor.remarks)}</textarea>
    <button class="subtle-button mt" data-action="receiver">${icon("plus")}${receiverExpanded?"Hide":"Add"} receiver contact details</button>${receiverExpanded?`<div class="fields two receiver-fields"><label>Receiver telephone<input data-field="receiverPhone" value="${esc(editor.receiverPhone)}"></label><label>Receiver email<input type="email" data-field="receiverEmail" value="${esc(editor.receiverEmail)}"></label></div>`:""}</div></section>
    <div class="action-bar"><div class="action-inner"><button class="btn text" data-action="clear-form">Clear form</button><span class="spacer"></span><span class="draft-status" id="draft-status">${dirty?"Unsaved changes":pallet?"Adding to selected pallet":"New pallet on completion"}</span><button class="btn" data-action="save" data-intent="draft">${icon("save")}Save draft</button><button class="btn" data-action="save" data-intent="keep_open">${icon("print")}Print &amp; keep open</button><button class="btn primary" data-action="save" data-intent="finalise">Finalise pallet ${icon("arrow")}</button></div></div>
    </div><aside id="pallet-panel" class="pallet-panel" aria-label="Open pallets">${renderPalletPanel()}</aside></div>`;
}

function lineTotals() {
  const used = editor.lines.filter(l=>["hu","part","description","dn"].some(k=>l[k]));
  const hus = new Set(used.map(l=>l.hu).filter(Boolean));
  return `<b>${used.length}</b> rows &nbsp; / &nbsp; <b>${hus.size}</b> HUs &nbsp; / &nbsp; <b>${nfmt(used.reduce((s,l)=>s+(Number(l.qty)||0),0))}</b> qty`;
}

function palletCard(p, clickable="select-pallet") {
  const forms = palletForms(p.id), c = counts(forms), emergency = forms.some(f=>f.automaticEmergency||f.manualEmergency);
  return `<button class="pallet-card ${selectedPallet===p.id&&clickable==="select-pallet"?"selected":""}" data-action="${clickable}" data-id="${p.id}"><div class="pallet-card-heading"><div><strong>${esc(p.destination.building || "Destination pending")}</strong><div class="pallet-department">${esc(p.destination.department || "Draft consolidation")}</div></div><span class="pallet-mark">${icon("box")}</span></div><div class="pallet-id">${esc(p.id)} · ${esc(p.destination.shipTo)}</div><div class="pallet-card-footer"><span>${forms.length} forms · ${c.hus} HUs${emergency?" · Emergency":""}</span>${statusPill(p.status)}</div></button>`;
}

function renderPalletPanel() {
  const pallets = state.pallets.filter(p=>p.status==="open").sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt));
  const selected = pallets.find(p=>p.id===selectedPallet), forms = selected ? palletForms(selected.id) : [];
  return `<div class="panel-heading"><div><h2>Open pallets</h2><p>Pick a pallet to add another form</p></div><span class="count-badge">${pallets.length}</span></div><div class="pallet-list">${pallets.length?pallets.map(p=>palletCard(p)).join(""):`<div class="empty">${icon("box")}<strong>Your next pallet starts here</strong><p>Complete a form and keep it open<br>to build a consolidation.</p></div>`}</div>
    ${selected?`<div class="selected-forms"><h3>FORMS ON THIS PALLET</h3>${forms.length?forms.map(f=>`<div class="mini-form"><span>${esc(f.id)}<small>${f.lines.filter(l=>l.hu).length} HUs · ${esc(f.status)}</small></span><button class="icon-button" data-action="edit-form" data-id="${f.id}" title="Edit ${f.id}" aria-label="Edit ${f.id}">${icon("edit")}</button></div>`).join(""):`<p class="field-hint">No forms yet.</p>`}</div>`:""}
    <div class="panel-bottom">${selected?`<p>Adding to <b>${esc(selected.destination.building)}</b>. Forms must share the same destination and origin.</p><button class="btn primary wide" data-action="finalise-selected">Finalise selected pallet ${icon("check")}</button><button class="btn text wide" data-action="new-form" data-detach="true">Start a different pallet</button>`:`<p>Individual forms print without a QR. Finalise when the whole pallet is ready.</p><button class="new-pallet-target" data-action="new-form" data-detach="true">${icon("plus")} New pallet</button>`}</div>`;
}

function sourceCard(kind,title,description,headers) {
  const source=state.sources[kind],draft=imports[kind];
  return `<section class="card"><div class="card-head"><div><h2>${title}</h2><p>${description}</p></div>${icon("database")}</div><div class="card-body"><div class="source-indicator"><span><strong>${source?nfmt(source.count):"0"}</strong> loaded records · ${source?nfmt(source.uniqueHus):"0"} HUs</span><span>${source?formatDate(source.importedAt):"Not imported"}</span></div><div class="banner">${icon("info")}Paste data into any cell. Headers are prefilled; pasting a full table with SAP headers replaces the input cells.</div>${sourceGrid(kind)}<div class="source-options"><div class="inline-actions"><button class="btn small" data-action="clipboard-grid" data-kind="${kind}">${icon("save")}Paste from clipboard</button><button class="btn small" data-action="choose-file" data-kind="${kind}">${icon("upload")}Import file</button></div><input class="file-input" type="file" id="file-${kind}" data-file="${kind}" accept=".xlsx,.csv,.tsv,.txt"><label>Decimal separator<select data-decimal="${kind}"><option value="." ${draft.decimalMark==="."?"selected":""}>Point (1.5)</option><option value="," ${draft.decimalMark===","?"selected":""}>Comma (1,5)</option></select></label></div>${draft.filename?`<div class="banner">${icon("form")}${esc(draft.filename)}<button class="subtle-button" data-action="discard-file" data-kind="${kind}">Remove</button></div>`:""}<button class="btn primary wide" data-action="preview-import" data-kind="${kind}">Validate &amp; apply ${icon("arrow")}</button><div class="source-footer"><span>${source?esc(source.filename):"XLSX, CSV, TSV or clipboard cells"}</span><button class="subtle-button" data-action="clear-source" data-kind="${kind}" ${!source?"disabled":""}>Clear loaded data</button></div></div></section>`;
}

function renderInfeed() {
  const mismatch = diagnostics.missingQuantities.length + diagnostics.missingShipto.length;
  return heading("Data workspace","SAP data infeed","Paste your two SAP tables. Preview them, check the results, then apply.",`<button class="btn" data-action="demo">${icon("grid")}Load fictional demo</button>`) +
    `<div class="banner">${icon("info")}Import replaces one table at a time. Completed forms retain their saved values. Drafts use the latest data when completed.</div><div class="data-grid">${sourceCard("shipto","01 · Ship-to data","Destination, delivery number and shipping priority",["Outbound Delivery Order","ERP Document","Handling Unit","Ship-To","Shipping Condition","External Delivery ID"])}${sourceCard("quantities","02 · Quantities","Item quantities, summed per handling unit",["Document","Handling Unit","Quantity"])}</div>
    <div class="diagnostics card"><div class="card-body"><h2>Source consistency</h2><p class="mb0" style="font-size:11px">${!state.sources.shipto||!state.sources.quantities?"Load both tables to compare HU coverage.":mismatch?`${mismatch} HUs are missing from one source. Affected forms will be flagged.`:"Both tables contain the same HUs."}</p>${mismatch?`<details class="mt"><summary>Show unmatched HUs</summary><pre>Missing Quantities: ${esc(diagnostics.missingQuantities.join(", ")) || "None"}\nMissing Ship-to: ${esc(diagnostics.missingShipto.join(", ")) || "None"}</pre></details>`:""}</div></div>
    <div class="integration-grid"><div class="integration-card">${icon("link")}<div><h3>Spotfire integration</h3><p>Ready for the dedicated report. SAP table imports are the active source.</p></div><span class="pill draft">Not connected</span></div><div class="integration-card">${icon("database")}<div><h3>Shared tracking</h3><p>Supabase and driver QR confirmations will connect in the next phase.</p></div><span class="pill draft">Next phase</span></div></div>`;
}

function matches(record) {
  return JSON.stringify(record).toLowerCase().includes(search.toLowerCase());
}

function sourceDate(value, time=false) {
  const number=Number(value);
  if(value!==""&&value!=null&&Number.isFinite(number)) {
    if(time&&number>=0&&number<1){const seconds=Math.round(number*86400)%86400;return [Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(v=>String(v).padStart(2,"0")).join(":");}
    if(!time&&number>20000&&number<100000)return new Date(Date.UTC(1899,11,30)+number*86400000).toLocaleDateString("en-GB",{timeZone:"UTC"});
  }
  return value||"—";
}
function renderOpenOrders() {
  const assigned = new Set(state.forms.filter(f=>f.palletId&&!f.removedAt).flatMap(f=>f.lines.map(l=>l.hu).filter(Boolean)));
  const rows=(state.sources.shipto?.rows||[]).filter(r=>!assigned.has(r.hu)&&matches(r));
  return heading("Shipping workload","Open orders","Imported HUs not yet assigned to a pallet. Refresh the SAP data to update locations.") + `<div class="view-toolbar"><strong>${rows.length} open HUs · ${new Set(rows.map(r=>r.dn)).size} DNs</strong><label class="search-box">${icon("search")}<input id="record-search" aria-label="Search open orders" placeholder="Search DN, HU, bin or ship-to…" value="${esc(search)}"></label></div><section class="card table-wrap"><table class="record-table"><thead><tr><th>DN</th><th>HU</th><th>Storage bin</th><th>Ship-to</th><th>Changed on</th><th>Changed at</th></tr></thead><tbody>${rows.map(r=>`<tr>${[r.dn,r.hu,r.bin,r.shipTo,sourceDate(r.changedOn),sourceDate(r.changedAt,true)].map(v=>`<td>${esc(v)||"—"}</td>`).join("")}</tr>`).join("")||`<tr><td colspan="6"><div class="empty">No open orders. Import SAP data or check your filter.</div></td></tr>`}</tbody></table></section>`;
}

function palletContents(forms) {
  return `<h3>Deliveries &amp; handling units</h3><div class="table-wrap"><table class="record-table"><thead><tr><th>DN</th><th>HU</th><th>Qty</th></tr></thead><tbody>${forms.flatMap(f=>f.lines).map(l=>`<tr><td>${esc(l.dn)||"—"}</td><td>${esc(l.hu)||"—"}</td><td>${esc(l.qty)||"—"}</td></tr>`).join("")}</tbody></table></div>`;
}

function renderPallets() {
  const pallets = state.pallets.filter(p=>(filter==="all"||p.status===filter)&&matches({...p,forms:palletForms(p.id)})).sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt));
  return heading("Consolidation workspace","Your pallets","Manage open consolidations and finalised pallets from one place.") + stats() + toolbar([["all","All pallets"],["open","Open"],["finalised","Ready for pick-up"]]) + `<div id="filter-results" class="pallet-grid">${pallets.length?pallets.map(p=>palletCard(p,"pallet-detail")).join(""):`<div class="card empty">${icon("box")}<strong>No pallets found</strong><p>Create an order or adjust the filters.</p></div>`}</div>`;
}

function toolbar(filters) {
  return `<div class="view-toolbar"><div class="segmented">${filters.map(([key,label])=>`<button class="${filter===key?"selected":""}" data-action="filter" data-filter="${key}">${label}</button>`).join("")}</div><label class="search-box">${icon("search")}<input id="record-search" aria-label="Search records" placeholder="Search HU, DN, pallet or destination…" value="${esc(search)}"></label></div>`;
}

function renderHistory() {
  let records = historyTab==="forms" ? [...state.forms] : historyTab==="pallets" ? [...state.pallets] : [...state.events];
  records = records.filter(r=>matches(r) && (historyTab==="activity"||filter==="all"||(filter==="removed"?r.removedAt:!r.removedAt&&r.status===filter))).sort((a,b)=>(b.updatedAt||b.at).localeCompare(a.updatedAt||a.at));
  const tabs = [["forms","Transport forms"],["pallets","Pallets"],["activity","Activity log"]];
  const filters = historyTab==="forms"?[["all","All forms"],["draft","Drafts"],["complete","Complete"],["removed","Removed"]]:historyTab==="pallets"?[["all","All pallets"],["open","Open"],["finalised","Ready for pick-up"]]:[["all","All activity"]];
  const headers = historyTab==="activity" ? ["Action","Record","Details","When / user"] : ["Reference","Destination","Contents","Status","Updated",""];
  return heading("Records & traceability","Order history","Find a shipment, reopen a pallet or review previous document revisions.") + `<div class="view-toolbar"><div class="segmented">${tabs.map(([key,label])=>`<button data-action="history-tab" data-tab="${key}" class="${historyTab===key?"selected":""}">${label}</button>`).join("")}</div></div>` + toolbar(filters) + `<section class="card table-wrap"><table class="record-table"><thead><tr>${headers.map(h=>`<th>${h}</th>`).join("")}</tr></thead><tbody>${records.length?records.map(r=>historyTab==="activity"?`<tr><td>${esc(r.action)}</td><td>${esc(r.target)}</td><td>${esc(r.detail)||"—"}</td><td>${formatDate(r.at)}<small>${esc(r.actor)}</small></td></tr>`:`<tr><td>${esc(r.id)}<small>${historyTab==="forms"?esc(r.palletId || "Unassigned draft"):`Revision ${r.revision}`}</small></td><td>${esc(r.destination.building || "Pending")}<small>${esc(r.destination.department)}</small></td><td>${historyTab==="forms"?`${r.lines.length} rows`:palletForms(r.id).length+" forms"}<small>${historyTab==="forms"?esc([...new Set(r.lines.map(l=>l.dn).filter(Boolean))].join(", ")):`${counts(palletForms(r.id)).hus} HUs`}</small></td><td>${statusPill(r.status,r.removedAt)}</td><td>${formatDate(r.updatedAt)}</td><td><button class="link-button" data-action="${historyTab==="forms"?"form-detail":"pallet-detail"}" data-id="${r.id}">View ${icon("chevron")}</button></td></tr>`).join(""):`<tr><td colspan="${headers.length}"><div class="empty">${icon("history")}<strong>No matching records</strong><p>Your saved orders and changes will appear here.</p></div></td></tr>`}</tbody></table></section>`;
}

function renderSettings() {
  const settings=state.settings;
  const options=selected=>[1,2,3,4,5].map(n=>`<option value="${n}" ${selected===n?"selected":""}>${n} ${n===1?"copy":"copies"}</option>`).join("");
  const printers=[...new Set([...(settings.printer?[settings.printer]:[]),...printerInfo.printers])];
  return heading("Workspace preferences","Settings","Choose your appearance, printer and copy counts.") + `<div class="settings-layout"><section class="card"><div class="card-head"><h2>Shipping preferences</h2>${icon("settings")}</div><div class="card-body"><label>Appearance<select id="setting-theme"><option value="light" ${settings.theme==="light"?"selected":""}>Light</option><option value="dark" ${settings.theme==="dark"?"selected":""}>Dark</option><option value="system" ${settings.theme==="system"?"selected":""}>Follow system</option></select></label><label>Prepared by / username<input id="setting-name" value="${esc(settings.preparedBy)}" placeholder="Your username"></label><h3>Default origin</h3>${locationFields("settingOrigin",settings.origin,"fromLocations")}<h3>Direct printing</h3><label>Printer<select id="setting-printer"><option value="" ${!settings.printer?"selected":""}>Windows default${printerInfo.defaultPrinter?" — "+esc(printerInfo.defaultPrinter):" (follows Windows)"}</option>${printers.map(name=>`<option value="${esc(name)}" ${settings.printer===name?"selected":""}>${esc(name)}</option>`).join("")}</select><span class="field-hint">Windows default is resolved for every print job. Selecting a printer here does not change your Windows default.</span></label><button class="btn small" data-action="refresh-printers">${icon("refresh")}Refresh printers</button>${printerInfo.supported===false?`<div class="banner warn mt">Direct printing is available on Windows. Document preview is available here.</div>`:""}${printerInfo.error?`<div class="banner error mt">${esc(printerInfo.error)}</div>`:""}<div class="fields two mt"><label>Open form copies<select id="setting-open-copies">${options(settings.openCopies)}</select><span class="field-hint">Default: 1 copy when keeping a pallet open.</span></label><label>Finalised pallet copies<select id="setting-final-copies">${options(settings.finalCopies)}</select><span class="field-hint">Default: 2 copies of the consolidation.</span></label></div><div class="settings-actions"><button class="btn primary" data-action="save-settings">Save preferences</button><button class="btn" data-action="backup">${icon("download")}Export backup</button></div></div></section><aside class="settings-note"><strong>Print directly from the form</strong><p>Print &amp; keep open sends the individual form to your printer. Finalise pallet sends the consolidated document. Neither action opens a browser print screen.</p><p>Saved revisions remain available in History for preview or reprinting. A print error keeps the saved document available for retry.</p><strong>Saved on this computer</strong><p>Imported tables, forms, pallets and your preferences remain available between sessions.</p></aside></div>`;
}

function render() {
  updateShell();
  $("#main").innerHTML = ({create:renderCreate,infeed:renderInfeed,pallets:renderPallets,"open-orders":renderOpenOrders,history:renderHistory,settings:renderSettings}[view] || renderCreate)();
  sessionStorage.setItem("transport-order.editor", JSON.stringify({editor,selectedPallet,dirty}));
}

function markDirty() {
  dirty = true;
  if ($("#draft-status")) $("#draft-status").textContent = "Unsaved changes";
  if ($("#line-totals")) $("#line-totals").innerHTML = lineTotals();
  sessionStorage.setItem("transport-order.editor", JSON.stringify({editor,selectedPallet,dirty}));
}

function toast(message) {
  $("#toast").textContent = message; $("#toast").classList.add("visible");
  clearTimeout(toast.timer); toast.timer = setTimeout(()=>$("#toast").classList.remove("visible"),4000);
}

function showDialog(title, body, foot="", wide=false, subtitle="") {
  const dialog = $("#dialog");
  if (dialog.open) dialog.close();
  dialogCallback = null;
  dialog.className = wide?"wide":"";
  dialog.innerHTML = `<div class="dialog-head"><div><h2 id="dialog-title">${esc(title)}</h2>${subtitle?`<p>${esc(subtitle)}</p>`:""}</div><button class="icon-button" data-action="close-dialog" aria-label="Close dialog">${icon("close")}</button></div>${body}${foot?`<div class="dialog-foot">${foot}</div>`:""}`;
  dialog.showModal();
}

function message(title, body) {
  showDialog(title,`<div class="dialog-body dialog-message">${esc(body)}</div>`,`<button class="btn primary" data-action="close-dialog">Got it</button>`);
}

function confirmAction(title, text, button="Continue", reason=false) {
  return new Promise(resolve=>{
    showDialog(title,`<div class="dialog-body"><p>${esc(text)}</p>${reason?`<label>Reason<textarea id="confirm-reason" rows="3" placeholder="Explain the correction"></textarea></label>`:""}</div>`,`<button class="btn" data-action="cancel-confirm">Cancel</button><button class="btn primary" data-action="accept-confirm">${esc(button)}</button>`);
    dialogCallback = result => resolve(result);
  });
}

async function confirmDiscard() {
  return !dirty || await confirmAction("Leave this form?","Your current changes have not been saved. Save a draft first if you want to resume them later.","Discard changes");
}

async function mutate(action, payload) {
  if (busy) throw new Error("Another save is in progress. Please wait.");
  busy = true;
  $$('[data-action="save"], [data-action="apply-import"], [data-action="finalise-selected"]').forEach(b=>b.disabled=true);
  try {
    const result = await api("action",{action,payload,expectedRevision:state.revision});
    await loadState();
    return result;
  } finally { busy=false; $$('[data-action="save"], [data-action="apply-import"], [data-action="finalise-selected"]').forEach(b=>b.disabled=false); }
}

async function resolveEditor() {
  if (editor.mode!=="automatic") return;
  const request = ++resolving, currentEditor = editor;
  const result = await api("resolve",{lines:editor.lines,formId:editor.id,destination:editor.destinationOverride?editor.destination:null,overrideReason:editor.overrideReason});
  if (request!==resolving || currentEditor!==editor) return;
  const filled = editor.lines.filter(l=>["part","description","qty","hu","dn"].some(k=>l[k]));
  result.lines.forEach((line,i)=>{
    if (filled[i]) Object.assign(filled[i],line);
  });
  editor.lines = [...filled,...Array.from({length:Math.max(0,5-filled.length)},emptyLine)];
  if (result.destination) editor.destination = result.destination;
  else if (!editor.destinationOverride) editor.destination = emptyLocation();
  editor.automaticEmergency = result.emergency;
  resolveResult = result;
  markDirty(); render();
}

async function saveForm(intent) {
  const result = await mutate("save_form",{...editor,intent,palletId:selectedPallet});
  resolveResult = null; dirty=false;
  selectedPallet = intent==="finalise" ? null : result.palletId;
  if (intent==="draft") {
    editor = structuredClone(state.forms.find(f=>f.id===result.formId));
    delete editor.versions;
    editor.destinationOverride = Boolean(editor.overridden || editor.overrideReason);
    if (!editor.lines.length) editor.lines = Array.from({length:5},emptyLine);
    toast("Draft saved. Resume it here or from History.");
  } else {
    editor = newEditor();
    toast(intent==="finalise"?"Pallet finalised. Sending the consolidation to your printer…":"Form saved. Sending it to your printer…");
  }
  render();
  if (result.print) await submitPrint(result.print);
}

async function submitPrint(document) {
  if(printingBusy)throw new Error("A print submission is already in progress.");
  printingBusy=true;pendingPrint={...document,requestId:document.requestId||globalThis.crypto.randomUUID()};
  try {
    const result=await api("print-job",pendingPrint);
    await loadState();render();
    $("#dialog").close();
    toast(`${result.copies} ${result.copies===1?"copy":"copies"} sent to ${result.printer}.`);
    if(result.auditWarning)message("Print submitted",result.auditWarning);
  } catch(error) {
    showDialog("Document saved · printing needs attention",`<div class="dialog-body"><p class="dialog-message">${esc(error.message)}</p><p>The form or pallet is already saved. Check the queue before retrying; no automatic retry is made.</p></div>`,`<button class="btn" data-action="close-dialog">Close</button><button class="btn" data-action="preview-pending">Preview document</button><button class="btn primary" data-action="retry-print">Retry printing</button>`);
  } finally { printingBusy=false; }
}

async function openPreview(document) {
  previewDocument = document;
  const html = await api("print?" + new URLSearchParams({...document,copies:1}),undefined,true);
  showDialog(document.kind==="pallet"?"Pallet consolidation":"Transport order",`<div class="preview-summary">${esc(document.id)} · Revision ${document.revision} · Saved document preview. Direct printing uses your selected Windows printer.</div><iframe id="print-frame" class="preview-frame" title="Printable transport document"></iframe>`,`<label>Copies<select id="print-copies">${[1,2,3,4,5].map(n=>`<option value="${n}" ${state.settings[document.kind==="pallet"?"finalCopies":"openCopies"]===n?"selected":""}>${n}</option>`).join("")}</select></label><button class="btn" data-action="close-dialog">Close</button><button class="btn primary" data-action="browser-pdf">Save PDF</button><button class="btn primary" data-action="print-document">${icon("print")}Print directly</button>`,true);
  $("#print-frame").srcdoc=html;
}

function detail(kind, id) {
  const record = (kind==="form"?state.forms:state.pallets).find(r=>r.id===id);
  if (!record) return;
  const forms = kind==="form"?[record]:palletForms(id);
  const related = new Set([id,...forms.map(f=>f.id)]);
  const events = state.events.filter(e=>related.has(e.target)).reverse();
  const pallet = kind==="form"?state.pallets.find(p=>p.id===record.palletId):record;
  const editable = !record.removedAt && (!pallet || pallet.status==="open");
  const versions = [...record.versions].reverse();
  showDialog(kind==="form"?"Transport order details":"Pallet details",`<div class="dialog-body"><div class="detail-meta"><div><strong>${esc(id)}</strong>${statusPill(record.status,record.removedAt)}<br>Created ${formatDate(record.createdAt)}<br>Updated ${formatDate(record.updatedAt)}</div><div><strong>${esc(record.destination.building || "Destination pending")}</strong>${esc(record.destination.department)}<br>${esc(record.destination.shipTo)}</div></div>${kind==="pallet"?`${palletContents(forms)}<h3>Forms on this pallet</h3><div class="detail-forms">${forms.map(f=>`<button class="btn small" data-action="form-detail" data-id="${f.id}">${esc(f.id)} · ${esc(f.status)}</button>`).join("")||"<p>No active forms.</p>"}</div>`:`<div class="table-wrap"><table class="record-table"><thead><tr><th>12NC</th><th>Description</th><th>Qty</th><th>HU</th><th>DN</th></tr></thead><tbody>${record.lines.map(l=>`<tr>${["part","description","qty","hu","dn"].map(k=>`<td>${esc(l[k])}</td>`).join("")}</tr>`).join("")}</tbody></table></div><p class="mt" style="white-space:pre-wrap">${esc(record.remarks)||"No additional remarks."}</p>`}<h3>Document revisions</h3><div class="detail-forms">${versions.length?versions.map(v=>`<button class="btn small" data-action="version" data-kind="${kind}" data-id="${id}" data-revision="${v.revision}">${icon("print")}Revision ${v.revision} · ${formatDate(v.at||v.updatedAt)}</button>`).join(""):"<p>No completed document yet.</p>"}</div><h3>Activity</h3><ul class="timeline">${events.map(e=>`<li>${esc(e.action)}${e.detail?` — ${esc(e.detail)}`:""}<small>${formatDate(e.at)} · ${esc(e.actor)}</small></li>`).join("")}</ul></div>`,`<button class="btn" data-action="close-dialog">Close</button>${kind==="form"&&editable?`<button class="btn danger" data-action="remove-form" data-id="${id}">Remove form</button><button class="btn primary" data-action="edit-form" data-id="${id}">${icon("edit")}Edit form</button>`:""}${kind==="pallet"&&record.status==="finalised"?`<button class="btn primary" data-action="reopen" data-id="${id}">Reopen pallet</button>`:""}${kind==="pallet"&&record.status==="open"?`<button class="btn primary" data-action="select-pallet" data-id="${id}">Continue this pallet</button>`:""}`,true);
}

function renderPresets(building="all", query="") {
  const matches = directory.toLocations.map((r,index)=>({...r,index})).filter(r=>(building==="all"||r.building===building)&&JSON.stringify(r).toLowerCase().includes(query.toLowerCase()));
  return matches.map(r=>`<button class="destination-option" data-action="choose-destination" data-index="${r.index}"><strong>${esc(r.building)} — ${esc(r.sourceCode||r.shipTo)}</strong><span>${esc(r.department)}</span>${r.label?`<small>${esc(r.label)}</small>`:""}</button>`).join("") || `<p>No matching destinations.</p>`;
}

function sourcePayload(kind) {
  const draft = imports[kind];
  return {kind,text:draft.fileBase64?"":draft.text||gridText(draft.grid),decimalMark:draft.decimalMark,...(draft.fileBase64?{fileBase64:draft.fileBase64}:{}),filename:draft.filename||"Pasted SAP table"};
}

async function previewImport(kind, silent=false) {
  const draft=imports[kind], payload=sourcePayload(kind), fingerprint=JSON.stringify(payload);
  if(silent && (!draft.fileBase64&&!draft.text&&!draft.grid.slice(1).some(r=>r?.some(v=>String(v).trim())) || draft.validated===fingerprint))return;
  const result=await api("import-preview",payload);
  if(result.errors.length)throw new Error(result.errors.map(e=>`${e.row?"Row "+e.row:"HU "+e.hu}: ${e.message}`).join("\n"));
  await mutate("import",payload);draft.validated=fingerprint;
  if(result.warnings.length)message("Data validated with warnings",result.warnings.join("\n"));
  else if(!silent)toast(`${result.count} records validated and loaded.`);
}

const actions = {
  async navigate(b) { if(view==="infeed"&&b.dataset.view!==view){for(const kind of ["shipto","quantities"])await previewImport(kind,true);}view=b.dataset.view; filter="all"; search=""; if(view==="settings")await loadPrinters();render(); },
  async refresh() { await loadState(); render(); toast("Saved data refreshed. Your current form is preserved."); },
  async mode(b) { if(editor.mode===b.dataset.mode)return; editor.mode=b.dataset.mode; resolveResult=null; editor.lines.forEach(l=>l.issues=[]); markDirty(); render(); if(editor.mode==="automatic"&&editor.lines.some(l=>l.hu))await resolveEditor(); },
  async origin() { originExpanded=!originExpanded; render(); },
  async receiver() { receiverExpanded=!receiverExpanded; render(); },
  async bulk() { bulkExpanded=!bulkExpanded; render(); $("#bulk-hus")?.focus(); },
  async "add-line"() { if(editor.lines.length>=500)throw new Error("Use at most 500 rows per form."); editor.lines.push(emptyLine()); markDirty(); render(); $(`[data-line="${editor.lines.length-1}"][data-line-field="hu"]`).focus(); },
  async "remove-line"(b) { editor.lines.splice(Number(b.dataset.index),1); if(!editor.lines.length)editor.lines.push(emptyLine()); markDirty(); if(editor.mode==="automatic")await resolveEditor(); else render(); },
  async "add-hus"() { const hus=$("#bulk-hus").value.trim().split(/[\s,;]+/).filter(Boolean); if(!hus.length)return; const used=editor.lines.filter(l=>["hu","part","description","qty","dn"].some(k=>l[k])); if(used.length+hus.length>500)throw new Error("Use at most 500 rows per form."); editor.lines=[...used,...hus.map(hu=>({...emptyLine(),hu}))]; bulkExpanded=false; markDirty(); if(editor.mode==="automatic")await resolveEditor(); else render(); },
  async resolve() { await resolveEditor(); toast(resolveResult?.valid?"All HUs checked. Destination and quantities match.":"Check the highlighted rows."); },
  async save(b) { await saveForm(b.dataset.intent); },
  async "clear-form"() { if(!await confirmDiscard())return; editor=newEditor();dirty=false;resolveResult=null;render(); },
  async "new-form"(b) { if(!await confirmDiscard())return; if(b.dataset.detach)selectedPallet=null; editor=newEditor();dirty=false;resolveResult=null;view="create";$("#dialog").close();render(); },
  async "select-pallet"(b) { if(!await confirmDiscard())return; selectedPallet=b.dataset.id;editor=newEditor();dirty=false;resolveResult=null;view="create";$("#dialog").close();render(); },
  async "finalise-selected"() { if(!selectedPallet)return; if(dirty&&editor.lines.some(l=>["hu","description","part","dn"].some(k=>l[k]))) { await saveForm("finalise"); return; } if(!await confirmAction("Finalise this pallet?","This closes the pallet and creates its consolidated document. It can be reopened from History for corrections.","Finalise pallet"))return; const result=await mutate("finalise_pallet",{id:selectedPallet});selectedPallet=null;editor=newEditor();dirty=false;render();await submitPrint(result.print); },
  async "edit-form"(b) { if(!await confirmDiscard())return; const f=state.forms.find(r=>r.id===b.dataset.id);const p=state.pallets.find(r=>r.id===f.palletId);if(p&&p.status!=="open")throw new Error("Reopen this pallet before editing its forms.");editor=structuredClone(f);delete editor.versions;editor.destinationOverride=Boolean(f.overridden||f.overrideReason);if(!editor.lines.length)editor.lines=[emptyLine()];selectedPallet=f.palletId;dirty=false;resolveResult=null;view="create";$("#dialog").close();render(); },
  async presets(b) { const building=b.dataset.building;showDialog("Choose a destination",`<div class="dialog-body"><label class="search-box">${icon("search")}<input id="preset-search" data-building="${esc(building)}" placeholder="Search building, department or ship-to"></label><div class="dialog-routes" id="preset-results">${renderPresets(building)}</div></div>`); },
  async "choose-destination"(b) { const r=directory.toLocations[Number(b.dataset.index)];editor.destination={building:r.building,department:r.department,shipTo:r.shipTo};editor.destinationOverride=editor.mode==="automatic";if(r.shipTo==="KEYSIGHT"&&!editor.remarks.includes("KEYSIGHT Tech."))editor.remarks=[editor.remarks,"KEYSIGHT Tech."].filter(Boolean).join("\n");markDirty();$("#dialog").close();render();if(editor.mode==="automatic"&&editor.lines.some(l=>l.hu))await resolveEditor(); },
  async "choose-file"(b) { $("#file-"+b.dataset.kind).click(); },
  async "discard-file"(b) { imports[b.dataset.kind]={...gridDraft(b.dataset.kind),decimalMark:imports[b.dataset.kind].decimalMark};render(); },
  async "preview-import"(b) { await previewImport(b.dataset.kind);render(); },
  async "apply-import"(b) { if($("#import-warning-ack")&&!$("#import-warning-ack").checked)throw new Error("Review the import warnings and tick the acknowledgement before applying.");const kind=b.dataset.kind;await mutate("import",sourcePayload(kind));imports[kind]={...gridDraft(kind),decimalMark:imports[kind].decimalMark};$("#dialog").close();render();toast("SAP table applied. Saved forms have not changed."); },
  async "clear-source"(b) { if(!await confirmAction("Clear this SAP table?","This removes the loaded source data. Saved forms and pallets are preserved.","Clear table"))return;await mutate("clear_source",{kind:b.dataset.kind});$("#dialog").close();render();toast("Source table cleared."); },
  async filter(b) { filter=b.dataset.filter;render(); },
  async "history-tab"(b) { historyTab=b.dataset.tab;filter="all";search="";render(); },
  async "form-detail"(b) { detail("form",b.dataset.id); },
  async "pallet-detail"(b) { detail("pallet",b.dataset.id); },
  async version(b) { await openPreview({kind:b.dataset.kind,id:b.dataset.id,revision:Number(b.dataset.revision)}); },
  async reopen(b) { const id=b.dataset.id;const reason=await confirmAction("Reopen pallet?","The previous consolidation remains in History and will be marked superseded. Finalise again after correcting the pallet.","Reopen pallet",true);if(!reason)return;await mutate("reopen_pallet",{id,reason});$("#dialog").close();render();toast("Pallet reopened. Its forms can now be edited."); },
  async "remove-form"(b) { const id=b.dataset.id;const reason=await confirmAction("Remove this form?","The form will leave the active pallet. Its previous documents and activity remain in History.","Remove form",true);if(!reason)return;await mutate("remove_form",{id,reason});if(editor.id===id){editor=newEditor();dirty=false;}$("#dialog").close();render();toast("Form removed from the active pallet."); },
  async "toggle-theme"() { const theme=document.documentElement.dataset.theme==="dark"?"light":"dark";await mutate("settings",{theme});render(); },
  async "refresh-printers"() { await loadPrinters();const select=$("#setting-printer"),selected=select.value;select.innerHTML=`<option value="">Windows default${printerInfo.defaultPrinter?" — "+esc(printerInfo.defaultPrinter):" (follows Windows)"}</option>`+[...new Set([...(selected?[selected]:[]),...printerInfo.printers])].map(name=>`<option value="${esc(name)}">${esc(name)}</option>`).join("");select.value=selected;toast(printerInfo.error||"Windows printers refreshed."); },
  async "save-settings"() { const origin={};for(const k of ["building","department","shipTo"])origin[k]=$(`[data-field="settingOrigin.${k}"]`).value;await mutate("settings",{preparedBy:$("#setting-name").value,openCopies:Number($("#setting-open-copies").value),finalCopies:Number($("#setting-final-copies").value),printer:$("#setting-printer").value,theme:$("#setting-theme").value,origin});render();toast("Preferences saved."); },
  async "clipboard-grid"(b) { try{const text=await navigator.clipboard.readText();pasteGrid(b.dataset.kind,text);render();}catch{message("Paste into a cell","Click the first data cell and press Ctrl+V to paste your copied SAP table.");} },
  async "grid-page"(b) { imports[b.dataset.kind].gridPage+=Number(b.dataset.step);render(); },
  async "clear-grid"(b) { if(!await confirmAction("Clear input cells?","This clears only the pasted cells. Your loaded SAP data and saved forms are kept.","Clear cells"))return;imports[b.dataset.kind]=gridDraft(b.dataset.kind);render(); },

  async backup() { const blob=new Blob([JSON.stringify(state,null,2)],{type:"application/json"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="TransportOrder-backup-"+new Date().toISOString().slice(0,10)+".json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast("Backup exported."); },
  async "browser-pdf"() { const copies=Number($("#print-copies").value);const html=await api("print?"+new URLSearchParams({...previewDocument,copies}),undefined,true);const frame=$("#print-frame");frame.onload=()=>{frame.onload=null;frame.contentWindow.focus();frame.contentWindow.print();};frame.srcdoc=html; },
  async "print-document"() { await submitPrint({...previewDocument,copies:Number($("#print-copies").value)}); },
  async "retry-print"() { if(!await confirmAction("Retry this print job?","Check the Windows print queue first. Retry only if the previous job did not reach the queue.","Retry printing"))return;await submitPrint(pendingPrint); },
  async "preview-pending"() { await openPreview(pendingPrint); },
  async "close-dialog"() { if(dialogCallback){const done=dialogCallback;dialogCallback=null;done(false);}$("#dialog").close(); },
  async "cancel-confirm"() { const done=dialogCallback;dialogCallback=null;$("#dialog").close();done?.(false); },
  async "accept-confirm"() { const input=$("#confirm-reason");const value=input?input.value.trim():true;if(input&&!value){input.focus();return;}const done=dialogCallback;dialogCallback=null;$("#dialog").close();done?.(value); },
  async help() { showDialog("Your shipping workflow",`<div class="dialog-body"><h3>1. Load the SAP data</h3><p>Open Data infeed. Paste Ship-to and Quantities including their headers, or import the XLSX files. Check the preview and apply each table.</p><h3>2. Prepare a form</h3><p>Paste HUs into the form. DN, destination, quantity and Emergency fill automatically. Add descriptions, part numbers and remarks as needed. Use Manual mode for exceptions.</p><h3>3. Build the pallet</h3><p>Choose Print &amp; keep open to save the form and print one copy by default, without a browser print screen. Select that pallet on the right to add more forms. Start a different pallet if the destination changes.</p><h3>4. Finalise when ready</h3><p>Finalisation prints two copies by default of a consolidation listing every delivery and HU. Open History to reprint, inspect revisions or reopen a pallet for correction.</p><div class="banner">${icon("info")}This phase saves on this computer. QR tracking, driver confirmations, shared storage and Spotfire are not connected yet.</div></div>`,`<button class="btn primary" data-action="close-dialog">Start preparing</button>`); },
  async shutdown() { if(!await confirmDiscard())return;if(!await confirmAction("Close TransportOrder?","Your saved drafts, forms and pallets will be available next time you start the application.","Close application"))return;await api("shutdown",{});dirty=false;sessionStorage.removeItem("transport-order.editor");$("#dialog").close();$("#main").innerHTML=heading("Workspace closed","All saved work is kept","You can close this window. Run the application again to continue."); },
  async demo() {
    if(!await confirmAction("Load fictional SAP data?","This replaces both imported tables with clearly fictional records. Existing forms and pallets are kept.","Load demo tables"))return;
    const shipto="Outbound Delivery Order\tERP Document\tHandling Unit\tShip-To\tShipping Condition\tExternal Delivery ID\nDEMO-ODO-01\tDEMO-DN-01\tDEMO-HU-001\tB21-MOASSY\tS1\t\nDEMO-ODO-02\tDEMO-DN-02\tDEMO-HU-002\tB21-MOASSY\tS4\t\nDEMO-ODO-03\tDEMO-DN-03\tDEMO-HU-003\tNL10C\tS1\t\nDEMO-ODO-04\tDEMO-DN-04\tDEMO-HU-004\tWH-WEERT1A\tS1\tSCRAP\nDEMO-ODO-05\tDEMO-DN-05\tDEMO-HU-005\tWH-WEERT1A\tI2\t\nDEMO-ODO-06\tDEMO-DN-06\tDEMO-HU-006\tNL05C\tS1\t";
    const quantities="Document\tHandling Unit\tQuantity\nDEMO-ODO-01\tDEMO-HU-001\t4\nDEMO-ODO-01\tDEMO-HU-001\t21\nDEMO-ODO-02\tDEMO-HU-002\t3\nDEMO-ODO-03\tDEMO-HU-003\t12\nDEMO-ODO-04\tDEMO-HU-004\t7\nDEMO-ODO-05\tDEMO-HU-005\t2\nDEMO-ODO-06\tDEMO-HU-006\t1";
    await mutate("import",{kind:"shipto",text:shipto,filename:"Fictional demonstration data"});await mutate("import",{kind:"quantities",text:quantities,filename:"Fictional demonstration data"});render();message("Demo tables loaded","Use DEMO-HU-001 and DEMO-HU-002 together for Building 21.\n\nDEMO-HU-001 sums to 25; DEMO-HU-002 triggers Emergency.\n\nAdd DEMO-HU-003 to see a destination conflict. DEMO-HU-004 and 005 demonstrate the Weert scrap split. DEMO-HU-006 requires a manual NL05 destination.");
  },
};

document.addEventListener("click",async event=>{
  const button=event.target.closest("[data-action]");
  if(!button||button.disabled)return;
  const action=actions[button.dataset.action];
  if(!action)return;
  try { await action(button); } catch(error) { message("Action needs attention",error.message); }
});

document.addEventListener("input",event=>{
  const input=event.target;
  if(input.dataset.lineField) { editor.lines[Number(input.dataset.line)][input.dataset.lineField]=input.value;markDirty(); }
  else if(input.dataset.field && !input.dataset.field.startsWith("settingOrigin")) {
    const keys=input.dataset.field.split(".");const value=input.type==="checkbox"?input.checked:input.value;
    if(keys.length===2) {
      if(keys[1]==="building"&&editor[keys[0]].building!==value){editor[keys[0]].department="";editor[keys[0]].shipTo="";}
      if(keys[1]==="department"&&editor[keys[0]].department!==value)editor[keys[0]].shipTo="";
      editor[keys[0]][keys[1]]=value;
    } else editor[keys[0]]=value;
    if(keys[0]==="destination")editor.destinationOverride=editor.mode==="automatic";
    markDirty();
  }
  if(input.dataset.grid) {
    const draft=imports[input.dataset.grid],row=Number(input.dataset.gridRow),col=Number(input.dataset.gridColumn);
    draft.grid[row] ||= [];draft.grid[row][col]=input.value;draft.text="";delete draft.fileBase64;delete draft.filename;
  }
  if(input.id==="preset-search")$("#preset-results").innerHTML=renderPresets(input.dataset.building,input.value);
  if(input.id==="record-search") { const start=input.selectionStart;search=input.value;const content=view==="pallets"?renderPallets():view==="open-orders"?renderOpenOrders():renderHistory();$("#main").innerHTML=content;$("#record-search").focus();$("#record-search").setSelectionRange(start,start); }
});

document.addEventListener("change",async event=>{
  const input=event.target;
  try {
    if(input.dataset.lineField==="hu"&&editor.mode==="automatic")await resolveEditor();
    if(input.dataset.field?.startsWith("destination.")||input.dataset.field?.startsWith("origin."))render();
    if(input.dataset.field==="overrideReason"&&editor.mode==="automatic")await resolveEditor();
    if(input.id==="setting-theme")applyTheme(input.value);
    if(input.dataset.decimal)imports[input.dataset.decimal].decimalMark=input.value;
    if(input.dataset.file&&input.files[0]) {
      const file=input.files[0],kind=input.dataset.file;
      if(file.size>14_000_000)throw new Error("Use a file smaller than 14 MB.");
      const draft=imports[kind];
      if(file.name.toLowerCase().endsWith(".xlsx")) {
        const data=new Uint8Array(await file.arrayBuffer());let binary="";
        for(let i=0;i<data.length;i+=8192)binary+=String.fromCharCode(...data.subarray(i,i+8192));
        draft.fileBase64=btoa(binary);draft.text="";draft.grid=[[...GRID_HEADERS[kind]]];
      } else { const text=await file.text();draft.grid=[[...GRID_HEADERS[kind]]];pasteGrid(kind,text);draft.text="";delete draft.fileBase64; }
      draft.filename=file.name;render();
    }
  } catch(error) { message("Check the input",error.message); }
});

document.addEventListener("paste",event=>{
  const input=event.target;
  const text=event.clipboardData.getData("text");
  if(input.dataset.grid) {
    event.preventDefault();
    try { pasteGrid(input.dataset.grid,text,Number(input.dataset.gridRow),Number(input.dataset.gridColumn));render(); }
    catch(error){message("Check pasted cells",error.message);}return;
  }
  if(input.dataset.lineField!=="hu")return;
  const hus=text.trim().split(/[\s,;]+/).filter(Boolean);
  if(hus.length<2)return;
  event.preventDefault();
  const index=Number(input.dataset.line);
  if(editor.lines.length+hus.length>500){message("Too many HUs","Use at most 500 rows per form.");return;}
  editor.lines[index].hu=hus.shift();
  editor.lines.splice(index+1,0,...hus.map(hu=>({...emptyLine(),hu})));
  markDirty();
  if(editor.mode==="automatic")resolveEditor().catch(e=>message("Check HUs",e.message));else render();
});

document.addEventListener("keydown",event=>{
  const input=event.target;if(!input.dataset.grid)return;
  let row=Number(input.dataset.gridRow),col=Number(input.dataset.gridColumn);
  if(event.key==="Enter"||event.key==="ArrowDown")row++;
  else if(event.key==="ArrowUp")row--;
  else if(event.key==="ArrowLeft"&&input.selectionStart===0)col--;
  else if(event.key==="ArrowRight"&&input.selectionStart===input.value.length)col++;
  else return;
  if(row<0||col<0||row>50000||col>=Math.max(GRID_HEADERS[input.dataset.grid].length,...Array.from(imports[input.dataset.grid].grid,r=>r?.length||0)))return;
  event.preventDefault();const kind=input.dataset.grid,draft=imports[kind];
  if(row>0){draft.gridPage=Math.floor((row-1)/50);if(!draft.grid[row])draft.grid[row]=[];}
  render();const target=$(`[data-grid="${kind}"][data-grid-row="${row}"][data-grid-column="${col}"]`);target?.focus();target?.select();
});
window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener("change",()=>{if(state?.settings.theme==="system")applyTheme();});

$("#dialog").addEventListener("cancel",()=>{if(dialogCallback){const done=dialogCallback;dialogCallback=null;done(false);}});
window.addEventListener("beforeunload",event=>{if(dirty){event.preventDefault();event.returnValue="";}});
$("#refresh-button").innerHTML=icon("refresh");
$("#help-icon").innerHTML=icon("info");
$("#power-icon").innerHTML=icon("power");

(async()=>{
  try {
    await loadState();
    editor=newEditor();
    try {
      const cached=JSON.parse(sessionStorage.getItem("transport-order.editor"));
      if(cached?.dirty&&cached.editor&&(!cached.editor.id||state.forms.some(f=>f.id===cached.editor.id&&!f.removedAt))) {
        editor=cached.editor;selectedPallet=cached.selectedPallet;dirty=true;
        if(selectedPallet&&!state.pallets.some(p=>p.id===selectedPallet&&p.status==="open")){selectedPallet=null;editor.palletId=null;}
      }
    } catch {}
    render();
  } catch(error) { $("#main").innerHTML=heading("Workspace unavailable","Open the application link",esc(error.message)); }
})();
