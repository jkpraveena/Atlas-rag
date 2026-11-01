#!/usr/bin/env python3
"""Ingests the corpus into all three chunking strategies' indices (or one,
with --strategy). Run this once before using the API/Streamlit app, or
after fetching a new corpus.

Usage:
    python scripts/ingest.py                       # all three strategies
    python scripts/ingest.py --strategy fixed_size  # just one
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.bm25_index import BM25Index
from src.embeddings import get_embedding_provider
from src.ingest import ingest_corpus
from src.models import ChunkingStrategy
from src.vector_store import VectorStore

# BM25 indices are in-memory (rank_bm25 has no persistence), so they're
# rebuilt at process start in the API/Streamlit app. This script's job is
# populating the persistent Chroma collections; run it once and both the
# API and the UI pick up the same on-disk index.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=[s.value for s in ChunkingStrategy], default=None)
    args = parser.parse_args()

    load_dotenv()
    embedding_provider = get_embedding_provider()
    print(f"Embedding provider: {embedding_provider.name}\n")

    strategies = [ChunkingStrategy(args.strategy)] if args.strategy else list(ChunkingStrategy)
    for strategy in strategies:
        store = VectorStore(strategy)
        bm25 = BM25Index()
        stats = ingest_corpus(strategy, embedding_provider, store, bm25)
        print(f"{strategy.value:16s} {stats}")


if __name__ == "__main__":
    main()
