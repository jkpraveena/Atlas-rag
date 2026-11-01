#!/usr/bin/env python3
"""Ingests the corpus (all 3 chunking strategies) if needed, then walks
through the whole story: a grounded+cited answer, a hybrid vs. dense-only
comparison, a question the corpus genuinely can't answer (refused, not
hallucinated), and the chunking strategy comparison. Fully offline by
default (mock embedding/reranker/generation).

Usage: python scripts/run_demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.bm25_index import BM25Index
from src.embeddings import get_embedding_provider
from src.eval import compare_chunking_strategies, run_eval
from src.generation import get_generation_provider
from src.golden_qa_loader import load_golden_qa
from src.graph import ask
from src.ingest import ingest_corpus
from src.models import AskRequest, ChunkingStrategy
from src.reranker import get_reranker
from src.vector_store import VectorStore


def main():
    load_dotenv()
    emb = get_embedding_provider()
    reranker = get_reranker()
    gen = get_generation_provider()
    print(f"Providers: embedding={emb.name}, reranker={reranker.name}, generation={gen.name}\n")

    print("Ingesting all three chunking strategies...")
    indices = {}
    for strategy in ChunkingStrategy:
        store = VectorStore(strategy)
        bm25 = BM25Index()
        stats = ingest_corpus(strategy, emb, store, bm25)
        indices[strategy] = (store, bm25)
        print(f"  {strategy.value:16s} {stats}")

    store, bm25 = indices[ChunkingStrategy.STRUCTURE_AWARE]

    print("\n" + "=" * 78)
    print("1. Grounded answer with citations")
    print("-" * 78)
    result = ask(AskRequest(question="How do I declare a path parameter with a specific type like int?"), store, bm25, emb, reranker, gen)
    print(f"Q: {result.question}")
    print(f"A: {result.answer_text[:300]}")
    print(f"Confidence: {result.confidence}")
    for c in result.citations:
        print(f"  {c.marker} {c.source_file} supported={c.supported}")

    print("\n" + "=" * 78)
    print("2. Hybrid vs. dense-only, same question")
    print("-" * 78)
    q = "What is an origin in the context of CORS?"
    hybrid = ask(AskRequest(question=q, use_hybrid=True), store, bm25, emb, reranker, gen)
    dense_only = ask(AskRequest(question=q, use_hybrid=False), store, bm25, emb, reranker, gen)
    print(f"Q: {q}")
    print(f"Hybrid retrieved:     {[c.chunk.source_file for c in hybrid.retrieved]}")
    print(f"Dense-only retrieved: {[c.chunk.source_file for c in dense_only.retrieved]}")
    print("(the exact rankings can shift slightly run to run -- Chroma's HNSW index is an")
    print(" approximate nearest-neighbor search, not a deterministic exact one; see the README's")
    print(" note on this. The two lists visibly diverging at all is the point: sparse retrieval's")
    print(" exact-term match on 'origin' pulls in results dense similarity alone ranks differently.)")

    print("\n" + "=" * 78)
    print("3. A question the corpus can't answer -- refused, not hallucinated")
    print("-" * 78)
    no_answer = ask(AskRequest(question="How do I deploy a FastAPI application to AWS Lambda?"), store, bm25, emb, reranker, gen)
    print(f"Q: {no_answer.question}")
    print(f"A: {no_answer.answer_text}")
    print(f"Citations: {len(no_answer.citations)} (none fabricated)")

    print("\n" + "=" * 78)
    print("4. Chunking strategy comparison (37-case golden Q&A set)")
    print("-" * 78)
    dataset = load_golden_qa()
    runs = []
    for strategy in ChunkingStrategy:
        s, b = indices[strategy]
        summary = run_eval(dataset, strategy, s, b, emb, reranker, gen)
        runs.append(summary)
        print(f"  {strategy.value:16s} pass_rate={summary.pass_rate:.2f} correctness={summary.avg_correctness:.2f} "
              f"faithfulness={summary.avg_faithfulness:.2f} citation_accuracy={summary.avg_citation_accuracy:.2f}")

    report = compare_chunking_strategies(runs)
    print("\nWinner by metric:", report.winner_by_metric)


if __name__ == "__main__":
    main()
