from src.models import ChunkingStrategy, DocumentChunk, RetrievalCandidate
from src.reranker import MockReranker, get_reranker


def _candidate(id_, text):
    chunk = DocumentChunk(id=id_, text=text, source_file="a.md", title="A", chunk_index=0, chunking_strategy=ChunkingStrategy.FIXED_SIZE)
    return RetrievalCandidate(chunk=chunk)


def test_reranks_by_lexical_overlap_with_query():
    candidates = [
        _candidate("1", "background tasks run after the response"),
        _candidate("2", "path parameters use type annotations for path segments"),
    ]
    reranked = MockReranker().rerank("how do path parameters work", candidates, top_k=2)
    assert reranked[0].chunk.id == "2"


def test_rerank_respects_top_k():
    candidates = [_candidate(str(i), f"text number {i}") for i in range(10)]
    reranked = MockReranker().rerank("text", candidates, top_k=3)
    assert len(reranked) == 3


def test_rerank_sets_score_on_every_kept_candidate():
    candidates = [_candidate("1", "some text here")]
    reranked = MockReranker().rerank("some text", candidates, top_k=5)
    assert all(c.rerank_score is not None for c in reranked)


def test_get_reranker_defaults_to_mock_without_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("RERANKER", raising=False)
    assert isinstance(get_reranker(), MockReranker)
