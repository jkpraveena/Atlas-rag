from src.eval import compare_chunking_strategies, run_eval
from src.generation import MockGenerationProvider
from src.golden_qa_loader import load_golden_qa
from src.models import ChunkingStrategy, Difficulty
from src.reranker import MockReranker


def test_run_eval_produces_a_result_per_case(ingested_structure_aware, embedding_provider):
    store, bm25, _ = ingested_structure_aware
    dataset = load_golden_qa()
    summary = run_eval(dataset, ChunkingStrategy.STRUCTURE_AWARE, store, bm25, embedding_provider, MockReranker(), MockGenerationProvider())

    assert len(summary.results) == len(dataset.cases)
    assert 0.0 <= summary.pass_rate <= 1.0


def test_no_answer_cases_score_meaningfully_after_confidence_gate(ingested_structure_aware, embedding_provider):
    """Regression guard: before the retrieval-confidence gate was added,
    the mock generator always attempted an answer and no_answer cases
    scored 0% correctness across the board. This pins the fix in place."""
    store, bm25, _ = ingested_structure_aware
    dataset = load_golden_qa()
    summary = run_eval(dataset, ChunkingStrategy.STRUCTURE_AWARE, store, bm25, embedding_provider, MockReranker(), MockGenerationProvider())

    no_answer_pass_rate = summary.per_difficulty_pass_rate.get(Difficulty.NO_ANSWER.value, 0.0)
    assert no_answer_pass_rate >= 0.5


def test_compare_chunking_strategies_picks_a_winner_per_metric(ingested_structure_aware, embedding_provider):
    store, bm25, _ = ingested_structure_aware
    dataset = load_golden_qa()
    run_a = run_eval(dataset, ChunkingStrategy.STRUCTURE_AWARE, store, bm25, embedding_provider, MockReranker(), MockGenerationProvider())
    run_b = run_eval(dataset, ChunkingStrategy.STRUCTURE_AWARE, store, bm25, embedding_provider, MockReranker(), MockGenerationProvider())

    report = compare_chunking_strategies([run_a, run_b])
    assert set(report.winner_by_metric.keys()) == {
        "pass_rate", "avg_correctness", "avg_faithfulness", "avg_retrieval_relevance", "avg_citation_accuracy",
    }
    assert all(w == ChunkingStrategy.STRUCTURE_AWARE.value for w in report.winner_by_metric.values())
