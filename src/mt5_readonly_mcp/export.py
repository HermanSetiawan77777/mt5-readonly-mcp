"""CSV export confined to one folder (MT5_EXPORT_DIR).

Export tools let an assistant analyse large datasets from files instead of
pulling thousands of rows into the conversation. Because the tool arguments
come from a language model, every path is resolved and must stay inside the
export folder: absolute paths and '..' are refused.
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path

DEFAULT_EXPORT_DIR = Path.home() / "mt5-readonly-mcp" / "exports"
_UNSAFE = re.compile(r"[^A-Za-z0-9._#+-]")


def export_root() -> Path:
    configured = os.environ.get("MT5_EXPORT_DIR", "").strip()
    return Path(configured) if configured else DEFAULT_EXPORT_DIR


def safe_name(name: str) -> str:
    """Make a broker symbol safe to use in a file name."""
    return _UNSAFE.sub("_", name)


def export_path(subfolder: str, *parts: str) -> Path:
    """Path inside the export folder. ``subfolder`` is optional and relative."""
    root = export_root().resolve()
    target = root.joinpath((subfolder or "").strip(), *parts).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"out_dir must be a relative folder inside the export folder ({root}).")
    return target


def write_csv(path: Path, header: list[str], rows: list[list]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    return {"path": str(path), "rows": len(rows), "bytes": path.stat().st_size}
