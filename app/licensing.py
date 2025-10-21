from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Cross-platform config paths
def _platform_paths() -> list[Path]:
    paths: list[Path] = []

    # Project-local (useful for internal packaging; NOT committed)
    paths.append(Path.cwd() / ".license")

    home = Path.home()
    # Linux
    paths.append(home / ".config" / "sportsthread" / "license")
    # macOS
    paths.append(home / "Library" / "Application Support" / "SportsThread" / "license")
    # Windows
    appdata = os.getenv("APPDATA")
    if appdata:
        paths.append(Path(appdata) / "SportsThread" / "license")

    return paths

def _read_text(path: Path) -> Optional[str]:
    try:
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            return text or None
    except Exception:
        pass
    return None

def get_license() -> Optional[str]:
    """
    Order of precedence (highest first):
      1) IRONPDF_LICENSE (env)
      2) IRONPDF_LICENSE_FILE (env path)
      3) ./.license (project root)
      4) OS config paths (per platform)
    Returns the license string, or None if not found.
    """
    # 1) Direct env
    if lic := os.getenv("IRONPDF_LICENSE_KEY"):
        return lic.strip() or None

    # 2) File via env
    lic_file = os.getenv("IRONPDF_LICENSE_FILE")
    if lic_file:
        if val := _read_text(Path(lic_file)):
            return val

    # 3) 4) Files in well-known locations
    for p in _platform_paths():
        if val := _read_text(p):
            return val

    return None
