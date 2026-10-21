from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
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
from msc.services.cache import CacheService
from msc.services.file_ops import FileOpsService
from msc.services.sync import ConflictBridge, OfflineSyncError, SyncService
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
        self._cache = CacheService(drive, store)
        self._file_ops = FileOpsService(drive, store)
        self._clipboard_items: list[FileRecord] | None = None
        self._clipboard_mode: str | None = None
        self._file_ops_busy = False
        self._conflict_bridge = ConflictBridge(self)
        self._sync = SyncService(drive, store, self._conflict_bridge)
        self._sync.set_after_local_edit(self._on_cached_file_edited)
        self._is_online = True
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(5000)
        self._reconnect_timer.timeout.connect(self._try_reconnect)
        self._folder_id = DRIVE_ROOT_ID
        self._path_stack: list[tuple[str, str]] = [(DRIVE_ROOT_ID, "My Drive")]
        self._last_download_dir: Path | None = None
        saved = store.get_setting("last_download_dir")
        if saved:
            self._last_download_dir = Path(saved)
        self._jobs: list[WorkerSignals] = []
        self._refreshing = False
        self._cache_busy = False
        self._initial_cache_sync_done = False

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
        self.sync_cache_btn = QPushButton("Sync cache")
        self.sync_cache_btn.setObjectName("secondaryButton")
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("secondaryButton")
        self.logout_btn = QPushButton("Log out")
        self.logout_btn.setObjectName("logoutButton")
        for btn in (
            self.upload_btn,
            self.sync_cache_btn,
            self.refresh_btn,
            self.logout_btn,
        ):
            btn.setMinimumHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        for btn in (
            self.upload_btn,
            self.sync_cache_btn,
            self.refresh_btn,
        ):
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
        self.file_view.fileActivated.connect(self._on_file_activated)
        self.file_view.downloadRequested.connect(self._on_download)
        self.file_view.keepOfflineRequested.connect(self._on_keep_offline)
        self.file_view.removeFromCacheRequested.connect(self._on_remove_from_cache)
        self.file_view.copyRequested.connect(self._on_copy)
        self.file_view.cutRequested.connect(self._on_cut)
        self.file_view.pasteRequested.connect(self._on_paste)
        self.file_view.renameRequested.connect(self._on_rename)
        self.file_view.deleteRequested.connect(self._on_delete)
        right_layout.addWidget(self.file_view, stretch=1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        self.upload_btn.clicked.connect(self._on_upload)
        self.sync_cache_btn.clicked.connect(self._on_sync_cache)
        self.refresh_btn.clicked.connect(self._refresh)
        self.logout_btn.clicked.connect(self._logout)

        self._install_file_op_shortcuts()
        self._update_breadcrumbs()
        self._update_file_ops_ui()
        self._refresh()

    def _install_file_op_shortcuts(self) -> None:
        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
        bindings = (
            (QKeySequence.StandardKey.Copy, self._on_copy),
            (QKeySequence.StandardKey.Cut, self._on_cut),
            (QKeySequence.StandardKey.Paste, self._on_paste),
            (QKeySequence("F2"), self._on_rename),
            (QKeySequence.StandardKey.Delete, self._on_delete),
        )
        for sequence, handler in bindings:
            shortcut = QShortcut(sequence, self)
            shortcut.setContext(ctx)
            shortcut.activated.connect(handler)

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

    def _refresh(self, *, sync_cache: bool = True) -> None:
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
                self._is_online = False
                self._sync.set_online(False)
                msg = "Offline – showing last known files"
                if result.error_message:
                    msg += f" ({result.error_message})"
                self.offline_banner.setText(msg)
                self.offline_banner.show()
                self._reconnect_timer.start()
                self._update_file_ops_ui()
            else:
                self._is_online = True
                self._sync.set_online(True)
                self.offline_banner.hide()
                self._reconnect_timer.stop()
                if result.removed:
                    self._cache.evict_removed(result.removed)
                if not self._initial_cache_sync_done:
                    self._initial_cache_sync_done = True
                    self._run_full_cache_sync()
                    return
                if sync_cache and self._run_folder_cache_sync(result.items):
                    return
                if self._run_flush_only():
                    return
            self._update_file_ops_ui()
            if not self._cache_busy:
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

        def task(sig):
            def progress(name: str, done: int, total: int) -> None:
                sig.progress.emit(name, done, total)

            self._sync.queue_upload_from_disk(local, parent_id)
            if self._is_online:
                self._sync.flush_pending(progress)
            return None

        def done(_r) -> None:
            self._reload_listing_from_store()
            if self._is_online:
                self.transfer_bar.set_idle("Upload complete")
            else:
                self.transfer_bar.set_idle("Queued offline")

        label = "Uploading…" if self._is_online else "Queuing offline…"
        signals = self._track(
            run_in_background(task, done, self._show_error, label=f"upload:{local.name}")
        )
        self.transfer_bar.set_idle(label)
        signals.progress.connect(
            lambda name, done, total: self.transfer_bar.set_progress(
                f"{label} {name}", done, total
            )
        )

    def _on_keep_offline(self) -> None:
        items = self.file_view.selected_items()
        if not items:
            QMessageBox.information(
                self,
                "Keep offline",
                "Select one or more files or folders to cache for offline use.",
            )
            return

        def task(sig):
            def progress(_name: str, done: int, total: int) -> None:
                sig.progress.emit(_name, done, total)

            self._cache.pin_items(items, progress)
            self._sync.refresh_watched_paths()
            return None

        self._run_cache_task(task, "Caching…", refresh_after=True)

    def _on_remove_from_cache(self) -> None:
        items = self.file_view.selected_items()
        if not items:
            QMessageBox.information(
                self,
                "Remove from cache",
                "Select cached files or folders to remove from offline cache.",
            )
            return

        def task(_sig):
            self._cache.unpin_items(items)
            return None

        self._run_cache_task(task, "Removing from cache…", refresh_after=True)

    def _on_sync_cache(self) -> None:
        self._run_full_cache_sync()

    def _run_full_cache_sync(self) -> None:
        def task(sig):
            def progress(name: str, done: int, total: int) -> None:
                sig.progress.emit(name, done, total)

            self._cache.sync_full(progress)
            self._sync.refresh_watched_paths()
            return None

        self._run_cache_task(
            task,
            "Syncing cache…",
            refresh_after=True,
            done_idle="Cache up to date",
        )

    def _run_folder_cache_sync(self, items: list[FileRecord]) -> bool:
        pinned = [i for i in items if i.pinned]
        if not pinned:
            return False

        def task(sig):
            def progress(name: str, done: int, total: int) -> None:
                sig.progress.emit(name, done, total)

            self._cache.sync_items_in_folder(pinned, progress)
            self._sync.refresh_watched_paths()
            return None

        self._run_cache_task(task, "Updating cache…", reload_store=True, flush_after=True)
        return True

    def _run_flush_only(self) -> bool:
        if not self._is_online or self._cache_busy:
            return False
        pending = self._store.list_pending()
        if not pending:
            self._sync.refresh_watched_paths()
            return False

        def task(sig):
            def progress(name: str, done: int, total: int) -> None:
                sig.progress.emit(name, done, total)

            self._sync.flush_pending(progress)
            self._sync.refresh_watched_paths()
            return None

        self._run_cache_task(task, "Uploading changes…", reload_store=True)
        return True

    def _reload_listing_from_store(self) -> None:
        self.file_view.set_items(self._store.get_children(self._folder_id))

    def _on_cached_file_edited(self, _file_id: str) -> None:
        self._reload_listing_from_store()
        if self._is_online:
            self._run_flush_only()

    def _run_cache_task(
        self,
        task_fn,
        label: str,
        refresh_after: bool = False,
        reload_store: bool = False,
        flush_after: bool = False,
        done_idle: str = "Ready",
    ) -> None:
        if self._cache_busy:
            return
        self._cache_busy = True
        self.transfer_bar.set_idle(label)

        def done(_result) -> None:
            self._cache_busy = False
            self.transfer_bar.set_idle(done_idle)
            if refresh_after:
                self._refresh(sync_cache=False)
            elif reload_store:
                self._reload_listing_from_store()
            if flush_after:
                self._run_flush_only()

        def failed(message: str) -> None:
            self._cache_busy = False
            if message == "offline" or "offline" in message.lower():
                self._mark_offline()
                return
            self._show_error(message)

        signals = self._track(run_in_background(task_fn, done, failed, label=label))
        signals.progress.connect(
            lambda name, done, total: self.transfer_bar.set_progress(
                f"{label} {name}", done, total
            )
        )

    def _try_reconnect(self) -> None:
        if self._is_online or self._refreshing or self._cache_busy:
            return
        self._refreshing = True
        folder_id = self._folder_id

        def task(_sig):
            return self._browse.list_folder(folder_id)

        def done(result) -> None:
            self._refreshing = False
            if result.from_cache:
                return
            self.file_view.set_items(result.items)
            self._is_online = True
            self._sync.set_online(True)
            self.offline_banner.hide()
            self._reconnect_timer.stop()
            if result.removed:
                self._cache.evict_removed(result.removed)
            if self._run_folder_cache_sync(result.items):
                return
            if self._run_flush_only():
                return
            self.transfer_bar.set_idle("Ready")

        def failed(_message: str) -> None:
            self._refreshing = False

        self._track(run_in_background(task, done, failed, label=f"reconnect:{folder_id}"))

    def _mark_offline(self) -> None:
        self._is_online = False
        self._sync.set_online(False)
        self.offline_banner.setText("Offline – showing last known files")
        self.offline_banner.show()
        self.transfer_bar.set_idle("Queued offline")
        self._reload_listing_from_store()
        self._update_file_ops_ui()
        self._reconnect_timer.start()

    def _update_file_ops_ui(self) -> None:
        has_clipboard = bool(self._clipboard_items)
        self.file_view.set_paste_enabled(has_clipboard and self._is_online)
        self.file_view.set_file_ops_enabled(self._is_online)
        cut_ids: set[str] = set()
        if self._clipboard_mode == "cut" and self._clipboard_items:
            cut_ids = {item.id for item in self._clipboard_items}
        self.file_view.set_cut_ids(cut_ids)

    def _require_online_ops(self) -> bool:
        if self._is_online:
            return True
        QMessageBox.information(
            self,
            "Offline",
            "This action requires an internet connection.",
        )
        return False

    def _reject_pending_local(self, items: list[FileRecord]) -> bool:
        if any(item.id.startswith("local_") for item in items):
            QMessageBox.information(
                self,
                "Not available",
                "Some items are still uploading. Try again after sync completes.",
            )
            return True
        return False

    def _run_file_op_task(self, label: str, task_fn, on_done) -> None:
        if self._file_ops_busy:
            return
        self._file_ops_busy = True
        self.transfer_bar.set_idle(label)

        def done(result) -> None:
            self._file_ops_busy = False
            on_done(result)
            if not self._cache_busy and not self._refreshing:
                self.transfer_bar.set_idle("Ready")

        def failed(message: str) -> None:
            self._file_ops_busy = False
            self._show_error(message)

        self._track(run_in_background(task_fn, done, failed, label=label))

    def _on_copy(self) -> None:
        if not self._require_online_ops():
            return
        items = self.file_view.selected_items()
        if not items or self._reject_pending_local(items):
            return
        self._clipboard_items = list(items)
        self._clipboard_mode = "copy"
        self._update_file_ops_ui()

    def _on_cut(self) -> None:
        if not self._require_online_ops():
            return
        items = self.file_view.selected_items()
        if not items or self._reject_pending_local(items):
            return
        self._clipboard_items = list(items)
        self._clipboard_mode = "cut"
        self._update_file_ops_ui()

    def _on_paste(self) -> None:
        if not self._require_online_ops():
            return
        if not self._clipboard_items or not self._clipboard_mode:
            return
        items = self._clipboard_items
        if self._reject_pending_local(items):
            return
        dest_parent = self._folder_id
        mode = self._clipboard_mode

        def task(_sig):
            if mode == "copy":
                self._file_ops.copy_items(items, dest_parent)
            else:
                self._file_ops.move_items(items, dest_parent)
            return mode

        def done(result_mode: str) -> None:
            if result_mode == "cut":
                self._clipboard_items = None
                self._clipboard_mode = None
            self._update_file_ops_ui()
            self._refresh(sync_cache=False)

        label = "Copying…" if mode == "copy" else "Moving…"
        self._run_file_op_task(label, task, done)

    def _on_rename(self) -> None:
        if not self._require_online_ops():
            return
        items = self.file_view.selected_items()
        if len(items) != 1:
            return
        item = items[0]
        if self._reject_pending_local([item]):
            return
        new_name, ok = QInputDialog.getText(self, "Rename", "Name:", text=item.name)
        if not ok:
            return
        if new_name.strip() == item.name:
            return

        def task(_sig):
            self._file_ops.rename_item(item, new_name)

        self._run_file_op_task(
            "Renaming…",
            task,
            lambda _: self._refresh(sync_cache=False),
        )

    def _on_delete(self) -> None:
        if not self._require_online_ops():
            return
        items = self.file_view.selected_items()
        if not items or self._reject_pending_local(items):
            return
        if len(items) == 1:
            text = f'Move "{items[0].name}" to trash?'
        else:
            text = f"Move {len(items)} items to trash?"
        reply = QMessageBox.question(
            self,
            "Delete",
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def task(_sig):
            return self._file_ops.delete_items(items)

        def done(removed: list[FileRecord]) -> None:
            if removed:
                self._cache.evict_removed(removed)
            self._refresh(sync_cache=False)

        self._run_file_op_task("Deleting…", task, done)

    def _on_file_activated(self, item: FileRecord) -> None:
        stored = self._store.get_file(item.id) or item
        local = stored.local_path
        if local and Path(local).is_file():
            TransferService.open_file(Path(local))
            return
        QMessageBox.information(
            self,
            "Not cached",
            "This file is not available offline. Use Keep offline to cache it.",
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
