from __future__ import annotations
import atexit
import faulthandler
import logging
import sys
import threading
from pathlib import Path
from msc.paths import logs_dir

_crash_file = None


def log_path() -> Path:
    return logs_dir() / "msc.log"


def crash_log_path() -> Path:
    return logs_dir() / "crash.log"


def setup_logging() -> Path:
    global _crash_file
    path = log_path()
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s"
    )
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(logging.WARNING)
    stream_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _crash_file = open(crash_log_path(), "a", encoding="utf-8")
    faulthandler.enable(file=_crash_file, all_threads=True)

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    atexit.register(_on_exit)

    return path


def install_qt_logging() -> None:
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    log = logging.getLogger("msc.qt")

    def handler(mode, context, message: str) -> None:
        where = ""
        if context is not None and getattr(context, "file", None):
            where = f" ({context.file}:{context.line})"
        text = f"{message}{where}"
        if mode == QtMsgType.QtFatalMsg:
            log.critical(text)
        elif mode == QtMsgType.QtCriticalMsg:
            log.error(text)
        elif mode == QtMsgType.QtWarningMsg:
            log.warning(text)

    qInstallMessageHandler(handler)


def _excepthook(exc_type, exc, tb) -> None:
    logging.getLogger("msc.crash").error(
        "Uncaught exception",
        exc_info=(exc_type, exc, tb),
    )
    if sys.__excepthook__ is not _excepthook:
        sys.__excepthook__(exc_type, exc, tb)


def _thread_excepthook(args) -> None:
    logging.getLogger("msc.crash").error(
        "Uncaught thread exception in %s",
        getattr(args.thread, "name", "?"),
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def _on_exit() -> None:
    logging.shutdown()
