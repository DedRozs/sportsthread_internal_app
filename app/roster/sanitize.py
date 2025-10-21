import re
from pathlib import Path

_SANITIZE = re.compile(r"[^A-Za-z0-9._-]+")
_MULTI_UNDERS = re.compile(r"_+")

def pdf_filename(team_name: str, team_id: str | int) -> str:
    base = f"{team_name}_{team_id}".replace(" ", "_")
    base = _SANITIZE.sub("_", base)
    base = _MULTI_UNDERS.sub("_", base).strip("_")
    name = (base[:116]) if len(base) > 116 else base  # keep room for ".pdf"
    return f"{name}.pdf"

def ensure_unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    i = 1
    while True:
        cand = path.with_name(f"{stem}-{i}{suffix}")
        if not cand.exists():
            return cand
        i += 1

__all__ = ["pdf_filename", "ensure_unique"]