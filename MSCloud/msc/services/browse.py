"""Folder listing with SQLite metadata cache."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from msc.db.store import FileRecord, SqliteStore, record_from_api
from msc.drive.client import DriveClient

log = logging.getLogger(__name__)


@dataclass
class BrowseResult:
    items: list[FileRecord]
    from_cache: bool
    error_message: str | None = None


class BrowseService:
    def __init__(self, drive: DriveClient, store: SqliteStore) -> None:
        self._drive = drive
        self._store = store

    def list_folder(self, folder_id: str) -> BrowseResult:
        try:
            raw = self._drive.list_children(folder_id)
            records = [record_from_api(item, folder_id) for item in raw]
            self._store.upsert_listing(folder_id, records)
            return BrowseResult(items=records, from_cache=False)
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
