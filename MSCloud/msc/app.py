from __future__ import annotations
import logging
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget
from msc.auth.oauth import get_credentials, login_interactive
from msc.db.store import SqliteStore
from msc.drive.client import DriveClient
from msc.logging_setup import install_qt_logging, setup_logging
from msc.paths import database_path
from msc.ui.login_view import LoginView
from msc.ui.main_window import MainWindow
from msc.ui.workers import run_in_background

log = logging.getLogger(__name__)


def _load_styles(app: QApplication) -> None:
    qss_path = Path(__file__).parent / "ui" / "style.qss"
    if qss_path.is_file():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
    else:
        log.warning("Stylesheet missing: %s", qss_path)


class AppShell(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MSCloud")
        self._store = SqliteStore(database_path())
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)
        self._main: MainWindow | None = None
        self._login_signals = None
        self._login = LoginView()
        self._login.sign_in_requested.connect(self._do_login)
        self._stack.addWidget(self._login)

        try:
            creds = get_credentials()
        except Exception:
            log.exception("Failed to load credentials")
            creds = None
        if creds:
            self._open_main(creds)
        else:
            self._show_login_page()

    def _show_login_page(self) -> None:
        if self._main is not None:
            self._stack.removeWidget(self._main)
            self._main.deleteLater()
            self._main = None
        self._stack.setCurrentWidget(self._login)
        self.resize(480, 360)
        self.show()
        self.raise_()
        self.activateWindow()

    def _do_login(self) -> None:
        self._login.set_busy(True)
        self._login_signals = run_in_background(
            lambda _sig: login_interactive(),
            self._on_login_ok,
            self._on_login_fail,
            label="oauth",
        )

    def _on_login_ok(self, creds) -> None:
        self._login.set_busy(False)
        self._login_signals = None
        QTimer.singleShot(0, lambda: self._open_main(creds))

    def _on_login_fail(self, message: str) -> None:
        log.error("OAuth callback: fail %s", message)
        self._login.set_busy(False)
        self._login_signals = None
        lowered = message.lower()
        if "missing" in lowered or "credentials" in lowered:
            self._login.show_error(message)
        else:
            self._login.show_error(f"Sign-in failed: {message}")
        self.show()
        self.raise_()
        self.activateWindow()

    def _open_main(self, creds) -> None:
        try:
            if self._main is not None:
                self._stack.removeWidget(self._main)
                self._main.deleteLater()
                self._main = None
            drive = DriveClient(creds)
            self._main = MainWindow(drive, self._store, self._on_logout)
            self._stack.addWidget(self._main)
            self._stack.setCurrentWidget(self._main)
            self.resize(1100, 700)
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception as exc:
            log.exception("Failed to open main window")
            self._login.show_error(f"Could not open Drive: {exc}")
            self._show_login_page()

    def _on_logout(self) -> None:
        self._show_login_page()

    def closeEvent(self, event) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()
        super().closeEvent(event)


def run() -> int:
    setup_logging()
    app = QApplication([])
    app.setApplicationName("MSCloud")
    app.setOrganizationName("MSCloud")
    install_qt_logging()
    _load_styles(app)
    shell = AppShell()
    shell.show()
    return app.exec()
