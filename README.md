Hybrid RAG Search Pipeline

A retrieval-augmented generation (RAG) system for searching technical documentation using hybrid retrieval, configurable document chunking, evidence-grounded answer generation, citation verification, and retrieval-confidence evaluation.

The system combines dense vector search using ChromaDB with sparse keyword retrieval using BM25. Reciprocal Rank Fusion (RRF) combines the results, followed by reranking, grounded answer generation, and citation verification. A confidence-based retrieval gate prevents the system from generating answers when sufficient supporting evidence is unavailable.

Key Features

* Hybrid Retrieval: Combines dense vector search and BM25 sparse keyword retrieval using Reciprocal Rank Fusion.
* Multiple Chunking Strategies: Implements fixed-size, structure-aware, and semantic chunking with an automated evaluation framework.
* Grounded Answer Generation: Generates answers using retrieved document context with inline source citations.
* Citation Verification: Validates individual citations against their corresponding source documents.
* Retrieval Confidence Gating: Evaluates retrieval quality before generation and abstains when supporting evidence is insufficient.
* LangGraph Orchestration: Coordinates retrieval, fusion, reranking, generation, and verification stages.
* Vector Database: Uses ChromaDB for persistent vector storage and similarity search.
* REST API: Exposes retrieval and evaluation functionality through FastAPI.
* Interactive Interface: Provides document querying, retrieval comparison, and evaluation through Streamlit.
* Automated Testing: Includes unit and integration tests covering core pipeline components.

Dataset and Knowledge Corpus

The system uses FastAPI’s official tutorial documentation as its knowledge corpus.

* Source: fastapi/fastapi
* Version: 0.104.1
* License: MIT
* Corpus: 28 Markdown documentation files.
* Golden Evaluation Dataset: 37 manually authored question-answer pairs.

The corpus is retrieved using scripts/fetch_docs.py. The script resolves embedded code references and produces self-contained Markdown documents.

The evaluation dataset in golden_qa/qa_v1.json contains:

Question Category	Count
Direct information retrieval	15
Multi-hop questions	8
Unanswerable questions	8
Ambiguous questions	6
Total	37

The expected answers are manually prepared and checked against the source documentation.

See docs_corpus/MANIFEST.md for documentation provenance and source details.

Architecture

The pipeline follows a modular retrieval and generation architecture.

                 User Query
                      |
                      v
              Query Processing
                      |
             +--------+--------+
             |                 |
             v                 v
       Dense Retrieval    Sparse Retrieval
          ChromaDB             BM25
             |                 |
             +--------+--------+
                      |
                      v
           Reciprocal Rank Fusion
                (RRF: 0.7/0.3)
                      |
                      v
                  Reranking
                      |
                      v
             Confidence Evaluation
                      |
              +-------+-------+
              |               |
          Sufficient       Insufficient
           Evidence          Evidence
              |               |
              v               v
        Answer Generation   Abstention
              |
              v
       Citation Verification
              |
              v
       Confidence Scoring
              |
              v
          Final Answer

Retrieval

The system implements two complementary retrieval methods:

Dense Retrieval

* Uses ChromaDB for vector storage.
* Performs cosine-similarity-based retrieval.
* Supports semantic matching between queries and document chunks.

Sparse Retrieval

* Uses BM25 for keyword-based document retrieval.
* Captures exact terms and technical keywords.
* Complements semantic retrieval when exact terminology matters.

Reciprocal Rank Fusion

Combines the rankings from both retrieval methods using configurable weights. The default configuration assigns 0.7 to dense retrieval and 0.3 to sparse retrieval.

Reranking

Retrieved candidates pass through a reranking stage to improve the relevance of the final context.

The project includes a lexical-overlap implementation for offline execution and an LLM-based reranking option.

Grounded Generation

The generation stage constructs answers using retrieved document context.

Answers include inline citations such as [1] and [2], allowing users to trace individual claims back to their supporting documents.

