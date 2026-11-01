from src.citation_verification import claims_by_marker, verify_citations_lexical
from src.models import ChunkingStrategy, Citation, DocumentChunk, RetrievalCandidate


def test_claims_by_marker_basic_split():
    text = "First claim here. [1] Second claim here. [2]"
    claims = claims_by_marker(text)
    assert claims["[1]"] == "First claim here."
    assert claims["[2]"] == "Second claim here."


def test_claims_by_marker_survives_terminal_punctuation_before_marker():
    """Regression test: a naive sentence-splitter (splitting on `[.!?]\\s+`)
    breaks BETWEEN the period and the marker when the cited span itself
    ends in terminal punctuation, orphaning the marker with an empty claim.
    Found by inspecting a real verification result where a well-formed
    citation was incorrectly reported as 'marker not found.'"""
    text = "In this case, `item_id` is declared to be an `int`. [5]"
    claims = claims_by_marker(text)
    assert claims["[5]"] == "In this case, `item_id` is declared to be an `int`."
    assert claims["[5]"] != ""


def test_claims_by_marker_handles_multiline_code_blocks():
    text = "Some intro.\n\n```python\ndef f():\n    pass\n```\n\nAfter code. [1]"
    claims = claims_by_marker(text)
    assert "```python" in claims["[1]"]
    assert "After code." in claims["[1]"]


def test_claims_by_marker_unmatched_marker_is_absent():
    assert claims_by_marker("No markers here at all.") == {}


def _candidate(chunk_id, text):
    chunk = DocumentChunk(id=chunk_id, text=text, source_file="a.md", title="A", chunk_index=0, chunking_strategy=ChunkingStrategy.FIXED_SIZE)
    return RetrievalCandidate(chunk=chunk)


def test_lexical_verification_supports_matching_claim():
    candidates = [_candidate("1", "Path parameters use standard Python type annotations for validation")]
    citations = [Citation(marker="[1]", chunk_id="1", source_file="a.md")]
    answer = "Path parameters use type annotations for validation. [1]"

    verified = verify_citations_lexical(answer, citations, candidates)
    assert verified[0].supported is True


def test_lexical_verification_flags_unsupported_claim():
    candidates = [_candidate("1", "CORS handles cross-origin requests between frontend and backend")]
    citations = [Citation(marker="[1]", chunk_id="1", source_file="a.md")]
    answer = "Background tasks run after the response is sent. [1]"

    verified = verify_citations_lexical(answer, citations, candidates)
    assert verified[0].supported is False


def test_verification_handles_missing_chunk_gracefully():
    citations = [Citation(marker="[1]", chunk_id="does-not-exist", source_file="a.md")]
    verified = verify_citations_lexical("Some claim. [1]", citations, [])
    assert verified[0].supported is None
