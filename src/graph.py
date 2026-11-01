"""LangGraph orchestration for one ask() call.

    retrieve_dense    retrieve_sparse       independent, same depth -> safe
        |------------------|                 parallel fan-out/fan-in (see the
                    v                        knowledge-graph sibling project's
                  fuse                       graph.py for why depth-matching
                    v                        matters for LangGraph fan-in)
                 rerank
                    v
                 generate
                    v
           verify_and_score
                    v
                   END
"""
from __future__ import annotations

import asyncio
import operator
import time
import uuid
from typing import Annotated, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from src.bm25_index import BM25Index
from src.citation_verification import get_citation_verifier
from src.confidence import compute_confidence, should_attempt_answer
from src.embeddings import EmbeddingProvider, get_embedding_provider
from src.fusion import reciprocal_rank_fusion
from src.generation import GenerationProvider, get_generation_provider
from src.models import AgentStep, AskRequest, AskResult, ChunkingStrategy
from src.reranker import Reranker, get_reranker
from src.vector_store import VectorStore

DENSE_TOP_K = 10
SPARSE_TOP_K = 10


class RAGState(TypedDict, total=False):
    request: AskRequest
    vector_store: VectorStore
    bm25_index: BM25Index
    embedding_provider: EmbeddingProvider
    reranker: Reranker
    generation_provider: GenerationProvider
    dense_results: list
    sparse_results: list
    fused: list
    reranked: list
    answer_text: str
    citations: list
    agent_trace: Annotated[List[AgentStep], operator.add]


async def _retrieve_dense_node(state: RAGState) -> dict:
    # Always runs, even in dense-only mode (request.use_hybrid=False) --
    # dense-only mode means "skip sparse", not "skip dense". See
    # _retrieve_sparse_node for the actual toggle.
    start = time.perf_counter()
    request = state["request"]
    query_emb = await asyncio.to_thread(state["embedding_provider"].embed_one, request.question)
    results = await asyncio.to_thread(state["vector_store"].query, query_emb, DENSE_TOP_K)
    step = AgentStep(agent="retrieve_dense", summary=f"{len(results)} candidate(s).", latency_ms=(time.perf_counter() - start) * 1000)
    return {"dense_results": results, "agent_trace": [step]}


async def _retrieve_sparse_node(state: RAGState) -> dict:
    start = time.perf_counter()
    request = state["request"]
    if not request.use_hybrid:
        return {"sparse_results": [], "agent_trace": [AgentStep(agent="retrieve_sparse", summary="skipped (dense-only mode)")]}

    results = await asyncio.to_thread(state["bm25_index"].query, request.question, SPARSE_TOP_K)
    step = AgentStep(agent="retrieve_sparse", summary=f"{len(results)} candidate(s).", latency_ms=(time.perf_counter() - start) * 1000)
    return {"sparse_results": results, "agent_trace": [step]}


async def _fuse_node(state: RAGState) -> dict:
    start = time.perf_counter()
    request = state["request"]
    fused = await asyncio.to_thread(
        reciprocal_rank_fusion, state["dense_results"], state["sparse_results"], request.dense_weight, 1 - request.dense_weight
    )
    step = AgentStep(agent="fuse", summary=f"{len(fused)} unique candidate(s) after RRF.", latency_ms=(time.perf_counter() - start) * 1000)
    return {"fused": fused, "agent_trace": [step]}


async def _rerank_node(state: RAGState) -> dict:
    start = time.perf_counter()
    request = state["request"]
    reranked = await asyncio.to_thread(state["reranker"].rerank, request.question, state["fused"], request.top_k)
    step = AgentStep(agent="rerank", summary=f"kept top {len(reranked)} via {state['reranker'].name}.", latency_ms=(time.perf_counter() - start) * 1000)
    return {"reranked": reranked, "agent_trace": [step]}


REFUSAL_TEXT = "I don't have enough information in the indexed documentation to answer this."


