import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from transport_order.domain import LOCATIONS, apply_action
from transport_order.native_print import PrintService, list_printers, run_native
from transport_order.integrations.sap import InputError
from transport_order.printing import document_model, render_document
from transport_order.storage import Store
from test_workflow import loaded_state, form


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.state = loaded_state()

    def test_final_document_has_no_individual_form_ids(self):
        first = apply_action(self.state, "save_form", form(remarks="Handle with care"))
        second = apply_action(self.state, "save_form", form(hu="HU2", palletId=first["palletId"], intent="finalise", remarks="Urgent tools"))
        html = render_document(self.state, "pallet", first["palletId"], 1)
        for record_id in (first["formId"], second["formId"]):
            self.assertNotIn(record_id, html)
        self.assertIn("Handle with care", html)
        self.assertIn("Urgent tools", html)
        self.assertIn("HU1", html)
        self.assertIn("DN2", html)

    def test_single_delivery_title_and_header_qr(self):
        saved=apply_action(self.state,"save_form",form(intent="finalise"))
        model=document_model(self.state,"pallet",saved["palletId"],1)
        self.assertEqual(model["title"],"Transport order")
        html=render_document(self.state,"pallet",saved["palletId"],1)
        self.assertLess(html.index("class='qr-placeholder'"),html.index("</header>"))
        self.assertIn("building-name",html)

    def test_two_delivery_title(self):
        first=apply_action(self.state,"save_form",form())
        apply_action(self.state,"save_form",form(hu="HU2",palletId=first["palletId"],intent="finalise"))
        self.assertEqual(document_model(self.state,"pallet",first["palletId"],1)["title"],"Pallet consolidation")

    def test_final_empty_optional_columns_are_omitted(self):
        saved = apply_action(self.state, "save_form", form(intent="finalise"))
        model = document_model(self.state, "pallet", saved["palletId"], 1)
        self.assertEqual([c["key"] for c in model["columns"]], ["qty", "hu", "dn"])

    def test_individual_order_omits_empty_optional_columns(self):
        saved=apply_action(self.state,"save_form",form())
        model=document_model(self.state,"form",saved["formId"],1)
        self.assertEqual([c["key"] for c in model["columns"]],["qty","hu","dn"])

    def test_nonempty_optional_column_is_retained(self):
        saved = apply_action(self.state, "save_form", form(intent="finalise", lines=[{"hu":"HU1", "description":"Tools"}]))
        model = document_model(self.state, "pallet", saved["palletId"], 1)
        self.assertIn("description", [c["key"] for c in model["columns"]])
        self.assertNotIn("part", [c["key"] for c in model["columns"]])

    def test_qr_placeholder_only_on_final_consolidation(self):
        saved = apply_action(self.state, "save_form", form(intent="finalise"))
        self.assertIn("class='qr-placeholder'", render_document(self.state,"pallet",saved["palletId"],1))
        self.assertNotIn("class='qr-placeholder'", render_document(self.state,"form",saved["formId"],1))

    def test_destination_picker_is_filtered_without_changing_origin(self):
        self.assertFalse(any(r["building"].upper() in ("BUILDING 05","BEST II","EINDHOVEN 1") for r in LOCATIONS["toLocations"]))
        self.assertTrue(any(r["building"] == "Building 05" for r in LOCATIONS["fromLocations"]))


class NativeSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = Store(self.temporary.name)
        self.store.state = loaded_state()
        self.saved = self.store.apply("save_form",form(intent="finalise"),0)
        self.service = PrintService()

    def tearDown(self):
        self.temporary.cleanup()

    def payload(self, kind="form", **changes):
        return {"kind":kind, "id":self.saved["palletId" if kind == "pallet" else "formId"], "revision":1, "requestId":"print-request-0001", **changes}

    def test_open_form_prints_one_copy_and_uses_live_windows_default(self):
        with patch("transport_order.native_print.run_native", return_value={"status":"submitted","printer":"Windows queue","copies":1}) as native:
            self.service.submit(self.store,self.payload())
        job = native.call_args.args[1]
        self.assertEqual(job["copies"],1)
        self.assertEqual(job["printer"],"")
        self.assertTrue(any(e["action"] == "Print submitted" for e in self.store.snapshot()["events"]))

    def test_final_pallet_prints_two_copies(self):
        with patch("transport_order.native_print.run_native", return_value={"status":"submitted","printer":"Windows queue","copies":2}) as native:
            self.service.submit(self.store,self.payload("pallet"))
        self.assertEqual(native.call_args.args[1]["copies"],2)

    def test_selected_printer_and_separate_copy_defaults(self):
        self.store.apply("settings", {"printer":"Follow-me queue", "openCopies":2, "finalCopies":4, "theme":"dark"},1)
        with patch("transport_order.native_print.run_native", return_value={"status":"submitted","printer":"Follow-me queue","copies":4}) as native:
            self.service.submit(self.store,self.payload("pallet"))
        self.assertEqual(native.call_args.args[1]["copies"],4)
        self.assertEqual(native.call_args.args[1]["printer"],"Follow-me queue")

    def test_duplicate_request_does_not_print_twice(self):
        with patch("transport_order.native_print.run_native", return_value={"status":"submitted","printer":"Queue","copies":1}) as native:
            first=self.service.submit(self.store,self.payload())
            second=self.service.submit(self.store,self.payload())
        self.assertEqual(first,second)
        native.assert_called_once()

    def test_failed_job_preserves_saved_form_and_has_no_success_event(self):
        before=copy.deepcopy(self.store.snapshot())
        with patch("transport_order.native_print.run_native", side_effect=InputError("Printer unavailable")):
            with self.assertRaisesRegex(InputError,"Printer unavailable"):
                self.service.submit(self.store,self.payload())
        self.assertEqual(self.store.snapshot(),before)

    def test_audit_failure_does_not_resubmit_a_printed_job(self):
        with patch.object(self.store,"audit",side_effect=OSError("Disk full")):
            with patch("transport_order.native_print.run_native",return_value={"status":"submitted","printer":"Queue","copies":1}) as native:
                result=self.service.submit(self.store,self.payload())
                self.service.submit(self.store,self.payload())
        native.assert_called_once()
        self.assertIn("auditWarning",result)

    def test_invalid_copy_count_does_not_reach_windows(self):
        with patch("transport_order.native_print.run_native") as native:
            with self.assertRaises(InputError):
                self.service.submit(self.store,self.payload(copies=0))
        native.assert_not_called()


class PreferenceMigrationTests(unittest.TestCase):
    def test_existing_data_gets_new_defaults_without_losing_forms(self):
        with tempfile.TemporaryDirectory() as directory:
            state=loaded_state()
            apply_action(state,"save_form",form())
            state["settings"]={"copies":3,"preparedBy":"Existing user","origin":state["settings"]["origin"]}
            (Path(directory)/"transport-order.json").write_text(json.dumps(state),encoding="utf-8")
            migrated=Store(directory).snapshot()
            self.assertEqual(migrated["settings"]["openCopies"],1)
            self.assertEqual(migrated["settings"]["finalCopies"],2)
            self.assertEqual(migrated["settings"]["printer"],"")
            self.assertEqual(migrated["settings"]["theme"],"light")
            self.assertEqual(migrated["forms"],state["forms"])

    def test_theme_update_preserves_print_preferences(self):
        state=loaded_state()
        apply_action(state,"settings",{"printer":"Warehouse queue", "finalCopies":4})
        apply_action(state,"settings",{"theme":"dark"})
        self.assertEqual(state["settings"]["printer"],"Warehouse queue")
        self.assertEqual(state["settings"]["finalCopies"],4)


@unittest.skipUnless(os.name == "nt", "Native renderer requires Windows")
class WindowsRendererTests(unittest.TestCase):
    def test_native_helper_compiles_and_paginates_without_a_printer(self):
        state=loaded_state()
        saved=apply_action(state,"save_form",form(intent="finalise"))
        model=document_model(state,"pallet",saved["palletId"],1)
        model["columns"]=[{"key":"description","label":"Description","weight":2},{"key":"hu","label":"HU","weight":1},{"key":"dn","label":"DN","weight":1}]
        model["rows"]=[["A very long description " * 80,"HU-"+str(i),"DN-"+str(i)] for i in range(25)]
        model["remarks"]="Long remark " * 400
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"render.png"
            result=run_native("render",{"document":model,"copies":2,"printer":"","outputPath":str(path)})
            self.assertGreater(result["pages"],2)
            self.assertEqual(path.read_bytes()[:8],b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
