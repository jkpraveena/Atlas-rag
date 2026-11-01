"""Three chunking strategies, switchable per the build guide:

  fixed_size:       baseline sliding window over raw characters, with overlap.
  structure_aware:   splits on markdown headers first, recursing into
                       fixed-size sub-chunks only for sections too large to
                       keep whole -- preserves the heading hierarchy as
                       metadata on every chunk either way.
  semantic:            embeds each paragraph and merges adjacent paragraphs
                         while they stay topically similar to the chunk's
                         running centroid, splitting on topic shifts.

Every chunk carries which strategy produced it, so the eval framework can
run the same golden questions against all three and report which wins on
which metric (see eval.py).
"""
from __future__ import annotations

import re
from typing import List, Optional

from src.embeddings import EmbeddingProvider
from src.models import ChunkingStrategy, DocumentChunk, SourceDocument
from src.text_utils import cosine_similarity, split_paragraphs

DEFAULT_CHUNK_SIZE = 800
DEFAULT_OVERLAP = 150
STRUCTURE_MAX_SECTION_SIZE = 1200
# Calibrated empirically against MockEmbeddingProvider's similarity
# distribution on this corpus (swept 0.0-0.12; higher thresholds fragmented
# aggressively -- 1760 chunks at 0.12 vs 510 at 0.0 -- because the hashing
# embedding's bag-of-words vectors rarely have strongly positive similarity
# between adjacent prose paragraphs even on-topic). Re-tune this when
# switching to a real embedding provider, whose similarity scores follow a
# different distribution.
SEMANTIC_SIMILARITY_THRESHOLD = 0.0
SEMANTIC_MAX_CHUNK_SIZE = 1500

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def _make_chunk(doc: SourceDocument, text: str, index: int, strategy: ChunkingStrategy, heading: Optional[str]) -> DocumentChunk:
    return DocumentChunk(
        id=f"{doc.source_file}::{strategy.value}::{index}",
        text=text.strip(),
        source_file=doc.source_file,
        title=doc.title,
        section_heading=heading,
        chunk_index=index,
        chunking_strategy=strategy,
    )


def _sliding_window(text: str, chunk_size: int, overlap: int) -> List[str]:
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    step = max(chunk_size - overlap, 1)
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # break on the nearest preceding whitespace so we don't cut mid-word
            boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start += step
    return chunks


def fixed_size_chunks(doc: SourceDocument, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> List[DocumentChunk]:
    pieces = _sliding_window(doc.raw_text, chunk_size, overlap)
    return [_make_chunk(doc, p, i, ChunkingStrategy.FIXED_SIZE, heading=None) for i, p in enumerate(pieces)]


def _split_by_headings(text: str):
    """Yields (heading_path, section_text) preserving header hierarchy."""
    matches = list(_HEADING_PATTERN.finditer(text))
    if not matches:
        yield None, text
        return

    stack: List[tuple] = []  # (level, title)
    preamble_end = matches[0].start()
    if text[:preamble_end].strip():
        yield None, text[:preamble_end]

    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        stack = [s for s in stack if s[0] < level] + [(level, title)]
        heading_path = " > ".join(t for _, t in stack)

        section_start = m.end()
        section_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[section_start:section_end].strip()
        if section_text:
            yield heading_path, section_text


def structure_aware_chunks(doc: SourceDocument, max_section_size: int = STRUCTURE_MAX_SECTION_SIZE) -> List[DocumentChunk]:
    chunks = []
    index = 0
    for heading, section_text in _split_by_headings(doc.raw_text):
        if len(section_text) <= max_section_size:
            chunks.append(_make_chunk(doc, section_text, index, ChunkingStrategy.STRUCTURE_AWARE, heading))
            index += 1
        else:
            # recurse into fixed-size sub-chunks, but keep the section heading
            for piece in _sliding_window(section_text, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP):
                chunks.append(_make_chunk(doc, piece, index, ChunkingStrategy.STRUCTURE_AWARE, heading))
                index += 1
    return chunks


def semantic_chunks(
    doc: SourceDocument,
    embedding_provider: EmbeddingProvider,
    similarity_threshold: float = SEMANTIC_SIMILARITY_THRESHOLD,
    max_chunk_size: int = SEMANTIC_MAX_CHUNK_SIZE,
) -> List[DocumentChunk]:
    paragraphs = split_paragraphs(doc.raw_text)
    if not paragraphs:
        return []

    embeddings = embedding_provider.embed(paragraphs)

    chunks: List[DocumentChunk] = []
    index = 0
    buffer_paragraphs = [paragraphs[0]]
    buffer_embedding = list(embeddings[0])
    buffer_count = 1

    def flush():
        nonlocal index
        text = "\n\n".join(buffer_paragraphs)
        chunks.append(_make_chunk(doc, text, index, ChunkingStrategy.SEMANTIC, heading=None))
        index += 1

    for para, emb in zip(paragraphs[1:], embeddings[1:]):
        centroid = [v / buffer_count for v in buffer_embedding]
        similarity = cosine_similarity(emb, centroid)
        candidate_size = sum(len(p) for p in buffer_paragraphs) + len(para)

        if similarity >= similarity_threshold and candidate_size <= max_chunk_size:
            buffer_paragraphs.append(para)
            buffer_embedding = [a + b for a, b in zip(buffer_embedding, emb)]
            buffer_count += 1
        else:
            flush()
            buffer_paragraphs = [para]
            buffer_embedding = list(emb)
            buffer_count = 1

    flush()
    return chunks


CHUNKERS = {
    ChunkingStrategy.FIXED_SIZE: fixed_size_chunks,
    ChunkingStrategy.STRUCTURE_AWARE: structure_aware_chunks,
}


def chunk_document(doc: SourceDocument, strategy: ChunkingStrategy, embedding_provider: Optional[EmbeddingProvider] = None) -> List[DocumentChunk]:
    if strategy == ChunkingStrategy.SEMANTIC:
        if embedding_provider is None:
            raise ValueError("semantic chunking requires an embedding_provider")
        return semantic_chunks(doc, embedding_provider)
    return CHUNKERS[strategy](doc)
