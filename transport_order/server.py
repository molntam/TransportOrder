import argparse
import base64
import binascii
import json
import os
import secrets
import subprocess
import threading
import webbrowser
from functools import partial
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .domain import LOCATIONS, resolve, source_diagnostics
from .integrations import PROVIDERS
from .integrations.sap import InputError, parse_table
from .printing import render_document
from .native_print import PrintService, list_printers
from .storage import ConflictError, Store, WorkspaceLock

WEB = Path(__file__).with_name("web")
MAX_BODY = 20_000_000


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, store, token, **kwargs):
        self.store, self.token = store, token
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        pass

    def send(self, status, data, content_type="application/json; charset=utf-8"):
        content = json.dumps(data, ensure_ascii=False).encode() if content_type.startswith("application/json") else data.encode() if isinstance(data, str) else data
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self' about:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
        self.end_headers()
        self.wfile.write(content)

    def trusted_request(self):
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get("Host", "") not in allowed:
            self.send(403, {"error": "Use the local application address."})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + host for host in allowed}:
            self.send(403, {"error": "Cross-origin requests are not allowed."})
            return False
        return True

    def authorised(self):
        if not self.trusted_request():
            return False
        if not secrets.compare_digest(self.headers.get("X-Session-Token", ""), self.token):
            self.send(401, {"error": "This session has expired. Reopen the link shown in the Python terminal."})
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            if not self.authorised():
                return
            state = self.store.snapshot()
            if path == "/api/state":
                self.send(200, {"state": state, "locations": LOCATIONS,
                    "diagnostics": source_diagnostics(state), "version": __version__,
                    "providers": [{k: getattr(p, k) for k in ("id", "label", "available", "description")} for p in PROVIDERS]})
            elif path == "/api/print":
                try:
                    q = parse_qs(urlsplit(self.path).query)
                    kind = q.get("kind", [""])[0]
                    if kind not in ("form", "pallet", "load"):
                        raise InputError("Unknown document type.")
                    copies = int(q.get("copies", ["1"])[0])
                    if copies not in range(1, 6):
                        raise InputError("Choose 1 to 5 copies.")
                    html = render_document(state, kind, q.get("id", [""])[0], int(q.get("revision", ["0"])[0]), copies, f"http://127.0.0.1:{self.server.server_port}")
                    self.send(200, html, "text/html; charset=utf-8")
                except (ValueError, KeyError) as exc:
                    self.send(400, {"error": str(exc)})
            elif path == "/api/dock-reminders":
                from .loads import dock_reminders
                try:
                    local_time = datetime.fromisoformat(parse_qs(urlsplit(self.path).query)["localTime"][0])
                    self.send(200, {"reminders": dock_reminders(state, local_time)})
                except (ValueError, KeyError):
                    self.send(400, {"error": "Supply a valid dock-local date and time."})
            elif path == "/api/printers":
                try:
                    self.send(200, list_printers())
                except (InputError, OSError) as exc:
                    self.send(400, {"error": str(exc)})
            else:
                self.send(404, {"error": "Unknown API endpoint."})
            return
        if not self.trusted_request():
            return
        static = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                  "/jsQR.js": ("jsQR.js", "text/javascript"),
                  "/styles.css": ("styles.css", "text/css"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}
        if path not in static:
            self.send(404, "Not found", "text/plain")
            return
        filename, mime = static[path]
        self.send(200, (WEB / filename).read_bytes(), mime + "; charset=utf-8")

    def do_POST(self):
        if not self.authorised():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                self.send(413, {"error": "Use an input smaller than 20 MB."})
                return
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise InputError("Expected an object.")
            path = urlsplit(self.path).path
            if path in ("/api/import-preview", "/api/action"):
                data = payload.get("payload", payload)
                if "fileBase64" in data:
                    data["content"] = base64.b64decode(data.pop("fileBase64"), validate=True)
            if path == "/api/resolve":
                result = resolve(self.store.snapshot(), payload.get("lines", []), payload.get("formId"), payload.get("destination"), payload.get("overrideReason", ""))
            elif path == "/api/import-preview":
                result = parse_table(payload.get("kind"), payload.get("text", ""), payload.get("content"), payload.get("decimalMark", "."))
            elif path == "/api/action":
                result = self.store.apply(payload.get("action"), payload.get("payload", {}), payload.get("expectedRevision"))
                result["revision"] = self.store.snapshot()["revision"]
            elif path == "/api/print-job":
                result = self.server.print_service.submit(self.store, payload)
            elif path == "/api/shutdown":
                self.send(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            else:
                self.send(404, {"error": "Unknown API endpoint."})
                return
            self.send(200, result)
        except ConflictError as exc:
            self.send(409, {"error": str(exc)})
        except (InputError, ValueError, KeyError, TypeError, binascii.Error) as exc:
            self.send(400, {"error": str(exc)})
        except OSError:
            self.send(500, {"error": "The data could not be saved. Check available disk space and folder permissions; your changes have not been committed."})
        except Exception:
            self.send(500, {"error": "The operation could not be completed. Your existing saved data has been preserved."})


def create_server(store, token, port=0):
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, store=store, token=token))
    server.daemon_threads = True
    server.print_service = PrintService(f"http://127.0.0.1:{server.server_port}")
    return server


def open_window(url, directory, browser):
    if os.name == "nt" and browser == "app":
        for root in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
            if not root:
                continue
            executable = Path(root) / "Microsoft/Edge/Application/msedge.exe"
            if executable.is_file():
                subprocess.Popen([str(executable), "--app=" + url,
                    "--user-data-dir=" + str(directory / "browser-profile"), "--no-first-run"])
                return
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(description="TransportOrder local shipping workspace")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=Path.home() / "TransportOrderData")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--browser", choices=("app", "default"), default="app")
    args = parser.parse_args()
    try:
        workspace_lock = WorkspaceLock(args.data_dir)
        store = Store(args.data_dir)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    token = secrets.token_urlsafe(32)
    try:
        server = create_server(store, token, args.port)
    except OSError:
        raise SystemExit(f"Port {args.port} is in use. If the app is already running, use its existing window. Otherwise run with --port 0.")
    url = f"http://127.0.0.1:{server.server_port}/#session={token}"
    print(f"TransportOrder {__version__}\nData folder: {store.directory}\nOpen: {url}\nKeep this terminal open. Press Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        open_window(url, store.directory, args.browser)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        workspace_lock.close()
