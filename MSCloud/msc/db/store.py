"""SQLite metadata store."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from msc.config import FOLDER_MIME


@dataclass(frozen=True)
class FileRecord:
    id: str
    parent_id: str
    name: str
    mime_type: str
    size: int | None
    md5: str | None
    modified_time: str | None
    is_folder: bool


class SqliteStore:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        schema_file = Path(__file__).with_name("schema.sql")
        sql = schema_file.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(sql)

    def upsert_listing(self, parent_id: str, items: list[FileRecord]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM files WHERE parent_id = ?", (parent_id,))
            for item in items:
                conn.execute(
                    """
                    INSERT INTO files (
                        id, parent_id, name, mime_type, size, md5,
                        modified_time, is_folder
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        parent_id=excluded.parent_id,
                        name=excluded.name,
                        mime_type=excluded.mime_type,
                        size=excluded.size,
                        md5=excluded.md5,
                        modified_time=excluded.modified_time,
                        is_folder=excluded.is_folder
                    """,
                    (
                        item.id,
                        item.parent_id,
                        item.name,
                        item.mime_type,
                        item.size,
                        item.md5,
                        item.modified_time,
                        1 if item.is_folder else 0,
                    ),
                )
            conn.commit()

    def get_children(self, parent_id: str) -> list[FileRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, parent_id, name, mime_type, size, md5, modified_time, is_folder
                FROM files WHERE parent_id = ?
                ORDER BY is_folder DESC, name COLLATE NOCASE
                """,
                (parent_id,),
            ).fetchall()
        return [_row_to_record(r) for r in rows]

    def get_setting(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()


def _row_to_record(row: sqlite3.Row) -> FileRecord:
    return FileRecord(
        id=row["id"],
        parent_id=row["parent_id"],
        name=row["name"],
        mime_type=row["mime_type"],
        size=row["size"],
        md5=row["md5"],
        modified_time=row["modified_time"],
        is_folder=bool(row["is_folder"]),
    )


def record_from_api(item: dict, parent_id: str) -> FileRecord:
    mime = item.get("mimeType", "")
    return FileRecord(
        id=item["id"],
        parent_id=parent_id,
        name=item.get("name", ""),
        mime_type=mime,
        size=int(item["size"]) if item.get("size") is not None else None,
        md5=item.get("md5Checksum"),
        modified_time=item.get("modifiedTime"),
        is_folder=mime == FOLDER_MIME,
    )
