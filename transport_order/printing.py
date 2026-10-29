from collections import defaultdict
from decimal import Decimal
from html import escape

from .domain import find
from .integrations.sap import InputError


def e(value):
    return escape(str(value or ""))


def address(location):
    return "<strong>" + e(location.get("building")) + "</strong><br>" + e(location.get("department")) + "<br>" + e(location.get("shipTo"))


def notes(form):
    values = []
    if form.get("automaticEmergency") or form.get("manualEmergency"):
        values.append("EMERGENCY")
    if form.get("specialPickup"):
        values.append("Special Pick-up")
    if form.get("remarks", "").strip():
        values.append(form["remarks"].strip())
    return "\n".join(values)


def table(lines, include_form=False):
    columns = (["Form"] if include_form else []) + ["12NC / Part nr.", "Description", "Qty", "HU", "DN"]
    head = "".join("<th>" + c + "</th>" for c in columns)
    rows = []
    for line in lines:
        fields = ([line.get("formId", "")] if include_form else []) + [line.get(k, "") for k in ("part", "description", "qty", "hu", "dn")]
        rows.append("<tr>" + "".join("<td>" + e(v) + "</td>" for v in fields) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


STYLE = """
@page { size: A4 portrait; margin: 13mm; }
* { box-sizing: border-box; }
body { margin: 0; color: #17233e; font: 10pt Arial, sans-serif; }
.copy + .copy { break-before: page; }
header { display: flex; justify-content: space-between; border-bottom: 3px solid #000066; padding-bottom: 12px; margin-bottom: 16px; }
h1 { color: #000066; font-size: 20pt; margin: 0 0 5px; }
h2 { color: #000066; font-size: 12pt; margin-top: 22px; }
.meta { text-align: right; font-size: 8pt; line-height: 1.6; }
.addresses { display: flex; gap: 24px; margin: 20px 0; }
.addresses div { flex: 1; border: 1px solid #ccd2e4; padding: 12px; line-height: 1.6; }
.label { color: #64708c; text-transform: uppercase; font-size: 8pt; letter-spacing: 1px; display: block; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; font-size: 8pt; }
th { background: #edf0fa; color: #000066; text-align: left; }
th, td { padding: 8px 5px; border: 1px solid #cbd2e1; vertical-align: top; overflow-wrap: anywhere; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
.remarks { border: 1px solid #cbd2e1; padding: 12px; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.6; }
.signature { margin-top: 28px; padding: 18px 0; border-top: 1px solid #cbd2e1; display: flex; justify-content: space-between; }
.status { background: #edf0fa; padding: 9px; margin-bottom: 15px; font-size: 9pt; }
.obsolete { background: #fff0df; border: 1px solid #c66d14; padding: 12px; margin-bottom: 15px; font-weight: bold; }
footer { color: #64708c; font-size: 8pt; border-top: 1px solid #d9deea; padding-top: 10px; margin-top: 20px; }
"""


def render_document(state, kind, record_id, revision, copies=1):
    record = find(state, "forms" if kind == "form" else "pallets", record_id)
    version = next((v for v in record["versions"] if v["revision"] == revision), None)
    if not version:
        raise InputError("There is no completed document for this revision.")
    obsolete = bool(record.get("removedAt")) or record["revision"] != revision or (kind == "pallet" and record["status"] != "finalised") or (kind == "form" and record["status"] != "complete")
    header = f"<header><div><h1>{'Transport order' if kind == 'form' else 'Pallet consolidation'}</h1><span>Delivery Operations · Netherlands</span></div><div class='meta'><b>{e(record_id)}</b><br>Revision {revision}<br>{e(version.get('updatedAt', version.get('at', '')))}<br>Prepared by {e(version.get('preparedBy', state['settings']['preparedBy']))}</div></header>"
    alert = "<div class='obsolete'>SUPERSEDED DOCUMENT — this record was changed, removed or reopened. Check the current revision before use.</div>" if obsolete else ""
    if kind == "form":
        form = version
        body = f"<div class='addresses'><div><span class='label'>From</span>{address(form['origin'])}</div><div><span class='label'>To</span>{address(form['destination'])}</div></div>"
        body += f"<div class='status'>Pallet {e(form.get('palletId'))} · Individual transport form · No tracking QR</div>"
        body += table(form["lines"])
        body += f"<h2>Remarks</h2><div class='remarks'>{e(notes(form)) or '—'}</div>"
        if form.get("overridden"):
            body += "<p>Manual destination override: " + e(form.get("overrideReason")) + "</p>"
        body += f"<p>Receiver telephone: {e(form.get('receiverPhone')) or '—'} &nbsp; Email: {e(form.get('receiverEmail')) or '—'}</p>"
    else:
        forms = version["forms"]
        body = f"<div class='addresses'><div><span class='label'>From</span>{address(forms[0]['origin'])}</div><div><span class='label'>To</span>{address(version['destination'])}</div></div>"
        lines = [dict(line, formId=f["id"]) for f in forms for line in f["lines"]]
        hus = {line["hu"] for line in lines if line.get("hu")}
        dns = {line["dn"] for line in lines if line.get("dn")}
        body += f"<div class='status'>Finalised pallet · {len(forms)} forms · {len(hus)} HUs · {len(dns)} deliveries · Tracking QR will be added in a later version</div>"
        summary = defaultdict(lambda: {"hus": set(), "qty": Decimal(0)})
        for line in lines:
            key = line.get("dn") or "No DN (manual)"
            summary[key]["qty"] += Decimal(line["qty"])
            if line.get("hu"):
                summary[key]["hus"].add(line["hu"])
        body += "<h2>Delivery summary</h2><table><thead><tr><th>DN</th><th>HUs</th><th>Quantity total (source units)</th></tr></thead><tbody>"
        body += "".join(f"<tr><td>{e(dn)}</td><td>{len(data['hus'])}</td><td>{e(format(data['qty'], 'f'))}</td></tr>" for dn, data in sorted(summary.items())) + "</tbody></table>"
        body += "<h2>All materials</h2>" + table(lines, True)
        remarks = "\n\n".join(f["id"] + ": " + notes(f) for f in forms if notes(f))
        body += "<h2>Remarks by form</h2><div class='remarks'>" + (e(remarks) or "—") + "</div>"
    body += "<div class='signature'><span>Received / transported by: __________________</span><span>Name + signature: __________________</span></div>"
    pages = "".join(f"<section class='copy'>{alert}{header}{body}<footer>{e(record_id)} · Revision {revision} · Copy {i + 1} of {copies} · TransportOrder prototype</footer></section>" for i in range(copies))
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{e(record_id)} — revision {revision}</title><style>{STYLE}</style></head><body>{pages}</body></html>"