Citation Verification

Each citation is checked against its corresponding source document to evaluate whether the cited content supports the associated claim.

Retrieval Confidence

Before generating an answer, the system evaluates retrieval quality.

The confidence mechanism considers:

* Retrieval relevance.
* Citation coverage.
* Answer completeness.

If retrieval confidence falls below the configured threshold, the system abstains instead of generating an unsupported answer.

Chunking Strategies and Evaluation

Three document chunking strategies are implemented:

Strategy	Description
Fixed-size	Divides documents into chunks using predefined size and overlap settings.
Structure-aware	Uses document structure, headings, and content boundaries to create chunks.
Semantic	Uses semantic similarity to determine appropriate chunk boundaries.

The evaluation framework compares these strategies against the 37-question golden dataset.

Metrics include:

* Pass rate.
* Answer correctness.
* Faithfulness.
* Retrieval relevance.
* Citation accuracy.

The comparison identifies the best-performing strategy for each evaluation metric.

Observed offline evaluation results:

Strategy	Pass Rate	Correctness	Faithfulness	Citation Accuracy
Fixed-size	0.24	0.32	0.62	0.56
Structure-aware	0.35	0.35	0.73	0.80
Semantic	0.19	0.27	0.70	0.71

Structure-aware chunking performed best across the reported metrics in this execution.

These results are specific to the current offline configuration and should not be interpreted as universal performance rankings.

Run the comparison again after switching to real embedding and generation providers to evaluate how the results change.

Hallucination-Aware Retrieval

An important design consideration is determining when the system should answer and when it should abstain.

During development, the initial implementation attempted to generate an answer even when retrieval returned insufficient evidence. This resulted in unsupported responses for unanswerable evaluation questions.

The retrieval-confidence mechanism was introduced to address this problem.

The configured confidence threshold is 0.25.

When retrieval confidence falls below the threshold, the system returns an insufficient-information response without invoking the generation stage.

This approach:

* Reduces unsupported answers.
* Avoids unnecessary generation calls.
* Improves handling of unanswerable questions.
* Makes retrieval quality an explicit part of answer generation.

The threshold is calibrated against the golden evaluation dataset and is not guaranteed to generalize to other corpora.

Technology Stack

Component	Technology
Language	Python
API Framework	FastAPI
Frontend	Streamlit
Orchestration	LangGraph
Vector Database	ChromaDB
Sparse Retrieval	BM25
Ranking	Reciprocal Rank Fusion
Embeddings	Mock hashing / OpenAI
Reranking	Lexical / LLM-based
Generation	Extractive / OpenAI / Anthropic
Evaluation	Custom golden-set evaluation
Testing	pytest
Containerization	Docker, Docker Compose
Storage	SQLite

Offline and Real Provider Configurations

The project supports offline mock implementations and real provider integrations.

The default configuration uses:

Component	Offline Implementation
Embeddings	Hashing-based vectorization
Reranking	Lexical overlap
Generation	Extractive generation
Vector Storage	ChromaDB

The hashing-based embedding implementation provides deterministic, vocabulary-dependent vectors, allowing retrieval experiments without external API dependencies.

Real provider integrations are also available for embeddings, reranking, generation, and citation verification.

Getting Started

Prerequisites

* Python 3.10+
* pip
* Git

Installation

Clone the repository:

git clone https://github.com/YOUR_USERNAME/rag-hybrid-search-pipeline.git
cd rag-hybrid-search-pipeline

Create and activate a virtual environment:

python3 -m venv .venv
source .venv/bin/activate

Install dependencies:

pip install -r requirements.txt

Document Ingestion

Process the documentation corpus and index all three chunking strategies:

python scripts/ingest.py

This performs document loading, chunking, embedding, deduplication, and vector indexing.

Run the Demonstration

python scripts/run_demo.py

The demonstration covers:

1. Grounded answer generation with citations.
2. Hybrid retrieval versus dense-only retrieval.
3. Handling questions outside the indexed corpus.
4. Comparison of the three chunking strategies.

