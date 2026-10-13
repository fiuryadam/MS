"""Upload and download to user-chosen directories."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from msc.db.store import FileRecord
from msc.drive.client import DriveClient
from msc.drive.mimes import can_download, export_info, is_google_native
from msc.paths import safe_destination


class TransferService:
    def __init__(self, drive: DriveClient) -> None:
        self._drive = drive

    def upload(
        self,
        local_path: Path,
        parent_id: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict:
        if not local_path.is_file():
            raise FileNotFoundError(str(local_path))
        return self._drive.upload_file(local_path, parent_id, progress_callback)

    def download(
        self,
        item: FileRecord,
        dest_dir: Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path:
        if not can_download(item.mime_type):
            raise ValueError(f"Cannot download: {item.name}")

        filename = item.name
        if is_google_native(item.mime_type):
            info = export_info(item.mime_type)
            if not info:
                raise ValueError(f"No export format for: {item.name}")
            export_mime, ext = info
            base = Path(item.name).stem
            filename = base + ext
            dest = safe_destination(dest_dir, filename)
            self._drive.export_google_doc(
                item.id, dest, export_mime, progress_callback
            )
            return dest

        dest = safe_destination(dest_dir, filename)
        self._drive.download_file(item.id, dest, progress_callback)
        return dest

    @staticmethod
    def open_file(path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    @staticmethod
    def show_in_folder(path: Path) -> None:
        resolved = path.resolve()
        if sys.platform == "win32":
            subprocess.run(
                ["explorer", "/select,", str(resolved)],
                check=False,
            )
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(resolved)], check=False)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved.parent)))
