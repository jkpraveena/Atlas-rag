"""Reciprocal Rank Fusion: merges dense and sparse ranked lists into one
ranked list, weighted per the build guide's suggested 0.7 dense / 0.3
sparse split (configurable). RRF combines by RANK POSITION, not raw score
magnitude -- which is the point: dense cosine similarities and BM25 scores
live on completely different scales and aren't otherwise comparable.
"""
from __future__ import annotations

from typing import List, Tuple

from src.models import DocumentChunk, RetrievalCandidate

DEFAULT_K = 60  # standard RRF damping constant


def reciprocal_rank_fusion(
    dense_results: List[Tuple[DocumentChunk, float]],
    sparse_results: List[Tuple[DocumentChunk, float]],
    dense_weight: float = 0.7,
    sparse_weight: float = 0.3,
    k: int = DEFAULT_K,
) -> List[RetrievalCandidate]:
    candidates: dict = {}

    for rank, (chunk, score) in enumerate(dense_results, start=1):
        candidates[chunk.id] = RetrievalCandidate(chunk=chunk, dense_score=score, dense_rank=rank)

    for rank, (chunk, score) in enumerate(sparse_results, start=1):
        if chunk.id in candidates:
            candidates[chunk.id].sparse_score = score
            candidates[chunk.id].sparse_rank = rank
        else:
            candidates[chunk.id] = RetrievalCandidate(chunk=chunk, sparse_score=score, sparse_rank=rank)

    for candidate in candidates.values():
        rrf = 0.0
        if candidate.dense_rank is not None:
            rrf += dense_weight / (k + candidate.dense_rank)
        if candidate.sparse_rank is not None:
            rrf += sparse_weight / (k + candidate.sparse_rank)
        candidate.rrf_score = rrf

    return sorted(candidates.values(), key=lambda c: c.rrf_score, reverse=True)
