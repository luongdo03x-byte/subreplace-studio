from __future__ import annotations

try:
    import PySide6  # noqa: F401
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True


class DesktopDependencyError(RuntimeError):
    pass


def require_pyside6() -> None:
    if not PYSIDE6_AVAILABLE:
        raise DesktopDependencyError("PySide6 is required for the desktop UI; install subreplace-studio[desktop]")
