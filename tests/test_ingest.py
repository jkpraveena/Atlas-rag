from src.ingest import deduplicate_within_file
from src.models import ChunkingStrategy, DocumentChunk


def _chunk(id_, source_file):
    return DocumentChunk(id=id_, text=f"text {id_}", source_file=source_file, title="A", chunk_index=0, chunking_strategy=ChunkingStrategy.FIXED_SIZE)


def test_deduplicates_near_identical_embeddings_within_same_file():
    chunks = [_chunk("1", "a.md"), _chunk("2", "a.md")]
    embeddings = [[1.0, 0.0], [0.999, 0.001]]  # cosine sim ~1.0, near-duplicate
    kept, kept_emb, skipped = deduplicate_within_file(chunks, embeddings)
    assert len(kept) == 1
    assert skipped == 1


def test_does_not_deduplicate_across_different_files():
    chunks = [_chunk("1", "a.md"), _chunk("2", "b.md")]
    embeddings = [[1.0, 0.0], [1.0, 0.0]]  # identical, but different source files
    kept, kept_emb, skipped = deduplicate_within_file(chunks, embeddings)
    assert len(kept) == 2
    assert skipped == 0


def test_does_not_deduplicate_dissimilar_chunks():
    chunks = [_chunk("1", "a.md"), _chunk("2", "a.md")]
    embeddings = [[1.0, 0.0], [0.0, 1.0]]  # orthogonal, cosine sim 0
    kept, kept_emb, skipped = deduplicate_within_file(chunks, embeddings)
    assert len(kept) == 2
    assert skipped == 0


def test_real_corpus_ingestion_produces_reasonable_stats(ingested_structure_aware):
    store, bm25, stats = ingested_structure_aware
    assert stats["documents"] >= 25
    assert stats["chunks_indexed"] > 0
    assert stats["chunks_indexed"] <= stats["chunks_before_dedup"]
    assert store.count() == stats["chunks_indexed"]
    assert bm25.count() == stats["chunks_indexed"]
