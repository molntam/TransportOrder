from collections import defaultdict
from decimal import Decimal
from html import escape

from .domain import find
from .integrations.sap import InputError


def e(value):
    return escape(str(value or ""))


def notes(form):
    values = []
    if form.get("automaticEmergency") or form.get("manualEmergency"):
        values.append("EMERGENCY")
    if form.get("specialPickup"):
        values.append("Special Pick-up")
    if form.get("remarks", "").strip():
        values.append(form["remarks"].strip())
    return "\n".join(values)


def document_model(state, kind, record_id, revision):
    if kind not in ("form", "pallet"):
        raise InputError("Unknown document type.")
    record = find(state, "forms" if kind == "form" else "pallets", record_id)
    version = next((v for v in record["versions"] if v["revision"] == revision), None)
    if not version:
        raise InputError("There is no completed document for this revision.")
    obsolete = bool(record.get("removedAt")) or record["revision"] != revision or (kind == "pallet" and record["status"] != "finalised") or (kind == "form" and record["status"] != "complete")
    forms = [version] if kind == "form" else version["forms"]
    lines = [line for form in forms for line in form["lines"]]
    columns = [{"key": key, "label": label, "weight": weight} for key, label, weight in
               [("part", "12NC / Part nr.", 1.2), ("description", "Description", 2.2),
                ("qty", "Qty", .6), ("hu", "HU", 1.3), ("dn", "DN", 1.3)]
               if kind == "form" or key not in ("part", "description") or any(line.get(key, "").strip() for line in lines)]
    summary = defaultdict(lambda: {"hus": set(), "qty": Decimal(0)})
    if kind == "pallet":
        for line in lines:
            item = summary[line.get("dn") or "No DN (manual)"]
            item["qty"] += Decimal(line["qty"])
            if line.get("hu"):
                item["hus"].add(line["hu"])
    remarks = "\n\n".join(dict.fromkeys(notes(f) for f in forms if notes(f)))
    contact = ""
    if kind == "form":
        contact = "Receiver telephone: " + (version.get("receiverPhone") or "—") + "    Email: " + (version.get("receiverEmail") or "—")
        if version.get("overridden"):
            remarks += "\n\nDestination override: " + version.get("overrideReason", "")
    hus = {line["hu"] for line in lines if line.get("hu")}
    dns = {line["dn"] for line in lines if line.get("dn")}
    return {"kind": kind, "id": record_id, "revision": revision,
            "title": "Transport order" if kind == "form" or len(dns) <= 1 else "Pallet consolidation",
            "at": version.get("updatedAt", version.get("at", "")),
            "preparedBy": ", ".join(dict.fromkeys(f.get("preparedBy") or "Local user" for f in forms)),
            "origin": forms[0]["origin"], "destination": version["destination"],
            "status": ("Individual transport form · " if kind == "form" else "Finalised pallet · ") + f"{len(hus)} HUs · {len(dns)} deliveries",
            "columns": columns, "rows": [[str(line.get(c["key"], "")) for c in columns] for line in lines],
            "summary": [[dn, str(len(v["hus"])), format(v["qty"], "f")] for dn, v in sorted(summary.items())],
            "remarks": remarks.strip(), "contact": contact, "obsolete": obsolete, "qrPlaceholder": kind == "pallet"}


def address(location):
    return "<strong class='building-name'>" + e(location.get("building")) + "</strong><br>" + e(location.get("department")) + "<br>" + e(location.get("shipTo"))


def html_table(columns, rows):
    return "<table><thead><tr>" + "".join("<th>" + e(c["label"]) + "</th>" for c in columns) + "</tr></thead><tbody>" + "".join("<tr>" + "".join("<td>" + e(cell) + "</td>" for cell in row) + "</tr>" for row in rows) + "</tbody></table>"


