#!/usr/bin/env python3
"""
project_structure.py — Generate a text file with the project's directory tree.

Usage:
  python project_structure.py                 # scan current directory, write PROJECT_STRUCTURE.txt
  python project_structure.py /path/to/repo   # scan a specific path
  python project_structure.py --show-sizes    # include file sizes
  python project_structure.py --max-depth 3   # limit depth
"""

from __future__ import annotations
import argparse
import fnmatch
import os
import sys
from datetime import datetime

DEFAULT_IGNORES = [
    # VCS & tooling
    ".git", ".svn", ".hg", ".idea", ".vscode",
    # Python
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv", "env",
    # Node / web
    "node_modules", "bower_components", ".next", ".nuxt", "coverage", "dist", "build", ".parcel-cache",
    # OS cruft
    ".DS_Store", "Thumbs.db",
    # Artifacts
    "*.pyc", "*.pyo", "*.pyd", "*.log",
    # PDFs & large binaries you probably don’t want in the tree
    "*.pdf", "*.zip", "*.tar", "*.gz", "*.7z",
]

def load_gitignore(root: str) -> list[str]:
    path = os.path.join(root, ".gitignore")
    patterns: list[str] = []
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    patterns.append(line)
        except Exception:
            pass
    return patterns

def is_ignored(name: str, rel_path: str, ignore_patterns: list[str]) -> bool:
    # Match against both the base name and the posix-style relative path
    rp = rel_path.replace(os.sep, "/")
    for pat in ignore_patterns:
        # treat directory-only patterns (like "build/") as both "build" and "build/*"
        if pat.endswith("/"):
            pat = pat[:-1]
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rp, pat) or fnmatch.fnmatch(rp, f"{pat}/*"):
            return True
    return False

def format_size(bytes_: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_ < 1024:
            return f"{bytes_}{unit}"
        bytes_ //= 1024
    return f"{bytes_}TB"

def walk_tree(root: str, show_sizes: bool, max_depth: int | None, ignore_patterns: list[str]) -> list[str]:
    lines: list[str] = []
    root = os.path.abspath(root)
    prefix_stack: list[bool] = []  # tracks whether there are more siblings at each depth

    def list_dir(path: str, depth: int):
        rel = os.path.relpath(path, root)
        entries = []
        try:
            entries = sorted(os.listdir(path), key=lambda s: (not os.path.isdir(os.path.join(path, s)), s.lower()))
        except PermissionError:
            return

        # Filter ignores
        filtered = []
        for name in entries:
            rel_child = os.path.normpath(os.path.join(rel, name)) if rel != "." else name
            if is_ignored(name, rel_child, ignore_patterns):
                continue
            filtered.append(name)

        for idx, name in enumerate(filtered):
            child_path = os.path.join(path, name)
            is_dir = os.path.isdir(child_path)
            is_last = (idx == len(filtered) - 1)

            branch = "└── " if is_last else "├── "
            pipes = "".join("│   " if has_more else "    " for has_more in prefix_stack)
            size_str = ""
            if show_sizes and not is_dir:
                try:
                    size_str = f"  ({format_size(os.path.getsize(child_path))})"
                except OSError:
                    size_str = ""

            line = f"{pipes}{branch}{name}{'/' if is_dir else ''}{size_str}"
            lines.append(line)

            if is_dir and (max_depth is None or depth < max_depth):
                prefix_stack.append(not is_last)  # if not last, we keep a pipe going
                list_dir(child_path, depth + 1)
                prefix_stack.pop()

    # Header
    header = [
        f"Project structure for: {root}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    lines.extend(header)
    lines.append("")  # blank line
    lines.append(".")  # root marker
    list_dir(root, depth=1)
    return lines

def main() -> int:
    parser = argparse.ArgumentParser(description="Write a PROJECT_STRUCTURE.txt from the current directory tree.")
    parser.add_argument("path", nargs="?", default=".", help="Root directory to scan (default: current dir)")
    parser.add_argument("--show-sizes", action="store_true", help="Include file sizes")
    parser.add_argument("--max-depth", type=int, default=None, help="Limit recursion depth (directories only)")
    parser.add_argument("--output", default="PROJECT_STRUCTURE.txt", help="Output filename")
    parser.add_argument("--no-default-ignores", action="store_true", help="Do not use the built-in ignore set")
    args = parser.parse_args()

    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    ignore_patterns = [] if args.no_default_ignores else list(DEFAULT_IGNORES)
    ignore_patterns.extend(load_gitignore(root))

    lines = walk_tree(
        root=root,
        show_sizes=bool(args.show_sizes),
        max_depth=args.max_depth,
        ignore_patterns=ignore_patterns,
    )

    out_path = os.path.join(root, args.output)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as e:
        print(f"Failed to write {out_path}: {e}", file=sys.stderr)
        return 1

    print(f"Wrote {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
