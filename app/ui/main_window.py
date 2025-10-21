from __future__ import annotations

import json
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QLineEdit,
    QInputDialog,
    QStackedLayout,
    QProgressBar,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
import time  # for simple ETA during export

# Internal modules (package layout per PROJECT_STRUCTURE.txt)
from app.roster.sort_and_group import group_and_sort
from app.roster.render_html import render_team
from app.roster.sanitize import pdf_filename, ensure_unique
from app.roster.messages import EMPTY_ROSTER, DB_LOST, PDF_ENGINE_FAILED, DISK_FULL
from app.DBFunctions import fetch_roster
from app.roster.export_engine import get_export_engine, ExportEngine

# Optional import: newer DBFunctions exposes fetch_partner_logo(event_id)
try:  # pragma: no cover - optional feature
    from app.DBFunctions import fetch_partner_logo  # type: ignore
except Exception:  # pragma: no cover - keep app working without it
    fetch_partner_logo = None  # type: ignore


class MainWindow(QMainWindow):
    """Main UI for building and previewing roster PDFs.

    Design goals:
    - Bootstrap styling visible in-preview: uses QWebEngineView instead of QTextEdit.
    - Deterministic preview: always previews the first Team_ID (ascending) in memory.
    - Safe defaults: guards for empty data, disk errors, and DB connectivity.
    """

    BRAND_PRIMARY = "#e44115"  # Sports Thread primary brand color

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Sports Thread • Roster PDF Generator")
        self.resize(1120, 760)

        # Data currently loaded in memory (flat rows from DB)
        self._rows: List[Dict[str, Any]] = []

        # Partner branding (DB URL preferred; optional manual file override)
        self._partner_logo_url: Optional[str] = None
        self._partner_logo_path: Optional[Path] = None

        root = QWidget(self)
        self.setCentralWidget(root)

        v = QVBoxLayout(root)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        # Apply brand styling early so subsequent widgets pick it up
        self._apply_styles()

        # Header
        header = QLabel("<b>Roster PDF Generator</b>")
        header.setTextFormat(Qt.RichText)
        sub = QLabel("Load data, preview a single team, then export PDFs.")
        sub.setProperty("st-subtle", True)

        v.addWidget(header)
        v.addWidget(sub)

        v.addWidget(header)
        v.addWidget(sub)

        # Top-right export progress (above buttons)
        status_row = QHBoxLayout()
        status_row.addStretch(1)
        self.export_status = QLabel("Ready")
        self.export_status.setAlignment(Qt.AlignRight)
        self.export_progress = QProgressBar()
        self.export_progress.setFixedWidth(220)
        self.export_progress.setTextVisible(True)
        self.export_progress.setRange(0, 1)  # hidden/idle by default
        self.export_progress.setValue(0)
        status_box = QVBoxLayout()
        status_box.setSpacing(4)
        status_box.addWidget(self.export_status)
        status_box.addWidget(self.export_progress)
        status_row.addLayout(status_box)
        v.addLayout(status_row)

        # Toolbar
        bar = QHBoxLayout()
        self.event_input = QLineEdit()
        self.event_input.setPlaceholderText("Event ID (for DB)")
        self.team_input = QLineEdit()
        self.team_input.setPlaceholderText("Optional Team ID filter")

        btn_load_db = QPushButton("Load Event Data")
        btn_load_db.clicked.connect(self.on_load_db)

        btn_choose_logo = QPushButton("Choose Partner Logo…")
        btn_choose_logo.clicked.connect(self.on_choose_logo)

        btn_preview = QPushButton("Preview")
        btn_preview.clicked.connect(self.on_preview)

        btn_export = QPushButton("Export PDFs…")
        btn_export.clicked.connect(self.on_export)

        for w in (
            QLabel("Event:"),
            self.event_input,
            QLabel("Team:"),
            self.team_input,
            btn_load_db,
            btn_choose_logo,
            btn_preview,
            btn_export,
        ):
            bar.addWidget(w)
        bar.addStretch(1)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)

        # Wrap the preview in a stacked container so we can show a loading overlay
        self.preview_container = QWidget(self)
        self.preview_stack = QStackedLayout(self.preview_container)
        self.preview_stack.setContentsMargins(0, 0, 0, 0)

        self.preview = QWebEngineView(self.preview_container)
        self.preview.setMinimumHeight(420)
        self.preview_stack.addWidget(self.preview)  # index 0

        # Build loading overlay (index 1)
        self.loading_overlay = self._make_loading_overlay()
        self.preview_stack.addWidget(self.loading_overlay)

        # Wire up WebEngine load signals to drive progress UI
        self.preview.loadStarted.connect(self._on_load_started)
        self.preview.loadProgress.connect(self._on_load_progress)
        self.preview.loadFinished.connect(self._on_load_finished)

        v.addLayout(bar)
        v.addWidget(line)
        v.addWidget(self.preview_container, 1)
        self.preview_stack.setCurrentWidget(self.preview)

    # ---- Export progress helpers ---------------------------------------
    def _export_progress_start(self, total: int) -> None:
        """Initialize the top-right progress UI for a run of `total` items."""
        # Determinate bar 0..total
        self.export_progress.setRange(0, max(1, total))
        self.export_progress.setValue(0)
        self._export_total = total
        self._export_started_at = time.monotonic()
        self.export_status.setText(f"Exporting… 0/{total}")

    def _export_progress_update(self, done: int) -> None:
        """Update bar + ETA based on how many items are done (1-based)."""
        self.export_progress.setValue(done)
        # Simple moving ETA based on average per item so far
        elapsed = max(0.0, time.monotonic() - getattr(self, "_export_started_at", time.monotonic()))
        avg = elapsed / max(1, done)
        remaining = max(0.0, (getattr(self, "_export_total", done) - done) * avg)
        mm = int(remaining // 60)
        ss = int(remaining % 60)
        self.export_status.setText(f"Exporting… {done}/{getattr(self, '_export_total', done)}  (~{mm:02d}:{ss:02d} left)")
        # Keep UI responsive
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

    def _export_progress_finish(self, ok_count: int, out_dir: str) -> None:
        """Show completion state and leave a short summary."""
        self.export_progress.setValue(self.export_progress.maximum())
        self.export_status.setText(f"Done • {ok_count} file(s) saved to {out_dir}")

    # ---- Styling ---------------------------------------------------------
    def _apply_styles(self) -> None:
        # Keep it minimal; most styling should come from Bootstrap in HTML preview.
        # This stylesheet just brands the Qt chrome.
        self.setStyleSheet(
            f"""
            QWidget {{ font-size: 14px; }}
            QPushButton {{
                background: {self.BRAND_PRIMARY};
                color: white;
                border: none; padding: 8px 12px; border-radius: 8px;
            }}
            QPushButton:hover {{ background: #f04a1f; }}
            QPushButton:pressed {{ background: #c73a12; }}
            QLineEdit {{ padding: 6px 8px; border: 1px solid #ddd; border-radius: 6px; min-width: 120px; }}
            QLabel[st-subtle="true"] {{ color: #6b7280; }}
            /* Loading overlay styling */
            #st-loading {{
                background: rgba(255,255,255,0.9);
            }}
            #st-loading QLabel#title {{
                font-weight: 700;
                font-size: 15px;
                margin-bottom: 8px;
            }}
            """
        )

    # ---- Loading overlay & signals --------------------------------------
    def _make_loading_overlay(self) -> QWidget:
        """Create a centered loading panel with message + progress bar."""
        panel = QWidget(self.preview_container)
        panel.setObjectName("st-loading")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("Loading preview…", panel)
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        desc = QLabel("Please wait while we prepare your preview.", panel)
        desc.setAlignment(Qt.AlignCenter)
        desc.setProperty("st-subtle", True)
        bar = QProgressBar(panel)
        bar.setMinimumWidth(320)
        bar.setTextVisible(True)
        # Save handles for later updates
        self._load_title = title
        self._load_desc = desc
        self._load_bar = bar
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(bar)
        return panel

    def _show_loading(self, title: str, desc: str = "", determinate: bool = False) -> None:
        """Show loading overlay. If determinate, the bar goes 0–100; else it's indeterminate."""
        self._load_title.setText(title)
        self._load_desc.setText(desc)
        if determinate:
            self._load_bar.setRange(0, 100)
            self._load_bar.setValue(0)
        else:
            # Indeterminate (busy) animation
            self._load_bar.setRange(0, 0)
        self.preview_stack.setCurrentWidget(self.loading_overlay)

    def _hide_loading(self) -> None:
        self.preview_stack.setCurrentWidget(self.preview)

    def _on_load_started(self) -> None:
        # HTML has started loading -> determinate progress
        self._show_loading("Loading preview…", "Applying styles and layout.", determinate=True)

    def _on_load_progress(self, pct: int) -> None:
        # Only meaningful if bar is determinate
        if self._load_bar.minimum() == 0 and self._load_bar.maximum() == 100:
            self._load_bar.setValue(max(0, min(100, int(pct))))

    def _on_load_finished(self, ok: bool) -> None:
        # Hide on success or failure; errors are still surfaced elsewhere if needed
        self._hide_loading()

    # ---- Actions ---------------------------------------------------------
    def on_choose_logo(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Partner Logo",
            str(Path.cwd()),
            "Images (*.png *.jpg *.jpeg *.svg)",
        )
        if path_str:
            self._partner_logo_path = Path(path_str)
            QMessageBox.information(self, "Logo set", f"Using partner logo:\n{path_str}")

    def _prompt_int(self, title: str, label: str, default: int = 0, minimum: int = 0) -> Optional[int]:
        # Use positional args to avoid binding keyword mismatch on some PySide builds.
        val, ok = QInputDialog.getInt(self, title, label, default, minimum, 2_147_483_647, 1)
        return val if ok else None

    def on_load_db(self) -> None:
        # Prefer typed entries if present; otherwise prompt.
        ev_text = self.event_input.text().strip()
        event_id: Optional[int] = int(ev_text) if ev_text.isdigit() else None
        if event_id is None:
            event_id = self._prompt_int("Load From Database", "Enter Event ID:", 0, 0)
        if event_id is None:
            return

        team_text = self.team_input.text().strip()
        team_id: Optional[int] = int(team_text) if team_text.isdigit() else None
        if team_id is None:
            # Optional prompt for team id
            team_id = self._prompt_int("(Optional) Team Filter", "Team ID (blank = all):", 0, 0)
            if team_id == 0:
                team_id = None

        try:
            # Show an indeterminate loading state while the blocking DB call runs
            self._show_loading("Fetching data…", f"Event {event_id} roster from database.", determinate=False)
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            # Roster rows
            rows = fetch_roster(event_id=event_id, team_id=team_id)
            # Partner logo URL (DB source of truth) — only if helper is available
            if fetch_partner_logo:
                try:
                    self._partner_logo_url = fetch_partner_logo(event_id) or None  # type: ignore[arg-type]
                except Exception:
                    self._partner_logo_url = None
        except Exception:
            self._hide_loading()
            QMessageBox.critical(self, "Database error", DB_LOST)
            return
        if not rows:
            self._hide_loading()
            QMessageBox.information(self, "No data", "No rows returned for that selection.")
            return
        # Store rows and immediately refresh the preview so the user sees results
        # without needing to click the Preview button.
        self._rows = rows
        # Auto-update preview (renders the first team deterministically)
        try:
            self.on_preview()
        except Exception:
            # If preview fails, keep going—user can still export or try again.
            pass
        finally:
            self._hide_loading()

        QMessageBox.information(
            self,
            "DB loaded",
            f"Loaded {len(rows)} rows for Event {event_id}{' (team '+str(team_id)+')' if team_id else ''}.",
        )

    def _render_html(self, team: Dict[str, Any]) -> str:
        """Call render_team with best-available partner logo hints.
        Falls back gracefully if the renderer doesn't support the new kwargs.
        """

        # Adapt structure: group_and_sort() puts core fields under team["meta"].
        # Our renderer may expect some at the top level, so flatten a few safely.
        tmeta = (team.get("meta") or {})
        adapted: Dict[str, Any] = dict(team)
        for k in ("Team_Name", "Team_ID", "Division", "Event_Name"):
            if k not in adapted and k in tmeta:
                adapted[k] = tmeta[k]

        # Prefer passing both URL/path for partner logo, and the selected coach if the renderer supports it
        try:
            sig = inspect.signature(render_team)
            kwargs: Dict[str, Any] = {}
            if "partner_logo_url" in sig.parameters:
                kwargs["partner_logo_url"] = self._partner_logo_url
            if "partner_logo_path" in sig.parameters:
                kwargs["partner_logo_path"] = self._partner_logo_path
            # Always pass footer logo when supported (defaults to bundled ST logo).
            if "footer_logo_src" in sig.parameters:
                try:
                    # Resolve bundled logo at repo root and inline as data URI.
                    from pathlib import Path as _P
                    from app.roster.render_html import _data_uri_from_path as _data  # reuse helper
                    # project root = app/ui/..../../../
                    _root = _P(__file__).resolve().parents[3]
                    _logo_path = _root / "sportsthread_logo.png"
                    _di = _data(_logo_path) if _logo_path.exists() else None
                    kwargs["footer_logo_src"] = _di
                except Exception:
                    # If anything goes wrong, renderer will still try its own default.
                    pass          
            # If renderer accepts a `coach` argument, pass the coach row selected by group_and_sort()
            if "coach" in sig.parameters and isinstance(team.get("coach"), dict):
                kwargs["coach"] = team["coach"]  # contains Name/Phone/Email from SQL
            if kwargs:
                return render_team(adapted, **kwargs)  # type: ignore[misc]
        except Exception:
            pass
        # Fallback to legacy signature: render_team(team)
        return render_team(adapted)

    def on_preview(self) -> None:
        if not self._rows:
            QMessageBox.information(self, "No data", "Load a event data first.")
            return
        teams = group_and_sort(self._rows)
        if not teams:
            QMessageBox.information(self, "No teams", "No teams found in data.")
            return
        # Deterministic first team for preview
        first_tid = sorted(teams.keys())[0]
        first_team = teams[first_tid]
        if not first_team["athletes"]:
            QMessageBox.information(self, "Empty roster", EMPTY_ROSTER)
            return
        # Show determinate overlay will flip on via loadStarted once setHtml hits
        html = self._render_html(first_team)
        self.preview.setHtml(html)

    def on_export(self) -> None:
        if not self._rows:
            QMessageBox.information(self, "No data", "Load event data first.")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Choose output folder", str(Path.cwd()))
        if not out_dir:
            return
        out_base = Path(out_dir)


        teams = group_and_sort(self._rows)
        export_queue = [t for t in teams.values() if t.get("athletes")]
        if not export_queue:
            QMessageBox.information(self, "Nothing to export", "All teams have empty rosters.")
            return


        # progress init (use helper with ETA)
        total = len(export_queue)
        self.export_progress.setVisible(True)
        self.export_status.setVisible(True)
        self._export_progress_start(total)

        # Decide if we can use parallel IronPDF (safe) or must stay serial (WebEngine).
        can_parallel = False
        try:
            import importlib
            importlib.import_module("ironpdf")
            # If IronPDF is importable, we'll create one renderer per worker thread.
            can_parallel = True
        except Exception:
            can_parallel = False

        ok_count = 0

        if not can_parallel:
            # Fallback: keep current serial behavior using the cached WebEngine/Iron engine.
            engine = self._get_engine()
            for idx, team in enumerate(export_queue, 1):
                html = self._render_html(team)
                meta = team.get("meta") or {}
                try:
                    team_name = meta["Team_Name"]; team_id = meta["Team_ID"]
                except KeyError:
                    QMessageBox.warning(self, "Export error", "Missing Team_Name/Team_ID for a team; skipping.")
                    self._export_progress_update(idx); continue
                out_path = ensure_unique(out_base / pdf_filename(str(team_name), str(team_id)))
                try:
                    ok = engine.render_pdf(html, out_path)
                except Exception:
                    QMessageBox.warning(self, "PDF engine error", PDF_ENGINE_FAILED); ok = False
                ok_count += int(bool(ok))
                self._export_progress_update(idx)
        else:
            # Parallel IronPDF path: create a fresh Iron renderer per worker.
            # NOTE: WebEngine is not thread-safe off the GUI thread; we never parallelize it.
            from app.roster.engine_ironpdf import IronPdfEngine  # type: ignore

            def _job(payload: dict) -> bool:
                """Worker: build its own renderer (warm-up happens in __init__) and render."""
                eng = IronPdfEngine()
                try:
                    return bool(eng.render_pdf(payload["html"], payload["out_path"]))
                except Exception:
                    return False

            # Prepare all payloads up front (HTML + unique path) on the UI thread.
            tasks: list[dict] = []
            for team in export_queue:
                meta = team.get("meta") or {}
                try:
                    team_name = meta["Team_Name"]; team_id = meta["Team_ID"]
                except KeyError:
                    # Skip silently; progress will still tick as we only submit valid tasks.
                    continue
                html = self._render_html(team)
                out_path = ensure_unique(out_base / pdf_filename(str(team_name), str(team_id)))
                tasks.append({"html": html, "out_path": out_path})

            # Fire off with 5 workers.
            done_so_far = 0
            with ThreadPoolExecutor(max_workers=5, thread_name_prefix="pdf") as pool:
                futures = [pool.submit(_job, t) for t in tasks]
                for fut in as_completed(futures):
                    ok_count += int(bool(fut.result()))
                    done_so_far += 1
                    self._export_progress_update(done_so_far)
 

        # finish progress UI
        self._export_progress_finish(ok_count, str(out_base))
        QMessageBox.information(self, "Done", f"Exported {ok_count} file(s) to {out_base}.")


    # ---- Engine selection -------------------------------------------------
    def _get_engine(self) -> ExportEngine:
        """
        Pick the best available PDF engine (IronPDF if licensed, else WebEngine).
        Cached per-window to avoid re-initting on every file.
        """
        if not hasattr(self, "_pdf_engine"):
            self._pdf_engine = get_export_engine()
            # Heads-up: WebEngine PDF may not repeat table headers across pages.
            try:
                if self._pdf_engine.__class__.__name__ == "WebEnginePdf" and not getattr(self, "_warned_engine", False):
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.information(
                        self,
                        "Note about PDF headers",
                        "Using the built-in WebEngine for export. Some browsers do not repeat table headers on each page. "
                        "For perfect header/masthead repetition, ensure IronPDF is installed and licensed."
                    )
                    self._warned_engine = True
            except Exception:
                pass
        return self._pdf_engine  # type: ignore[attr-defined]


    # ---- Helpers ---------------------------------------------------------
    def _render_pdf(self, html: str, out_path: Path) -> bool:
        """Best-effort HTML→PDF via an offscreen QWebEngineView.

        Returns True when a PDF file is written, False on failure.
        """
        finished: list[bool] = []  # poor-man's Future[bool]
        try:
            view = QWebEngineView()
            page = view.page()

            def on_pdf_finished(path: str, ok: bool) -> None:
                finished.append(bool(ok))

            def on_loaded(ok: bool) -> None:
                if not ok:
                    finished.append(False)
                    return
                # Connect the finished signal, then fire the file-path overload (no callback)
                page.pdfPrintingFinished.connect(on_pdf_finished)
                page.printToPdf(str(out_path))

            # Load HTML, then print once ready
            view.loadFinished.connect(on_loaded)
            view.setHtml(html)

            # Block the UI with a busy cursor while the async job runs
            self.setCursor(Qt.BusyCursor)
            from PySide6.QtWidgets import QApplication
            import time
            deadline = time.time() + 30  # 30s guardrail
            while not finished and time.time() < deadline:
                QApplication.processEvents()
            self.unsetCursor()
            return bool(finished and finished[-1])
        except Exception:
            self.unsetCursor()
            QMessageBox.warning(self, "PDF engine error", PDF_ENGINE_FAILED)
            return False


__all__ = ["MainWindow"]
