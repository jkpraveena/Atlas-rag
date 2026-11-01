from src.generation import MockGenerationProvider, get_generation_provider
from src.models import ChunkingStrategy, DocumentChunk, RetrievalCandidate


def _candidate(id_, text, heading=None):
    chunk = DocumentChunk(id=id_, text=text, source_file="a.md", title="A", section_heading=heading, chunk_index=0, chunking_strategy=ChunkingStrategy.FIXED_SIZE)
    return RetrievalCandidate(chunk=chunk)


def test_extractive_answer_cites_every_candidate():
    candidates = [
        _candidate("1", "Path parameters are declared with type annotations. They are required."),
        _candidate("2", "Query parameters have default values that make them optional."),
    ]
    answer, citations = MockGenerationProvider().generate("how do path parameters work?", candidates)
    assert "[1]" in answer
    assert "[2]" in answer
    assert len(citations) == 2
    assert citations[0].chunk_id == "1"


def test_no_candidates_returns_refusal():
    answer, citations = MockGenerationProvider().generate("anything", [])
    assert "don't have enough information" in answer.lower()
    assert citations == []


def test_extractive_answer_only_ever_contains_source_text():
    text = "FastAPI uses Starlette under the hood for the web parts."
    candidates = [_candidate("1", text)]
    answer, _ = MockGenerationProvider().generate("what does fastapi use", candidates)
    # strip the citation marker and whitespace, what's left must be a substring of the source
    stripped = answer.replace("[1]", "").strip()
    assert stripped in text


def test_get_generation_provider_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GENERATION_PROVIDER", raising=False)
    assert isinstance(get_generation_provider(), MockGenerationProvider)
def test_extractive_answer_removes_html_tags():
    text = (
        'For more information, check the '
        '<a href="https://example.com">official documentation</a> '
        'for additional details.'
    )
    candidates = [_candidate("1", text)]

    answer, _ = MockGenerationProvider().generate(
        "Where can I find more information?",
        candidates,
    )

    assert "<a href=" not in answer
    assert "official documentation" in answer
def test_extractive_answer_filters_irrelevant_sentences():
    candidates = [
        _candidate(
            "1",
            "FastAPI is a modern web framework for building APIs with Python. "
            "It supports automatic interactive API documentation.",
        ),
        _candidate(
            "2",
            "In a real application, you should put your tests in a different file.",
        ),
    ]

    answer, citations = MockGenerationProvider().generate(
        "What is FastAPI?",
        candidates,
    )

    assert "FastAPI is a modern web framework" in answer
    assert "put your tests in a different file" not in answer
    assert len(citations) <= 3