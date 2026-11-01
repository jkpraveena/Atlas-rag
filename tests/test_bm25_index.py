from src.bm25_index import BM25Index
from src.models import ChunkingStrategy, DocumentChunk


def _chunk(id_, text):
    return DocumentChunk(id=id_, text=text, source_file="a.md", title="A", chunk_index=0, chunking_strategy=ChunkingStrategy.FIXED_SIZE)


def test_exact_keyword_match_ranks_first():
    index = BM25Index()
    index.build([
        _chunk("1", "FastAPI supports dependency injection for shared logic"),
        _chunk("2", "CORS middleware handles cross origin requests"),
        _chunk("3", "background tasks run after the response is sent"),
    ])
    results = index.query("dependency injection", top_k=3)
    assert results[0][0].id == "1"


def test_no_match_returns_empty():
    index = BM25Index()
    index.build([_chunk("1", "FastAPI supports dependency injection")])
    assert index.query("completely unrelated gibberish xyz", top_k=3) == []


def test_empty_index_returns_empty():
    index = BM25Index()
    assert index.query("anything", top_k=5) == []


def test_count():
    index = BM25Index()
    index.build([_chunk("1", "a"), _chunk("2", "b")])
    assert index.count() == 2
