"""
Main entrypoint for the Sports Thread Internal App.
- Loads configuration securely (supports encrypted .env.enc + OS keychain; falls back to .env)
- Starts the Qt UI (MainWindow)
- Keeps logs clean (no secrets) and shows actionable errors to the user

This file is designed to be PyInstaller‑friendly (guarded main, safe Qt flags).
"""
from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

# --- Early, minimal logging (avoid secrets) ---------------------------------
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger("app.main")

# --- Prefer secure env bootstrap; fall back to dotenv ------------------------
# secure_env is optional (added by our encrypted env flow). If not present, we
# still support plain .env via python-dotenv so dev runs remain simple.

def _load_env(app_dir: Path) -> None:
    """Load environment from .env or decrypt .env.enc if present.
    This function is safe to run multiple times.
    """
    try:
        from app.security.secure_env import ensure_env  # type: ignore
        try:
            from app.ui.passphrase_prompt import ask_passphrase  # type: ignore
        except Exception:
            # Headless fallback: prompt in terminal
            def ask_passphrase(error: str | None = None) -> str | None:  # type: ignore
                if error:
                    print(error, file=sys.stderr)
                try:
                    return input("Enter setup passphrase: ").strip() or None
                except EOFError:
                    return None
        ensure_env(app_dir, prompt_for_passphrase=ask_passphrase)
        return
    except Exception as e:
        log.debug("secure_env not available or failed: %s", e)

    # Fallback: plain dotenv lookup (project root -> CWD -> user config dir)
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(app_dir / ".env")
        load_dotenv()  # CWD
        load_dotenv(Path.home() / ".config" / "sportsthread" / ".env")
    except Exception as e:  # pragma: no cover
        log.warning("dotenv not available; continuing without .env (%s)", e)


# --- Optional: warm up IronPDF license early (non-fatal) ---------------------

def _warm_ironpdf_license() -> None:
    """Attempt to trigger IronPDF license detection early.
    Non-fatal if unavailable; keeps logs minimal.
    """
    try:
        log.info("Attempting import of IronPdf")
        # Import inside try so missing package doesn’t crash the app
        import ironpdf  # type: ignore  # noqa: F401
        log.info("IronPdf import OK")
    except Exception as e:
        log.info("IronPdf not initialized (%s)", e)


# --- Qt Application bootstrap -----------------------------------------------

def _apply_qt_attributes():
    """Set Qt attributes for better DPI/scaling behavior."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        # High DPI & consistent rendering
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception as e:  # pragma: no cover
        log.debug("Qt attributes not applied: %s", e)


def _start_qt_mainwindow():
    from PySide6.QtWidgets import QApplication, QMessageBox

    try:
        from app.ui.main_window import MainWindow  # our primary UI
    except Exception as e:
        # If imports fail, show a clear dialog and exit with error
        QMessageBox.critical(None, "Startup Error", f"Failed to load UI: {e}")
        raise

    app = QApplication(sys.argv)
    _apply_qt_attributes()

    win = MainWindow()
    win.show()
    return app.exec()


# --- Public entrypoint -------------------------------------------------------

def main() -> int:
    # Ensure frozen apps (PyInstaller/py2exe) can spawn safely on Windows
    if sys.platform.startswith("win"):
        try:
            import multiprocessing as mp
            mp.freeze_support()
        except Exception:
            pass

    app_dir = Path(__file__).resolve().parents[1]
    _load_env(app_dir)
    _warm_ironpdf_license()

    try:
        return _start_qt_mainwindow()
    except Exception as e:
        # Last‑chance logging; avoid dumping env or secrets
        log.exception("Fatal error: %s", e)
        # Best‑effort user notification if Qt is available
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Application Error", str(e))
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
