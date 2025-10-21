# Purpose: Define the pluggable interface + factory to choose IronPDF (if licensed) or WebEngine.


from __future__ import annotations
from pathlib import Path
from typing import Protocol


class ExportEngine(Protocol):
    def render_pdf(self, html: str, out_path: Path) -> bool: # returns True on success
        return




def _try_ironpdf() -> ExportEngine | None:
    try:
        # Import lazily to avoid hard dependency when IronPDF isn't installed.
        from .engine_ironpdf import IronPdfEngine  # type: ignore
        # Quick import of ironpdf to verify native deps are present
        import importlib
        importlib.import_module("ironpdf")
    except Exception:
        return None
    try:
        eng = IronPdfEngine()
        return eng
    except Exception:
        # Could not initialize (e.g., license missing or native download failed).
        return None

def _try_webengine() -> ExportEngine | None:
    try:
        from .engine_web import WebEnginePdf  # type: ignore
        return WebEnginePdf()
    except Exception:
        return None

def get_export_engine() -> ExportEngine:
    """Return the best available engine (IronPDF if available & licensed)."""
    eng = _try_ironpdf()
    if eng is None:
        eng = _try_webengine()
    if eng is None:
        # Make failure explicit so callers don't get a NoneType later.
        raise RuntimeError("No PDF engine available (IronPDF/WebEngine init failed)")
    return eng




__all__ = ["ExportEngine", "get_export_engine"]