from src.embeddings import MockEmbeddingProvider, get_embedding_provider
from src.text_utils import cosine_similarity


def test_mock_embedding_is_deterministic():
    emb = MockEmbeddingProvider()
    a = emb.embed_one("path parameters in FastAPI")
    b = emb.embed_one("path parameters in FastAPI")
    assert a == b


def test_mock_embedding_related_text_scores_higher_than_unrelated():
    emb = MockEmbeddingProvider()
    a = emb.embed_one("Path parameters let you declare dynamic path segments")
    b = emb.embed_one("You can declare path parameters with type annotations")
    c = emb.embed_one("CORS refers to cross-origin resource sharing between frontend and backend")

    related = cosine_similarity(a, b)
    unrelated = cosine_similarity(a, c)
    assert related > unrelated


def test_mock_embedding_self_similarity_is_one():
    emb = MockEmbeddingProvider()
    v = emb.embed_one("some text")
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-9


def test_mock_embedding_dimension_is_fixed():
    emb = MockEmbeddingProvider()
    assert len(emb.embed_one("short")) == emb.dimension
    assert len(emb.embed_one("a much longer piece of text with many more words in it")) == emb.dimension


def test_get_embedding_provider_defaults_to_mock_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    assert isinstance(get_embedding_provider(), MockEmbeddingProvider)


def test_get_embedding_provider_respects_override():
    assert isinstance(get_embedding_provider("mock"), MockEmbeddingProvider)
