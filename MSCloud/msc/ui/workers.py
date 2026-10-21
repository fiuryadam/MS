"""Background workers for network I/O."""

from __future__ import annotations

import logging
import sys
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

log = logging.getLogger(__name__)
_pool = QThreadPool.globalInstance()


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(str, int, int)


class _Runnable(QRunnable):
    def __init__(self, fn: Callable[[], Any], signals: WorkerSignals, label: str) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._fn = fn
        self._signals = signals
        self._label = label

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:
            from msc.services.sync import OfflineSyncError

            if isinstance(exc, OfflineSyncError):
                log.warning("Worker offline during %s", self._label)
            else:
                log.exception("Worker failed: %s", self._label)
            try:
                self._signals.error.emit(str(exc))
            except Exception:
                log.exception("Could not emit worker error signal: %s", self._label)
            return
        try:
            self._signals.finished.emit(result)
        except Exception:
            log.exception("Could not emit worker finished signal: %s", self._label)


def run_in_background(
    fn: Callable[[WorkerSignals], Any],
    on_finished: Callable[[Any], None],
    on_error: Callable[[str], None],
    label: str = "task",
) -> WorkerSignals:
    signals = WorkerSignals()

    def _finished(result: Any) -> None:
        try:
            on_finished(result)
        except Exception:
            log.exception("finished callback failed: %s", label)

    def _error(message: str) -> None:
        try:
            on_error(message)
        except Exception:
            log.exception("error callback failed: %s", label)

    signals.finished.connect(_finished)
    signals.error.connect(_error)
    _pool.start(_Runnable(lambda: fn(signals), signals, label))
    return signals
