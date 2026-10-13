"""Table model for Drive file listing."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QFont

from msc.db.store import FileRecord
from msc.ui.icons import icon_for


def _format_size(size: int | None) -> str:
    if size is None:
        return "—"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.1f} GB"


def _format_modified(modified: str | None) -> str:
    if not modified:
        return "—"
    return modified[:10]


class FileTableModel(QAbstractTableModel):
    HEADERS = ["Name", "Modified", "Size"]

    def __init__(self) -> None:
        super().__init__()
        self._items: list[FileRecord] = []

    def set_items(self, items: list[FileRecord]) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 3

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return self.HEADERS[section]
            if role == Qt.ItemDataRole.TextAlignmentRole and section != 0:
                return int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DecorationRole and col == 0:
            return icon_for(item.mime_type, item.is_folder)

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return item.name
            if col == 1:
                return _format_modified(item.modified_time)
            if col == 2:
                return "—" if item.is_folder else _format_size(item.size)

        if role == Qt.ItemDataRole.TextAlignmentRole and col != 0:
            return int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.FontRole and col == 0 and item.is_folder:
            font = QFont()
            font.setWeight(QFont.Weight.DemiBold)
            return font

        if role == Qt.ItemDataRole.UserRole:
            return item

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def item_at(self, row: int) -> FileRecord | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None
