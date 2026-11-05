"""Load thresholds.toml (repo config dir by default, overridable)."""

from __future__ import annotations

import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = _REPO_ROOT / "config" / "thresholds.toml"


def load(path: str | Path | None = None) -> dict:
    p = Path(path) if path else DEFAULT_CONFIG
    with open(p, "rb") as f:
        cfg = tomllib.load(f)
    return cfg
