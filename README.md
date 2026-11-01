# RAG Pipeline with Hybrid Search

[![tests](https://github.com/kushimahar/rag-hybrid-search-pipeline/actions/workflows/tests.yml/badge.svg)](https://github.com/kushimahar/rag-hybrid-search-pipeline/actions/workflows/tests.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

### Skills demonstrated

Hybrid retrieval (dense + BM25 sparse, Reciprocal Rank Fusion) · configurable chunking
strategies with an empirical comparison harness · grounded generation with verified inline
citations · retrieval-confidence gating against hallucination · LangGraph orchestration ·
real vector database (ChromaDB) · FastAPI · Streamlit · pytest

A production-grade RAG system over a **real** documentation corpus: dense vector search
(ChromaDB) fused with BM25 sparse keyword search via Reciprocal Rank Fusion, a reranking
pass, grounded generation with inline `[1][2]`-style citations, automated citation
verification, and a composite confidence score -- with a retrieval-confidence gate that
refuses to answer rather than hallucinate when nothing relevant was actually retrieved.

## Why this exists

Most RAG portfolio projects are a single PDF and a LangChain quickstart. This one deliberately
takes on the production concerns the build guide calls out as the actual differentiator:
hybrid retrieval instead of dense-only, a documented chunking-strategy comparison instead of
one arbitrary choice, citation verification instead of trusting the model cited correctly, and
a real empirically-measured decision about when the system should say "I don't know" instead
of confidently making something up.

## The corpus is real, not synthetic

`docs_corpus/` is ~29 pages of FastAPI's actual official tutorial documentation, fetched live
from `github.com/fastapi/fastapi` (pinned to tag `0.104.1`, MIT licensed) via
`scripts/fetch_docs.py` -- not hand-written filler text. FastAPI's docs keep runnable code
samples in separate files and include them into the markdown at build time
(`{!path/to/file.py!}` directives); the fetch script resolves and inlines every one of those
so the corpus is fully self-contained. See `docs_corpus/MANIFEST.md` for the full page list
and exact source commit.

`golden_qa/qa_v1.json` is a hand-authored 37-question golden set grounded in that same
corpus -- 15 straightforward lookups, 8 multi-hop questions spanning two source files, 8
questions the corpus genuinely doesn't answer, and 6 deliberately ambiguous questions. Every
answer was checked against the actual fetched text, not generated.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/ingest.py       # chunk + embed + index all 3 strategies (~10s, offline)
python scripts/run_demo.py     # the whole story: citations, hybrid vs dense-only,
                                # a refused no-answer case, chunking comparison

pytest tests/ -v                # 83 tests, no network calls, no API key needed

uvicorn src.api:app --reload    # -> http://localhost:8000/docs
streamlit run streamlit_app.py  # separate terminal
```

## Architecture at a glance

```
   retrieve_dense      retrieve_sparse        independent, same graph depth ->
   (ChromaDB, cosine)   (BM25, exact terms)     safe LangGraph fan-out/fan-in
        |-------------------|
                 v
    fuse (Reciprocal Rank Fusion, 0.7 dense / 0.3 sparse by default)
                 v
    rerank (mock lexical overlap, or a real LLM-as-judge pass)
                 v
    generate -- but ONLY if retrieval confidence clears a threshold;
                below it, refuse immediately without calling generation at all
                 v
    verify_and_score (does every [N] citation actually say what's claimed?
                       composite confidence: retrieval + citation coverage + completeness)
```

## Hybrid retrieval actually matters here -- shown, not just claimed

`python scripts/run_demo.py` runs the same question ("What is an origin in the context of
CORS?") through hybrid and dense-only retrieval and prints both result sets side by side.
`origin` is short and generic enough that pure embedding similarity doesn't always pin it
down precisely, while BM25's exact-term matching catches it directly -- the two result sets
visibly diverge. (Note: ChromaDB's HNSW index is an *approximate* nearest-neighbor search,
not an exact deterministic one, so the precise ranking can shift slightly between runs --
itself a real characteristic of production vector databases worth knowing, not a bug.)

## Chunking strategy comparison -- a real number, not a guess

`python scripts/run_chunking_comparison.py` runs the full 37-case golden set against all
three strategies (fixed-size, structure-aware, semantic) and reports a winner per metric. A
representative run in offline mode:

| Strategy | Pass rate | Correctness | Faithfulness | Citation accuracy |
|---|---|---|---|---|
| fixed_size | 0.68 | 0.53 | 0.70 | 0.89 |
| structure_aware | 0.59 | 0.47 | 0.68 | 0.84 |
| semantic | 0.59 | 0.48 | 0.65 | 0.78 |

**Fixed-size chunking wins most metrics here, which is not the "obviously correct" answer a
lot of RAG tutorials imply.** With the offline mock embedding, fixed-size's larger, more
uniform chunks give the extractive answer generator more surrounding context per chunk to
work with. This is real, measured signal from this specific configuration -- re-run the
comparison after switching to a real embedding provider (`OPENAI_API_KEY`) before trusting it
as a general claim about chunking strategies; the ranking may well change with genuinely
semantic embeddings instead of the offline hashing-trick stand-in.

## Don't hallucinate when there's nothing to retrieve

Per the build guide's explicit requirement, low-confidence retrieval short-circuits straight
to a refusal *before* generation runs at all -- saving a real LLM call's cost too, not just
avoiding a bad answer. This wasn't obvious from the start: **the first version of this system
always attempted an answer and scored 0% correctness on every single "no answer expected"
golden case**, extracting a confident-sounding but nonsensical response from whatever
marginally-relevant chunk got retrieved. Sweeping the top retrieval score across all 37
golden cases by difficulty (see `src/confidence.py`) found a real, if imperfect, separation:
no-answer questions cluster around 0.17-0.30 dense similarity, answerable questions around
0.23-0.56 -- enough overlap that no threshold is perfect, but `should_attempt_answer()`'s
calibrated 0.25 cutoff took no-answer accuracy from 0% to 75% with only marginal cost to the
other categories. That calibration note and its tradeoffs are documented directly in the code.

## Switching to real providers

Every stage (embeddings, reranking, generation, citation verification) has an offline mock
and a real LLM-backed implementation behind the same interface. Set a key and nothing else
changes:

```bash
export OPENAI_API_KEY=sk-...
python scripts/ingest.py       # re-ingest with real embeddings (dimension changes: 256 -> 1536)
python scripts/run_demo.py
```

**Re-ingestion is required after switching embedding providers** -- the vector store holds
embeddings from whichever provider indexed them, and mixing dimensions doesn't work. Chroma
collections are namespaced by chunking strategy, so `python scripts/ingest.py` (or the
`--strategy` flag for just one) rebuilds cleanly either way.

## API

```
POST /v1/ask                  {"question": "...", "chunking_strategy": "structure_aware", "use_hybrid": true}
GET  /v1/documents?strategy=structure_aware
POST /v1/ingest?strategy=fixed_size
GET  /v1/queries/{id}
GET  /v1/queries
GET  /v1/eval/run?strategy=structure_aware
GET  /v1/eval/chunking-comparison
```

Full interactive docs at `/docs` once running.

## Running with Docker

```bash
docker compose up --build
```

Three services: a one-shot `init` job that ingests the (already-committed) corpus into a
shared volume, the API (`:8000`), and the Streamlit UI (`:8501`) -- both wait for `init` to
complete before starting. Set `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` in a `.env` file to run
against real providers.

## Design decisions worth knowing about

**Why ChromaDB needed no mock/real split, but embeddings/generation/reranking did.** ChromaDB
is itself a real, free, local, embedded vector database -- no server, no API key, exactly
what the build guide asks for. The offline/online distinction only applies where a paid API
is actually involved.

**Why the mock embedding is a hashing-trick bag-of-words vectorizer, not random noise.**
Verified directly (see `tests/test_embeddings.py`): two chunks sharing vocabulary get
genuinely higher cosine similarity than two that don't. That's what makes dense retrieval,
semantic chunking, and the no-answer confidence gate all produce real, reproducible signal
offline -- a stub returning fixed or random vectors couldn't support any of those three.

**Why citation verification splits on the `[N]` markers themselves, not on sentence
punctuation.** An early version split the whole answer into sentences first and checked which
sentence contained each marker. When a cited claim itself ends in terminal punctuation
("...an `int`. [5]"), that naive split breaks *between* the period and the marker, leaving the
marker alone in its own empty "sentence" -- a well-formed, correct citation got reported as
"marker not found." Splitting on the markers directly and treating the span between two
markers as the claim sidesteps the failure mode entirely; `tests/test_citation_verification.py`
pins this down as a named regression test, not just a fixed bug.

**Why `eval_run_endpoint` and `eval_chunking_comparison_endpoint` are sync `def`, not
`async def`, while `ask_endpoint` is async.** `run_eval()` calls the synchronous `ask()`
wrapper, which drives the LangGraph pipeline via `asyncio.run()`. Declaring the FastAPI
handler `async def` means it's already executing inside a running event loop, and
`asyncio.run()` cannot be nested inside one -- a real `RuntimeError` caught by the API test
suite, not a hypothetical. FastAPI runs sync `def` handlers in a worker thread automatically,
which sidesteps the conflict entirely. `ask_endpoint` avoids the issue by awaiting
`ask_async()` directly instead of going through the sync wrapper.

**Why deduplication is scoped per-source-file instead of corpus-wide.** An O(n²) cosine
comparison across the full corpus (up to ~1700 candidate chunks pre-dedup for the semantic
strategy) is real, avoidable work. FastAPI's docs inline multiple near-identical code variants
of the same example back to back *within a single file* (Python 3.9+ syntax, `Annotated`-style,
etc.) -- exactly the redundancy this step exists to catch -- so scoping comparisons to each
file keeps dedup fast without giving up the case it's actually for.

## Project layout

```
src/
  models.py                 Pydantic contracts: chunks, citations, confidence, eval results
  document_loader.py           loads docs_corpus/ into SourceDocument objects
  chunking.py                    fixed_size / structure_aware / semantic strategies
  embeddings.py                    Mock (hashing-trick) / OpenAI providers
  vector_store.py                    ChromaDB wrapper, one collection per chunking strategy
  bm25_index.py                        sparse keyword search (rank_bm25)
  fusion.py                              Reciprocal Rank Fusion
  reranker.py                              Mock (lexical) / LLM-as-judge reranking
  generation.py                              Mock (extractive) / OpenAI / Anthropic generation
  citation_verification.py                     verifies each [N] citation against its source
  confidence.py                                  retrieval-confidence gate + composite scoring
  ingest.py                                        ties loader+chunker+embedder+stores together
  graph.py                                           LangGraph orchestration for one ask() call
  eval.py                                              golden-set eval + chunking comparison
  storage.py                                             SQLite query/eval history
  api.py                                                    FastAPI service
scripts/
  fetch_docs.py               live-fetches the real FastAPI docs corpus, resolves code includes
  build_golden_qa.py            builds golden_qa/qa_v1.json from hand-authored source data
  ingest.py                       CLI: (re)ingest one or all chunking strategies
  run_chunking_comparison.py        golden-set eval across all 3 strategies
  run_demo.py                         the full walkthrough
docs_corpus/                real FastAPI tutorial pages (see MANIFEST.md for provenance)
golden_qa/qa_v1.json        hand-authored, corpus-grounded golden Q&A set
streamlit_app.py            Ask / Hybrid vs Dense-only / Chunking Comparison / Documents / History
tests/                      83 tests -- unit + integration against the real committed corpus
docker-compose.yml
Dockerfile
```

## Recording a walkthrough

`python scripts/run_demo.py` runs the whole story end-to-end and is screen-recordable as-is.
For a UI-driven recording: ask a question in the Ask tab and show the citations table with
per-citation verification, switch to Hybrid vs Dense-only and run the CORS/"origin" question
to show the two retrieval modes visibly diverging, then run the Chunking Strategy Comparison
tab to show the winner-by-metric table generated live.

## License

MIT (see `LICENSE`) for the code in this repository. `docs_corpus/` contains real content
fetched from [fastapi/fastapi](https://github.com/fastapi/fastapi) (also MIT licensed) --
see `docs_corpus/MANIFEST.md` for the exact source pages and commit tag.
