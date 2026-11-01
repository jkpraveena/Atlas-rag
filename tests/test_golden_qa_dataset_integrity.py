from pathlib import Path

from src.golden_qa_loader import load_golden_qa
from src.models import Difficulty

CORPUS_DIR = Path(__file__).resolve().parent.parent / "docs_corpus"


def test_minimum_case_count():
    dataset = load_golden_qa()
    assert len(dataset.cases) >= 30


def test_case_ids_are_unique():
    dataset = load_golden_qa()
    ids = [c.id for c in dataset.cases]
    assert len(ids) == len(set(ids))


def test_all_difficulties_represented():
    dataset = load_golden_qa()
    seen = {c.difficulty for c in dataset.cases}
    assert seen == set(Difficulty)


def test_no_answer_cases_have_no_source_files():
    dataset = load_golden_qa()
    for c in dataset.cases:
        if c.difficulty == Difficulty.NO_ANSWER:
            assert c.source_files == [], f"{c.id} is no_answer but lists source files"


def test_lookup_and_multi_hop_cases_have_source_files():
    dataset = load_golden_qa()
    for c in dataset.cases:
        if c.difficulty in (Difficulty.LOOKUP, Difficulty.MULTI_HOP):
            assert c.source_files, f"{c.id} ({c.difficulty.value}) has no source files"


def test_multi_hop_cases_reference_at_least_two_sources():
    dataset = load_golden_qa()
    for c in dataset.cases:
        if c.difficulty == Difficulty.MULTI_HOP:
            assert len(c.source_files) >= 2, f"{c.id} is multi_hop but only cites {c.source_files}"


def test_referenced_source_files_actually_exist_in_the_corpus():
    dataset = load_golden_qa()
    existing = {p.name for p in CORPUS_DIR.glob("*.md")}
    for c in dataset.cases:
        for f in c.source_files:
            assert f in existing, f"{c.id} references {f}, which isn't in docs_corpus/"


def test_no_empty_questions_or_answers():
    dataset = load_golden_qa()
    for c in dataset.cases:
        assert c.question.strip()
        assert c.expected_answer.strip()
