from __future__ import annotations

from app.ui.qt_compat import DesktopDependencyError, PYSIDE6_AVAILABLE


def run_app() -> int:
    if not PYSIDE6_AVAILABLE:
        raise DesktopDependencyError("PySide6 is required to run SubReplace Studio Next; install subreplace-studio-next[desktop]")
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("SubReplace")
    app.setApplicationName("SubReplace Studio Next")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_app())
