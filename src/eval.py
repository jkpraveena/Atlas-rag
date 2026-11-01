"""Evaluation framework: runs the golden Q&A set through the real pipeline
and scores four dimensions per the build guide -- answer correctness,
faithfulness, retrieval relevance, and citation accuracy -- then, for the
chunking strategy comparison, runs the same set against all three
strategies' indices and reports which wins on which metric.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from src.bm25_index import BM25Index
from src.citation_verification import claims_by_marker
from src.embeddings import EmbeddingProvider
from src.generation import GenerationProvider
from src.graph import ask
from src.models import (
    AskRequest,
    ChunkingComparisonReport,
    ChunkingStrategy,
    Difficulty,
    EvalCaseResult,
    EvalRunSummary,
    GoldenDataset,
)
from src.reranker import Reranker
from src.text_utils import overlap_ratio
from src.vector_store import VectorStore

REFUSAL_PHRASE = "don't have enough information"
CORRECTNESS_PASS_THRESHOLD = 0.35


def _score_correctness(qa_difficulty: Difficulty, generated: str, expected: str) -> float:
    if qa_difficulty == Difficulty.NO_ANSWER:
        return 1.0 if REFUSAL_PHRASE in generated.lower() else 0.0
    return min(overlap_ratio(expected, generated) * 1.3, 1.0)


def _score_retrieval_relevance(qa_source_files: List[str], retrieved_source_files: List[str]) -> float:
    if not qa_source_files:
        return 1.0  # no_answer cases: nothing to have retrieved
    hits = sum(1 for f in qa_source_files if f in retrieved_source_files)
    return hits / len(qa_source_files)


def _score_faithfulness(answer_text: str, num_citations_used: int) -> float:
    """Fraction of claim spans in the answer that have a citation attached
    at all -- distinct from citation_accuracy, which measures whether
    those citations are actually correct. An answer can be 100% cited and
    still wrong (low accuracy), or mostly uncited (low faithfulness) while
    what little is cited checks out (high accuracy)."""
    claims = claims_by_marker(answer_text)
    non_empty_claims = [c for c in claims.values() if c]
    total_spans = len(non_empty_claims) or 1
    return min(num_citations_used / total_spans, 1.0)


def run_eval(
    dataset: GoldenDataset,
    chunking_strategy: ChunkingStrategy,
    vector_store: VectorStore,
    bm25_index: BM25Index,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    generation_provider: GenerationProvider,
) -> EvalRunSummary:
    results: List[EvalCaseResult] = []

    for qa in dataset.cases:
        request = AskRequest(question=qa.question, chunking_strategy=chunking_strategy)
        result = ask(request, vector_store, bm25_index, embedding_provider, reranker, generation_provider)

        retrieved_files = [c.chunk.source_file for c in result.retrieved]
        used_citations = [c for c in result.citations if c.supported is not None]

        correctness = _score_correctness(qa.difficulty, result.answer_text, qa.expected_answer)
        faithfulness = _score_faithfulness(result.answer_text, len(used_citations))
        retrieval_relevance = _score_retrieval_relevance(qa.source_files, retrieved_files)
        citation_accuracy = (
            sum(1 for c in used_citations if c.supported) / len(used_citations) if used_citations else
            (1.0 if qa.difficulty == Difficulty.NO_ANSWER else 0.0)
        )

        passed = correctness >= CORRECTNESS_PASS_THRESHOLD and (not used_citations or citation_accuracy >= 0.5)

        results.append(
            EvalCaseResult(
                qa_id=qa.id,
                difficulty=qa.difficulty,
                question=qa.question,
                generated_answer=result.answer_text,
                expected_answer=qa.expected_answer,
                correctness_score=round(correctness, 3),
                faithfulness_score=round(faithfulness, 3),
                retrieval_relevance_score=round(retrieval_relevance, 3),
                citation_accuracy_score=round(citation_accuracy, 3),
                passed=passed,
            )
        )

    total = len(results)
    per_difficulty: dict = {}
    for diff in Difficulty:
        cases = [r for r in results if r.difficulty == diff]
        if cases:
            per_difficulty[diff.value] = sum(1 for r in cases if r.passed) / len(cases)

    return EvalRunSummary(
        run_id=f"eval-{uuid.uuid4().hex[:10]}",
        chunking_strategy=chunking_strategy,
        timestamp=datetime.now(timezone.utc),
        dataset_version=dataset.dataset_version,
        results=results,
        pass_rate=sum(1 for r in results if r.passed) / total if total else 0.0,
        avg_correctness=sum(r.correctness_score for r in results) / total if total else 0.0,
        avg_faithfulness=sum(r.faithfulness_score for r in results) / total if total else 0.0,
        avg_retrieval_relevance=sum(r.retrieval_relevance_score for r in results) / total if total else 0.0,
        avg_citation_accuracy=sum(r.citation_accuracy_score for r in results) / total if total else 0.0,
        per_difficulty_pass_rate=per_difficulty,
    )


def compare_chunking_strategies(runs: List[EvalRunSummary]) -> ChunkingComparisonReport:
    metrics = ["pass_rate", "avg_correctness", "avg_faithfulness", "avg_retrieval_relevance", "avg_citation_accuracy"]
    winner_by_metric = {}
    for metric in metrics:
        best = max(runs, key=lambda r: getattr(r, metric))
        winner_by_metric[metric] = best.chunking_strategy.value
    return ChunkingComparisonReport(runs=runs, winner_by_metric=winner_by_metric)
