"""Reranks the top RRF-fused candidates against the actual query, per the
build guide's note that a second precision pass measurably improves
results over fusion rank alone.

`MockReranker` scores lexical overlap between the query and each
candidate's full text -- a real, if crude, relevance signal, not a
placeholder (RRF only ever saw rank position, never the actual query
text against the actual chunk text; this is the first thing in the
pipeline that does). `LLMReranker` swaps in an actual judgment call from a
real model, scoring true topical relevance rather than word overlap.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import List

from src.models import RetrievalCandidate
from src.text_utils import overlap_ratio

RERANK_CANDIDATE_POOL = 20
RERANK_KEEP = 5


class Reranker(ABC):
    name: str = "base"

    @abstractmethod
    def rerank(self, query: str, candidates: List[RetrievalCandidate], top_k: int = RERANK_KEEP) -> List[RetrievalCandidate]: ...


class MockReranker(Reranker):
    name = "mock-lexical"

    def rerank(self, query: str, candidates: List[RetrievalCandidate], top_k: int = RERANK_KEEP) -> List[RetrievalCandidate]:
        pool = candidates[:RERANK_CANDIDATE_POOL]
        for c in pool:
            c.rerank_score = overlap_ratio(query, c.chunk.text)
        return sorted(pool, key=lambda c: c.rerank_score, reverse=True)[:top_k]


class LLMReranker(Reranker):
    name = "llm-judge"

    def __init__(self, provider_name: str = None):
        self._provider_name = provider_name or os.environ.get("RERANK_PROVIDER") or (
            "openai" if os.environ.get("OPENAI_API_KEY") else "anthropic"
        )

    def _score_batch(self, query: str, pool: List[RetrievalCandidate]) -> List[float]:
        listing = "\n".join(f"[{i}] {c.chunk.text[:500]}" for i, c in enumerate(pool))
        prompt = (
            f"Question: {query}\n\nCandidate passages:\n{listing}\n\n"
            "Score each passage's relevance to answering the question, 0-10 (10 = directly answers it, "
            '0 = irrelevant). Respond with ONLY a JSON array of {len(pool)} numbers, e.g. [7, 2, 9, ...], '
            "in the same order as the passages."
        )
        if self._provider_name == "openai":
            from openai import OpenAI

            client = OpenAI()
            response = client.chat.completions.create(
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
        else:
            from anthropic import Anthropic

            client = Anthropic()
            response = client.messages.create(
                model=os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            content = "".join(b.text for b in response.content if hasattr(b, "text"))

        scores = json.loads(content[content.find("["): content.rfind("]") + 1])
        return [float(s) for s in scores]

    def rerank(self, query: str, candidates: List[RetrievalCandidate], top_k: int = RERANK_KEEP) -> List[RetrievalCandidate]:
        pool = candidates[:RERANK_CANDIDATE_POOL]
        try:
            scores = self._score_batch(query, pool)
        except Exception:
            # LLM reranking failing shouldn't break retrieval -- degrade to the mock signal
            return MockReranker().rerank(query, candidates, top_k)

        for c, s in zip(pool, scores):
            c.rerank_score = s
        return sorted(pool, key=lambda c: c.rerank_score, reverse=True)[:top_k]


def get_reranker(name: str = None) -> Reranker:
    name = name or os.environ.get("RERANKER")
    if name == "llm":
        return LLMReranker()
    if name == "mock":
        return MockReranker()
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"):
        return LLMReranker()
    return MockReranker()
