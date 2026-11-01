import copy
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from .integrations.sap import InputError, identifier, parse_table, quantity

LOCATIONS = json.loads(Path(__file__).with_name("locations.json").read_text(encoding="utf-8"))
LOCATIONS["toLocations"] = [r for r in LOCATIONS["toLocations"] if r["building"].upper() not in {"BUILDING 05", "BEST II", "EINDHOVEN 1"}]
for location in LOCATIONS["toLocations"]:
    if location["building"] == "WH21-MPS":
        location["building"] = "Building 21"
        location["sourceCode"] = "WH21-MPSC"
LOCATIONS["automatic"]["WH21-MPSC"]["building"] = "Building 21"
for location in LOCATIONS["toLocations"]:
    if location["shipTo"] == "KEYSIGHT":
        location["department"] = "Key sight"
        location["label"] = "Weert 2 — Key sight"
DEFAULT_ORIGIN = {"building": "Building 05", "department": "Delivery Ops", "shipTo": "B5L - Delivery Ops"}


def default_settings():
    return {"preparedBy": "", "origin": dict(DEFAULT_ORIGIN), "openCopies": 1,
            "finalCopies": 2, "manifestCopies": 1, "dockSlots": [], "printer": "", "theme": "light"}


def migrate_settings(settings):
    result = {**default_settings(), **settings}
    result.pop("copies", None)
    return result


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def uid(prefix):
    return prefix + "-" + uuid4().hex[:12].upper()


def initial_state():
    return {"schema": 1, "revision": 0, "sources": {"shipto": None, "quantities": None},
            "forms": [], "pallets": [], "loads": [], "events": [],
            "settings": default_settings()}


def event(state, action, target, detail=""):
    state["events"].append({"id": uid("EV"), "at": now(), "action": action,
                            "target": target, "detail": detail,
                            "actor": state["settings"]["preparedBy"] or "Local user"})


def find(state, collection, record_id):
    record = next((r for r in state[collection] if r["id"] == record_id), None)
    if record is None:
        raise InputError("This record no longer exists. Refresh the page.")
    return record


def clean_location(value):
    value = value if isinstance(value, dict) else {}
    return {k: str(value.get(k, "")).strip()[:300] for k in ("building", "department", "shipTo")}


def route_key(location):
    return tuple(str(location.get(k, "")).strip().upper() for k in ("building", "department", "shipTo"))


def route_for(record):
    code = record["shipTo"].strip().upper()
    if code == "NL05C":
        return None, "NL05C needs an explicit destination: Weert or Eindhoven / BIC."
    if code == "WH-WEERT1A":
        external = record.get("externalId", "").strip().upper()
        if external == "SCRAP":
            return {"building": "Weert 1A", "department": "SCRAP", "shipTo": "WEERT1A SCRAP"}, ""
        if external in ("", "0", "KNIKKERBAK"):
            return {"building": "Weert 1A", "department": "Reverse Logistics / Re-use parts", "shipTo": "WH-WEERT1A"}, ""
        return None, "Unrecognised Weert 1A External Delivery ID; review the route manually."
    route = LOCATIONS["automatic"].get(code)
    return copy.deepcopy(route), "" if route else "No destination mapping exists; select a destination manually."


def source_diagnostics(state):
    a = {r["hu"] for r in (state["sources"]["shipto"] or {}).get("rows", [])}
    b = {r["hu"] for r in (state["sources"]["quantities"] or {}).get("rows", [])}
    return {"missingQuantities": sorted(a - b), "missingShipto": sorted(b - a)}


