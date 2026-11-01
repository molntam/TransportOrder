import json
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path

from .integrations.sap import InputError
from .printing import document_model

SOURCE = Path(__file__).with_name("native") / "NativePrinter.cs"
COMMAND = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
    Add-Type -AssemblyName System.Drawing
    Add-Type -AssemblyName System.Web.Extensions
    $source = [IO.File]::ReadAllText($env:TRANSPORT_ORDER_PRINT_SOURCE)
    Add-Type -TypeDefinition $source -ReferencedAssemblies System.Drawing,System.Web.Extensions
    $inputJson = if ($env:TRANSPORT_ORDER_PRINT_JOB) { [IO.File]::ReadAllText($env:TRANSPORT_ORDER_PRINT_JOB) } else { '' }
    $result = [TransportOrderPrinter]::Run($inputJson, $env:TRANSPORT_ORDER_PRINT_ACTION)
    [IO.File]::WriteAllText($env:TRANSPORT_ORDER_PRINT_RESULT, $result, (New-Object System.Text.UTF8Encoding($false)))
} catch {
    [Console]::Error.WriteLine($_.Exception.GetBaseException().Message)
    exit 1
}
"""


def run_native(action, payload=None):
    if os.name != "nt":
        raise InputError("Direct printing is available on Windows. You can still open a document preview on this computer.")
    executable = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    environment = os.environ.copy()
    environment.update({"TRANSPORT_ORDER_PRINT_SOURCE": str(SOURCE), "TRANSPORT_ORDER_PRINT_ACTION": action})
    with tempfile.TemporaryDirectory(prefix="transport-order-print-") as directory:
        response_path = Path(directory) / "result.json"
        environment["TRANSPORT_ORDER_PRINT_RESULT"] = str(response_path)
        if payload is not None:
            job = Path(directory) / "job.json"
            job.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            environment["TRANSPORT_ORDER_PRINT_JOB"] = str(job)
        else:
            environment.pop("TRANSPORT_ORDER_PRINT_JOB", None)
        try:
            process = subprocess.run([str(executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", COMMAND],
                env=environment, capture_output=True, encoding="utf-8", errors="replace", timeout=45,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as exc:
            raise InputError("Windows did not confirm the printer operation. Check the print queue before retrying; the job may already have been submitted.") from exc
        if process.returncode:
            detail = process.stderr.strip()[:1200] or "The Windows print helper could not run."
            raise InputError("Windows printing: " + detail + " Check the print queue before retrying.")
        try:
            return json.loads(response_path.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as exc:
            raise InputError("Windows returned an unexpected printer response. Check the print queue before retrying.") from exc


def list_printers():
    if os.name != "nt":
        return {"supported": False, "printers": [], "defaultPrinter": ""}
    return run_native("list")


class PrintService:
    def __init__(self, base_url=""):
        self.base_url = base_url
        self.lock = threading.Lock()
        self.completed = {}

    def submit(self, store, payload):
        request_id = str(payload.get("requestId", ""))
        if not re.fullmatch(r"[a-zA-Z0-9-]{8,100}", request_id):
            raise InputError("A unique print request ID is required.")
        with self.lock:
            if request_id in self.completed:
                return self.completed[request_id]
            state = store.snapshot()
            kind = payload.get("kind")
            model = document_model(state, kind, payload.get("id"), int(payload.get("revision", 0)), self.base_url)
            copies = int(payload.get("copies", state["settings"]["manifestCopies" if kind == "load" else "finalCopies" if kind == "pallet" else "openCopies"]))
            if copies not in range(1, 6):
                raise InputError("Choose between 1 and 5 copies.")
            output = store.directory / "printouts"
            output.mkdir(exist_ok=True)
            job = {"document": model, "copies": copies, "printer": state["settings"]["printer"],
                   "outputPath": str(output / f"{model['id']}-r{model['revision']}-{request_id}.pdf")}
            result = run_native("print", job)
            if result.get("status") != "submitted":
                raise InputError("The print job was not confirmed. Check the Windows queue before retrying.")
            self.completed[request_id] = result
            try:
                store.audit("Print submitted", model["id"], f"Revision {model['revision']}; {copies} copies; {result['printer']}")
            except OSError:
                result["auditWarning"] = "The job was submitted, but its history entry could not be saved. Do not resend it just to record history."
            return result
