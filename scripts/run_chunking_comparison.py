#!/usr/bin/env python3
"""Runs the full golden Q&A set against all three chunking strategies and
reports which wins on which metric -- the concrete, numeric deliverable
the build guide asks for in Phase 4.3, not just a claim about which
strategy "should" be better.

Requires the corpus to already be ingested (python scripts/ingest.py).

Usage: python scripts/run_chunking_comparison.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.embeddings import get_embedding_provider
from src.eval import compare_chunking_strategies, run_eval
from src.generation import get_generation_provider
from src.golden_qa_loader import load_golden_qa
from src.ingest import load_indices
from src.models import ChunkingStrategy
from src.reranker import get_reranker


def main():
    load_dotenv()
    dataset = load_golden_qa()
    embedding_provider = get_embedding_provider()
    reranker = get_reranker()
    generation_provider = get_generation_provider()

    print(f"Providers: embedding={embedding_provider.name}, reranker={reranker.name}, generation={generation_provider.name}")
    print(f"Golden dataset: {len(dataset.cases)} cases\n")

    runs = []
    for strategy in ChunkingStrategy:
        vector_store, bm25_index = load_indices(strategy)
        if vector_store.count() == 0:
            print(f"SKIPPING {strategy.value}: not ingested yet (run scripts/ingest.py first)")
            continue
        summary = run_eval(dataset, strategy, vector_store, bm25_index, embedding_provider, reranker, generation_provider)
        runs.append(summary)
        print(
            f"{strategy.value:16s} pass_rate={summary.pass_rate:.2f}  correctness={summary.avg_correctness:.2f}  "
            f"faithfulness={summary.avg_faithfulness:.2f}  retrieval_relevance={summary.avg_retrieval_relevance:.2f}  "
            f"citation_accuracy={summary.avg_citation_accuracy:.2f}"
        )

    if len(runs) < 2:
        print("\nNeed at least 2 ingested strategies to compare. Run scripts/ingest.py first.")
        return

    report = compare_chunking_strategies(runs)
    print("\nWinner by metric:")
    for metric, winner in report.winner_by_metric.items():
        print(f"  {metric:22s} -> {winner}")


if __name__ == "__main__":
    main()
