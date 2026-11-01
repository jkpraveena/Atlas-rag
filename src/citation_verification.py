"""Verifies that each [N] citation in a generated answer is actually
supported by the chunk it points to -- the quality layer most RAG systems
skip entirely, per the build guide. Runs regardless of which generation
provider produced the answer, including the mock (which is structurally
incapable of failing this check, since it only ever copies from the cited
source -- but the check runs anyway rather than special-casing it).
"""
from __future__ import annotations

import json
import os
import re
from typing import List

from src.models import Citation, RetrievalCandidate
from src.text_utils import overlap_ratio

SUPPORT_THRESHOLD = 0.3
_MARKER_PATTERN = re.compile(r"\[(\d+)\]")


def claims_by_marker(answer_text: str) -> dict:
    """Maps each '[N]' marker to the text span it terminates -- i.e. the
    text between the previous marker (or start of answer) and this one.

    Deliberately NOT sentence-splitting the whole answer first: when the
    cited span itself ends in terminal punctuation ("...an `int`. [5]"),
    a naive `re.split(r"(?<=[.!?])\s+", ...)` sentence splitter breaks
    *between* the period and the marker, leaving the marker alone in its
    own empty "sentence" with no claim text attached to it at all. Splitting
    on the markers themselves instead of on sentence punctuation sidesteps
    that failure mode entirely -- found by inspecting a real verification
    result where a valid, well-formed citation was incorrectly reported as
    "marker not found."
    """
    parts = re.split(r"(\[\d+\])", answer_text)
    claims = {}
    pending_text = ""
    for part in parts:
        if _MARKER_PATTERN.fullmatch(part):
            claims[part] = pending_text.strip()
            pending_text = ""
        else:
            pending_text += part
    return claims


def _sentence_for_marker(answer_text: str, marker: str) -> str:
    return claims_by_marker(answer_text).get(marker, "")


def verify_citations_lexical(answer_text: str, citations: List[Citation], candidates: List[RetrievalCandidate]) -> List[Citation]:
    chunk_by_id = {c.chunk.id: c.chunk for c in candidates}
    for citation in citations:
        claim = _sentence_for_marker(answer_text, citation.marker)
        chunk = chunk_by_id.get(citation.chunk_id)
        if not claim or chunk is None:
            citation.supported = None
            citation.verification_note = "citation marker not found in answer text (unused source)"
            continue
        ratio = overlap_ratio(claim, chunk.text)
        citation.supported = ratio >= SUPPORT_THRESHOLD
        citation.verification_note = f"lexical overlap {ratio:.2f} between claim and cited source"
    return citations


def verify_citations_llm(answer_text: str, citations: List[Citation], candidates: List[RetrievalCandidate], provider_name: str = None) -> List[Citation]:
    chunk_by_id = {c.chunk.id: c.chunk for c in candidates}
    pairs = []
    for citation in citations:
        claim = _sentence_for_marker(answer_text, citation.marker)
        chunk = chunk_by_id.get(citation.chunk_id)
        if claim and chunk is not None:
            pairs.append((citation, claim, chunk.text))

    if not pairs:
        return citations

    provider_name = provider_name or os.environ.get("CITATION_PROVIDER") or (
        "openai" if os.environ.get("OPENAI_API_KEY") else "anthropic"
    )
    listing = "\n".join(f"{i}. Claim: {claim!r}\n   Source: {text[:400]!r}" for i, (_, claim, text) in enumerate(pairs))
    prompt = (
        f"For each claim/source pair below, answer whether the source actually supports the claim.\n\n{listing}\n\n"
        f'Respond with ONLY a JSON array of {len(pairs)} booleans, e.g. [true, false, true].'
    )

    try:
        if provider_name == "openai":
            from openai import OpenAI

            response = OpenAI().chat.completions.create(
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
        else:
            from anthropic import Anthropic

            response = Anthropic().messages.create(
                model=os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"), max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            content = "".join(b.text for b in response.content if hasattr(b, "text"))

        verdicts = json.loads(content[content.find("["): content.rfind("]") + 1])
        for (citation, _, _), verdict in zip(pairs, verdicts):
            citation.supported = bool(verdict)
            citation.verification_note = "LLM-as-judge verification"
    except Exception as exc:  # noqa: BLE001 - fall back to the lexical check rather than losing verification entirely
        for citation, claim, source_text in pairs:
            ratio = overlap_ratio(claim, source_text)
            citation.supported = ratio >= SUPPORT_THRESHOLD
            citation.verification_note = f"LLM verification failed ({exc}); fell back to lexical overlap {ratio:.2f}"

    return citations


def get_citation_verifier(name: str = None):
    name = name or os.environ.get("CITATION_VERIFIER")
    if name == "llm":
        return verify_citations_llm
    if name == "mock":
        return verify_citations_lexical
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"):
        return verify_citations_llm
    return verify_citations_lexical