def resolve(state, lines, form_id=None, chosen_destination=None, override_reason=""):
    if not isinstance(lines, list) or len(lines) > 500:
        raise InputError("A form can contain at most 500 rows.")
    ships, quantities = defaultdict(list), defaultdict(list)
    for row in (state["sources"]["shipto"] or {}).get("rows", []):
        ships[row["hu"]].append(row)
    for row in (state["sources"]["quantities"] or {}).get("rows", []):
        quantities[row["hu"]].append(row)
    assigned = {}
    for form in state["forms"]:
        if form["id"] == form_id or form.get("removedAt") or form["status"] == "draft":
            continue
        for line in form["lines"]:
            if line.get("hu"):
                assigned[line["hu"]] = form
    resolved, issues, routes, codes, seen = [], [], [], set(), set()
    emergency = False
    for number, raw in enumerate(lines, 1):
        line = {k: str(raw.get(k, "") or "").strip()[:1000] for k in ("part", "description", "hu", "dn", "qty")}
        line.update({"issues": [], "emergency": False, "sourceShipTo": "", "destination": None})
        if not any(line.values()):
            continue
        hu = identifier(line["hu"])
        line["hu"] = hu

        def issue(message, code="error"):
            item = {"line": number, "hu": hu, "message": message, "code": code}
            issues.append(item)
            line["issues"].append(item)

        if not hu:
            issue("Enter a HU or switch to Manual mode.")
        elif hu in seen:
            issue("Duplicate HU on this form. Remove the repeated row.")
        elif hu in assigned:
            other = assigned[hu]
            issue(f"Already assigned to {other.get('palletId') or 'form'} / {other['id']}.")
        seen.add(hu)
        records = ships.get(hu, [])
        values = {tuple(r.get(k, "") for k in ("document", "dn", "shipTo", "condition", "externalId")) for r in records}
        if not records:
            line.update({"dn": "", "qty": ""})
            issue("HU not found in Ship-to data.")
        elif len(values) > 1:
            line.update({"dn": "", "qty": ""})
            issue("Conflicting Ship-to records; correct the imported data.")
        else:
            record = records[0]
            route, warning = route_for(record)
            line.update({"dn": record["dn"], "sourceShipTo": record["shipTo"],
                         "document": record["document"], "condition": record.get("condition", ""),
                         "externalId": record.get("externalId", ""), "destination": route,
                         "emergency": record.get("condition", "").upper() in ("S4", "I2")})
            emergency = emergency or line["emergency"]
            codes.add(record["shipTo"].upper())
            if route:
                routes.append(route)
            if warning:
                code = "override" if chosen_destination and all(chosen_destination.values()) and override_reason.strip() else "error"
                issue(warning, code)
            qrows = quantities.get(hu, [])
            if not qrows:
                line["qty"] = ""
                issue("HU has no quantity records.")
            elif {r["document"] for r in qrows} != {record["document"]}:
                line["qty"] = ""
                issue("Document mismatch: Ship-to " + record["document"] + "; Quantities " + ", ".join(sorted({r["document"] for r in qrows})) + ".")
            else:
                total = sum((Decimal(r["qty"]) for r in qrows), Decimal(0))
                line["qty"] = format(total, "f")
                line["quantityRecords"] = len(qrows)
                if total <= 0:
                    issue("Total quantity must be greater than zero.")
        resolved.append(line)
    unique_routes = {route_key(r) for r in routes}
    if len(codes) > 1 or len(unique_routes) > 1:
        for line in resolved:
            if line.get("sourceShipTo"):
                item = {"hu": line["hu"], "code": "error", "message": "Destination conflict: " + line["sourceShipTo"] + " / " + (line.get("destination") or {}).get("department", "review route")}
                line["issues"].append(item)
                issues.append(item)
    destination = routes[0] if len(unique_routes) == 1 and len(codes) == 1 else None
    needs_override = any(i["code"] == "override" for i in issues)
    if chosen_destination and all(chosen_destination.values()):
        if destination and route_key(chosen_destination) != route_key(destination):
            if override_reason.strip():
                needs_override = True
            else:
                issues.append({"code": "error", "message": "The selected destination differs from the SAP route. Enter a reason to override it."})
        if needs_override:
            destination = chosen_destination
    return {"lines": resolved, "issues": issues, "destination": destination,
            "emergency": emergency, "overridden": needs_override,
            "valid": bool(resolved) and not any(i["code"] == "error" for i in issues)}


def normalize_form(state, payload, complete):
    mode = payload.get("mode", "automatic")
    if mode not in ("automatic", "manual"):
        raise InputError("Choose Automatic or Manual mode.")
    lines = payload.get("lines", [])
    if not isinstance(lines, list) or len(lines) > 500:
        raise InputError("Use at most 500 material rows.")
    destination = clean_location(payload.get("destination"))
    origin = clean_location(payload.get("origin"))
    reason = str(payload.get("overrideReason", "")).strip()[:1000]
    automatic_emergency, overridden, issues = False, False, []
    if mode == "automatic":
        result = resolve(state, lines, payload.get("id"), destination, reason)
        lines, automatic_emergency, overridden = result["lines"], result["emergency"], result["overridden"]
        issues = [i for i in result["issues"] if i["code"] == "error"]
        if result["destination"]:
            destination = result["destination"]
    else:
        lines = [{k: str(line.get(k, "") or "").strip()[:1000] for k in ("part", "description", "hu", "dn", "qty")} for line in lines]
        lines = [line for line in lines if any(line.values())]
        seen = set()
        existing = {line["hu"]: form for form in state["forms"] if form["id"] != payload.get("id") and not form.get("removedAt") and form["status"] != "draft" for line in form["lines"] if line.get("hu")}
        for line in lines:
            line["hu"] = identifier(line["hu"])
            if line["hu"]:
                if line["hu"] in seen or line["hu"] in existing:
                    issues.append({"message": f"HU {line['hu']} is already used on this form or another active form."})
                seen.add(line["hu"])
    if complete:
        if not all(origin.values()) or not all(destination.values()):
            issues.append({"message": "Complete the From and To building, department and ship-to fields."})
        if not lines:
            issues.append({"message": "Add at least one material row."})
        for i, line in enumerate(lines, 1):
            if not any(line.get(k) for k in ("part", "description", "hu", "dn")):
                issues.append({"message": f"Row {i}: enter a part number, description, HU or DN."})
            try:
                line["qty"] = quantity(line.get("qty", ""))
                if Decimal(line["qty"]) <= 0:
                    raise InputError("Quantity must be greater than zero.")
            except InputError as exc:
                issues.append({"message": f"Row {i}: {exc}"})
        if issues:
            raise InputError("\n".join(dict.fromkeys(i["message"] for i in issues)))
    return {"mode": mode, "origin": origin, "destination": destination, "lines": lines,
            "preparedBy": str(payload.get("preparedBy", "")).strip()[:200],
            "remarks": str(payload.get("remarks", ""))[:5000],
            "receiverPhone": str(payload.get("receiverPhone", ""))[:200],
            "receiverEmail": str(payload.get("receiverEmail", ""))[:300],
            "manualEmergency": bool(payload.get("manualEmergency")),
            "specialPickup": bool(payload.get("specialPickup")),
            "automaticEmergency": automatic_emergency, "overrideReason": reason,
            "overridden": overridden, "sourceImports": {k: v["importedAt"] if v else None for k, v in state["sources"].items()}}


