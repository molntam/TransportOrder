import copy
import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from transport_order.domain import initial_state, apply_action, resolve, DEFAULT_ORIGIN
from transport_order.integrations.sap import parse_table, InputError, quantity
from transport_order.printing import render_document
from transport_order.server import create_server
from transport_order.storage import Store, ConflictError, WorkspaceLock


SHIP_HEADER = "Outbound Delivery Order\tERP Document\tHandling Unit\tShip-To\tShipping Condition\tExternal Delivery ID\n"
QUANTITY_HEADER = "Document\tHandling Unit\tQuantity\n"


def loaded_state():
    state = initial_state()
    apply_action(state, "import", {"kind": "shipto", "text": SHIP_HEADER +
        "ODO1\tDN1\tHU1\tB21-MOASSY\tS1\t\nODO2\tDN2\tHU2\tB21-MOASSY\tS4\t\n"
        "ODO3\tDN3\tHU3\tNL10C\tS1\t\nODO4\tDN4\tHU4\tWH-WEERT1A\tS1\tSCRAP\n"
        "ODO5\tDN5\tHU5\tWH-WEERT1A\tI2\t\nODO6\tDN6\tHU6\tNL05C\tS1\t\n"
        "ODO7\tDN7\tHU7\tWH-WEERT1A\tS1\tOTHER"})
    apply_action(state, "import", {"kind": "quantities", "text": QUANTITY_HEADER +
        "ODO1\tHU1\t4\nODO1\tHU1\t21\nODO2\tHU2\t3\nODO3\tHU3\t12\n"
        "ODO4\tHU4\t7\nODO5\tHU5\t2\nODO6\tHU6\t1\nODO7\tHU7\t4"})
    return state


def form(hu="HU1", **updates):
    result = {"mode": "automatic", "origin": dict(DEFAULT_ORIGIN), "destination": {},
              "lines": [{"hu": hu}], "preparedBy": "Demo user", "intent": "keep_open"}
    result.update(updates)
    return result


