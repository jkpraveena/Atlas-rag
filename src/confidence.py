"""Composite confidence scoring: retrieval confidence (how relevant were
the top chunks?), citation coverage (what fraction of claims have verified
citations?), and completeness (did the answer address the question?). A
single number can't tell you why an answer might be untrustworthy; three
numbers with distinct meanings can.
"""
from __future__ import annotations

from typing import List

from typing import List

from src.models import AnswerConfidence, Citation, RetrievalCandidate
from src.text_utils import overlap_ratio

# Calibrated empirically against the golden Q&A set with MockEmbeddingProvider
# (swept the top dense-similarity score across all 37 cases, grouped by
# difficulty): no_answer questions cluster at 0.166-0.302 (avg 0.236),
# lookup/multi_hop/ambiguous questions cluster at 0.227-0.559 (avg 0.31-0.36).
# There's real overlap in the middle -- this is a crude bag-of-words signal,
# not a semantic one -- so 0.25 is a deliberate tradeoff: it correctly
# gates ~5/8 no_answer cases while only misfiring on the single lowest-margin
# case in each other category. Re-tune when switching to a real embedding
# provider, whose similarity distribution will separate more cleanly.
MIN_DENSE_SCORE_TO_ATTEMPT_ANSWER = 0.25


def should_attempt_answer(candidates: List[RetrievalCandidate], min_dense_score: float = MIN_DENSE_SCORE_TO_ATTEMPT_ANSWER) -> bool:
    """Gate that runs BEFORE generation, per the build guide: if retrieval
    confidence is too low, don't hallucinate an answer from marginally
    relevant chunks -- refuse immediately instead, without even calling
    the (possibly paid, real) generation provider."""
    dense_scores = [c.dense_score for c in candidates if c.dense_score is not None]
    if not dense_scores:
        return False
    return max(dense_scores) >= min_dense_score


def score_retrieval_confidence(
    candidates: List[RetrievalCandidate],
) -> float:
    """Estimate retrieval strength using the top reranking scores.

    This is a heuristic, not a calibrated probability.
    """
    if not candidates:
        return 0.0

    scores = [
        c.rerank_score
        for c in candidates
        if c.rerank_score is not None
    ]

    if not scores:
        return 0.0

    # Normalize mock (0–1) and LLM (0–10) scores.
    normalized = [
        min(score / 10.0, 1.0) if score > 1.0 else max(score, 0.0)
        for score in scores
    ]

    # Weight the strongest match more heavily, while accounting
    # for the quality of the other retrieved candidates.
    top_score = max(normalized)
    mean_score = sum(normalized) / len(normalized)

    return round(0.7 * top_score + 0.3 * mean_score, 3)


def score_citation_coverage(citations: List[Citation]) -> float:
    used = [c for c in citations if c.supported is not None]
    if not used:
        return 0.0
    supported = sum(1 for c in used if c.supported)
    return supported / len(used)


def score_completeness(question: str, answer_text: str) -> float:
    """Estimate answer relevance using lexical overlap.

    This is a heuristic, not a semantic completeness score.
    """
    if not answer_text:
        return 0.0

    normalized_answer = answer_text.lower().strip()

    refusal_phrases = (
        "i don't have enough information",
        "i do not have enough information",
    )

    if any(phrase in normalized_answer for phrase in refusal_phrases):
        return 0.0

    # Remove citation markers before evaluating the answer text.
    answer_without_citations = __import__("re").sub(
        r"\[\d+\]", "", answer_text
    ).strip()

    if not answer_without_citations:
        return 0.0

    return round(min(overlap_ratio(question, answer_without_citations), 1.0), 3)


def compute_confidence(question: str, answer_text: str, candidates: List[RetrievalCandidate], citations: List[Citation]) -> AnswerConfidence:
    retrieval = score_retrieval_confidence(candidates)
    coverage = score_citation_coverage(citations)
    completeness = score_completeness(question, answer_text)
    composite = round(0.4 * retrieval + 0.35 * coverage + 0.25 * completeness, 3)

    return AnswerConfidence(
        retrieval_confidence=round(retrieval, 3),
        citation_coverage=round(coverage, 3),
        completeness=round(completeness, 3),
        composite=composite,
    )
