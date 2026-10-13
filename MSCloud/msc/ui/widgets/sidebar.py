from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from msc.ui.widgets.transfer_bar import TransferBar


class Sidebar(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setMinimumWidth(200)
        self.setMaximumWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(8)

        title = QLabel("MSCloud")
        title.setObjectName("sidebarTitle")
        layout.addWidget(title)

        self.drive_btn = QLabel("My Drive")
        self.drive_btn.setObjectName("sidebarItemActive")
        layout.addWidget(self.drive_btn)

        layout.addStretch()

        self.transfer_bar = TransferBar()
        layout.addWidget(self.transfer_bar)