class ParsingTests(unittest.TestCase):
    def test_identifiers_preserve_leading_zeros(self):
        r = parse_table("quantities", QUANTITY_HEADER + "0001\t00002\t3")
        self.assertEqual(r["rows"][0]["hu"], "00002")
        self.assertEqual(r["rows"][0]["document"], "0001")

    def test_multi_item_quantity_records_are_not_deduplicated(self):
        r = parse_table("quantities", QUANTITY_HEADER + "D1\tH1\t3\nD1\tH1\t3")
        self.assertEqual(r["count"], 2)
        self.assertEqual(len(r["warnings"]), 1)

    def test_duplicate_shipto_records_are_skipped(self):
        row = "D1\tDN1\tH1\tB21-MOASSY\tS1\t"
        r = parse_table("shipto", SHIP_HEADER + row + "\n" + row)
        self.assertEqual(r["count"], 1)

    def test_conflicting_shipto_records_block_import(self):
        r = parse_table("shipto", SHIP_HEADER + "D1\tDN1\tH1\tB21-MOASSY\tS1\t\nD1\tDN1\tH1\tNL10C\tS1\t")
        self.assertTrue(r["errors"])

    def test_missing_headers_block_import(self):
        with self.assertRaises(InputError):
            parse_table("shipto", "HU\tDN\nH1\tD1")

    def test_bad_quantity_identifies_source_row(self):
        r = parse_table("quantities", QUANTITY_HEADER + "D1\tH1\tunknown")
        self.assertEqual(r["errors"][0]["row"], 2)

    def test_decimal_comma_and_thousands(self):
        self.assertEqual(quantity("42.700,50", ","), "42700.50")
        self.assertEqual(quantity("42,700.50", "."), "42700.50")
        self.assertEqual(quantity("1,5", ","), "1.5")
        with self.assertRaises(InputError):
            quantity("1,5", ".")

    def test_semicolon_csv(self):
        r = parse_table("quantities", 'Document;Handling Unit;Quantity\nD1;H1;1,5', decimal_mark=",")
        self.assertEqual(r["rows"][0]["qty"], "1.5")

    def test_scientific_identifier_requires_original_text(self):
        r = parse_table("quantities", QUANTITY_HEADER + "D1\t2.006E9\t3")
        self.assertIn("scientific notation", r["errors"][0]["message"])

    def test_xlsx_shared_and_inline_strings(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w") as book:
            book.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="SAP" sheetId="1" r:id="rId1"/></sheets></workbook>')
            book.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            book.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Document</t></si><si><t>Handling Unit</t></si><si><t>Quantity</t></si></sst>')
            book.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>D1</t></is></c><c r="B2" t="inlineStr"><is><t>00001</t></is></c><c r="C2"><v>1.5</v></c></row></sheetData></worksheet>')
        result = parse_table("quantities", content=content.getvalue(), decimal_mark=",")
        self.assertEqual(result["rows"][0]["hu"], "00001")
        self.assertEqual(result["rows"][0]["qty"], "1.5")


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.state = loaded_state()

    def test_hu_uses_erp_document_and_sums_quantity(self):
        r = resolve(self.state, [{"hu": "HU1"}])
        self.assertTrue(r["valid"])
        self.assertEqual(r["lines"][0]["dn"], "DN1")
        self.assertEqual(r["lines"][0]["qty"], "25")
        self.assertEqual(r["destination"]["building"], "Building 21")

    def test_both_emergency_codes(self):
        for hu in ("HU2", "HU5"):
            self.assertTrue(resolve(self.state, [{"hu": hu}])["emergency"])

    def test_different_destinations_identify_each_hu(self):
        r = resolve(self.state, [{"hu": "HU1"}, {"hu": "HU3"}])
        self.assertFalse(r["valid"])
        conflicts = [i["hu"] for i in r["issues"] if "Destination conflict" in i["message"]]
        self.assertEqual(conflicts, ["HU1", "HU3"])

    def test_weert_scrap_does_not_mix_with_reuse(self):
        r = resolve(self.state, [{"hu": "HU4"}, {"hu": "HU5"}])
        self.assertFalse(r["valid"])
        self.assertEqual(r["lines"][0]["destination"]["department"], "SCRAP")

    def test_unknown_weert_external_id_needs_override(self):
        self.assertFalse(resolve(self.state, [{"hu": "HU7"}])["valid"])

    def test_nl05_requires_explicit_destination_and_reason(self):
        self.assertFalse(resolve(self.state, [{"hu": "HU6"}])["valid"])
        chosen = {"building": "Weert 2", "department": "ASML Service Operations", "shipTo": "NL05C"}
        r = resolve(self.state, [{"hu": "HU6"}], chosen_destination=chosen, override_reason="Address checked")
        self.assertTrue(r["valid"])
        self.assertEqual(r["destination"], chosen)
        self.assertTrue(r["overridden"])

    def test_missing_hu_has_specific_error(self):
        r = resolve(self.state, [{"hu": "MISSING"}])
        self.assertEqual(r["issues"][0]["hu"], "MISSING")
        self.assertFalse(r["valid"])

    def test_duplicate_hu_blocks_completion(self):
        self.assertFalse(resolve(self.state, [{"hu": "HU1"}, {"hu": "HU1"}])["valid"])

    def test_quantity_document_must_match(self):
        self.state["sources"]["quantities"]["rows"][0]["document"] = "WRONG"
        r = resolve(self.state, [{"hu": "HU1"}])
        self.assertFalse(r["valid"])
        self.assertTrue(any("Document mismatch" in i["message"] for i in r["issues"]))

    def test_missing_quantity_is_not_zero(self):
        self.state["sources"]["quantities"]["rows"] = []
        r = resolve(self.state, [{"hu": "HU1"}])
        self.assertFalse(r["valid"])
        self.assertEqual(r["lines"][0]["qty"], "")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.state = loaded_state()

    def save(self, **kwargs):
        return apply_action(self.state, "save_form", form(**kwargs))

    def test_incomplete_draft_can_be_saved(self):
        r = self.save(hu="", intent="draft")
        self.assertIsNone(r["palletId"])
        self.assertEqual(self.state["forms"][0]["status"], "draft")

    def test_completed_form_creates_open_pallet(self):
        self.save()
        self.assertEqual(self.state["pallets"][0]["status"], "open")
        self.assertEqual(self.state["forms"][0]["revision"], 1)

    def test_add_form_to_same_pallet_and_finalise(self):
        first = self.save()
        r = self.save(hu="HU2", palletId=first["palletId"], intent="finalise")
        p = self.state["pallets"][0]
        self.assertEqual(p["status"], "finalised")
        self.assertEqual(len(p["versions"][0]["forms"]), 2)
        self.assertEqual(r["print"]["kind"], "pallet")

    def test_wrong_destination_cannot_join_pallet(self):
        first = self.save()
        with self.assertRaisesRegex(InputError, "does not match"):
            self.save(hu="HU3", palletId=first["palletId"])

    def test_hu_cannot_be_assigned_twice(self):
        self.save()
        with self.assertRaisesRegex(InputError, "Already assigned"):
            self.save()

    def test_manual_form_without_hu(self):
        r = apply_action(self.state, "save_form", form(mode="manual", destination={"building":"Custom","department":"Tools","shipTo":"Custom dock"}, lines=[{"description":"Demo material","qty":"2"}]))
        self.assertTrue(r["palletId"])

    def test_manual_quantity_cannot_be_blank(self):
        with self.assertRaisesRegex(InputError, "Invalid quantity"):
            self.save(mode="manual", destination={"building":"Custom","department":"Tools","shipTo":"Custom dock"}, lines=[{"description":"Material"}])

    def test_finalised_pallet_requires_reopen_before_edit(self):
        r = self.save(intent="finalise")
        with self.assertRaisesRegex(InputError, "Reopen"):
            self.save(id=r["formId"], palletId=r["palletId"])

    def test_reopen_preserves_snapshot_and_revisions(self):
        r = self.save(intent="finalise")
        p = self.state["pallets"][0]
        before = copy.deepcopy(p["versions"][0])
        apply_action(self.state, "reopen_pallet", {"id":p["id"],"reason":"Forgot an item"})
        self.save(hu="HU2", palletId=p["id"], intent="finalise")
        self.assertEqual(p["revision"], 2)
        self.assertEqual(p["versions"][0], before)
        self.assertEqual(len(p["versions"][1]["forms"]), 2)

    def test_reopen_needs_reason(self):
        r = self.save(intent="finalise")
        with self.assertRaises(InputError):
            apply_action(self.state,"reopen_pallet",{"id":r["palletId"],"reason":""})

    def test_source_refresh_does_not_change_saved_form(self):
        self.save()
        before = copy.deepcopy(self.state["forms"])
        apply_action(self.state,"import",{"kind":"quantities","text":QUANTITY_HEADER+"ODO1\tHU1\t999"})
        self.assertEqual(self.state["forms"], before)

    def test_print_escapes_html_and_keeps_emergency_with_remarks(self):
        r = self.save(hu="HU2", remarks="<script>alert('x')</script>")
        html = render_document(self.state,"form",r["formId"],1)
        self.assertNotIn("<script>",html)
        self.assertIn("&lt;script&gt;",html)
        self.assertIn("EMERGENCY",html)

    def test_old_consolidation_marked_superseded(self):
        r = self.save(intent="finalise")
        apply_action(self.state,"reopen_pallet",{"id":r["palletId"],"reason":"Correction"})
        self.assertIn("SUPERSEDED",render_document(self.state,"pallet",r["palletId"],1))

    def test_incomplete_draft_prevents_finalisation(self):
        r = self.save()
        self.save(hu="HU2",intent="draft",palletId=r["palletId"])
        with self.assertRaisesRegex(InputError,"Complete every draft"):
            apply_action(self.state,"finalise_pallet",{"id":r["palletId"]})

    def test_removed_form_remains_in_history(self):
        r = self.save()
        apply_action(self.state,"remove_form",{"id":r["formId"]})
        self.assertTrue(self.state["forms"][0]["removedAt"])
        self.assertEqual(len(self.state["forms"][0]["versions"]),1)
        self.assertTrue(resolve(self.state,[{"hu":"HU1"}])["valid"])


class PersistenceTests(unittest.TestCase):
    def test_atomic_failure_does_not_leave_created_pallet_or_form(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.state = loaded_state()
            result = store.apply("save_form",form(),0)
            store.apply("save_form",form(hu="HU2",intent="draft",palletId=result["palletId"]),1)
            before = store.snapshot()
            with self.assertRaises(InputError):
                store.apply("save_form",form(hu="HU1",id=result["formId"],intent="finalise",palletId=result["palletId"]),2)
            self.assertEqual(store.snapshot(),before)
            self.assertEqual(Store(directory).snapshot(),before)

    def test_restart_and_previous_state_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.apply("settings",{"preparedBy":"A","copies":2,"origin":DEFAULT_ORIGIN},0)
            store.apply("settings",{"preparedBy":"B","copies":3,"origin":DEFAULT_ORIGIN},1)
            self.assertEqual(Store(directory).snapshot()["settings"]["preparedBy"],"B")
            previous = json.loads((Path(directory)/"transport-order.previous.json").read_text())
            self.assertEqual(previous["settings"]["preparedBy"],"A")

    def test_concurrent_window_cannot_overwrite_newer_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.apply("settings",{"preparedBy":"A","copies":2},0)
            with self.assertRaises(ConflictError):
                store.apply("settings",{"preparedBy":"B","copies":3},0)

    def test_corrupt_file_is_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"transport-order.json"
            path.write_text("broken")
            with self.assertRaises(RuntimeError):
                Store(directory)
            self.assertEqual(path.read_text(),"broken")

    def test_second_process_cannot_open_same_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            first = WorkspaceLock(directory)
            try:
                with self.assertRaises(RuntimeError):
                    WorkspaceLock(directory)
            finally:
                first.close()
            second = WorkspaceLock(directory)
            second.close()


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(self.directory.name)
        self.server = create_server(self.store,"test-session")
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.directory.cleanup()

    def test_api_needs_session_token(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.url+"/api/state")
        self.assertEqual(caught.exception.code,401)

    def test_cross_origin_write_is_rejected(self):
        req = Request(self.url+"/api/action",data=b"{}",headers={"X-Session-Token":"test-session","Origin":"https://example.com"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(req)
        self.assertEqual(caught.exception.code,403)

    def test_post_and_restart_state_through_api(self):
        payload = {"action":"save_form","expectedRevision":0,"payload":form(hu="",intent="draft")}
        req = Request(self.url+"/api/action",data=json.dumps(payload).encode(),headers={"X-Session-Token":"test-session","Content-Type":"application/json"})
        with urlopen(req) as response:
            result = json.load(response)
        self.assertTrue(result["formId"])
        self.assertEqual(Store(self.directory.name).snapshot()["revision"],1)

    def test_static_paths_do_not_expose_saved_data(self):
        for path in ("/../transport-order.json","/transport-order.json","/server.py"):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.url+path)
            self.assertEqual(caught.exception.code,404)


if __name__ == "__main__":
    unittest.main()
