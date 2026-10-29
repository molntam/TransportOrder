import copy
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path

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
                if self.state.get("schema") != 1 or not all(k in self.state for k in initial_state()):
                    raise ValueError("Unsupported data format")
            except (ValueError, OSError) as exc:
                raise RuntimeError(f"Cannot read {self.path}. The file has been preserved. Restore a valid backup before restarting.") from exc
        self.state["settings"] = migrate_settings(self.state["settings"])

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def apply(self, action, payload, expected_revision):
        with self.lock:
            if expected_revision != self.state["revision"]:
                raise ConflictError("Another window changed the data. Refresh before saving; your current form is still on screen.")
            candidate = copy.deepcopy(self.state)
            result = apply_action(candidate, action, payload)
            candidate["revision"] += 1
            self._write(candidate)
            self.state = candidate
            return result

    def _write(self, state):
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
