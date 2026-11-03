from __future__ import annotations
import hashlib
import logging
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from googleapiclient.errors import HttpError
from msc.db.store import FileRecord, SqliteStore, record_from_api
from msc.drive.mimes import can_download
from msc.paths import cache_dir
from msc.services.sync import _fs_mtime_iso, _progress_adapter, is_network_error
from msc.services.transfer import TransferService

if TYPE_CHECKING:
    from msc.drive.client import DriveClient

log = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int], None]


class CacheService:
    def __init__(self, drive: DriveClient, store: SqliteStore) -> None:
        self._drive = drive
        self._store = store
        self._transfer = TransferService(drive)

    def pin_items(
        self,
        items: list[FileRecord],
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        for item in items:
            if item.is_folder:
                self._pin_folder_tree(item.id, progress_callback)
            else:
                self._pin_file(item.id, progress_callback)

    def unpin_items(self, items: list[FileRecord]) -> None:
        ids: set[str] = set()
        for item in items:
            if item.is_folder:
                ids.add(item.id)
                for desc in self._store.get_descendants(item.id):
                    ids.add(desc.id)
            else:
                ids.add(item.id)
        for file_id in ids:
            self._store.set_pinned(file_id, False)
            self._store.set_dirty(file_id, False)
            self._store.delete_pending_for_file(file_id)
            self._evict_disk(file_id)
            self._store.clear_local_copy(file_id)

    def sync_full(self, progress_callback: ProgressCallback | None = None) -> None:
        try:
            pinned = self._store.get_pinned()
            folder_ids = {p.id for p in pinned if p.is_folder}
            for folder in pinned:
                if folder.is_folder:
                    self._sync_folder_tree(folder.id, progress_callback)
            for item in pinned:
                if not item.is_folder and not self._under_pinned_folder(
                    item, folder_ids
                ):
                    self._sync_pinned_file(item.id, progress_callback)
        except Exception as exc:
            if is_network_error(exc):
                log.warning("cache sync aborted (offline): %s", exc)
                return
            raise

    def sync_items_in_folder(
        self,
        items: list[FileRecord],
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """Light sync for pinned entries visible in the current folder listing."""
        for item in items:
            if not item.pinned:
                continue
            if item.is_folder:
                self._sync_folder_tree(item.id, progress_callback)
            elif can_download(item.mime_type):
                self._sync_pinned_file(item.id, progress_callback)

    def is_stale(self, record: FileRecord) -> bool:
        if record.is_folder or not can_download(record.mime_type):
            return False
        if not record.local_path or not Path(record.local_path).is_file():
            return True
        if record.modified_time != record.local_mtime:
            return True
        if record.md5:
            local_md5 = _file_md5(Path(record.local_path))
            if local_md5 and local_md5 != record.md5:
                return True
        return False

    def _pin_file(
        self, file_id: str, progress_callback: ProgressCallback | None
    ) -> None:
        self._store.set_pinned(file_id, True)
        self._sync_pinned_file(file_id, progress_callback)

    def _pin_folder_tree(
        self, folder_id: str, progress_callback: ProgressCallback | None
    ) -> None:
        self._store.set_pinned(folder_id, True)
        self._sync_folder_tree(folder_id, progress_callback, pin_descendants=True)

    def _sync_folder_tree(
        self,
        folder_id: str,
        progress_callback: ProgressCallback | None,
        pin_descendants: bool = False,
    ) -> None:
        try:
            raw = self._drive.list_children(folder_id)
        except Exception:
            log.exception("Cannot list folder %s during cache sync", folder_id)
            return
        folder_rec = self._store.get_file(folder_id)
        inherit_pin = pin_descendants or bool(folder_rec and folder_rec.pinned)
        records = [record_from_api(item, folder_id) for item in raw]
        removed = self._store.upsert_listing(folder_id, records)
        self.evict_removed(removed)
        for rec in records:
            if inherit_pin:
                self._store.set_pinned(rec.id, True)
            stored = self._store.get_file(rec.id) or rec
            if stored.is_folder:
                self._sync_folder_tree(
                    stored.id,
                    progress_callback,
                    pin_descendants=inherit_pin,
                )
            elif can_download(stored.mime_type) and stored.pinned:
                self._ensure_cached(stored, progress_callback)

    def _sync_pinned_file(
        self, file_id: str, progress_callback: ProgressCallback | None
    ) -> None:
        existing = self._store.get_file(file_id)
        if existing and existing.dirty:
            return
        try:
            api = self._drive.get_file(file_id)
        except Exception as exc:
            if is_network_error(exc):
                raise
            if isinstance(exc, HttpError) and exc.resp.status != 404:
                raise
            log.exception("Pinned file %s missing on Drive", file_id)
            self._store.set_pinned(file_id, False)
            self._evict_disk(file_id)
            self._store.delete_file(file_id)
            return
        existing = self._store.get_file(file_id)
        parent_id = existing.parent_id if existing else (api.get("parents") or [""])[0]
        meta = record_from_api(api, parent_id)
        self._store.upsert_metadata(meta)
        stored = self._store.get_file(file_id)
        if not stored or not stored.pinned:
            return
        self._ensure_cached(stored, progress_callback)

    def _ensure_cached(
        self,
        record: FileRecord,
        progress_callback: ProgressCallback | None,
    ) -> None:
        if not can_download(record.mime_type):
            return
        fresh = self._store.get_file(record.id) or record
        if fresh.dirty:
            return
        if not self.is_stale(fresh):
            return
        dest_dir = cache_dir() / fresh.id
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = self._transfer.download(
            fresh,
            dest_dir,
            _progress_adapter(fresh.name, progress_callback),
        )
        remote_mtime = fresh.modified_time or ""
        self._store.set_local_copy(
            fresh.id, str(path), remote_mtime, _fs_mtime_iso(path)
        )

    def evict_removed(self, removed: list[FileRecord]) -> None:
        for rec in removed:
            self._evict_disk(rec.id)

    def _evict_disk(self, file_id: str) -> None:
        path = cache_dir() / file_id
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

    def _under_pinned_folder(
        self, record: FileRecord, folder_ids: set[str]
    ) -> bool:
        current = record.parent_id
        seen: set[str] = set()
        while current and current not in seen:
            if current in folder_ids:
                return True
            seen.add(current)
            parent = self._store.get_file(current)
            if not parent:
                break
            current = parent.parent_id
        return False

def offline_label(record: FileRecord) -> str:
    if record.id.startswith("local_"):
        return "Queued"
    if record.dirty:
        return "Dirty"
    if not record.pinned:
        return ""
    if record.is_folder:
        return "Pinned"
    if not can_download(record.mime_type):
        return "Pinned"
    if not record.local_path or not Path(record.local_path).is_file():
        return "Pinned"
    if record.modified_time != record.local_mtime:
        return "Stale"
    return "Cached"

def _file_md5(path: Path) -> str | None:
    try:
        h = hashlib.md5()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None
