from __future__ import annotations
import io
import threading
from pathlib import Path
from typing import Callable
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from msc.drive.mimes import guess_mime_from_path


class DriveClient:
    def __init__(self, creds: Credentials) -> None:
        self._lock = threading.Lock()
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)

    def list_children(self, folder_id: str) -> list[dict]:
        query = f"'{folder_id}' in parents and trashed = false"
        fields = "nextPageToken, files(id, name, mimeType, size, modifiedTime, md5Checksum, parents)"
        items: list[dict] = []
        page_token: str | None = None
        with self._lock:
            while True:
                response = (
                    self._service.files()
                    .list(
                        q=query,
                        spaces="drive",
                        fields=fields,
                        pageToken=page_token,
                        pageSize=200,
                        orderBy="folder,name_natural",
                    )
                    .execute()
                )
                batch = response.get("files", [])
                items.extend(batch)
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        return items

    def upload_file(
        self,
        local_path: Path,
        parent_id: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict:
        mime = guess_mime_from_path(str(local_path))
        metadata = {"name": local_path.name, "parents": [parent_id]}
        media = MediaFileUpload(str(local_path), mimetype=mime, resumable=True)
        with self._lock:
            request = self._service.files().create(
                body=metadata, media_body=media, fields="id, name"
            )
            result = self._resumable_upload(request, progress_callback)
        return result

    def download_file(
        self,
        file_id: str,
        dest_path: Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        with self._lock:
            request = self._service.files().get_media(fileId=file_id)
            self._download_to_path(request, dest_path, progress_callback)

    def export_google_doc(
        self,
        file_id: str,
        dest_path: Path,
        export_mime: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        with self._lock:
            request = self._service.files().export_media(
                fileId=file_id, mimeType=export_mime
            )
            self._download_to_path(request, dest_path, progress_callback)

    def _download_to_path(
        self,
        request,
        dest_path: Path,
        progress_callback: Callable[[int, int], None] | None,
    ) -> None:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with io.FileIO(dest_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status and progress_callback:
                    progress_callback(
                        int(status.resumable_progress), int(status.total_size or 0)
                    )

    def _resumable_upload(
        self,
        request,
        progress_callback: Callable[[int, int], None] | None,
    ) -> dict:
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status and progress_callback:
                progress_callback(
                    int(status.resumable_progress), int(status.total_size or 0)
                )
        return response
