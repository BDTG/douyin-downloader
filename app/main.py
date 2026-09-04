"""Douyin Downloader standalone — Qt gọi thẳng stack Python local.

Chạy:  python -m app --stack-dir D:/ThucTap/douyin-docker
Mở app là tự bật stack (api:8000/gallery:8001/web:8080), thoát app là dừng.
Gallery/Tracker/Files vẫn là web — mở bằng trình duyệt từ trong app.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow

from .localapi import LocalStack
from .qss import build_qss
from .views.douyin import DouyinPage


class Win(QMainWindow):
    def __init__(self, stack: LocalStack):
        super().__init__()
        self.stack = stack
        self.setWindowTitle("Douyin Downloader")
        self.resize(1100, 850)
        self.setCentralWidget(DouyinPage(stack))

    def closeEvent(self, ev):
        try:
            self.stack.stop()
        except Exception:
            pass
        super().closeEvent(ev)


def build_app(stack_dir: str):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(build_qss())
    stack = LocalStack(stack_dir)
    stack.start()
    win = Win(stack)
    return app, win, stack


def _default_stack() -> str:
    here = Path(__file__).resolve()
    cands = [here.parents[1] / "engine", Path("D:/ThucTap/douyin-docker")]
    for c in cands:
        if (c / "api").is_dir():
            return str(c)
    return str(cands[0])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Douyin Downloader (standalone)")
    ap.add_argument("--stack-dir", default=_default_stack())
    args = ap.parse_args(argv)
    if not Path(args.stack_dir).is_dir():
        print(f"khong thay stack dir: {args.stack_dir}", file=sys.stderr)
        return 2
    app, win, stack = build_app(args.stack_dir)
    win.show()
    rc = app.exec()
    try:
        stack.stop()
    except Exception:
        pass
    return rc


def _fatal_guard(argv) -> int:
    try:
        return main(argv)
    except Exception as exc:
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            a = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "Douyin Downloader", str(exc))
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
