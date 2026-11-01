"""FastAPI service exposing the hybrid-search RAG pipeline.

    POST /v1/ask                          question in, grounded+cited answer out
    GET  /v1/documents                     ingested source files + chunk counts
    POST /v1/ingest                         (re)ingest the corpus for a strategy
    GET  /v1/queries/{id}
    GET  /v1/queries
    GET  /v1/eval/run                        run the golden set against one strategy
    GET  /v1/eval/chunking-comparison         run all three strategies and compare
    GET  /health
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Query

from src.bm25_index import BM25Index
from src.embeddings import get_embedding_provider
from src.eval import compare_chunking_strategies, run_eval
from src.generation import get_generation_provider
from src.golden_qa_loader import load_golden_qa
from src.graph import ask_async
from src.ingest import ingest_corpus, load_indices
from src.models import AskRequest, AskResult, ChunkingComparisonReport, ChunkingStrategy, EvalRunSummary
from src.reranker import get_reranker
from src.storage import count_queries, get_query, list_recent_queries, save_eval_run, save_query
from src.vector_store import VectorStore

app = FastAPI(
    title="RAG Hybrid Search Pipeline",
    description=(
        "Production-grade RAG over a real documentation corpus: dense + sparse hybrid retrieval "
        "with Reciprocal Rank Fusion, a reranking pass, grounded generation with inline citations, "
        "citation verification, and confidence scoring. Corpus: FastAPI's official tutorial docs, "
        "fetched live (see scripts/fetch_docs.py)."
    ),
    version="1.0.0",
)

_indices: Dict[ChunkingStrategy, Tuple[VectorStore, BM25Index]] = {}


def _get_indices(strategy: ChunkingStrategy) -> Tuple[VectorStore, BM25Index]:
    if strategy not in _indices:
        _indices[strategy] = load_indices(strategy)
    return _indices[strategy]


@app.get("/health")
async def health():
    counts = {}
    for strategy in ChunkingStrategy:
        store, _ = _get_indices(strategy)
        counts[strategy.value] = store.count()
    return {"status": "ok", "queries_recorded": count_queries(), "indexed_chunks": counts}


@app.post("/v1/ask", response_model=AskResult)
async def ask_endpoint(request: AskRequest):
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="question must be non-empty")
    store, bm25 = _get_indices(request.chunking_strategy)
    if store.count() == 0:
        raise HTTPException(status_code=409, detail=f"'{request.chunking_strategy.value}' hasn't been ingested yet -- POST /v1/ingest first")

    result = await ask_async(request, store, bm25, get_embedding_provider(), get_reranker(), get_generation_provider())
    save_query(result)
    return result


@app.post("/v1/ingest")
def ingest_endpoint(strategy: ChunkingStrategy):
    # sync `def`: chunking + embedding a whole corpus is real CPU/IO work
    # that shouldn't block the event loop -- FastAPI runs it in a thread.
    store, bm25 = _get_indices(strategy)
    stats = ingest_corpus(strategy, get_embedding_provider(), store, bm25)
    return stats


@app.get("/v1/documents")
async def list_documents_endpoint(strategy: ChunkingStrategy = ChunkingStrategy.STRUCTURE_AWARE):
    store, _ = _get_indices(strategy)
    chunks = store.get_all_chunks()
    by_file: Dict[str, int] = {}
    for c in chunks:
        by_file[c.source_file] = by_file.get(c.source_file, 0) + 1
    return {"strategy": strategy.value, "total_chunks": len(chunks), "documents": by_file}


@app.get("/v1/queries/{query_id}", response_model=AskResult)
async def get_query_endpoint(query_id: str):
    result = get_query(query_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No query found with id {query_id}")
    return result


@app.get("/v1/queries", response_model=List[AskResult])
async def list_queries_endpoint(limit: int = Query(default=50, ge=1, le=500)):
    return list_recent_queries(limit)


@app.get("/v1/eval/run", response_model=EvalRunSummary)
def eval_run_endpoint(strategy: ChunkingStrategy = ChunkingStrategy.STRUCTURE_AWARE):
    # Deliberately a sync `def`, not `async def`: run_eval() calls the sync
    # ask() wrapper, which calls asyncio.run() internally to drive the
    # LangGraph pipeline. Declaring this handler async would mean it's
    # already executing inside anyio's running event loop, and nesting
    # asyncio.run() inside a running loop raises "asyncio.run() cannot be
    # called from a running event loop." FastAPI runs sync `def` handlers
    # in a worker thread automatically, which sidesteps the conflict --
    # found by an actual RuntimeError on this exact endpoint, not by
    # reasoning about it in advance.
    store, bm25 = _get_indices(strategy)
    if store.count() == 0:
        raise HTTPException(status_code=409, detail=f"'{strategy.value}' hasn't been ingested yet")
    dataset = load_golden_qa()
    summary = run_eval(dataset, strategy, store, bm25, get_embedding_provider(), get_reranker(), get_generation_provider())
    save_eval_run(summary)
    return summary


@app.get("/v1/eval/chunking-comparison", response_model=ChunkingComparisonReport)
def eval_chunking_comparison_endpoint():
    # sync `def` for the same reason as eval_run_endpoint above
    dataset = load_golden_qa()
    embedding_provider = get_embedding_provider()
    reranker = get_reranker()
    generation_provider = get_generation_provider()

    runs = []
    for strategy in ChunkingStrategy:
        store, bm25 = _get_indices(strategy)
        if store.count() == 0:
            raise HTTPException(status_code=409, detail=f"'{strategy.value}' hasn't been ingested yet -- POST /v1/ingest for all three strategies first")
        summary = run_eval(dataset, strategy, store, bm25, embedding_provider, reranker, generation_provider)
        save_eval_run(summary)
        runs.append(summary)

    return compare_chunking_strategies(runs)
