"""RAG Hybrid Search Pipeline -- Streamlit dashboard.

Run with: streamlit run streamlit_app.py
(after `python scripts/ingest.py` at least once)

Tabs: ask a question with full citation/confidence detail, compare hybrid
vs. dense-only retrieval side by side on the same question, compare all
three chunking strategies against the golden Q&A set, browse the ingested
corpus, and review query history.
"""
import re

import pandas as pd
import streamlit as st

from src.embeddings import get_embedding_provider
from src.eval import compare_chunking_strategies, run_eval
from src.generation import get_generation_provider
from src.golden_qa_loader import load_golden_qa
from src.graph import ask
from src.ingest import load_indices
from src.models import AskRequest, ChunkingStrategy
from src.reranker import get_reranker
from src.storage import list_recent_queries, save_query

st.set_page_config(page_title="RAG Hybrid Search Pipeline", page_icon="🔎", layout="wide")


@st.cache_resource
def get_index(strategy: ChunkingStrategy):
    return load_indices(strategy)


def render_answer_with_citations(answer_text: str) -> str:
    return re.sub(r"\[(\d+)\]", r"**[\1]**", answer_text)


def render_ask_result(result):
    st.markdown("#### Answer")
    st.markdown(render_answer_with_citations(result.answer_text))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
    "Composite heuristic score",
    f"{result.confidence.composite:.0%}",
    )
    c2.metric(
        "Retrieval relevance estimate",
        f"{result.confidence.retrieval_confidence:.0%}",
    )
    c3.metric(
        "Citations marked supported",
        f"{result.confidence.citation_coverage:.0%}",
    )
    c4.metric(
        "Question-answer lexical overlap",
        f"{result.confidence.completeness:.0%}",
    )

    st.caption(
        "These are heuristic scores, not calibrated probabilities of correctness. "
        "Citation support is assessed using the configured verification method."
    )

    if result.citations:
        st.markdown("#### Citations")
        st.dataframe(
            pd.DataFrame([
                {
                    "marker": c.marker, "source": c.source_file, "section": c.section_heading or "-",
                    "supported": "✅" if c.supported else ("❌" if c.supported is False else "—"),
                    "note": c.verification_note,
                }
                for c in result.citations
            ]),
            use_container_width=True, hide_index=True,
        )

    with st.expander(f"Retrieved chunks ({len(result.retrieved)})"):
        for c in result.retrieved:
            dense_str = f"{c.dense_score:.3f}" if c.dense_score is not None else "-"
            sparse_str = f"{c.sparse_score:.3f}" if c.sparse_score is not None else "-"
            rerank_str = f"{c.rerank_score:.3f}" if c.rerank_score is not None else "-"
            st.markdown(f"**{c.chunk.source_file}** {f'· {c.chunk.section_heading}' if c.chunk.section_heading else ''}")
            st.caption(
                f"dense_score={dense_str} (rank {c.dense_rank}) · sparse_score={sparse_str} (rank {c.sparse_rank}) · "
                f"rerank_score={rerank_str}"
            )
            st.text(c.chunk.text[:300] + ("..." if len(c.chunk.text) > 300 else ""))
            st.divider()

    with st.expander("Agent trace"):
        for step in result.agent_trace:
            st.markdown(f"**{step.agent}** ({step.latency_ms:.2f}ms) -- {step.summary}")


tab_ask, tab_compare, tab_chunking, tab_docs, tab_history = st.tabs(
    ["Ask", "Hybrid vs Dense-only", "Chunking Strategy Comparison", "Documents", "History"]
)

with tab_ask:
    st.markdown("### Ask a question about the indexed documentation")
    question = st.text_input("Question", placeholder="e.g. How do I declare a path parameter with a specific type?")
    col1, col2, col3 = st.columns(3)
    strategy = col1.selectbox("Chunking strategy", [s.value for s in ChunkingStrategy], index=1)
    use_hybrid = col2.checkbox("Use hybrid (dense + sparse)", value=True)
    top_k = col3.slider("Top K after rerank", 1, 10, 5)

    if st.button("Ask", type="primary") and question:
        store, bm25 = get_index(ChunkingStrategy(strategy))
        if store.count() == 0:
            st.error(f"'{strategy}' hasn't been ingested. Run `python scripts/ingest.py` first.")
        else:
            with st.spinner("Retrieving, fusing, reranking, generating, verifying..."):
                request = AskRequest(question=question, chunking_strategy=ChunkingStrategy(strategy), use_hybrid=use_hybrid, top_k=top_k)
                result = ask(request, store, bm25, get_embedding_provider(), get_reranker(), get_generation_provider())
                save_query(result)
            st.session_state["last_result"] = result

    if "last_result" in st.session_state:
        st.divider()
        render_ask_result(st.session_state["last_result"])

