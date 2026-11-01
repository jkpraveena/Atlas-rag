"""Sparse keyword search via BM25 (rank_bm25) -- catches exact term
matches (function names, config keys, error codes) that dense/semantic
retrieval can miss, per the build guide."""
from __future__ import annotations

from typing import List, Tuple

from rank_bm25 import BM25Okapi

from src.models import DocumentChunk
from src.text_utils import content_tokens


class BM25Index:
    def __init__(self):
        self._bm25: BM25Okapi = None
        self._chunks: List[DocumentChunk] = []

    def build(self, chunks: List[DocumentChunk]) -> None:
        self._chunks = list(chunks)
        tokenized = [sorted(content_tokens(c.text)) for c in self._chunks]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    def query(self, query_text: str, top_k: int = 10) -> List[Tuple[DocumentChunk, float]]:
        if self._bm25 is None or not self._chunks:
            return []
        query_tokens = sorted(content_tokens(query_text))
        scores = self._bm25.get_scores(query_tokens)
        ranked = sorted(zip(self._chunks, scores), key=lambda pair: pair[1], reverse=True)
        return [(chunk, score) for chunk, score in ranked[:top_k] if score > 0]

    def count(self) -> int:
        return len(self._chunks)
