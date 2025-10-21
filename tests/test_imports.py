def test_can_import_main_window():
    # This catches path/package mistakes (missing __init__.py, wrong file paths).
    import importlib

    mod = importlib.import_module("app.ui.main_window")
    assert hasattr(mod, "MainWindow"), "MainWindow class not found in app.ui.main_window"


def test_app_entrypoint_parses():
    # Ensures app.main can be imported (no top-level side effects).
    mod = __import__("app.main", fromlist=["main"])
    assert callable(getattr(mod, "main", None)), "main() not found in app.main"
