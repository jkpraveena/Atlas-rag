"""Grounded answer generation with inline [1][2]-style citations.

`MockGenerationProvider` is an extractive QA system, not a placeholder --
extractive QA (pull the most relevant sentence per source rather than
generate new prose) is a legitimate, well-established approach in its own
right, and it has a structural property generative answers don't: it is
*incapable* of hallucinating a claim the source text doesn't contain,
because every word in its answer is copied, not generated. `OpenAIProvider`
/ `AnthropicProvider` produce real synthesized prose under a system prompt
that requires citing every claim and explicitly permits "I don't know."
"""
from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from typing import List, Tuple

from src.models import Citation, RetrievalCandidate
from src.text_utils import overlap_ratio

SYSTEM_PROMPT = """\
You are a documentation assistant. Answer the user's question using ONLY the numbered \
source passages provided below.

Rules:
- Cite the source for every factual claim using its marker, e.g. [1], [2]. A claim with \
no citation is not acceptable.
- If the passages don't contain enough information to answer, say so explicitly rather \
than guessing or using outside knowledge.
- Do not cite a source for something it doesn't actually say.
- Be concise and direct.
"""


class GenerationProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, question: str, candidates: List[RetrievalCandidate]) -> Tuple[str, List[Citation]]: ...


def _build_citations(candidates: List[RetrievalCandidate]) -> List[Citation]:
    return [
        Citation(marker=f"[{i}]", chunk_id=c.chunk.id, source_file=c.chunk.source_file, section_heading=c.chunk.section_heading)
        for i, c in enumerate(candidates, start=1)
    ]


class MockGenerationProvider(GenerationProvider):
    name = "mock-extractive"

    @staticmethod
    def _clean_text(text: str) -> str:
        """Remove HTML tags and normalize whitespace in documentation text."""
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _sentences(text: str) -> List[str]:
        """Extract readable prose sentences while preserving source wording."""
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())

        return [
            sentence.strip()
            for sentence in sentences
            if len(sentence.split()) >= 4
            and not sentence.strip().startswith(("http://", "https://"))
        ]
    def generate(
        self,
        question: str,
        candidates: List[RetrievalCandidate],
    ) -> Tuple[str, List[Citation]]:
        refusal = (
            "I don't have enough information in the indexed documentation to answer this."
        )

        if not candidates:
            return refusal, []

        # Score individual sentences rather than entire chunks.
        selected = []

        for candidate in candidates:
            cleaned_text = self._clean_text(candidate.chunk.text)
            sentences = self._sentences(cleaned_text)

            if not sentences:
                continue

            scored_sentences = [
                (sentence, overlap_ratio(question, sentence))
                for sentence in sentences
            ]

            best_sentence, best_score = max(
                scored_sentences,
                key=lambda item: item[1],
            )

            # Reject sentences with very little lexical relevance.
            if best_score < 0.10:
                continue

            selected.append((candidate, best_sentence, best_score))

        if not selected:
            return refusal, []

        # Prefer stronger matches and avoid repeating the same sentence.
        selected.sort(key=lambda item: item[2], reverse=True)

        answer_parts = []
        citations = []
        seen_sentences = set()

        for candidate, sentence, score in selected:
            normalized_sentence = sentence.lower().strip()

            if normalized_sentence in seen_sentences:
                continue

            seen_sentences.add(normalized_sentence)

            marker = f"[{len(citations) + 1}]"

            citations.append(
                Citation(
                    marker=marker,
                    chunk_id=candidate.chunk.id,
                    source_file=candidate.chunk.source_file,
                    section_heading=candidate.chunk.section_heading,
                )
            )

            answer_parts.append(f"{sentence} {marker}")

            if len(answer_parts) == 3:
                break

        if not answer_parts:
            return refusal, []

        return " ".join(answer_parts), citations
    

def _format_context(candidates: List[RetrievalCandidate], citations: List[Citation]) -> str:
    blocks = []
    for citation, candidate in zip(citations, candidates):
        heading = f" ({candidate.chunk.section_heading})" if candidate.chunk.section_heading else ""
        blocks.append(f"{citation.marker} Source: {candidate.chunk.source_file}{heading}\n{candidate.chunk.text}")
    return "\n\n".join(blocks)


class OpenAIGenerationProvider(GenerationProvider):
    name = "openai"

    def __init__(self, api_key: str = None, model: str = None):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
        self._model = model or os.environ.get("GENERATION_MODEL", "gpt-4o-mini")

    def generate(self, question: str, candidates: List[RetrievalCandidate]) -> Tuple[str, List[Citation]]:
        citations = _build_citations(candidates)
        context = _format_context(candidates, citations)
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Sources:\n\n{context}\n\nQuestion: {question}"},
            ],
        )
        return response.choices[0].message.content, citations


class AnthropicGenerationProvider(GenerationProvider):
    name = "anthropic"

    def __init__(self, api_key: str = None, model: str = None):
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self._model = model or os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    def generate(self, question: str, candidates: List[RetrievalCandidate]) -> Tuple[str, List[Citation]]:
        citations = _build_citations(candidates)
        context = _format_context(candidates, citations)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Sources:\n\n{context}\n\nQuestion: {question}"}],
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        return text, citations


def get_generation_provider(name: str = None) -> GenerationProvider:
    name = name or os.environ.get("GENERATION_PROVIDER")
    if name == "openai":
        return OpenAIGenerationProvider()
    if name == "anthropic":
        return AnthropicGenerationProvider()
    if name == "mock":
        return MockGenerationProvider()
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIGenerationProvider()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicGenerationProvider()
    return MockGenerationProvider()