def pallet_compatibility(state, pallet, form, exclude_id=None):
    others = [f for f in state["forms"] if f.get("palletId") == pallet["id"] and f["id"] != exclude_id and not f.get("removedAt")]
    routes = [f["destination"] for f in others if all(f["destination"].values())]
    if routes and all(form["destination"].values()) and any(route_key(r) != route_key(form["destination"]) for r in routes):
        raise InputError("This form does not match the selected pallet's building, department and ship-to. Select another pallet or start a new one.")
    source_codes = {l.get("sourceShipTo", "").upper() for f in others for l in f["lines"] if l.get("sourceShipTo")}
    new_codes = {l.get("sourceShipTo", "").upper() for l in form["lines"] if l.get("sourceShipTo")}
    if len(source_codes | new_codes) > 1:
        raise InputError("The selected pallet contains a different SAP ship-to code. Keep the destinations separate.")
    if others and any(route_key(f["origin"]) != route_key(form["origin"]) for f in others):
        raise InputError("Forms on one pallet must have the same origin.")


def finalise(state, pallet):
    if pallet["status"] != "open":
        raise InputError("This pallet is already finalised.")
    forms = [f for f in state["forms"] if f.get("palletId") == pallet["id"] and not f.get("removedAt")]
    if not forms or any(f["status"] != "complete" for f in forms):
        raise InputError("Complete every draft on this pallet before finalising.")
    seen = set()
    for form in forms:
        pallet_compatibility(state, pallet, form, form["id"])
        for line in form["lines"]:
            if line.get("hu"):
                if line["hu"] in seen:
                    raise InputError("HU " + line["hu"] + " appears more than once on this pallet.")
                seen.add(line["hu"])
    pallet["revision"] += 1
    pallet.update({"status": "finalised", "finalisedAt": now(), "updatedAt": now(), "destination": forms[0]["destination"]})
    pallet["versions"].append({"revision": pallet["revision"], "at": now(), "forms": copy.deepcopy(forms), "destination": copy.deepcopy(pallet["destination"])})
    event(state, "Pallet finalised", pallet["id"], f"Revision {pallet['revision']}; {len(forms)} forms; {len(seen)} HUs")
    return {"print": {"kind": "pallet", "id": pallet["id"], "revision": pallet["revision"]}}


