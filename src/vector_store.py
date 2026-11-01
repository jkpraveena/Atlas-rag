"""Chroma-backed dense vector store.

Unlike the LLM/embedding providers elsewhere in this project, there's no
mock/real split needed here: ChromaDB is itself a real, free, local,
embedded vector database (no server, no API key) -- exactly what the build
guide calls for ("ChromaDB (file-based)"). One collection per chunking
strategy, since the eval framework needs to compare all three strategies
against the same golden questions.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import chromadb
from chromadb.config import Settings

from src.models import ChunkingStrategy, DocumentChunk

PERSIST_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma"


def _client(persist_dir: Path = PERSIST_DIR):
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir), settings=Settings(anonymized_telemetry=False))


class VectorStore:
    def __init__(self, strategy: ChunkingStrategy, persist_dir: Path = PERSIST_DIR):
        self.strategy = strategy
        self._client = _client(persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=f"docs_{strategy.value}",
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, chunks: List[DocumentChunk], embeddings: List[List[float]]) -> None:
        if not chunks:
            return
        self._collection.upsert(
            ids=[c.id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    "source_file": c.source_file,
                    "title": c.title,
                    "section_heading": c.section_heading or "",
                    "chunk_index": c.chunk_index,
                    "chunking_strategy": c.chunking_strategy.value,
                }
                for c in chunks
            ],
        )

    def query(self, query_embedding: List[float], top_k: int = 10) -> List[Tuple[DocumentChunk, float]]:
        if self._collection.count() == 0:
            return []
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self._collection.count()),
        )
        results = []
        for i, chunk_id in enumerate(result["ids"][0]):
            distance = result["distances"][0][i]
            similarity = 1 - distance  # cosine space: distance = 1 - cosine_similarity
            meta = result["metadatas"][0][i]
            chunk = DocumentChunk(
                id=chunk_id,
                text=result["documents"][0][i],
                source_file=meta["source_file"],
                title=meta["title"],
                section_heading=meta["section_heading"] or None,
                chunk_index=meta["chunk_index"],
                chunking_strategy=ChunkingStrategy(meta["chunking_strategy"]),
            )
            results.append((chunk, similarity))
        return results

    def get_all_chunks(self) -> List[DocumentChunk]:
        """Reconstructs every indexed chunk from Chroma's stored documents +
        metadata. Used to rebuild the (in-memory-only) BM25 index from the
        persisted vector store at process startup, so the API/Streamlit app
        doesn't need to re-run the full ingestion pipeline every time it
        starts -- Chroma is the single persisted source of truth for "what's
        indexed," BM25 is rebuilt from it on demand.
        """
        if self._collection.count() == 0:
            return []
        result = self._collection.get()
        chunks = []
        for i, chunk_id in enumerate(result["ids"]):
            meta = result["metadatas"][i]
            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    text=result["documents"][i],
                    source_file=meta["source_file"],
                    title=meta["title"],
                    section_heading=meta["section_heading"] or None,
                    chunk_index=meta["chunk_index"],
                    chunking_strategy=ChunkingStrategy(meta["chunking_strategy"]),
                )
            )
        return chunks

    def count(self) -> int:
        return self._collection.count()

    def clear(self) -> None:
        self._client.delete_collection(f"docs_{self.strategy.value}")
        self._collection = self._client.get_or_create_collection(
            name=f"docs_{self.strategy.value}", metadata={"hnsw:space": "cosine"}
        )
