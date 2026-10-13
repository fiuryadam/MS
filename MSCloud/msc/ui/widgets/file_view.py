from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QHeaderView, QTableView, QWidget

from msc.db.store import FileRecord
from msc.drive.mimes import can_download
from msc.ui.file_model import FileTableModel


class FileView(QTableView):
    folderActivated = Signal(str)
    fileActivated = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = FileTableModel()
        self.setModel(self._model)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.setIconSize(QSize(22, 22))
        self.verticalHeader().setDefaultSectionSize(36)
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(64)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.doubleClicked.connect(self._on_double_click)

    @property
    def file_model(self) -> FileTableModel:
        return self._model

    def set_items(self, items) -> None:
        self._model.set_items(items)
        self._fit_columns()

    def _fit_columns(self) -> None:
        for col in (1, 2):
            self.resizeColumnToContents(col)
            self.setColumnWidth(col, self.columnWidth(col) + 24)

    def items_for_download(self) -> list[FileRecord]:
        selection = self.selectionModel()
        if not selection:
            return []
        items: list[FileRecord] = []
        for index in selection.selectedRows(0):
            item = self._model.item_at(index.row())
            if item and can_download(item.mime_type):
                items.append(item)
        return items

    def _on_double_click(self, index) -> None:
        item = self._model.item_at(index.row())
        if not item:
            return
        if item.is_folder:
            self.folderActivated.emit(item.id)
        else:
            self.fileActivated.emit(item)
