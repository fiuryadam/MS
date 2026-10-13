from PySide6.QtWidgets import QProgressBar, QVBoxLayout, QWidget


class TransferBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("transferBar")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)
        self.set_idle("Ready")

    def set_idle(self, text: str = "Ready") -> None:
        self.progress.setValue(0)
        self.progress.setFormat(text)

    def set_progress(self, label: str, done: int, total: int) -> None:
        self.progress.setFormat("%p%")
        if total > 0:
            self.progress.setValue(min(100, int(done * 100 / total)))
        else:
            self.progress.setValue(0)
