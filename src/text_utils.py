"""Small, dependency-free text helpers shared by chunking, the mock
embedding provider, and the mock reranker/judge. Not linguistically
rigorous by design -- documented as approximate, same philosophy as the
rest of this line of projects' offline-mode code."""
from __future__ import annotations

import math
import re

_STOPWORDS = {
    "the", "a", "an", "to", "of", "and", "is", "are", "for", "on", "in",
    "my", "i", "me", "it", "was", "with", "this", "that", "please", "can",
    "you", "your", "have", "has", "be", "as", "at", "or", "we", "us", "its",
    "by", "from", "will", "would", "should", "could", "than", "then",
    "so", "if", "but", "not", "no", "do", "does", "did", "their", "they",
    "what", "why", "how", "when", "where", "who", "which", "whether",
}


def tokenize(text: str):
    return re.findall(r"[a-zA-Z0-9_]+(?:'[a-zA-Z]+)*", text.lower())


def stem(token: str) -> str:
    if token.endswith("'s"):
        token = token[:-2]
    if len(token) > 5 and token.endswith("ing"):
        token = token[:-3]
    elif len(token) > 4 and token.endswith("ed"):
        token = token[:-2]
    elif len(token) > 4 and token.endswith("es"):
        token = token[:-2]
    elif len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        token = token[:-1]
    return token


def content_tokens(text: str) -> set:
    return {stem(t) for t in tokenize(text)} - _STOPWORDS


def cosine_similarity(a, b) -> float:
    if len(a) != len(b):
        raise ValueError("vectors must be the same length")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def overlap_ratio(a: str, b: str) -> float:
    """Measure token overlap using precision and recall.

    Returns 0 when either text has no meaningful content tokens.
    """
    a_tokens = content_tokens(a)
    b_tokens = content_tokens(b)

    if not a_tokens or not b_tokens:
        return 0.0

    intersection = len(a_tokens & b_tokens)

    precision = intersection / len(b_tokens)
    recall = intersection / len(a_tokens)

    if precision + recall == 0:
        return 0.0

    return 2 * precision * recall / (precision + recall)


def split_paragraphs(text: str):
    paragraphs = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in paragraphs if p.strip()]
