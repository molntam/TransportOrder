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
    querySelector(selector) { return selector.startsWith("#") ? this.elements.get(selector.slice(1)) || null : null; },
    querySelectorAll() { return []; },
    addEventListener() {},
    createElement() { return new Element(this, "temporary"); },
  };
  for (const id of ["main","navigation","page-label","source-health","user-label","avatar","dialog","toast","refresh-button","help-icon","power-icon","app-version"]) {
    document.elements.set(id, new Element(document,id));
  }
  const saved = new Map();
  const sessionStorage = {getItem:key=>saved.get(key)||null,setItem:(key,value)=>saved.set(key,value),removeItem:key=>saved.delete(key)};
  const context = vm.createContext({document,sessionStorage,console,URLSearchParams,structuredClone,Intl,Date,Number,String,Set,Map,Blob,URL,
    location:{hash:"#session=smoke-test-session"},history:{replaceState(){}},window:{addEventListener(){}},
    setTimeout:(fn,ms)=>setTimeout(fn,ms).unref(),clearTimeout,
    fetch:(url,options)=>fetch(base+url,options),
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
  assert.ok(execute("selectedPallet"));
  assert.match(document.elements.get("print-frame").srcdoc,/Keep this note/);

  execute('editor.lines=[{...emptyLine(),hu:"DEMO-HU-002"}]');
  await execute("resolveEditor()");
  assert.equal(execute("editor.automaticEmergency"),true);
  await execute('saveForm("finalise")');
  assert.equal(execute("state.pallets[0].status"),"finalised");
  assert.equal(execute("state.pallets[0].versions[0].forms.length"),2);
  assert.match(document.elements.get("print-frame").srcdoc,/Delivery summary/);
  assert.match(document.elements.get("print-frame").srcdoc,/EMERGENCY/);

  for (const page of ["infeed","pallets","history","settings","create"]) {
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
  assert.match(document.elements.get("print-frame").srcdoc,/Manual material/);
  console.log("UI smoke passed: all five views, imports, HU resolution, quantity sum, two-form consolidation, Emergency, print HTML, reopening, conflict rejection and manual entry.");
  console.log("This is a DOM-shell/API integration check, not a rendered-browser or physical-printer test.");
}

main().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{
  server.kill();
  fs.rmSync(temporary,{recursive:true,force:true});
});
