"""Typed data contracts shared across the whole pipeline: ingestion,
retrieval, generation, citation verification, and evaluation."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ChunkingStrategy(str, Enum):
    FIXED_SIZE = "fixed_size"
    STRUCTURE_AWARE = "structure_aware"
    SEMANTIC = "semantic"


class Difficulty(str, Enum):
    LOOKUP = "lookup"
    MULTI_HOP = "multi_hop"
    NO_ANSWER = "no_answer"
    AMBIGUOUS = "ambiguous"


# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------

class SourceDocument(BaseModel):
    source_file: str
    title: str
    raw_text: str


class DocumentChunk(BaseModel):
    id: str
    text: str
    source_file: str
    title: str
    section_heading: Optional[str] = None
    chunk_index: int
    chunking_strategy: ChunkingStrategy
    char_count: int = 0

    def model_post_init(self, __context) -> None:
        if not self.char_count:
            self.char_count = len(self.text)


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------

class RetrievalCandidate(BaseModel):
    chunk: DocumentChunk
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    dense_rank: Optional[int] = None
    sparse_rank: Optional[int] = None
    rrf_score: Optional[float] = None
    rerank_score: Optional[float] = None


# --------------------------------------------------------------------------
# Generation / citations
# --------------------------------------------------------------------------

class Citation(BaseModel):
    marker: str  # e.g. "[1]"
    chunk_id: str
    source_file: str
    section_heading: Optional[str] = None
    supported: Optional[bool] = None
    verification_note: str = ""


class AnswerConfidence(BaseModel):
    retrieval_confidence: float = Field(ge=0, le=1)
    citation_coverage: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    composite: float = Field(ge=0, le=1)


class AgentStep(BaseModel):
    agent: str
    summary: str
    latency_ms: float = 0.0


class AskRequest(BaseModel):
    question: str
    top_k: int = 5
    use_hybrid: bool = True
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.STRUCTURE_AWARE
    dense_weight: float = 0.7


class AskResult(BaseModel):
    query_id: str
    question: str
    answer_text: str
    citations: List[Citation]
    confidence: AnswerConfidence
    retrieved: List[RetrievalCandidate]
    used_hybrid: bool
    chunking_strategy: ChunkingStrategy
    generation_provider: str
    agent_trace: List[AgentStep]
    total_latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.now)


# --------------------------------------------------------------------------
# Golden eval dataset
# --------------------------------------------------------------------------

class GoldenQAPair(BaseModel):
    id: str
    question: str
    expected_answer: str
    source_files: List[str] = Field(default_factory=list)
    difficulty: Difficulty
    notes: str = ""


class GoldenDataset(BaseModel):
    dataset_version: str
    created_at: datetime
    description: str = ""
    cases: List[GoldenQAPair]


class EvalCaseResult(BaseModel):
    qa_id: str
    difficulty: Difficulty
    question: str
    generated_answer: str
    expected_answer: str
    correctness_score: float = Field(ge=0, le=1)
    faithfulness_score: float = Field(ge=0, le=1)
    retrieval_relevance_score: float = Field(ge=0, le=1)
    citation_accuracy_score: float = Field(ge=0, le=1)
    passed: bool


class EvalRunSummary(BaseModel):
    run_id: str
    chunking_strategy: ChunkingStrategy
    timestamp: datetime
    dataset_version: str
    results: List[EvalCaseResult]
    pass_rate: float = 0.0
    avg_correctness: float = 0.0
    avg_faithfulness: float = 0.0
    avg_retrieval_relevance: float = 0.0
    avg_citation_accuracy: float = 0.0
    per_difficulty_pass_rate: Dict[str, float] = Field(default_factory=dict)


class ChunkingComparisonReport(BaseModel):
    runs: List[EvalRunSummary]
    winner_by_metric: Dict[str, str] = Field(default_factory=dict)
