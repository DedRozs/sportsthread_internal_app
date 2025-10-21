# Purpose: Current behavior factored into an engine class.


from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWebEngineWidgets import QWebEngineView


class WebEnginePdf:
    def render_pdf(self, html: str, out_path: Path) -> bool:
        finished: list[bool] = []
        try:
            view = QWebEngineView()
            page = view.page()


            def on_pdf_finished(path: str, ok: bool) -> None:
                finished.append(bool(ok))


            def on_loaded(ok: bool) -> None:
                if not ok:
                    finished.append(False)
                    return
                page.pdfPrintingFinished.connect(on_pdf_finished)
                page.printToPdf(str(out_path))


            view.loadFinished.connect(on_loaded)
            view.setHtml(html)


            # Process events until finished or short timeout
            from PySide6.QtWidgets import QApplication
            import time
            deadline = time.time() + 30
            while not finished and time.time() < deadline:
                QApplication.processEvents()
            return bool(finished and finished[-1])
        except Exception:
            return False




__all__ = ["WebEnginePdf"]