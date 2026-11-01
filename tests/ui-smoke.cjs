const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vm = require("node:vm");
const { spawn } = require("node:child_process");
const { once } = require("node:events");

const root = path.resolve(__dirname, "..");
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "transport-order-smoke-"));
const script = `from transport_order.server import create_server\nfrom transport_order.storage import Store\ns=create_server(Store(${JSON.stringify(temporary)}),'smoke-test-session',0)\nprint(s.server_port,flush=True)\ns.serve_forever()`;
const server = spawn(process.env.PYTHON || "python", ["-u", "-c", script], {cwd:root});
let serverErrors = "";
server.stderr.on("data", chunk => serverErrors += chunk);

class Element {
  constructor(document, id) {
    this.document = document;
    this.id = id;
    this.value = "";
    this.open = false;
    this.dataset = {};
    this.classList = {add(){}, remove(){}};
  }
  set innerHTML(value) {
    this.html = value;
    for (const match of value.matchAll(/\bid="([^"]+)"/g)) {
      this.document.elements.set(match[1], new Element(this.document, match[1]));
    }
  }
  get innerHTML() { return this.html || ""; }
  addEventListener() {}
  setAttribute() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
  focus() {}
  click() {}
}

async function main() {
  const [chunk] = await Promise.race([
    once(server.stdout, "data"),
    once(server, "exit").then(()=>{throw new Error("Test server failed: " + serverErrors);}),
    new Promise((_, reject)=>setTimeout(()=>reject(new Error("Test server did not start: " + serverErrors)),8000).unref()),
  ]);
  const base = "http://127.0.0.1:" + String(chunk).trim();
  const document = {
    elements:new Map(),
    documentElement:{dataset:{}},
    querySelector(selector) { return selector.startsWith("#") ? this.elements.get(selector.slice(1)) || null : null; },
    querySelectorAll() { return []; },
    addEventListener() {},
    createElement() { return new Element(this, "temporary"); },
  };
  for (const id of ["main","navigation","page-label","source-health","user-label","avatar","dialog","toast","refresh-button","help-icon","power-icon","app-version","theme-button"]) {
    document.elements.set(id, new Element(document,id));
  }
  const saved = new Map();
  const sessionStorage = {getItem:key=>saved.get(key)||null,setItem:(key,value)=>saved.set(key,value),removeItem:key=>saved.delete(key)};
  const printRequests=[];
  const context = vm.createContext({document,crypto:require("node:crypto").webcrypto,sessionStorage,console,URLSearchParams,structuredClone,Intl,Date,Number,String,Set,Map,Blob,URL,
    location:{hash:"#session=smoke-test-session"},history:{replaceState(){}},window:{addEventListener(){},matchMedia(){return {matches:false,addEventListener(){}};}},
    setTimeout:(fn,ms)=>setTimeout(fn,ms).unref(),clearTimeout,
    fetch:(url,options)=>{
      if(url==="/api/print-job"){
        const request=JSON.parse(options.body);printRequests.push(request);
        return Promise.resolve(new Response(JSON.stringify({status:"submitted",printer:"Test queue",copies:request.copies||(request.kind==="pallet"?2:1)}),{status:200}));
      }
      return fetch(base+url,options);
    },
  });
  const execute = code => vm.runInContext(code,context);
  await execute(fs.readFileSync(path.join(root,"transport_order/web/app.js"),"utf8"));
  assert.match(document.elements.get("main").innerHTML,/Prepare a transport order/);
  execute('confirmAction = async (title,text,button,reason) => reason ? "Test correction" : true');

  await execute("actions.demo()");
  assert.equal(execute("state.sources.shipto.uniqueHus"),6);
  execute('editor.lines=[{...emptyLine(),hu:"DEMO-HU-001"}]; editor.remarks="Keep this note"');
  await execute("resolveEditor()");
  assert.equal(execute("editor.lines[0].qty"),"25");
  assert.equal(execute("editor.lines[0].dn"),"DEMO-DN-01");
  assert.equal(execute("editor.destination.building"),"Building 21");
  assert.equal(execute("resolveResult.valid"),true);
  await execute('saveForm("keep_open")');
  assert.equal(execute("state.forms.length"),1);
  assert.equal(execute("selectedPallet"),null);
  assert.equal(printRequests.length,1);
  assert.equal(printRequests[0].kind,"form");
  assert.equal(document.elements.get("dialog").open,false);
  await execute('openPreview({kind:"form",id:state.forms[0].id,revision:1})');
  assert.match(document.elements.get("print-frame").srcdoc,/Keep this note/);

  execute('selectedPallet=state.pallets[0].id;editor=newEditor();editor.lines=[{...emptyLine(),hu:"DEMO-HU-002"}]');
  await execute("resolveEditor()");
  assert.equal(execute("editor.automaticEmergency"),true);
  await execute('saveForm("finalise")');
  assert.equal(execute("state.pallets[0].status"),"finalised");
  assert.equal(execute("state.pallets[0].versions[0].forms.length"),2);
  assert.equal(printRequests.length,2);
  assert.equal(printRequests[1].kind,"pallet");
  assert.equal(document.elements.get("dialog").open,false);
  await execute('openPreview({kind:"pallet",id:state.pallets[0].id,revision:1})');
  assert.match(document.elements.get("print-frame").srcdoc,/Delivery summary/);
  assert.match(document.elements.get("print-frame").srcdoc,/EMERGENCY/);

  for (const page of ["infeed","open-orders","pallets","history","settings","create"]) {
    execute(`view=${JSON.stringify(page)}; render()`);
    assert.ok(document.elements.get("main").innerHTML.length>500);
    assert.doesNotMatch(document.elements.get("main").innerHTML, /\bundefined\b/);
  }
  await execute('actions.reopen({dataset:{id:state.pallets[0].id}})');
  assert.equal(execute("state.pallets[0].status"),"open");
  await execute('openPreview({kind:"pallet",id:state.pallets[0].id,revision:1})');
  assert.match(document.elements.get("print-frame").srcdoc,/SUPERSEDED/);

  execute('editor=newEditor(null);selectedPallet=null;editor.lines=[{...emptyLine(),hu:"DEMO-HU-003"},{...emptyLine(),hu:"DEMO-HU-004"}]');
  await execute("resolveEditor()");
  assert.equal(execute("resolveResult.valid"),false);
  assert.match(document.elements.get("main").innerHTML,/Destination conflict/);
  await assert.rejects(()=>execute('saveForm("keep_open")'),/Destination conflict/);
  assert.equal(execute("state.forms.length"),2);
  execute('editor=newEditor(null);selectedPallet=null;editor.mode="manual";editor.destination={building:"Demo",department:"Tools",shipTo:"Demo dock"};editor.lines=[{...emptyLine(),description:"Manual material",qty:"2"}]');
  await execute('saveForm("keep_open")');
  assert.equal(execute("state.forms.length"),3);
  await execute('openPreview({kind:"form",id:state.forms[2].id,revision:1})');
  assert.match(document.elements.get("print-frame").srcdoc,/Manual material/);
  assert.equal(execute('directory.toLocations.some(r=>["Building 05","Best II","Eindhoven 1"].includes(r.building))'),false);
  assert.match(execute('renderPresets("Building 21")'),/Building 21 — NL15C/);
  await execute('actions["toggle-theme"]()');
  assert.equal(document.documentElement.dataset.theme,"dark");
  assert.equal(execute('state.settings.theme'),"dark");
  execute('pasteGrid("quantities","Document\\tHandling Unit\\tQuantity\\nD1\\t00001\\t1,5")');
  assert.equal(execute('imports.quantities.grid[1][1]'),"00001");
  assert.match(execute('sourcePayload("quantities").text'),/D1\t00001\t1,5/);
  execute('pasteGrid("quantities","D2\\t00002\\t3",10,0)');
  assert.equal(execute('imports.quantities.grid[10][1]'),"00002");
  assert.match(execute('sourceGrid("quantities")'),/data-grid-row="10"/);
  execute('pasteGrid("quantities","Document\\tHandling Unit\\tQuantity\\nD3\\t00003\\t5")');
  assert.equal(execute('imports.quantities.grid.length'),2);
  assert.equal(execute(`parseGridClipboard(${JSON.stringify('"Description"\t"HU"\n"Line 1\nLine 2"\t"H1"')})[1][0]`),"Line 1\nLine 2");
  execute('view="infeed";imports.quantities.decimalMark="."');
  await execute('actions.navigate({dataset:{view:"open-orders"}})');
  assert.equal(execute('state.sources.quantities.rows[0].hu'),"00003");
  assert.match(execute('renderOpenOrders()'),/DEMO-HU-003/);
  assert.doesNotMatch(execute('renderOpenOrders()'),/>DEMO-HU-001</);
  assert.match(execute('palletContents(palletForms(state.pallets[0].id))'),/DEMO-DN-01/);
  assert.match(execute('renderPresets("Building 21")'),/WH21/);
  assert.match(execute('renderPresets("Weert 2")'),/Key sight/);
  assert.doesNotMatch(execute('renderCreate()'),/class="stats"/);
  assert.match(execute('renderHistory()'),/class="stats"/);
  assert.equal(execute('unexpectedRemarks({destination:{building:"Building 17",shipTo:"B17-MOTION"},remarks:"KEYSIGHT Tech."}).length'),1);
  assert.equal(execute('unexpectedRemarks({destination:{building:"Weert 2",shipTo:"KEYSIGHT"},remarks:"KEYSIGHT Tech."}).length'),0);
  assert.equal(execute('unexpectedRemarks({automaticEmergency:true,remarks:"EMERGENCY\\nOld instructions"}).length'),1);
  execute('palletSearch="DEMO-HU-001"');
  assert.match(execute('renderPalletPanel()'),/Building 21 — B21-MOASSY/);
  assert.match(execute('renderInfeed()'),/>Internals</);
  assert.match(execute('renderInfeed()'),/expand-source/);

  for(const hu of ["LOAD-HU-01","LOAD-HU-02"]) {
    execute(`editor=newEditor(null);selectedPallet=null;editor.mode="manual";editor.destination={building:"Loading test",department:"Dock",shipTo:"LOAD-DOCK"};editor.lines=[{...emptyLine(),hu:${JSON.stringify(hu)},dn:"LOAD-DN",qty:"1"}]`);
    await execute('saveForm("finalise")');
  }
  await execute('actions["create-load"]({dataset:{building:"Loading test"}})');
  assert.equal(execute('state.loads[0].pallets.length'),2);
  assert.equal(execute('readyForLoad("Loading test").length'),0);
  assert.match(execute('renderLoads()'),/Loading test/);
  execute('openScanner(selectedLoad)');
  await execute('acceptScan("TO:PALLET:"+state.loads[0].pallets[0].id+":1")');
  assert.equal(execute('state.loads[0].scans.length'),1);
  await execute('acceptScan("TO:PALLET:"+state.loads[0].pallets[0].id+":1")');
  assert.equal(execute('state.loads[0].scans.length'),1);
  assert.match(document.elements.get("scan-feedback").textContent,/Already scanned/);
  await execute('acceptScan("TO:PALLET:"+state.pallets[0].id+":1")');
  assert.match(document.elements.get("scan-feedback").textContent,/Wrong destination/);
  execute('$("#loading-driver").value="Test driver";$("#loading-vehicle").value="TEST-01"');
  await execute('actions["complete-load"]()');
  assert.equal(execute('state.loads[0].status'),"partial");
  assert.equal(execute('readyForLoad("Loading test").length'),1);
  await execute('openPreview({kind:"load",id:state.loads[0].id,revision:1})');
  assert.match(document.elements.get("print-frame").srcdoc,/Loading manifest/);
  assert.match(document.elements.get("print-frame").srcdoc,/LOAD-HU-01/);
  assert.match(document.elements.get("print-frame").srcdoc,/Shipment QR code/);
  for(const page of ["loads","docks"]) {
    execute(`view=${JSON.stringify(page)};render()`);
    assert.doesNotMatch(document.elements.get("main").innerHTML,/\bundefined\b/);
  }
  const jsQR=require(path.join(root,"transport_order/web/jsQR.js"));
  const {spawnSync}=require("node:child_process");
  for(const payload of ["TO:PALLET:P-123456789ABC:1","http://127.0.0.1:8765/#scan=TO:LOAD:LOAD-123456789ABC:1"]) {
    const qr=spawnSync(process.env.PYTHON||"python",["-c","import json,sys;from transport_order.qr import matrix;print(json.dumps(matrix(sys.argv[1])))",payload],{cwd:root,encoding:"utf8"});
    assert.equal(qr.status,0,qr.stderr);
    const matrix=JSON.parse(qr.stdout),scale=6,width=(matrix.length+8)*scale,pixels=new Uint8ClampedArray(width*width*4).fill(255);
    matrix.forEach((row,y)=>[...row].forEach((cell,x)=>{if(cell==="1")for(let dy=0;dy<scale;dy++)for(let dx=0;dx<scale;dx++){const i=(((y+4)*scale+dy)*width+(x+4)*scale+dx)*4;pixels[i]=pixels[i+1]=pixels[i+2]=0;}}));
    assert.equal(jsQR(pixels,width,width).data,payload);
  }
  console.log("UI/API smoke passed, including manifest creation, QR progress, duplicates, wrong destination, partial pickup, manifest print and QR encode/decode roundtrip.");
  console.log("Native submission is mocked; this is not a physical-printer or live-camera test.");
}

main().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{
  server.kill();
  fs.rmSync(temporary,{recursive:true,force:true});
});
