from __future__ import annotations
import logging
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from googleapiclient.errors import HttpError
from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal
from PySide6.QtWidgets import QMessageBox

from msc.db.store import FileRecord, SqliteStore, record_from_api
from msc.drive.mimes import guess_mime_from_path, is_google_native
from msc.paths import cache_dir, safe_destination
from msc.services.transfer import TransferService

if TYPE_CHECKING:
    from msc.drive.client import DriveClient

log = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int], None]


class OfflineSyncError(Exception):
    """Drive API failed because the machine is offline."""


def is_network_error(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    text = str(exc).lower()
    return any(
        token in text
        for token in ("getaddrinfo", "10054", "10060", "10065", "timed out", "disconnected")
    )
ConflictChoice = str  # keep_local | keep_remote | keep_both


@dataclass
class ConflictPrompt:
    title: str
    message: str
    event: threading.Event
    choice: ConflictChoice | None = None


class ConflictBridge(QObject):
    """Marshals conflict dialogs onto the GUI thread."""

    show_conflict = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.show_conflict.connect(self._on_show)

    def _on_show(self, prompt: ConflictPrompt) -> None:
        msg = QMessageBox()
        msg.setWindowTitle(prompt.title)
        msg.setText(prompt.message)
        local_btn = msg.addButton("Keep local", QMessageBox.ButtonRole.AcceptRole)
        remote_btn = msg.addButton("Keep remote", QMessageBox.ButtonRole.DestructiveRole)
        both_btn = msg.addButton("Keep both", QMessageBox.ButtonRole.ActionRole)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == local_btn:
            prompt.choice = "keep_local"
        elif clicked == remote_btn:
            prompt.choice = "keep_remote"
        elif clicked == both_btn:
            prompt.choice = "keep_both"
        else:
            prompt.choice = "keep_local"
        prompt.event.set()

    def ask(self, title: str, message: str) -> ConflictChoice:
        prompt = ConflictPrompt(title=title, message=message, event=threading.Event())
        self.show_conflict.emit(prompt)
        prompt.event.wait()
        return prompt.choice or "keep_local"


class LocalFileWatcher(QObject):
    """Watch cached files for local edits."""

    file_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._watcher = None
        self._paths: dict[str, str] = {}
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(1500)
        self._pending_ids: set[str] = set()
        self._applying = False

    def set_applying(self, value: bool) -> None:
        self._applying = value

    def start(self) -> None:
        if self._watcher is None:
            self._watcher = QFileSystemWatcher(self)
            self._watcher.fileChanged.connect(self._on_fs_change)
            self._debounce.timeout.connect(self._flush_pending)

    def sync_paths(self, records: list[FileRecord]) -> None:
        if self._watcher is None:
            self.start()
        assert self._watcher is not None
        desired: dict[str, str] = {}
        for rec in records:
            if rec.is_folder or not rec.local_path:
                continue
            p = Path(rec.local_path)
            if p.is_file():
                desired[str(p.resolve())] = rec.id
        for path in list(self._paths):
            if path not in desired:
                self._watcher.removePath(path)
                del self._paths[path]
        for path, fid in desired.items():
            if path not in self._paths:
                self._watcher.addPath(path)
            self._paths[path] = fid

    def _on_fs_change(self, path: str) -> None:
        if self._applying:
            return
        fid = self._paths.get(path)
        if not fid:
            return
        self._pending_ids.add(fid)
        self._debounce.start()

    def _flush_pending(self) -> None:
        ids = list(self._pending_ids)
        self._pending_ids.clear()
        for fid in ids:
            self.file_changed.emit(fid)


class SyncService:
    def __init__(
        self,
        drive: DriveClient,
        store: SqliteStore,
        conflict_bridge: ConflictBridge,
    ) -> None:
        self._drive = drive
        self._store = store
        self._transfer = TransferService(drive)
        self._conflicts = conflict_bridge
        self._watcher = LocalFileWatcher()
        self._watcher.file_changed.connect(self._on_local_edit)
        self._watcher.start()
        self._online = True
        self._after_local_edit: Callable[[str], None] | None = None

    def set_after_local_edit(self, callback: Callable[[str], None] | None) -> None:
        self._after_local_edit = callback

    def set_online(self, online: bool) -> None:
        self._online = online

    def refresh_watched_paths(self) -> None:
        self._watcher.sync_paths(self._store.get_pinned())

    def queue_upload_from_disk(
        self, local_path: Path, parent_id: str
    ) -> FileRecord:
        temp_id = f"local_{uuid.uuid4()}"
        dest_dir = cache_dir() / temp_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = safe_destination(dest_dir, local_path.name)
        shutil.copy2(local_path, dest)
        mime = guess_mime_from_path(str(local_path))
        size = dest.stat().st_size
        fs_mtime = _fs_mtime_iso(dest)
        record = FileRecord(
            id=temp_id,
            parent_id=parent_id,
            name=local_path.name,
            mime_type=mime,
            size=size,
            md5=None,
            modified_time=None,
            is_folder=False,
            pinned=True,
            local_path=str(dest),
            dirty=True,
            local_mtime=None,
            fs_mtime=fs_mtime,
        )
        self._store.insert_local_file(record)
        self._store.enqueue_op(
            "create",
            {
                "temp_id": temp_id,
                "parent_id": parent_id,
                "name": local_path.name,
                "local_path": str(dest),
                "mime_type": mime,
            },
        )
        self.refresh_watched_paths()
        return record

    def flush_pending(
        self,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        if not self._online:
            return
        for op in self._store.list_pending():
            try:
                if op.op_type == "create":
                    self._flush_create(op, progress_callback)
                elif op.op_type == "update":
                    self._flush_update(op, progress_callback)
                elif op.op_type == "create_office":
                    self._flush_create_office(op, progress_callback)
                self._store.delete_op(op.id)
            except Exception as exc:
                if is_network_error(exc):
                    self._online = False
                    raise OfflineSyncError("offline") from exc
                log.exception("Failed pending op %s", op.op_type)
                raise

    def _on_local_edit(self, file_id: str) -> None:
        rec = self._store.get_file(file_id)
        if not rec or not rec.local_path:
            return
        path = Path(rec.local_path)
        if not path.is_file():
            return
        fs_mtime = _fs_mtime_iso(path)
        self._store.set_local_copy(
            file_id, str(path), rec.local_mtime or "", fs_mtime
        )
        if is_google_native(rec.mime_type):
            self._store.delete_pending_for_file(file_id, "create_office")
            self._store.enqueue_op(
                "create_office",
                {
                    "file_id": file_id,
                    "parent_id": rec.parent_id,
                    "name": path.name,
                    "local_path": str(path),
                    "mime_type": guess_mime_from_path(str(path)),
                },
            )
        else:
            self._store.delete_pending_for_file(file_id, "update")
            self._store.enqueue_op(
                "update",
                {
                    "file_id": file_id,
                    "local_path": str(path),
                    "base_modified_time": rec.local_mtime or "",
                },
            )
        self._store.set_dirty(file_id, True)
        if self._after_local_edit is not None:
            self._after_local_edit(file_id)

    def _flush_create(
        self, op, progress_callback: ProgressCallback | None
    ) -> None:
        payload = op.payload
        temp_id = payload["temp_id"]
        parent_id = payload["parent_id"]
        local_path = Path(payload["local_path"])
        name = payload["name"]
        existing_id = self._find_remote_by_name(parent_id, name)
        if existing_id:
            choice = self._conflicts.ask(
                "Upload conflict",
                f'A file named "{name}" already exists on Drive.\n'
                "How should this upload be resolved?",
            )
            if choice == "keep_remote":
                self._store.delete_file(temp_id)
                shutil.rmtree(cache_dir() / temp_id, ignore_errors=True)
                return
            if choice == "keep_both":
                conflict_name = _conflict_name(name)
                conflict_path = self._rename_local(temp_id, conflict_name, local_path)
                result = self._transfer.upload(
                    conflict_path,
                    parent_id,
                    _progress_adapter(conflict_name, progress_callback),
                )
                self._finalize_create(temp_id, result, conflict_path, parent_id)
                return
            self._push_update(
                existing_id, local_path, progress_callback, temp_id=temp_id
            )
            return
        result = self._transfer.upload(
            local_path,
            parent_id,
            _progress_adapter(name, progress_callback),
        )
        self._finalize_create(temp_id, result, local_path, parent_id)

    def _flush_update(
        self, op, progress_callback: ProgressCallback | None
    ) -> None:
        payload = op.payload
        file_id = payload["file_id"]
        local_path = Path(payload["local_path"])
        base_mtime = payload.get("base_modified_time", "")
        rec = self._store.get_file(file_id)
        if not rec:
            return
        try:
            api = self._drive.get_file(file_id)
        except Exception as exc:
            if is_network_error(exc):
                raise
            if isinstance(exc, HttpError) and getattr(exc.resp, "status", None) == 404:
                log.exception("Update target %s missing", file_id)
                return
            raise
        remote_mtime = api.get("modifiedTime", "")
        if base_mtime and remote_mtime != base_mtime:
            choice = self._conflicts.ask(
                "Sync conflict",
                f"“{rec.name}” was changed both locally and on Drive.\n"
                "Choose which version to keep.",
            )
            if choice == "keep_remote":
                self._revert_local_to_remote(rec, api, progress_callback)
                return
            if choice == "keep_both":
                self._keep_both_update(rec, local_path, api, progress_callback)
                return
        self._push_update(file_id, local_path, progress_callback)

    def _keep_both_update(
        self,
        rec: FileRecord,
        local_path: Path,
        remote_api: dict,
        progress_callback: ProgressCallback | None,
    ) -> None:
        conflict_name = _conflict_name(rec.name)
        result = self._transfer.upload(
            local_path,
            rec.parent_id,
            _progress_adapter(conflict_name, progress_callback),
            name=conflict_name,
        )
        new_id = result["id"]
        if not result.get("modifiedTime"):
            result = self._drive.get_file(new_id)

        new_dir = cache_dir() / new_id
        new_dir.mkdir(parents=True, exist_ok=True)
        conflict_path = safe_destination(new_dir, conflict_name)
        shutil.copy2(local_path, conflict_path)

        self._store.upsert_metadata(record_from_api(result, rec.parent_id))
        self._store.set_pinned(new_id, True)
        self._store.set_local_copy(
            new_id,
            str(conflict_path),
            result.get("modifiedTime", ""),
            _fs_mtime_iso(conflict_path),
        )
        self._store.set_dirty(new_id, False)

        self._revert_local_to_remote(rec, remote_api, progress_callback)
        self.refresh_watched_paths()

    def _revert_local_to_remote(
        self,
        rec: FileRecord,
        api: dict,
        progress_callback: ProgressCallback | None,
    ) -> None:
        if not rec.local_path:
            self._store.set_dirty(rec.id, False)
            return
        self._watcher.set_applying(True)
        try:
            path = self._transfer.download(
                rec,
                Path(rec.local_path).parent,
                _progress_adapter(rec.name, progress_callback),
            )
            mtime = api.get("modifiedTime", "")
            self._store.upsert_metadata(record_from_api(api, rec.parent_id))
            self._store.set_local_copy(rec.id, str(path), mtime, _fs_mtime_iso(path))
            self._store.set_dirty(rec.id, False)
        finally:
            self._watcher.set_applying(False)

    def _flush_create_office(
        self, op, progress_callback: ProgressCallback | None
    ) -> None:
        payload = op.payload
        local_path = Path(payload["local_path"])
        parent_id = payload["parent_id"]
        name = payload.get("name", local_path.name)
        self._transfer.upload(
            local_path,
            parent_id,
            _progress_adapter(name, progress_callback),
        )
        file_id = payload["file_id"]
        self._store.set_dirty(file_id, False)
        fs = _fs_mtime_iso(local_path)
        rec = self._store.get_file(file_id)
        if rec and rec.local_mtime:
            self._store.set_local_copy(file_id, str(local_path), rec.local_mtime, fs)

    def _push_update(
        self,
        file_id: str,
        local_path: Path,
        progress_callback: ProgressCallback | None,
        temp_id: str | None = None,
    ) -> None:
        self._watcher.set_applying(True)
        try:
            result = self._drive.update_file(
                file_id,
                local_path,
                _progress_adapter(local_path.name, progress_callback),
            )
        finally:
            self._watcher.set_applying(False)
        mtime = result.get("modifiedTime", "")
        fs = _fs_mtime_iso(local_path)
        if temp_id:
            new_path = self._move_cache_dir(temp_id, file_id, local_path.name)
            old_rec = self._store.get_file(temp_id)
            parent_id = old_rec.parent_id if old_rec else "root"
            self._store.replace_file_id(
                temp_id,
                file_id,
                name=result.get("name", local_path.name),
                modified_time=mtime,
                md5=result.get("md5Checksum"),
                mime_type=result.get("mimeType", guess_mime_from_path(str(local_path))),
                size=int(result["size"]) if result.get("size") else local_path.stat().st_size,
                local_path=str(new_path),
                dirty=False,
                local_mtime=mtime,
                fs_mtime=fs,
                parent_id=parent_id,
            )
        else:
            self._store.set_local_copy(file_id, str(local_path), mtime, fs)
            self._store.set_dirty(file_id, False)
            rec = self._store.get_file(file_id)
            if rec:
                meta = record_from_api(result, rec.parent_id)
                self._store.upsert_metadata(meta)

    def _finalize_create(
        self, temp_id: str, result: dict, local_path: Path, parent_id: str
    ) -> None:
        file_id = result["id"]
        mtime = result.get("modifiedTime", datetime.now(timezone.utc).isoformat())
        new_path = self._move_cache_dir(temp_id, file_id, local_path.name)
        self._store.replace_file_id(
            temp_id,
            file_id,
            parent_id=parent_id,
            name=result.get("name", local_path.name),
            modified_time=mtime,
            local_mtime=mtime,
            fs_mtime=_fs_mtime_iso(new_path),
            dirty=False,
        )
        self.refresh_watched_paths()

    def _find_remote_by_name(self, parent_id: str, name: str) -> str | None:
        try:
            items = self._drive.list_children(parent_id)
        except Exception:
            return None
        for item in items:
            if item.get("name") == name and item.get("mimeType") != "application/vnd.google-apps.folder":
                return item["id"]
        return None

    def _rename_local(self, temp_id: str, new_name: str, old_path: Path) -> Path:
        dest = safe_destination(old_path.parent, new_name)
        if dest != old_path:
            shutil.move(str(old_path), str(dest))
        rec = self._store.get_file(temp_id)
        if rec:
            self._store.replace_file_id(temp_id, temp_id, name=new_name, local_path=str(dest))
        return dest

    def _move_cache_dir(self, old_id: str, new_id: str, filename: str) -> Path:
        old_dir = cache_dir() / old_id
        new_dir = cache_dir() / new_id
        new_dir.mkdir(parents=True, exist_ok=True)
        dest = new_dir / filename
        src = old_dir / filename
        if src.is_file():
            if dest.exists():
                dest.unlink()
            shutil.move(str(src), str(dest))
        shutil.rmtree(old_dir, ignore_errors=True)
        return dest


def _fs_mtime_iso(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _conflict_name(name: str) -> str:
    p = Path(name)
    return f"{p.stem} (conflict){p.suffix}"


def _progress_adapter(
    label: str, callback: ProgressCallback | None
) -> Callable[[int, int], None] | None:
    if callback is None:
        return None
    return lambda done, total: callback(label, done, total)