with tab_compare:
    st.markdown("### Hybrid vs. dense-only, side by side")
    st.caption("Same question, same chunking strategy, only the retrieval mode differs.")
    q2 = st.text_input("Question", key="compare_question", placeholder="e.g. What package is needed for file uploads?")
    strategy2 = st.selectbox("Chunking strategy", [s.value for s in ChunkingStrategy], index=1, key="compare_strategy")

    if st.button("Compare") and q2:
        store, bm25 = get_index(ChunkingStrategy(strategy2))
        if store.count() == 0:
            st.error(f"'{strategy2}' hasn't been ingested. Run `python scripts/ingest.py` first.")
        else:
            emb, reranker, gen = get_embedding_provider(), get_reranker(), get_generation_provider()
            with st.spinner("Running both modes..."):
                hybrid_result = ask(AskRequest(question=q2, chunking_strategy=ChunkingStrategy(strategy2), use_hybrid=True), store, bm25, emb, reranker, gen)
                dense_result = ask(AskRequest(question=q2, chunking_strategy=ChunkingStrategy(strategy2), use_hybrid=False), store, bm25, emb, reranker, gen)
                save_query(hybrid_result)
                save_query(dense_result)

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("#### Hybrid (dense + sparse)")
                render_ask_result(hybrid_result)
            with col_b:
                st.markdown("#### Dense-only")
                render_ask_result(dense_result)

with tab_chunking:
    st.markdown("### Chunking strategy comparison")
    st.caption("Runs the full 37-case golden Q&A set against all three strategies. Takes a few seconds in mock mode.")

    if st.button("Run comparison"):
        dataset = load_golden_qa()
        emb, reranker, gen = get_embedding_provider(), get_reranker(), get_generation_provider()
        runs = []
        progress = st.progress(0.0)
        for i, strategy in enumerate(ChunkingStrategy):
            store, bm25 = get_index(strategy)
            if store.count() == 0:
                st.error(f"'{strategy.value}' hasn't been ingested. Run `python scripts/ingest.py` first.")
                st.stop()
            runs.append(run_eval(dataset, strategy, store, bm25, emb, reranker, gen))
            progress.progress((i + 1) / len(ChunkingStrategy))

        report = compare_chunking_strategies(runs)
        st.session_state["comparison_report"] = report

    if "comparison_report" in st.session_state:
        report = st.session_state["comparison_report"]
        st.dataframe(
            pd.DataFrame([
                {
                    "strategy": r.chunking_strategy.value, "pass_rate": f"{r.pass_rate:.0%}",
                    "correctness": f"{r.avg_correctness:.0%}", "faithfulness": f"{r.avg_faithfulness:.0%}",
                    "retrieval_relevance": f"{r.avg_retrieval_relevance:.0%}", "citation_accuracy": f"{r.avg_citation_accuracy:.0%}",
                }
                for r in report.runs
            ]),
            use_container_width=True, hide_index=True,
        )
        st.markdown("#### Winner by metric")
        for metric, winner in report.winner_by_metric.items():
            st.markdown(f"- **{metric}**: `{winner}`")

with tab_docs:
    st.markdown("### Indexed documentation")
    strategy3 = st.selectbox("Chunking strategy", [s.value for s in ChunkingStrategy], index=1, key="docs_strategy")
    store, _ = get_index(ChunkingStrategy(strategy3))
    chunks = store.get_all_chunks()
    by_file = {}
    for c in chunks:
        by_file[c.source_file] = by_file.get(c.source_file, 0) + 1
    st.metric("Total chunks", len(chunks))
    st.dataframe(
        pd.DataFrame([{"source_file": f, "chunks": n} for f, n in sorted(by_file.items())]),
        use_container_width=True, hide_index=True,
    )

with tab_history:
    st.markdown("### Recent queries")
    recent = list_recent_queries(50)
    if not recent:
        st.info("No queries yet -- ask something in the Ask tab.")
    else:
        st.dataframe(
            pd.DataFrame([
                {
                    "id": r.query_id, "question": r.question, "strategy": r.chunking_strategy.value,
                    "hybrid": r.used_hybrid, "confidence": f"{r.confidence.composite:.0%}",
                    "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M"),
                }
                for r in recent
            ]),
            use_container_width=True, hide_index=True,
        )
