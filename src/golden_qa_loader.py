"""Loads the versioned golden Q&A dataset."""
from __future__ import annotations

import json
from pathlib import Path

from src.models import GoldenDataset

GOLDEN_QA_DIR = Path(__file__).resolve().parent.parent / "golden_qa"


def load_golden_qa(version: str = "v1") -> GoldenDataset:
    path = GOLDEN_QA_DIR / f"qa_{version}.json"
    if not path.exists():
        raise FileNotFoundError(f"No golden QA dataset found at {path}")
    with open(path) as f:
        raw = json.load(f)
    return GoldenDataset(**raw)
