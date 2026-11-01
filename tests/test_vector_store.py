from src.models import ChunkingStrategy, DocumentChunk
from src.vector_store import VectorStore


def _chunk(id_, text, source="a.md"):
    return DocumentChunk(id=id_, text=text, source_file=source, title="A", chunk_index=0, chunking_strategy=ChunkingStrategy.FIXED_SIZE)


def test_add_and_query_round_trip(tmp_path, embedding_provider):
    store = VectorStore(ChunkingStrategy.FIXED_SIZE, persist_dir=tmp_path)
    chunks = [_chunk("1", "path parameters and type annotations"), _chunk("2", "cross origin resource sharing CORS")]
    embeddings = embedding_provider.embed([c.text for c in chunks])
    store.add(chunks, embeddings)

    query_emb = embedding_provider.embed_one("how do path parameters work")
    results = store.query(query_emb, top_k=2)
    assert len(results) == 2
    assert results[0][0].id == "1"  # more similar chunk ranks first
    assert results[0][1] > results[1][1]


def test_empty_store_query_returns_empty(tmp_path):
    store = VectorStore(ChunkingStrategy.FIXED_SIZE, persist_dir=tmp_path)
    assert store.query([0.0] * 256, top_k=5) == []


def test_count_and_clear(tmp_path, embedding_provider):
    store = VectorStore(ChunkingStrategy.FIXED_SIZE, persist_dir=tmp_path)
    chunks = [_chunk("1", "some text")]
    store.add(chunks, embedding_provider.embed([c.text for c in chunks]))
    assert store.count() == 1
    store.clear()
    assert store.count() == 0


def test_get_all_chunks_reconstructs_metadata(tmp_path, embedding_provider):
    store = VectorStore(ChunkingStrategy.FIXED_SIZE, persist_dir=tmp_path)
    chunk = _chunk("1", "some text", source="b.md")
    store.add([chunk], embedding_provider.embed([chunk.text]))

    reloaded = store.get_all_chunks()
    assert len(reloaded) == 1
    assert reloaded[0].source_file == "b.md"
    assert reloaded[0].text == "some text"


def test_upsert_does_not_duplicate(tmp_path, embedding_provider):
    store = VectorStore(ChunkingStrategy.FIXED_SIZE, persist_dir=tmp_path)
    chunk = _chunk("1", "original text")
    store.add([chunk], embedding_provider.embed([chunk.text]))
    updated = _chunk("1", "updated text")
    store.add([updated], embedding_provider.embed([updated.text]))

    assert store.count() == 1
    assert store.get_all_chunks()[0].text == "updated text"
