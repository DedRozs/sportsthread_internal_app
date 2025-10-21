from __future__ import annotations
import os
from pathlib import Path
import tempfile

from app.licensing import get_license

def test_env_variable_wins(monkeypatch):
    monkeypatch.delenv("IRONPDF_LICENSE", raising=False)
    monkeypatch.delenv("IRONPDF_LICENSE_FILE", raising=False)
    monkeypatch.setenv("IRONPDF_LICENSE", "ENV_KEY_123")
    assert get_license() == "ENV_KEY_123"

def test_env_file_second(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("IRONPDF_LICENSE", raising=False)
    lic_file = tmp_path / "k.txt"
    lic_file.write_text("FILE_KEY_456", encoding="utf-8")
    monkeypatch.setenv("IRONPDF_LICENSE_FILE", str(lic_file))
    assert get_license() == "FILE_KEY_456"

def test_project_local_third(monkeypatch, tmp_path: Path):
    # Simulate project root
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".license").write_text("LOCAL_KEY_789", encoding="utf-8")
    monkeypatch.delenv("IRONPDF_LICENSE", raising=False)
    monkeypatch.delenv("IRONPDF_LICENSE_FILE", raising=False)
    assert get_license() == "LOCAL_KEY_789"
