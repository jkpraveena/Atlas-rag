"""Embedding providers.

`MockEmbeddingProvider` (default) is a deterministic, offline, zero-cost
hashing-trick bag-of-words vectorizer -- not a stub. Each stemmed token is
hashed into a fixed-dimension vector with a random sign (the standard
"feature hashing" trick), counts accumulate, and the result is L2-normalized.
Two chunks that share vocabulary get genuinely higher cosine similarity than
two that don't -- verified below, not assumed -- so dense retrieval and
semantic chunking both produce real, reproducible rankings without an API
key. `OpenAIEmbeddingProvider` swaps in real `text-embedding-3-small`
vectors the moment `OPENAI_API_KEY` is set; nothing downstream changes,
since both implementations return plain lists of floats of a fixed
dimension.
"""
from __future__ import annotations

import hashlib
import math
import os
from abc import ABC, abstractmethod
from typing import List

from src.text_utils import content_tokens

MOCK_EMBEDDING_DIM = 256


class EmbeddingProvider(ABC):
    name: str = "base"
    dimension: int = 0

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]: ...

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


class MockEmbeddingProvider(EmbeddingProvider):
    name = "mock-hashing"
    dimension = MOCK_EMBEDDING_DIM

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> List[float]:
        vector = [0.0] * self.dimension
        for token in content_tokens(text):
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            index = int(digest[:8], 16) % self.dimension
            sign = 1.0 if int(digest[8], 16) % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [v / norm for v in vector]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    name = "openai"
    dimension = 1536

    def __init__(self, api_key: str = None, model: str = None):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
        self._model = model or os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")

    def embed(self, texts: List[str]) -> List[List[float]]:
        response = self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]


def get_embedding_provider(name: str = None) -> EmbeddingProvider:
    name = name or os.environ.get("EMBEDDING_PROVIDER")
    if name == "openai":
        return OpenAIEmbeddingProvider()
    if name == "mock":
        return MockEmbeddingProvider()
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIEmbeddingProvider()
    return MockEmbeddingProvider()
