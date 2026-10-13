from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class BreadcrumbBar(QWidget):
    navigated = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("breadcrumbBar")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 6, 10, 6)
        self._layout.setSpacing(2)
        self._crumbs: list[tuple[str, str]] = []

    def set_path(self, crumbs: list[tuple[str, str]]) -> None:
        """crumbs: list of (folder_id, display_name)."""
        self._crumbs = crumbs
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        last = len(crumbs) - 1
        for i, (folder_id, name) in enumerate(crumbs):
            if i > 0:
                sep = QLabel("›")
                sep.setObjectName("breadcrumbSep")
                sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._layout.addWidget(sep)

            btn = QPushButton(name)
            is_current = i == last
            btn.setObjectName("breadcrumbCurrent" if is_current else "breadcrumbLink")
            btn.setFlat(True)
            if is_current:
                btn.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(
                    lambda _=False, fid=folder_id: self.navigated.emit(fid)
                )
            self._layout.addWidget(btn)

        self._layout.addStretch()