Run Automated Tests

pytest tests/ -v

The test suite covers retrieval, chunking, confidence evaluation, citation verification, API endpoints, and other pipeline components.

Start the FastAPI Server

uvicorn src.api:app --reload

API documentation:

http://localhost:8000/docs

Start the Streamlit Application

Open another terminal:

source .venv/bin/activate
streamlit run streamlit_app.py

Application:

http://localhost:8501

API Endpoints

Method	Endpoint	Description
POST	/v1/ask	Submit a question to the RAG pipeline
GET	/v1/documents	Retrieve indexed documents
POST	/v1/ingest	Ingest and index documents
GET	/v1/queries/{id}	Retrieve query history by ID
GET	/v1/queries	Retrieve query history
GET	/v1/eval/run	Execute evaluation for a chunking strategy
GET	/v1/eval/chunking-comparison	Compare all chunking strategies

Example request:

{
  "question": "What is an origin in the context of CORS?",
  "chunking_strategy": "structure_aware",
  "use_hybrid": true
}

Docker Deployment

The project supports containerized execution using Docker Compose.

docker compose up --build

The Docker configuration includes:

* An initialization service for document ingestion.
* A FastAPI backend.
* A Streamlit frontend.
* Shared storage for the indexed document collections.

Optional provider credentials can be configured through environment variables in a local .env file.

Engineering Decisions

Hybrid retrieval instead of dense-only search

Semantic similarity does not always capture exact technical terminology. BM25 complements dense retrieval by matching specific terms, while Reciprocal Rank Fusion combines their rankings.

Multiple chunking strategies

Different chunking approaches can produce different retrieval and answer-quality outcomes. The evaluation framework measures these differences instead of assuming one strategy is universally optimal.

Citation verification

Generated citations should not automatically be trusted. The verification stage checks whether individual cited sources support their associated claims.

Confidence-based abstention

The system evaluates retrieval sufficiency before generation. This prevents unnecessary generation when the indexed corpus does not contain adequate supporting information.

Offline-first architecture

Mock implementations allow the complete pipeline to be tested without external API credentials. Real provider integrations can be enabled when needed.

Per-document deduplication

Deduplication is scoped to individual source documents to reduce redundant chunks while avoiding expensive corpus-wide comparisons.

Asynchronous orchestration and API execution

The API separates synchronous evaluation handlers from asynchronous question-answering handlers to avoid nested event-loop execution issues.

Project Structure

rag-hybrid-search-pipeline/
│
├── src/
│   ├── models.py
│   ├── document_loader.py
│   ├── chunking.py
│   ├── embeddings.py
│   ├── vector_store.py
│   ├── bm25_index.py
│   ├── fusion.py
│   ├── reranker.py
│   ├── generation.py
│   ├── citation_verification.py
│   ├── confidence.py
│   ├── ingest.py
│   ├── graph.py
│   ├── eval.py
│   ├── storage.py
│   └── api.py
│
├── scripts/
│   ├── fetch_docs.py
│   ├── build_golden_qa.py
│   ├── ingest.py
│   ├── run_chunking_comparison.py
│   └── run_demo.py
│
├── docs_corpus/
├── golden_qa/
│   └── qa_v1.json
│
├── tests/
├── data/
│
├── streamlit_app.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md

Future Improvements

* Evaluate retrieval performance using additional technical documentation datasets.
* Improve embedding quality using domain-appropriate embedding models.
* Experiment with cross-encoder reranking.
* Expand evaluation with more diverse and challenging queries.
* Improve confidence calibration across different document collections.
* Add distributed caching and scalable storage options.
* Integrate additional observability and performance monitoring.

License

The project code is licensed under the MIT License.

The documentation corpus is sourced from the MIT-licensed FastAPI repository, version 0.104.1.

Refer to LICENSE and docs_corpus/MANIFEST.md for licensing and source details.
