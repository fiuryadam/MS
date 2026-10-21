from PySide6.QtCore import QItemSelectionModel, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHeaderView,
    QMenu,
    QStyledItemDelegate,
    QTableView,
    QWidget,
)

from msc.db.store import FileRecord
from msc.drive.mimes import can_download
from msc.ui.file_model import FileTableModel


class _CutItemDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index) -> None:
        super().initStyleOption(option, index)
        fg = index.data(Qt.ItemDataRole.ForegroundRole)
        if fg is not None:
            color = QColor(fg)
            option.palette.setColor(option.palette.ColorRole.Text, color)
            option.palette.setColor(option.palette.ColorRole.HighlightedText, color)


class FileView(QTableView):
    folderActivated = Signal(str)
    fileActivated = Signal(object)
    downloadRequested = Signal()
    keepOfflineRequested = Signal()
    removeFromCacheRequested = Signal()
    copyRequested = Signal()
    cutRequested = Signal()
    pasteRequested = Signal()
    renameRequested = Signal()
    deleteRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = FileTableModel()
        self.setModel(self._model)
        self.setItemDelegate(_CutItemDelegate(self))
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
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.doubleClicked.connect(self._on_double_click)
        self._paste_enabled = False
        self._file_ops_enabled = True

    @property
    def file_model(self) -> FileTableModel:
        return self._model

    def set_paste_enabled(self, enabled: bool) -> None:
        self._paste_enabled = enabled

    def set_file_ops_enabled(self, enabled: bool) -> None:
        self._file_ops_enabled = enabled

    def set_cut_ids(self, ids: set[str]) -> None:
        self._model.set_cut_ids(ids)

    def set_items(self, items) -> None:
        selected_ids = {item.id for item in self.selected_items()}
        self._model.set_items(items)
        self._fit_columns()
        if not selected_ids:
            return
        selection = self.selectionModel()
        if not selection:
            return
        for row in range(self._model.rowCount()):
            item = self._model.item_at(row)
            if item and item.id in selected_ids:
                index = self._model.index(row, 0)
                selection.select(
                    index,
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )

    def _fit_columns(self) -> None:
        for col in (1, 2, 3):
            self.resizeColumnToContents(col)
            self.setColumnWidth(col, self.columnWidth(col) + 24)

    def selected_items(self) -> list[FileRecord]:
        selection = self.selectionModel()
        if not selection:
            return []
        items: list[FileRecord] = []
        for index in selection.selectedRows(0):
            item = self._model.item_at(index.row())
            if item:
                items.append(item)
        return items

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

    def _show_context_menu(self, pos: QPoint) -> None:
        index = self.indexAt(pos)
        if index.isValid():
            selection = self.selectionModel()
            if selection and not selection.isSelected(index):
                self.selectRow(index.row())
        items = self.selected_items()

        menu = QMenu(self)
        if not items:
            if self._paste_enabled:
                paste = menu.addAction("Paste")
                chosen = menu.exec(self.viewport().mapToGlobal(pos))
                if chosen == paste:
                    self.pasteRequested.emit()
            return

        ops_enabled = self._file_ops_enabled
        copy_act = menu.addAction("Copy")
        copy_act.setEnabled(ops_enabled)
        cut_act = menu.addAction("Cut")
        cut_act.setEnabled(ops_enabled)
        paste_act = menu.addAction("Paste")
        paste_act.setEnabled(self._paste_enabled)
        rename_act = menu.addAction("Rename")
        rename_act.setEnabled(ops_enabled and len(items) == 1)
        delete_act = menu.addAction("Delete")
        delete_act.setEnabled(ops_enabled)
        menu.addSeparator()
        download = menu.addAction("Download")
        download.setEnabled(bool(self.items_for_download()))
        pin = menu.addAction("Keep offline")
        unpin = menu.addAction("Remove from cache")
        unpin.setEnabled(any(item.pinned or item.local_path for item in items))

        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == copy_act:
            self.copyRequested.emit()
        elif chosen == cut_act:
            self.cutRequested.emit()
        elif chosen == paste_act:
            self.pasteRequested.emit()
        elif chosen == rename_act:
            self.renameRequested.emit()
        elif chosen == delete_act:
            self.deleteRequested.emit()
        elif chosen == download:
            self.downloadRequested.emit()
        elif chosen == pin:
            self.keepOfflineRequested.emit()
        elif chosen == unpin:
            self.removeFromCacheRequested.emit()
