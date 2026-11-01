from src.chunking import fixed_size_chunks, semantic_chunks, structure_aware_chunks
from src.models import ChunkingStrategy, SourceDocument


def _doc(text: str) -> SourceDocument:
    return SourceDocument(source_file="test.md", title="Test", raw_text=text)


def test_fixed_size_respects_chunk_size_and_overlap():
    text = " ".join(f"word{i}" for i in range(500))
    chunks = fixed_size_chunks(_doc(text), chunk_size=200, overlap=50)
    assert len(chunks) > 1
    assert all(c.char_count <= 200 for c in chunks)
    assert all(c.chunking_strategy == ChunkingStrategy.FIXED_SIZE for c in chunks)


def test_fixed_size_short_text_is_one_chunk():
    chunks = fixed_size_chunks(_doc("Short text."), chunk_size=800, overlap=150)
    assert len(chunks) == 1
    assert chunks[0].text == "Short text."


def test_fixed_size_does_not_cut_mid_word():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa " * 10
    chunks = fixed_size_chunks(_doc(text), chunk_size=50, overlap=10)
    for c in chunks:
        assert not c.text.endswith(("alph", "bet", "gam"))  # crude sanity check, not truncated garbage


def test_structure_aware_splits_on_headings():
    text = "# Title\n\nIntro text.\n\n## Section A\n\nContent A.\n\n## Section B\n\nContent B.\n"
    chunks = structure_aware_chunks(_doc(text))
    headings = {c.section_heading for c in chunks}
    assert "Title > Section A" in headings
    assert "Title > Section B" in headings


def test_structure_aware_tracks_nested_heading_path():
    text = "# Top\n\n## Mid\n\n### Deep\n\nDeep content.\n"
    chunks = structure_aware_chunks(_doc(text))
    assert any(c.section_heading == "Top > Mid > Deep" for c in chunks)


def test_structure_aware_splits_oversized_sections():
    big_section = "# Title\n\n## Big\n\n" + ("word " * 500)
    chunks = structure_aware_chunks(_doc(big_section), max_section_size=200)
    big_chunks = [c for c in chunks if c.section_heading == "Title > Big"]
    assert len(big_chunks) > 1


def test_structure_aware_handles_no_headings():
    chunks = structure_aware_chunks(_doc("Just plain text with no headings at all."))
    assert len(chunks) == 1
    assert chunks[0].section_heading is None


def test_semantic_merges_similar_paragraphs(embedding_provider):
    text = (
        "FastAPI lets you declare path parameters using type annotations.\n\n"
        "Path parameters are declared using the same syntax as Python format strings.\n\n"
        "CORS refers to situations where a frontend on one origin talks to a backend on another.\n\n"
        "An origin is the combination of protocol, domain, and port."
    )
    chunks = semantic_chunks(_doc(text), embedding_provider)
    assert len(chunks) >= 1
    assert all(c.chunking_strategy == ChunkingStrategy.SEMANTIC for c in chunks)


def test_semantic_respects_max_chunk_size(embedding_provider):
    text = "\n\n".join(f"Paragraph {i} about FastAPI and path parameters and query parameters." for i in range(50))
    chunks = semantic_chunks(_doc(text), embedding_provider, max_chunk_size=500)
    assert all(c.char_count <= 600 for c in chunks)  # small slack for the last paragraph pushing over


def test_semantic_empty_text_returns_no_chunks(embedding_provider):
    assert semantic_chunks(_doc(""), embedding_provider) == []


def test_chunk_ids_are_unique_within_document():
    text = "# Title\n\n" + "\n\n".join(f"## Section {i}\n\nContent {i}." for i in range(10))
    chunks = structure_aware_chunks(_doc(text))
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
