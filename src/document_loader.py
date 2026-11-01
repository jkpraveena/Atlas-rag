"""Loads the fetched markdown corpus into SourceDocument objects."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

from src.models import SourceDocument

CORPUS_DIR = Path(__file__).resolve().parent.parent / "docs_corpus"


def _extract_title(text: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def load_corpus(corpus_dir: Path = CORPUS_DIR) -> List[SourceDocument]:
    documents = []
    for path in sorted(corpus_dir.glob("*.md")):
        if path.name == "MANIFEST.md":
            continue
        text = path.read_text()
        title = _extract_title(text, fallback=path.stem)
        documents.append(SourceDocument(source_file=path.name, title=title, raw_text=text))
    return documents
