import copy
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path

from .archive import local_day, archive_document
from .domain import initial_state, apply_action, migrate_settings, event
from .integrations.sap import InputError


class ConflictError(InputError):
    pass


class WorkspaceLock:
    def __init__(self, directory):
        directory = Path(directory).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        self.handle = (directory / ".workspace.lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                self.handle.write(b"0")
                self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            raise RuntimeError("This data folder is already open in another TransportOrder process. Use its existing window.") from exc

    def close(self):
        self.handle.close()


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "transport-order.json"
        self.backup = self.directory / "transport-order.previous.json"
        self.lock = threading.RLock()
        self.state = initial_state()
        if self.path.exists():
            try:
                self.state = json.loads(self.path.read_text(encoding="utf-8"))
                if self.state.get("schema") != 1 or not all(k in self.state for k in initial_state() if k != "loads"):
                    raise ValueError("Unsupported data format")
            except (ValueError, OSError) as exc:
                raise RuntimeError(f"Cannot read {self.path}. The file has been preserved. Restore a valid backup before restarting.") from exc
        self.state.setdefault("loads", [])
        for load in self.state["loads"]:
            online = load.get("online", {})
            if online.get("url", "").startswith("https://transportorder-driver.chicaron.chatgpt.site/"):
                online["url"] = online["url"].replace("https://transportorder-driver.chicaron.chatgpt.site/", "https://molntam.github.io/TransportOrder/", 1)
        self.state["settings"] = migrate_settings(self.state["settings"])

    def rollover(self):
        today = local_day()
        day = self.state.get("workspaceDay")
        legacy = day is None
        if legacy:
            dates = [local_day(r["createdAt"]) for key in ("forms", "pallets", "loads") for r in self.state.get(key, []) if r.get("createdAt")]
            dates += [local_day(source["importedAt"]) for source in self.state["sources"].values() if source and source.get("importedAt")]
            day = min(dates, default=today)
        if day == today:
            self.state["workspaceDay"] = today
            return
        folder = self.directory / "archive" / "workspaces"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{day}-r{self.state['revision']}.json"
        if not target.exists():
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
            temporary.replace(target)
        candidate = initial_state()
        if legacy:
            current = lambda record: bool(record.get("createdAt")) and local_day(record["createdAt"]) == today
            candidate["loads"] = [copy.deepcopy(r) for r in self.state["loads"] if current(r)]
            pallet_ids = {r["id"] for r in self.state["pallets"] if current(r)}
            pallet_ids.update(f["palletId"] for f in self.state["forms"] if current(f) and f.get("palletId"))
            pallet_ids.update(p["id"] for load in candidate["loads"] for p in load["pallets"])
            candidate["pallets"] = [copy.deepcopy(r) for r in self.state["pallets"] if r["id"] in pallet_ids]
            candidate["forms"] = [copy.deepcopy(r) for r in self.state["forms"] if current(r) or r.get("palletId") in pallet_ids]
            candidate["sources"] = {k: copy.deepcopy(v) if v and v.get("importedAt") and local_day(v["importedAt"]) == today else None for k,v in self.state["sources"].items()}
        candidate["settings"] = copy.deepcopy(self.state["settings"])
        candidate["workspaceDay"] = today
        candidate["revision"] = self.state["revision"] + 1
        self._write(candidate)
        self.state = candidate

    def snapshot(self):
        with self.lock:
            self.rollover()
            return copy.deepcopy(self.state)

    def apply(self, action, payload, expected_revision):
        with self.lock:
            self.rollover()
            last_edit = self.state.get("lastEditRevision", self.state["revision"])
            if (not isinstance(expected_revision, int) or expected_revision > self.state["revision"]
                    or expected_revision < last_edit):
                raise ConflictError("Another window changed the data. Refresh before saving; your current form is still on screen.")
            candidate = copy.deepcopy(self.state)
            result = apply_action(candidate, action, payload)
            candidate["revision"] += 1
            self._write(candidate)
            self.state = candidate
            if result.get("print"):
                try:
                    archive_document(self, candidate, result["print"])
                except OSError:
                    result["archiveWarning"] = "Document saved, but its archive could not be written. Check disk space and reprint to retry."
            return result

    def import_spotfire(self, content, automatic=False):
        from .integrations.spotfire import parse_export
        from .domain import now
        parsed = parse_export(content)
        with self.lock:
            self.rollover()
            if automatic and (self.state["settings"]["dataSource"] != "spotfire" or not self.state["settings"]["spotfireEnabled"]):
                return parsed
            previous = self.state["sources"].get("spotfire") or {}
            if parsed["fingerprint"] == previous.get("fingerprint") and (automatic or self.state["settings"]["dataSource"] == "spotfire"):
                return parsed
            candidate = copy.deepcopy(self.state)
            candidate.setdefault("lastEditRevision", self.state["revision"])
            timestamp = now()
            for source in parsed["sources"].values():
                source["importedAt"] = timestamp
            candidate["sources"]["spotfire"] = {**parsed, "importedAt": timestamp}
            if not automatic:
                candidate["settings"]["dataSource"] = "spotfire"
            event(candidate, "Spotfire data updated", "spotfire", f"{parsed['uniqueHus']} HUs; {parsed['rowCount']} item rows")
            candidate["revision"] += 1
            self._write(candidate, source_only=automatic)
            self.state = candidate
            return parsed

    def _write(self, state, source_only=False):
        if not source_only:
            state["lastEditRevision"] = state["revision"]
        descriptor, temporary = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            if self.path.exists():
                shutil.copy2(self.path, self.backup)
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def audit(self, action, target, detail):
        with self.lock:
            candidate = copy.deepcopy(self.state)
            event(candidate, action, target, detail)
            candidate["revision"] += 1
            self._write(candidate)
            self.state = candidate