async def _generate_node(state: RAGState) -> dict:
    start = time.perf_counter()
    request = state["request"]
    reranked = state["reranked"]

    if not should_attempt_answer(reranked):
        step = AgentStep(
            agent="generate",
            summary="retrieval confidence below threshold -- refused without calling the generation provider.",
            latency_ms=(time.perf_counter() - start) * 1000,
        )
        return {"answer_text": REFUSAL_TEXT, "citations": [], "agent_trace": [step]}

    answer_text, citations = await asyncio.to_thread(state["generation_provider"].generate, request.question, reranked)
    step = AgentStep(agent="generate", summary=f"generated via {state['generation_provider'].name}, {len(citations)} citation(s).", latency_ms=(time.perf_counter() - start) * 1000)
    return {"answer_text": answer_text, "citations": citations, "agent_trace": [step]}


async def _verify_and_score_node(state: RAGState) -> dict:
    start = time.perf_counter()
    verifier = get_citation_verifier()
    citations = await asyncio.to_thread(verifier, state["answer_text"], state["citations"], state["reranked"])
    step = AgentStep(agent="verify_and_score", summary=f"verified {len(citations)} citation(s).", latency_ms=(time.perf_counter() - start) * 1000)
    return {"citations": citations, "agent_trace": [step]}


_compiled_graph = None


def build_graph():
    graph = StateGraph(RAGState)
    graph.add_node("retrieve_dense", _retrieve_dense_node)
    graph.add_node("retrieve_sparse", _retrieve_sparse_node)
    graph.add_node("fuse", _fuse_node)
    graph.add_node("rerank", _rerank_node)
    graph.add_node("generate", _generate_node)
    graph.add_node("verify_and_score", _verify_and_score_node)

    graph.set_entry_point("retrieve_dense")
    graph.set_entry_point("retrieve_sparse")
    graph.add_edge("retrieve_dense", "fuse")
    graph.add_edge("retrieve_sparse", "fuse")
    graph.add_edge("fuse", "rerank")
    graph.add_edge("rerank", "generate")
    graph.add_edge("generate", "verify_and_score")
    graph.add_edge("verify_and_score", END)

    return graph.compile()


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


async def ask_async(
    request: AskRequest,
    vector_store: VectorStore,
    bm25_index: BM25Index,
    embedding_provider: Optional[EmbeddingProvider] = None,
    reranker: Optional[Reranker] = None,
    generation_provider: Optional[GenerationProvider] = None,
) -> AskResult:
    embedding_provider = embedding_provider or get_embedding_provider()
    reranker = reranker or get_reranker()
    generation_provider = generation_provider or get_generation_provider()

    graph = get_compiled_graph()
    start = time.perf_counter()
    final_state = await graph.ainvoke({
        "request": request,
        "vector_store": vector_store,
        "bm25_index": bm25_index,
        "embedding_provider": embedding_provider,
        "reranker": reranker,
        "generation_provider": generation_provider,
        "agent_trace": [],
    })
    total_latency_ms = (time.perf_counter() - start) * 1000

    confidence = compute_confidence(request.question, final_state["answer_text"], final_state["reranked"], final_state["citations"])

    return AskResult(
        query_id=f"ask-{uuid.uuid4().hex[:10]}",
        question=request.question,
        answer_text=final_state["answer_text"],
        citations=final_state["citations"],
        confidence=confidence,
        retrieved=final_state["reranked"],
        used_hybrid=request.use_hybrid,
        chunking_strategy=request.chunking_strategy,
        generation_provider=generation_provider.name,
        agent_trace=final_state["agent_trace"],
        total_latency_ms=total_latency_ms,
    )


def ask(
    request: AskRequest,
    vector_store: VectorStore,
    bm25_index: BM25Index,
    embedding_provider: Optional[EmbeddingProvider] = None,
    reranker: Optional[Reranker] = None,
    generation_provider: Optional[GenerationProvider] = None,
) -> AskResult:
    return asyncio.run(ask_async(request, vector_store, bm25_index, embedding_provider, reranker, generation_provider))
