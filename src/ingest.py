"""Ties the loader, chunker, embedder, vector store, and BM25 index
together into one ingestion pipeline, with near-duplicate detection before
anything gets indexed.

Deduplication is scoped per-source-file rather than corpus-wide: an O(n^2)
cosine comparison across the full corpus (up to ~1700 chunks for the
semantic strategy) is real but avoidable work, and near-duplicates in this
corpus are a within-document phenomenon in practice -- FastAPI's docs
inline multiple code variants of the same example (Python 3.9+ syntax,
Annotated-style, etc.) back to back in the same file, which is exactly the
redundancy this step exists to catch. Scoping to per-file comparisons
keeps dedup fast without giving up the case it's actually for.
"""
from __future__ import annotations

from typing import List

from src.bm25_index import BM25Index
from src.chunking import chunk_document
from src.document_loader import load_corpus
from src.embeddings import EmbeddingProvider
from src.models import ChunkingStrategy, DocumentChunk
from src.text_utils import cosine_similarity
from src.vector_store import VectorStore

DUPLICATE_SIMILARITY_THRESHOLD = 0.95


def deduplicate_within_file(chunks: List[DocumentChunk], embeddings: List[List[float]]):
    """Returns (kept_chunks, kept_embeddings, num_skipped)."""
    kept_chunks, kept_embeddings = [], []
    skipped = 0
    by_file: dict = {}

    for chunk, emb in zip(chunks, embeddings):
        seen = by_file.setdefault(chunk.source_file, [])
        is_duplicate = any(cosine_similarity(emb, other) >= DUPLICATE_SIMILARITY_THRESHOLD for other in seen)
        if is_duplicate:
            skipped += 1
            continue
        seen.append(emb)
        kept_chunks.append(chunk)
        kept_embeddings.append(emb)

    return kept_chunks, kept_embeddings, skipped


def load_indices(strategy: ChunkingStrategy) -> tuple:
    """Opens the persisted Chroma collection for `strategy` and rebuilds a
    BM25 index from its contents (see VectorStore.get_all_chunks). Use this
    at process startup instead of `ingest_corpus` when you just want to
    query an already-ingested index -- it's far cheaper than re-chunking
    and re-embedding the whole corpus."""
    from src.bm25_index import BM25Index
    from src.vector_store import VectorStore

    vector_store = VectorStore(strategy)
    bm25_index = BM25Index()
    bm25_index.build(vector_store.get_all_chunks())
    return vector_store, bm25_index


def ingest_corpus(
    strategy: ChunkingStrategy,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStore,
    bm25_index: BM25Index,
) -> dict:
    documents = load_corpus()

    all_chunks: List[DocumentChunk] = []
    for doc in documents:
        kwargs = {"embedding_provider": embedding_provider} if strategy == ChunkingStrategy.SEMANTIC else {}
        all_chunks.extend(chunk_document(doc, strategy, **kwargs))

    embeddings = embedding_provider.embed([c.text for c in all_chunks])
    kept_chunks, kept_embeddings, skipped = deduplicate_within_file(all_chunks, embeddings)

    vector_store.clear()
    vector_store.add(kept_chunks, kept_embeddings)
    bm25_index.build(kept_chunks)

    return {
        "documents": len(documents),
        "chunks_before_dedup": len(all_chunks),
        "chunks_indexed": len(kept_chunks),
        "duplicates_skipped": skipped,
    }
