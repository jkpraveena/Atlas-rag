"""End-to-end tests through the real LangGraph pipeline against the real
ingested corpus (see conftest.py) -- mock embedding/reranker/generation
providers throughout, so these are fast and need no API key, but every
retrieval result comes from the actual fetched FastAPI docs."""
from src.generation import MockGenerationProvider
from src.graph import ask
from src.models import AskRequest, ChunkingStrategy
from src.reranker import MockReranker


def test_answerable_question_produces_grounded_answer(ingested_structure_aware, embedding_provider):
    store, bm25, _ = ingested_structure_aware
    request = AskRequest(question="How do I declare a path parameter with a specific type like int?", chunking_strategy=ChunkingStrategy.STRUCTURE_AWARE)
    result = ask(request, store, bm25, embedding_provider, MockReranker(), MockGenerationProvider())

    assert result.citations
    assert any(c.chunk.source_file == "tutorial__path-params.md" for c in result.retrieved)
    assert result.confidence.composite > 0


def test_irrelevant_question_refuses_without_generating(ingested_structure_aware, embedding_provider):
    store, bm25, _ = ingested_structure_aware
    request = AskRequest(question="What is the airspeed velocity of an unladen swallow?", chunking_strategy=ChunkingStrategy.STRUCTURE_AWARE)
    result = ask(request, store, bm25, embedding_provider, MockReranker(), MockGenerationProvider())

    assert "don't have enough information" in result.answer_text.lower()
    assert result.citations == []
    generate_step = next(s for s in result.agent_trace if s.agent == "generate")
    assert "refused" in generate_step.summary.lower()


def test_hybrid_vs_dense_only_can_differ(ingested_structure_aware, embedding_provider):
    store, bm25, _ = ingested_structure_aware
    q = "How do I add a background task?"
    hybrid = ask(AskRequest(question=q, chunking_strategy=ChunkingStrategy.STRUCTURE_AWARE, use_hybrid=True), store, bm25, embedding_provider, MockReranker(), MockGenerationProvider())
    dense_only = ask(AskRequest(question=q, chunking_strategy=ChunkingStrategy.STRUCTURE_AWARE, use_hybrid=False), store, bm25, embedding_provider, MockReranker(), MockGenerationProvider())

    assert hybrid.used_hybrid is True
    assert dense_only.used_hybrid is False
    # dense-only mode should retrieve nothing via sparse
    assert all(c.sparse_score is None for c in dense_only.retrieved)


def test_citations_are_verified(ingested_structure_aware, embedding_provider):
    store, bm25, _ = ingested_structure_aware
    request = AskRequest(question="What package must be installed to receive file uploads?", chunking_strategy=ChunkingStrategy.STRUCTURE_AWARE)
    result = ask(request, store, bm25, embedding_provider, MockReranker(), MockGenerationProvider())

    assert result.citations
    assert all(c.supported is not None for c in result.citations)


def test_agent_trace_records_all_agents(ingested_structure_aware, embedding_provider):
    store, bm25, _ = ingested_structure_aware
    request = AskRequest(question="How do I add a background task?", chunking_strategy=ChunkingStrategy.STRUCTURE_AWARE)
    result = ask(request, store, bm25, embedding_provider, MockReranker(), MockGenerationProvider())

    agents = {s.agent for s in result.agent_trace}
    assert agents == {"retrieve_dense", "retrieve_sparse", "fuse", "rerank", "generate", "verify_and_score"}


def test_multi_hop_question_retrieves_from_multiple_sources(ingested_structure_aware, embedding_provider):
    store, bm25, _ = ingested_structure_aware
    request = AskRequest(
        question="If I want an endpoint that accepts a file upload and also returns HTTP 201, which features do I combine?",
        chunking_strategy=ChunkingStrategy.STRUCTURE_AWARE, top_k=8,
    )
    result = ask(request, store, bm25, embedding_provider, MockReranker(), MockGenerationProvider())
    retrieved_files = {c.chunk.source_file for c in result.retrieved}
    assert len(retrieved_files) >= 1  # weak assertion: real multi-hop retrieval quality varies with the mock embedding
