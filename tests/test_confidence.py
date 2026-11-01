from src.confidence import compute_confidence, should_attempt_answer
from src.models import ChunkingStrategy, Citation, DocumentChunk, RetrievalCandidate


def _candidate(dense_score, rerank_score=None):
    chunk = DocumentChunk(id="1", text="text", source_file="a.md", title="A", chunk_index=0, chunking_strategy=ChunkingStrategy.FIXED_SIZE)
    return RetrievalCandidate(chunk=chunk, dense_score=dense_score, rerank_score=rerank_score)


def test_should_attempt_answer_true_above_threshold():
    assert should_attempt_answer([_candidate(0.5)]) is True


def test_should_attempt_answer_false_below_threshold():
    assert should_attempt_answer([_candidate(0.1)]) is False


def test_should_attempt_answer_false_with_no_candidates():
    assert should_attempt_answer([]) is False


def test_should_attempt_answer_uses_best_candidate():
    assert should_attempt_answer([_candidate(0.1), _candidate(0.9)]) is True


def test_compute_confidence_no_candidates_is_zero():
    conf = compute_confidence("question", "I don't have enough information in the indexed documentation to answer this.", [], [])
    assert conf.retrieval_confidence == 0.0
    assert conf.completeness == 0.0


def test_compute_confidence_all_citations_supported_is_high_coverage():
    citations = [Citation(marker="[1]", chunk_id="1", source_file="a.md", supported=True)]
    candidates = [_candidate(0.5, rerank_score=0.8)]
    conf = compute_confidence("what is x", "x is y [1]", candidates, citations)
    assert conf.citation_coverage == 1.0


def test_compute_confidence_composite_is_bounded():
    citations = [Citation(marker="[1]", chunk_id="1", source_file="a.md", supported=True)]
    candidates = [_candidate(0.9, rerank_score=9.5)]
    conf = compute_confidence("q", "answer text here", candidates, citations)
    assert 0.0 <= conf.composite <= 1.0
def test_refusal_has_zero_completeness():
    from src.confidence import score_completeness

    score = score_completeness(
        "What is FastAPI?",
        "I don't have enough information in the indexed documentation to answer this.",
    )

    assert score == 0.0


def test_citation_coverage_penalizes_unsupported_citations():
    from src.confidence import score_citation_coverage

    citations = [
        Citation(
            marker="[1]",
            chunk_id="1",
            source_file="a.md",
            supported=True,
        ),
        Citation(
            marker="[2]",
            chunk_id="2",
            source_file="b.md",
            supported=False,
        ),
    ]

    assert score_citation_coverage(citations) == 0.5