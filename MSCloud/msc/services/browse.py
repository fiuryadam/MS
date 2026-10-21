from __future__ import annotations
import logging
from dataclasses import dataclass, field
from msc.db.store import FileRecord, SqliteStore, record_from_api
from msc.drive.client import DriveClient

log = logging.getLogger(__name__)


@dataclass
class BrowseResult:
    items: list[FileRecord]
    from_cache: bool
    error_message: str | None = None
    removed: list[FileRecord] = field(default_factory=list)


class BrowseService:
    def __init__(self, drive: DriveClient, store: SqliteStore) -> None:
        self._drive = drive
        self._store = store

    def list_folder(self, folder_id: str) -> BrowseResult:
        try:
            raw = self._drive.list_children(folder_id)
            records = [record_from_api(item, folder_id) for item in raw]
            removed = self._store.upsert_listing(folder_id, records)
            items = self._store.get_children(folder_id)
            return BrowseResult(items=items, from_cache=False, removed=removed)
        except Exception as exc:
            log.exception("browse API failed, trying cache")
            cached = self._store.get_children(folder_id)
            if cached:
                return BrowseResult(
                    items=cached,
                    from_cache=True,
                    error_message=str(exc),
                )
            raise
