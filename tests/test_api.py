import functools

import pytest
from fastapi.testclient import TestClient

import src.api as api_module
import src.storage as storage_module
from src.models import ChunkingStrategy


@pytest.fixture
def client(tmp_path, monkeypatch, ingested_structure_aware):
    db_path = tmp_path / "test_api.db"
    for fn_name in ("save_query", "list_recent_queries", "get_query", "save_eval_run", "count_queries"):
        real_fn = getattr(storage_module, fn_name)
        monkeypatch.setattr(api_module, fn_name, functools.partial(real_fn, db_path=db_path))

    # Inject the already-ingested real-corpus fixture instead of hitting the
    # default on-disk index path, so API tests are isolated and fast. Also
    # patch `load_indices` itself (not just pre-populate `_indices`) so that
    # a strategy NOT explicitly injected here resolves to a guaranteed-empty
    # store -- without this, a test asserting "strategy X isn't ingested"
    # could pass or fail depending on whatever's left over on disk from an
    # earlier manual `python scripts/ingest.py` run, which is exactly what
    # happened here during development.
    store, bm25, _ = ingested_structure_aware
    monkeypatch.setattr(api_module, "_indices", {ChunkingStrategy.STRUCTURE_AWARE: (store, bm25)})

    def _empty_indices(strategy):
        from src.bm25_index import BM25Index
        from src.vector_store import VectorStore
        return VectorStore(strategy, persist_dir=tmp_path / f"empty_{strategy.value}"), BM25Index()

    monkeypatch.setattr(api_module, "load_indices", _empty_indices)

    return TestClient(api_module.app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["indexed_chunks"]["structure_aware"] > 0


def test_ask_returns_grounded_answer(client):
    response = client.post("/v1/ask", json={"question": "How do I declare a path parameter with a specific type?", "chunking_strategy": "structure_aware"})
    assert response.status_code == 200
    body = response.json()
    assert body["query_id"].startswith("ask-")
    assert body["citations"]


def test_ask_rejects_empty_question(client):
    response = client.post("/v1/ask", json={"question": "  "})
    assert response.status_code == 422


def test_ask_unignested_strategy_is_409(client):
    response = client.post("/v1/ask", json={"question": "anything", "chunking_strategy": "semantic"})
    assert response.status_code == 409


def test_get_query_round_trip(client):
    created = client.post("/v1/ask", json={"question": "How do I add a background task?", "chunking_strategy": "structure_aware"}).json()
    fetched = client.get(f"/v1/queries/{created['query_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["query_id"] == created["query_id"]


def test_get_missing_query_is_404(client):
    assert client.get("/v1/queries/does-not-exist").status_code == 404


def test_list_queries(client):
    client.post("/v1/ask", json={"question": "q1", "chunking_strategy": "structure_aware"})
    client.post("/v1/ask", json={"question": "q2", "chunking_strategy": "structure_aware"})
    response = client.get("/v1/queries")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_documents(client):
    response = client.get("/v1/documents", params={"strategy": "structure_aware"})
    assert response.status_code == 200
    body = response.json()
    assert body["total_chunks"] > 0
    assert len(body["documents"]) >= 25


def test_eval_run_endpoint(client):
    response = client.get("/v1/eval/run", params={"strategy": "structure_aware"})
    assert response.status_code == 200
    body = response.json()
    assert body["chunking_strategy"] == "structure_aware"
    assert len(body["results"]) >= 30
