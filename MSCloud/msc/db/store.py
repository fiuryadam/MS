from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from msc.config import FOLDER_MIME

_FILE_COLUMNS = """
    id, parent_id, name, mime_type, size, md5, modified_time, is_folder,
    pinned, local_path, dirty, local_mtime, fs_mtime
"""


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
    pinned: bool = False
    local_path: str | None = None
    dirty: bool = False
    local_mtime: str | None = None
    fs_mtime: str | None = None


@dataclass(frozen=True)
class PendingOp:
    id: int
    op_type: str
    payload: dict
    status: str
    created_at: str


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
            cols = {r[1] for r in conn.execute("PRAGMA table_info(files)").fetchall()}
            if "fs_mtime" not in cols:
                conn.execute("ALTER TABLE files ADD COLUMN fs_mtime TEXT")
            conn.commit()

    def _should_preserve_row(self, conn: sqlite3.Connection, file_id: str) -> bool:
        if file_id.startswith("local_"):
            return True
        row = conn.execute(
            "SELECT dirty FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        if row and row["dirty"]:
            return True
        pending = conn.execute(
            """
            SELECT 1 FROM pending_ops
            WHERE status = 'pending' AND payload_json LIKE ?
            LIMIT 1
            """,
            (f'%"{file_id}"%',),
        ).fetchone()
        return pending is not None

    def upsert_listing(self, parent_id: str, items: list[FileRecord]) -> list[FileRecord]:
        """Refresh folder children; return removed rows (for cache eviction)."""
        new_ids = {item.id for item in items}
        removed: list[FileRecord] = []
        with self._connect() as conn:
            old_rows = conn.execute(
                f"SELECT {_FILE_COLUMNS} FROM files WHERE parent_id = ?",
                (parent_id,),
            ).fetchall()
            for row in old_rows:
                fid = row["id"]
                if fid not in new_ids:
                    if self._should_preserve_row(conn, fid):
                        continue
                    removed.extend(self._delete_subtree(conn, fid))
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
        return removed

    def get_children(self, parent_id: str) -> list[FileRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {_FILE_COLUMNS}
                FROM files WHERE parent_id = ?
                ORDER BY is_folder DESC, name COLLATE NOCASE
                """,
                (parent_id,),
            ).fetchall()
        return [_row_to_record(r) for r in rows]

    def get_file(self, file_id: str) -> FileRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_FILE_COLUMNS} FROM files WHERE id = ?",
                (file_id,),
            ).fetchone()
        return _row_to_record(row) if row else None

    def get_pinned(self) -> list[FileRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {_FILE_COLUMNS} FROM files WHERE pinned = 1
                ORDER BY is_folder DESC, name COLLATE NOCASE
                """
            ).fetchall()
        return [_row_to_record(r) for r in rows]

    def get_descendants(self, folder_id: str) -> list[FileRecord]:
        result: list[FileRecord] = []
        queue = [folder_id]
        with self._connect() as conn:
            while queue:
                parent = queue.pop(0)
                rows = conn.execute(
                    f"SELECT {_FILE_COLUMNS} FROM files WHERE parent_id = ?",
                    (parent,),
                ).fetchall()
                for row in rows:
                    rec = _row_to_record(row)
                    result.append(rec)
                    if rec.is_folder:
                        queue.append(rec.id)
        return result

    def insert_local_file(self, record: FileRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO files (
                    id, parent_id, name, mime_type, size, md5, modified_time,
                    is_folder, pinned, local_path, dirty, local_mtime, fs_mtime
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.parent_id,
                    record.name,
                    record.mime_type,
                    record.size,
                    record.md5,
                    record.modified_time,
                    1 if record.is_folder else 0,
                    1 if record.pinned else 0,
                    record.local_path,
                    1 if record.dirty else 0,
                    record.local_mtime,
                    record.fs_mtime,
                ),
            )
            conn.commit()

    def replace_file_id(self, old_id: str, new_id: str, **updates: object) -> None:
        rec = self.get_file(old_id)
        if not rec:
            return
        merged = FileRecord(
            id=new_id,
            parent_id=str(updates.get("parent_id", rec.parent_id)),
            name=str(updates.get("name", rec.name)),
            mime_type=str(updates.get("mime_type", rec.mime_type)),
            size=updates.get("size", rec.size),
            md5=updates.get("md5", rec.md5),
            modified_time=updates.get("modified_time", rec.modified_time),
            is_folder=bool(updates.get("is_folder", rec.is_folder)),
            pinned=bool(updates.get("pinned", rec.pinned)),
            local_path=updates.get("local_path", rec.local_path),
            dirty=bool(updates.get("dirty", rec.dirty)),
            local_mtime=updates.get("local_mtime", rec.local_mtime),
            fs_mtime=updates.get("fs_mtime", rec.fs_mtime),
        )
        with self._connect() as conn:
            conn.execute("DELETE FROM files WHERE id = ?", (old_id,))
            conn.execute(
                """
                INSERT INTO files (
                    id, parent_id, name, mime_type, size, md5, modified_time,
                    is_folder, pinned, local_path, dirty, local_mtime, fs_mtime
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    merged.id,
                    merged.parent_id,
                    merged.name,
                    merged.mime_type,
                    merged.size,
                    merged.md5,
                    merged.modified_time,
                    1 if merged.is_folder else 0,
                    1 if merged.pinned else 0,
                    merged.local_path,
                    1 if merged.dirty else 0,
                    merged.local_mtime,
                    merged.fs_mtime,
                ),
            )
            conn.commit()

    def upsert_metadata(self, record: FileRecord) -> None:
        """Insert or update listing metadata without clearing pin/cache columns."""
        with self._connect() as conn:
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
                    record.id,
                    record.parent_id,
                    record.name,
                    record.mime_type,
                    record.size,
                    record.md5,
                    record.modified_time,
                    1 if record.is_folder else 0,
                ),
            )
            conn.commit()

    def set_pinned(self, file_id: str, pinned: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE files SET pinned = ? WHERE id = ?",
                (1 if pinned else 0, file_id),
            )
            conn.commit()

    def set_dirty(self, file_id: str, dirty: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE files SET dirty = ? WHERE id = ?",
                (1 if dirty else 0, file_id),
            )
            conn.commit()

    def set_local_copy(
        self,
        file_id: str,
        local_path: str,
        local_mtime: str,
        fs_mtime: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE files SET local_path = ?, local_mtime = ?, fs_mtime = ?
                WHERE id = ?
                """,
                (local_path, local_mtime, fs_mtime, file_id),
            )
            conn.commit()

    def clear_local_copy(self, file_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE files SET local_path = NULL, local_mtime = NULL, fs_mtime = NULL
                WHERE id = ?
                """,
                (file_id,),
            )
            conn.commit()

    def enqueue_op(self, op_type: str, payload: dict) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO pending_ops (op_type, payload_json, status)
                VALUES (?, ?, 'pending')
                """,
                (op_type, json.dumps(payload)),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_pending(self) -> list[PendingOp]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, op_type, payload_json, status, created_at
                FROM pending_ops WHERE status = 'pending'
                ORDER BY id
                """
            ).fetchall()
        return [
            PendingOp(
                id=row["id"],
                op_type=row["op_type"],
                payload=json.loads(row["payload_json"]),
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def delete_op(self, op_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM pending_ops WHERE id = ?", (op_id,))
            conn.commit()

    def delete_pending_for_file(self, file_id: str, op_type: str | None = None) -> None:
        with self._connect() as conn:
            for row in conn.execute(
                "SELECT id, payload_json FROM pending_ops WHERE status = 'pending'"
            ).fetchall():
                payload = json.loads(row["payload_json"])
                match = (
                    payload.get("file_id") == file_id
                    or payload.get("temp_id") == file_id
                )
                if match and (op_type is None or row["op_type"] == op_type):
                    conn.execute("DELETE FROM pending_ops WHERE id = ?", (row["id"],))
            conn.commit()

    def has_pending_create(self, temp_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM pending_ops
                WHERE status = 'pending' AND op_type = 'create'
                AND payload_json LIKE ?
                """,
                (f'%"{temp_id}"%',),
            ).fetchone()
        return row is not None

    def delete_file(self, file_id: str) -> list[FileRecord]:
        """Delete a row and its subtree; return removed records."""
        with self._connect() as conn:
            removed = self._delete_subtree(conn, file_id)
            conn.commit()
        return removed

    def _delete_subtree(
        self, conn: sqlite3.Connection, file_id: str
    ) -> list[FileRecord]:
        removed: list[FileRecord] = []
        child_rows = conn.execute(
            "SELECT id FROM files WHERE parent_id = ?", (file_id,)
        ).fetchall()
        for child in child_rows:
            removed.extend(self._delete_subtree(conn, child["id"]))
        row = conn.execute(
            f"SELECT {_FILE_COLUMNS} FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
            removed.append(_row_to_record(row))
        return removed

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
    keys = row.keys()
    dirty = bool(row["dirty"]) if "dirty" in keys else False
    fs_mtime = row["fs_mtime"] if "fs_mtime" in keys else None
    return FileRecord(
        id=row["id"],
        parent_id=row["parent_id"],
        name=row["name"],
        mime_type=row["mime_type"],
        size=row["size"],
        md5=row["md5"],
        modified_time=row["modified_time"],
        is_folder=bool(row["is_folder"]),
        pinned=bool(row["pinned"]),
        local_path=row["local_path"],
        dirty=dirty,
        local_mtime=row["local_mtime"],
        fs_mtime=fs_mtime,
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
