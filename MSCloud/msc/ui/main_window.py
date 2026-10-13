from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from msc.auth.oauth import logout
from msc.config import DRIVE_ROOT_ID
from msc.db.store import FileRecord, SqliteStore
from msc.drive.client import DriveClient
from msc.services.browse import BrowseService
from msc.services.transfer import TransferService
from msc.ui.widgets.breadcrumbs import BreadcrumbBar
from msc.ui.widgets.file_view import FileView
from msc.ui.widgets.sidebar import Sidebar
from msc.ui.workers import WorkerSignals, run_in_background

log = logging.getLogger(__name__)


class MainWindow(QWidget):
    def __init__(
        self,
        drive: DriveClient,
        store: SqliteStore,
        on_logout: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._on_logout = on_logout
        self._browse = BrowseService(drive, store)
        self._transfer = TransferService(drive)
        self._folder_id = DRIVE_ROOT_ID
        self._path_stack: list[tuple[str, str]] = [(DRIVE_ROOT_ID, "My Drive")]
        self._last_download_dir: Path | None = None
        saved = store.get_setting("last_download_dir")
        if saved:
            self._last_download_dir = Path(saved)
        self._jobs: list[WorkerSignals] = []
        self._refreshing = False

        self.setMinimumSize(960, 600)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        self.transfer_bar = self.sidebar.transfer_bar

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)

        toolbar = QHBoxLayout()
        self.upload_btn = QPushButton("Upload")
        self.upload_btn.setObjectName("primaryButton")
        self.download_btn = QPushButton("Download selected")
        self.download_btn.setObjectName("secondaryButton")
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("secondaryButton")
        self.logout_btn = QPushButton("Log out")
        self.logout_btn.setObjectName("logoutButton")
        for btn in (self.upload_btn, self.download_btn, self.refresh_btn, self.logout_btn):
            btn.setMinimumHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        for btn in (self.upload_btn, self.download_btn, self.refresh_btn):
            toolbar.addWidget(btn)
        toolbar.addStretch()
        toolbar.addWidget(self.logout_btn)
        right_layout.addLayout(toolbar)

        self.offline_banner = QLabel("")
        self.offline_banner.setObjectName("offlineBanner")
        self.offline_banner.hide()
        right_layout.addWidget(self.offline_banner)

        self.breadcrumbs = BreadcrumbBar()
        self.breadcrumbs.navigated.connect(self._navigate_to)
        right_layout.addWidget(self.breadcrumbs)

        self.file_view = FileView()
        self.file_view.folderActivated.connect(self._enter_folder)
        right_layout.addWidget(self.file_view, stretch=1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        self.upload_btn.clicked.connect(self._on_upload)
        self.download_btn.clicked.connect(self._on_download)
        self.refresh_btn.clicked.connect(self._refresh)
        self.logout_btn.clicked.connect(self._logout)

        self._update_breadcrumbs()
        self._refresh()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Backspace and len(self._path_stack) > 1:
            self._path_stack.pop()
            self._folder_id = self._path_stack[-1][0]
            self._update_breadcrumbs()
            self._refresh()
        else:
            super().keyPressEvent(event)

    def _update_breadcrumbs(self) -> None:
        self.breadcrumbs.set_path(self._path_stack)

    def _enter_folder(self, folder_id: str) -> None:
        name = "Folder"
        for row in range(self.file_view.file_model.rowCount()):
            item = self.file_view.file_model.item_at(row)
            if item and item.id == folder_id:
                name = item.name
                break
        self._folder_id = folder_id
        if not self._path_stack or self._path_stack[-1][0] != folder_id:
            self._path_stack.append((folder_id, name))
        self._update_breadcrumbs()
        self._refresh()

    def _navigate_to(self, folder_id: str) -> None:
        for i, (fid, _) in enumerate(self._path_stack):
            if fid == folder_id:
                self._path_stack = self._path_stack[: i + 1]
                break
        self._folder_id = folder_id
        self._update_breadcrumbs()
        self._refresh()

    def _track(self, signals: WorkerSignals) -> WorkerSignals:
        self._jobs.append(signals)

        def _drop(_=None) -> None:
            if signals in self._jobs:
                self._jobs.remove(signals)

        signals.finished.connect(_drop)
        signals.error.connect(_drop)
        return signals

    def _refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        self.transfer_bar.set_idle("Loading…")
        folder_id = self._folder_id

        def task(_sig):
            return self._browse.list_folder(folder_id)

        def done(result) -> None:
            self._refreshing = False
            self.file_view.set_items(result.items)
            if result.from_cache:
                msg = "Offline – showing last known files"
                if result.error_message:
                    msg += f" ({result.error_message})"
                self.offline_banner.setText(msg)
                self.offline_banner.show()
            else:
                self.offline_banner.hide()
            self.transfer_bar.set_idle("Ready")

        def failed(message: str) -> None:
            self._refreshing = False
            self._show_error(message)

        self._track(run_in_background(task, done, failed, label=f"refresh:{folder_id}"))

    def _on_upload(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Upload file")
        if not path:
            return
        local = Path(path)
        parent_id = self._folder_id

        signals = self._track(
            run_in_background(
                lambda sig: self._transfer.upload(
                    local,
                    parent_id,
                    lambda d, t: sig.progress.emit(local.name, d, t),
                ),
                lambda _r: (
                    self.transfer_bar.set_idle("Upload complete"),
                    self._refresh(),
                ),
                self._show_error,
                label=f"upload:{local.name}",
            )
        )
        signals.progress.connect(
            lambda _name, done, total: self.transfer_bar.set_progress(
                f"Uploading {local.name}", done, total
            )
        )

    def _on_download(self) -> None:
        items = self.file_view.items_for_download()
        if not items:
            QMessageBox.information(
                self,
                "Download",
                "Select one or more files to download. Folders cannot be downloaded.",
            )
            return
        start_dir = str(self._last_download_dir or Path.home())
        dest = QFileDialog.getExistingDirectory(self, "Download to folder", start_dir)
        if not dest:
            return
        dest_dir = Path(dest)
        self._last_download_dir = dest_dir
        self._store.set_setting("last_download_dir", str(dest_dir))
        self._download_queue(list(items), dest_dir)

    def _download_queue(self, items: list[FileRecord], dest_dir: Path) -> None:
        if not items:
            self.transfer_bar.set_idle("Download complete")
            return
        item = items[0]
        remaining = items[1:]

        signals = self._track(
            run_in_background(
                lambda sig: self._transfer.download(
                    item,
                    dest_dir,
                    lambda d, t: sig.progress.emit(item.name, d, t),
                ),
                lambda path: self._prompt_after_download(path, remaining, dest_dir),
                self._show_error,
                label=f"download:{item.name}",
            )
        )
        signals.progress.connect(
            lambda _name, done, total: self.transfer_bar.set_progress(
                f"Downloading {item.name}", done, total
            )
        )

    def _prompt_after_download(
        self, path: Path, remaining: list[FileRecord], dest_dir: Path
    ) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle("Downloaded")
        msg.setText(f"Saved to:\n{path}")
        open_btn = msg.addButton("Open", QMessageBox.ButtonRole.AcceptRole)
        folder_btn = msg.addButton("Show in folder", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Continue", QMessageBox.ButtonRole.YesRole)
        stop_btn = msg.addButton("Stop", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == open_btn:
            TransferService.open_file(path)
        elif clicked == folder_btn:
            TransferService.show_in_folder(path)
        if clicked == stop_btn:
            self.transfer_bar.set_idle("Ready")
            return
        self._download_queue(remaining, dest_dir)

    def _logout(self) -> None:
        logout()
        self._on_logout()

    def _show_error(self, message: str) -> None:
        log.error("UI error: %s", message)
        self.transfer_bar.set_idle("Error")
        QMessageBox.critical(self, "Error", message)
