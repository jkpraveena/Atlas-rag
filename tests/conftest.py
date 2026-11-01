import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.bm25_index import BM25Index
from src.embeddings import MockEmbeddingProvider
from src.ingest import ingest_corpus
from src.models import ChunkingStrategy
from src.vector_store import VectorStore


@pytest.fixture(scope="session")
def embedding_provider():
    return MockEmbeddingProvider()


@pytest.fixture(scope="session")
def ingested_structure_aware(tmp_path_factory, embedding_provider):
    """Ingests the REAL corpus (docs_corpus/) once per test session -- fast
    enough (~1-2s) that there's no reason to fabricate a synthetic corpus
    when the real one is already sitting in the repo."""
    persist_dir = tmp_path_factory.mktemp("chroma_structure_aware")
    store = VectorStore(ChunkingStrategy.STRUCTURE_AWARE, persist_dir=persist_dir)
    bm25 = BM25Index()
    stats = ingest_corpus(ChunkingStrategy.STRUCTURE_AWARE, embedding_provider, store, bm25)
    return store, bm25, stats
