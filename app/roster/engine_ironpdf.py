# Purpose: IronPDF engine wrapper (loaded opportunistically by factory). Avoids import if lib/license absent.


from __future__ import annotations
from pathlib import Path


class IronPdfEngine:
    def __init__(self) -> None:
        # Import locally so environments without IronPDF don't break imports.
        from ironpdf import ChromePdfRenderer # type: ignore
        from app.licensing import get_license # env-based loader lives at project root


        key = get_license()
        if key:
            # IronPDF auto-picks up license via env variable as well; we also set programmatically.
            from ironpdf import License
            License.LicenseKey = key
        self._renderer = ChromePdfRenderer()


        # --- Lock print media + paper config once (spec: 0.5" margins) ---
        # Defaults: Letter; override with PDF_PAPER=A4 if needed.
        try:
            import os as _os
            # IronPDF enums
            from ironpdf import PdfPaperSize, PdfCssMediaType  # type: ignore
            ro = self._renderer.RenderingOptions
            # Paper size
            paper_env = (_os.getenv("PDF_PAPER", "Letter") or "").strip().lower()
            ro.PaperSize = PdfPaperSize.A4 if paper_env == "a4" else PdfPaperSize.Letter
            # Margins: 0.5 inch = 12.7 mm
            mm = 12.7
            ro.MarginTop = mm
            ro.MarginBottom = mm
            ro.MarginLeft = mm
            ro.MarginRight = mm
            # Use print CSS rules
            ro.CssMediaType = PdfCssMediaType.Print
        except Exception:
            # If the wrapper/enums differ on a given build, keep going with IronPDF defaults.
            pass

        # Disable JavaScript by default (safer & faster for our static HTML).
        # Override with PDF_ENABLE_JS=1 if needed for a partner layout.
        try:
            import os as _os
            _js_env = (_os.getenv("PDF_ENABLE_JS", "0") or "").strip().lower()
            _enable_js = _js_env in ("1", "true", "yes", "on")
            # IronPDF exposes RenderingOptions.EnableJavaScript
            self._renderer.RenderingOptions.EnableJavaScript = _enable_js
        except Exception:
            # Don’t block initialization if an option isn’t available on a given build.
            pass

        # Optional warm-up: render a tiny HTML once to spin up Chrome runtime & caches.
        # Controlled by env PDF_WARMUP (default on). Set PDF_WARMUP=0 to disable.
        try:
            import os as _os
            if _os.getenv("PDF_WARMUP", "1") != "0":
                _ = self._renderer.RenderHtmlAsPdf("<html><body><small>warmup</small></body></html>")
        except Exception:
            # Warm-up failures should not block the app; continue with cold renderer.
            pass


    def render_pdf(self, html: str, out_path: Path) -> bool:
        # Render and write in one step
        pdf = self._renderer.RenderHtmlAsPdf(html)
        pdf.SaveAs(str(out_path))
        return out_path.exists() and out_path.stat().st_size > 0


__all__ = ["IronPdfEngine"]