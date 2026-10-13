from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LoginView(QWidget):
    sign_in_requested = Signal()
    sign_in_finished = Signal(object)
    sign_in_failed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(16)

        title = QLabel("MSCloud")
        title.setObjectName("loginTitle")
        from PySide6.QtCore import Qt

        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        subtitle = QLabel("Google Drive client")
        subtitle.setObjectName("loginSubtitle")

        self.error_label = QLabel("")
        self.error_label.setObjectName("loginError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        self.hint_label = QLabel("")
        self.hint_label.setObjectName("loginSubtitle")
        self.hint_label.setWordWrap(True)
        self.hint_label.hide()

        self.sign_in_btn = QPushButton("Sign in with Google")
        self.sign_in_btn.setObjectName("primaryButton")
        self.sign_in_btn.setMinimumHeight(44)
        self.sign_in_btn.clicked.connect(self.sign_in_requested.emit)

        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(24)
        layout.addWidget(self.sign_in_btn)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.error_label)
        layout.addStretch()

    def show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
        self.sign_in_btn.setEnabled(True)

    def set_busy(self, busy: bool) -> None:
        self.sign_in_btn.setEnabled(not busy)
        if busy:
            self.error_label.hide()
            self.hint_label.setText("Complete sign-in in your browser, then return here.")
            self.hint_label.show()
        else:
            self.hint_label.hide()
