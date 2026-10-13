"""MIME helpers and Google export mapping."""

from msc.config import FOLDER_MIME, GOOGLE_EXPORT

GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."


def is_folder(mime_type: str) -> bool:
    return mime_type == FOLDER_MIME


def is_google_native(mime_type: str) -> bool:
    return mime_type.startswith(GOOGLE_NATIVE_PREFIX) and mime_type != FOLDER_MIME


def can_download(mime_type: str) -> bool:
    if is_folder(mime_type):
        return False
    if is_google_native(mime_type):
        return mime_type in GOOGLE_EXPORT
    return True


def export_info(mime_type: str) -> tuple[str, str] | None:
    """Return (export_mime, extension) for Google native types."""
    return GOOGLE_EXPORT.get(mime_type)


def guess_mime_from_path(path: str) -> str:
    import mimetypes

    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"