STYLE = """
@page { size: A4 portrait; margin: 13mm; }
* { box-sizing: border-box; }
body { margin: 0; color: #17233e; font: 11pt 'Segoe UI', Arial, sans-serif; }
.copy + .copy { break-before: page; }
header { display: flex; justify-content: space-between; gap: 12px; border-bottom: 3px solid #000066; padding-bottom: 12px; margin-bottom: 16px; }
h1 { color: #000066; font-size: 21pt; margin: 0 0 5px; }
h2 { color: #000066; font-size: 12pt; margin-top: 22px; }
.meta { text-align: right; font-size: 9pt; line-height: 1.6; }
.addresses { display: flex; gap: 18px; margin: 20px 0; align-items: stretch; }
.addresses .address { flex: 1; border: 1px solid #aab5c9; padding: 12px; line-height: 1.6; overflow-wrap: anywhere; }
.building-name { font-size: 18pt; font-weight: 800; color: #000066; }
.label { color: #485976; text-transform: uppercase; font-size: 9pt; letter-spacing: 1px; display: block; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; font-size: 10pt; }
th { background: #edf0fa; color: #000066; text-align: left; }
th, td { padding: 8px 6px; border: 1px solid #aab5c9; vertical-align: top; overflow-wrap: anywhere; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
.remarks { border: 1px solid #aab5c9; padding: 12px; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.6; }
.signature { margin-top: 28px; padding: 18px 0; border-top: 1px solid #aab5c9; display: flex; justify-content: space-between; }
.status { background: #edf0fa; padding: 9px; margin-bottom: 15px; font-size: 10pt; }
.obsolete { background: #fff0df; border: 1px solid #c66d14; padding: 12px; margin-bottom: 15px; font-weight: bold; }
.qr-placeholder { width: 92px; min-height: 92px; border: 2px dashed #7b89a3; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; flex-shrink: 0; padding: 8px; break-inside: avoid; }
.qr-placeholder strong { color: #000066; font-size: 11pt; }
.qr-placeholder small { font-size: 8pt; color: #485976; line-height: 1.4; margin-top: 6px; }
footer { color: #485976; font-size: 9pt; border-top: 1px solid #aab5c9; padding-top: 10px; margin-top: 20px; }
"""


def render_document(state, kind, record_id, revision, copies=1):
    model = document_model(state, kind, record_id, revision)
    qr = "<div class='qr-placeholder' aria-label='QR code placeholder'><strong>QR CODE</strong><small>Tracking to be connected</small></div>" if model["qrPlaceholder"] else ""
    header = f"<header><div><h1>{e(model['title'])}</h1><span>Delivery Operations · Netherlands</span></div><div class='meta'><b>{e(record_id)}</b><br>Revision {revision}<br>{e(model['at'])}<br>Prepared by {e(model['preparedBy'])}</div>{qr}</header>"
    alert = "<div class='obsolete'>SUPERSEDED DOCUMENT — this record was changed, removed or reopened. Check the current revision before use.</div>" if model["obsolete"] else ""
    body = f"<div class='addresses'><div class='address'><span class='label'>From</span>{address(model['origin'])}</div><div class='address'><span class='label'>To</span>{address(model['destination'])}</div></div><div class='status'>{e(model['status'])}</div>"
    if model["summary"]:
        body += "<h2>Delivery summary</h2>" + html_table([{"label":"DN"},{"label":"HUs"},{"label":"Quantity total (source units)"}], model["summary"])
        body += "<h2>Handling units &amp; deliveries</h2>"
    body += html_table(model["columns"], model["rows"])
    if model["remarks"]:
        body += "<h2>Remarks</h2><div class='remarks'>" + e(model["remarks"]) + "</div>"
    if model["contact"]:
        body += "<p>" + e(model["contact"]) + "</p>"
    body += "<div class='signature'><span>Received / transported by: __________________</span><span>Name + signature: __________________</span></div>"
    pages = "".join(f"<section class='copy'>{alert}{header}{body}<footer>{e(record_id)} · Revision {revision} · Copy {i + 1} of {copies} · TransportOrder</footer></section>" for i in range(copies))
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{e(record_id)} — revision {revision}</title><style>{STYLE}</style></head><body>{pages}</body></html>"