def apply_action(state, action, payload):
    from .loads import apply_load_action, reserved_ids, validate_slots
    if action in {"create_load", "scan_load", "unscan_load", "complete_load", "cancel_load"}:
        return apply_load_action(state, action, payload)
    if action == "import":
        result = parse_table(payload.get("kind"), payload.get("text", ""), payload.get("content"), payload.get("decimalMark", "."))
        if result["errors"]:
            raise InputError("Correct all import errors before applying this table.")
        state["sources"][result["kind"]] = {"rows": result["rows"], "importedAt": now(),
            "count": result["count"], "uniqueHus": result["uniqueHus"], "warnings": result["warnings"],
            "filename": str(payload.get("filename", "Pasted SAP table"))[:200]}
        event(state, "SAP data imported", result["kind"], f"{result['count']} records; {result['uniqueHus']} HUs")
        return {}
    if action == "clear_source":
        kind = payload.get("kind")
        if kind not in state["sources"]:
            raise InputError("Unknown source.")
        state["sources"][kind] = None
        event(state, "SAP data cleared", kind)
        return {}
    if action == "settings":
        settings = migrate_settings({**state["settings"], **payload})
        for key in ("openCopies", "finalCopies", "manifestCopies"):
            settings[key] = int(settings[key])
            if settings[key] not in range(1, 6):
                raise InputError("Choose between 1 and 5 copies for each document type.")
        if settings["theme"] not in ("light", "dark", "system"):
            raise InputError("Choose Light, Dark or Follow system.")
        state["settings"] = {"preparedBy": str(settings["preparedBy"]).strip()[:200],
            "origin": clean_location(settings["origin"]), "openCopies": settings["openCopies"],
            "finalCopies": settings["finalCopies"], "printer": str(settings["printer"]).strip()[:300],
            "theme": settings["theme"], "manifestCopies": settings["manifestCopies"],
            "dockSlots": validate_slots(settings["dockSlots"])}
        event(state, "Settings updated", "settings")
        return {}
    if action == "save_form":
        intent = payload.get("intent", "draft")
        if intent not in ("draft", "keep_open", "finalise"):
            raise InputError("Unknown form action.")
        old = find(state, "forms", payload["id"]) if payload.get("id") else None
        if old and old.get("removedAt"):
            raise InputError("This form was removed. Create a new form.")
        previous = find(state, "pallets", old["palletId"]) if old and old.get("palletId") else None
        if previous and previous["status"] != "open":
            raise InputError("Reopen the finalised pallet before editing its forms.")
        form = normalize_form(state, payload, intent != "draft")
        pallet_id = payload.get("palletId")
        if old and old.get("palletId") != pallet_id:
            raise InputError("Remove the form from its current pallet before assigning it elsewhere.")
        pallet = find(state, "pallets", pallet_id) if pallet_id else None
        if pallet and pallet["status"] != "open":
            raise InputError("Select an open pallet.")
        if intent != "draft" and not pallet:
            pallet = {"id": uid("P"), "status": "open", "revision": 0, "createdAt": now(),
                      "updatedAt": now(), "destination": form["destination"], "versions": []}
            state["pallets"].append(pallet)
            event(state, "Pallet opened", pallet["id"])
        if pallet:
            pallet_compatibility(state, pallet, form, old["id"] if old else None)
            pallet.update({"updatedAt": now(), "destination": form["destination"]})
        form.update({"id": old["id"] if old else uid("TO"),
                     "palletId": pallet["id"] if pallet else None,
                     "createdAt": old["createdAt"] if old else now(), "updatedAt": now(),
                     "status": "draft" if intent == "draft" else "complete",
                     "revision": (old["revision"] if old else 0) + (intent != "draft"),
                     "versions": copy.deepcopy(old.get("versions", [])) if old else []})
        if intent != "draft":
            form["versions"].append({k: copy.deepcopy(v) for k, v in form.items() if k != "versions"})
        if old:
            state["forms"][state["forms"].index(old)] = form
        else:
            state["forms"].append(form)
        event(state, "Draft saved" if intent == "draft" else "Form completed", form["id"], form.get("overrideReason", ""))
        result = {"formId": form["id"], "palletId": form["palletId"]}
        if intent == "finalise":
            result.update(finalise(state, pallet))
        elif intent == "keep_open":
            result["print"] = {"kind": "form", "id": form["id"], "revision": form["revision"]}
        return result
    if action == "finalise_pallet":
        return finalise(state, find(state, "pallets", payload.get("id")))
    if action == "reopen_pallet":
        pallet = find(state, "pallets", payload.get("id"))
        if pallet.get("collectedAt") or pallet["id"] in reserved_ids(state):
            raise InputError("This pallet is collected or reserved on a loading manifest. Cancel the manifest before correcting an uncollected pallet.")
        reason = str(payload.get("reason", "")).strip()[:1000]
        if pallet["status"] != "finalised" or not reason:
            raise InputError("Select a finalised pallet and enter a reason for reopening.")
        pallet.update({"status": "open", "updatedAt": now()})
        event(state, "Pallet reopened", pallet["id"], reason)
        return {"palletId": pallet["id"]}
    if action == "remove_form":
        form = find(state, "forms", payload.get("id"))
        if form.get("palletId"):
            pallet = find(state, "pallets", form["palletId"])
            if pallet["status"] != "open":
                raise InputError("Reopen this pallet before removing a form.")
            pallet["updatedAt"] = now()
        if form.get("removedAt"):
            raise InputError("This form is already removed.")
        form["removedAt"] = now()
        event(state, "Form removed", form["id"], str(payload.get("reason", "Correction"))[:1000])
        return {}
    raise InputError("Unknown action.")
