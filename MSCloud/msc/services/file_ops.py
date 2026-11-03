from __future__ import annotations
from typing import TYPE_CHECKING
from msc.config import FOLDER_MIME
from msc.db.store import FileRecord, SqliteStore, record_from_api
if TYPE_CHECKING:
    from msc.drive.client import DriveClient


class FileOpsError(Exception):
    """User-visible file operation failure."""


class FileOpsService:
    def __init__(self, drive: DriveClient, store: SqliteStore) -> None:
        self._drive = drive
        self._store = store

    def copy_items(self, items: list[FileRecord], dest_parent_id: str) -> None:
        for item in items:
            if item.is_folder:
                self._copy_folder_tree(item.id, dest_parent_id, item.name)
            else:
                self._drive.copy_file(item.id, dest_parent_id)

    def move_items(self, items: list[FileRecord], dest_parent_id: str) -> None:
        for item in items:
            if item.parent_id == dest_parent_id:
                continue
            if item.is_folder and self._is_descendant_of(dest_parent_id, item.id):
                raise FileOpsError(
                    f'Cannot move folder "{item.name}" into itself or a subfolder.'
                )
            api = self._drive.move_file(item.id, dest_parent_id, item.parent_id)
            meta = record_from_api(api, dest_parent_id)
            self._store.upsert_metadata(meta)

    def rename_item(self, item: FileRecord, new_name: str) -> None:
        name = new_name.strip()
        if not name:
            raise FileOpsError("Name cannot be empty.")
        api = self._drive.rename_file(item.id, name)
        meta = record_from_api(api, item.parent_id)
        self._store.upsert_metadata(meta)

    def delete_items(self, items: list[FileRecord]) -> list[FileRecord]:
        removed: list[FileRecord] = []
        for item in items:
            self._drive.trash_file(item.id)
            removed.extend(self._store.delete_file(item.id))
        return removed

    def _copy_folder_tree(
        self, source_folder_id: str, dest_parent_id: str, name: str
    ) -> None:
        api = self._drive.create_folder(dest_parent_id, name)
        new_folder_id = api["id"]
        for child in self._drive.list_children(source_folder_id):
            mime = child.get("mimeType", "")
            if mime == FOLDER_MIME:
                self._copy_folder_tree(
                    child["id"], new_folder_id, child.get("name", "Folder")
                )
            else:
                self._drive.copy_file(child["id"], new_folder_id)

    def _is_descendant_of(self, folder_id: str, ancestor_id: str) -> bool:
        if folder_id == ancestor_id:
            return True
        current = folder_id
        seen: set[str] = set()
        while current and current not in seen:
            if current == ancestor_id:
                return True
            seen.add(current)
            rec = self._store.get_file(current)
            if not rec:
                break
            current = rec.parent_id
        return False
