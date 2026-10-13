"""Small Drive-like file/folder icons drawn with QPainter."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_CACHE: dict[tuple[str, int], QIcon] = {}


def icon_for(mime_type: str, is_folder: bool, size: int = 22) -> QIcon:
    kind = _kind(mime_type, is_folder)
    key = (kind, size)
    if key not in _CACHE:
        _CACHE[key] = QIcon(_paint(kind, size))
    return _CACHE[key]


def _kind(mime_type: str, is_folder: bool) -> str:
    if is_folder:
        return "folder"
    mime = mime_type or ""
    if mime == "application/vnd.google-apps.document":
        return "docs"
    if mime == "application/vnd.google-apps.spreadsheet":
        return "sheets"
    if mime == "application/vnd.google-apps.presentation":
        return "slides"
    if mime.startswith("image/"):
        return "image"
    if mime == "application/pdf" or mime.endswith("/pdf"):
        return "pdf"
    if mime.startswith("text/") or mime.endswith(".txt") or "plain" in mime:
        return "text"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if "zip" in mime or "compressed" in mime:
        return "archive"
    return "file"


def _paint(kind: str, size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if kind == "folder":
        _draw_folder(p, size)
    else:
        _draw_file(p, size, kind)
    p.end()
    return pm


def _draw_folder(p: QPainter, size: int) -> None:
    s = float(size)
    tab = QPainterPath()
    tab.addRoundedRect(QRectF(s * 0.08, s * 0.22, s * 0.38, s * 0.22), 2.5, 2.5)
    body = QPainterPath()
    body.addRoundedRect(QRectF(s * 0.08, s * 0.32, s * 0.84, s * 0.56), 3.5, 3.5)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#fbbc04"))
    p.drawPath(tab)
    p.setBrush(QColor("#f9ab00"))
    p.drawPath(body)
    p.setBrush(QColor("#ffe082"))
    p.drawRoundedRect(QRectF(s * 0.08, s * 0.40, s * 0.84, s * 0.16), 2, 2)


def _draw_file(p: QPainter, size: int, kind: str) -> None:
    colors = {
        "docs": QColor("#1a73e8"),
        "sheets": QColor("#0f9d58"),
        "slides": QColor("#f9ab00"),
        "image": QColor("#34a853"),
        "pdf": QColor("#d93025"),
        "text": QColor("#5f6368"),
        "video": QColor("#a142f4"),
        "audio": QColor("#f4511e"),
        "archive": QColor("#e8710a"),
        "file": QColor("#80868b"),
    }
    accent = colors.get(kind, colors["file"])
    s = float(size)
    page = QPainterPath()
    fold = s * 0.22
    page.moveTo(s * 0.22, s * 0.10)
    page.lineTo(s * 0.70 - fold, s * 0.10)
    page.lineTo(s * 0.78, s * 0.10 + fold)
    page.lineTo(s * 0.78, s * 0.90)
    page.lineTo(s * 0.22, s * 0.90)
    page.closeSubpath()
    p.setPen(QPen(QColor("#dadce0"), 1.0))
    p.setBrush(QColor("#ffffff"))
    p.drawPath(page)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#f1f3f4"))
    corner = QPainterPath()
    corner.moveTo(s * 0.70 - fold, s * 0.10)
    corner.lineTo(s * 0.78, s * 0.10 + fold)
    corner.lineTo(s * 0.70 - fold, s * 0.10 + fold)
    corner.closeSubpath()
    p.drawPath(corner)
    p.setBrush(accent)
    p.drawRoundedRect(QRectF(s * 0.30, s * 0.58, s * 0.40, s * 0.18), 2.2, 2.2)
    p.setPen(QPen(QColor("#e8eaed"), 1.0))
    y = s * 0.34
    for _ in range(2):
        p.drawLine(int(s * 0.32), int(y), int(s * 0.62), int(y))
        y += s * 0.09


def icon_size() -> QSize:
    return QSize(22, 22)
