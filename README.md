**Hybrid RAG Search Pipeline**

A modular Retrieval-Augmented Generation (RAG) system that combines dense vector search, sparse keyword retrieval, document reranking, grounded answer generation, citation verification, and retrieval-confidence evaluation.

Built using Python, LangGraph, ChromaDB, BM25, FastAPI, and Streamlit, the system explores practical approaches to improving retrieval relevance, answer reliability, and hallucination prevention.

**Key Features**

* Hybrid Retrieval: Combines dense vector search and BM25 sparse keyword retrieval using Reciprocal Rank Fusion (RRF).
* Configurable Chunking: Implements fixed-size, structure-aware, and semantic chunking strategies.
* Reranking: Reorders retrieved candidates based on relevance.
* Grounded Generation: Generates answers using retrieved document context with inline citations.
* Citation Verification: Validates individual citations against their corresponding source documents.
* Confidence-Based Abstention: Prevents answer generation when retrieved evidence is insufficient.
* LangGraph Orchestration: Coordinates retrieval, fusion, reranking, generation, and verification.
* Vector Storage: Uses ChromaDB for persistent vector indexing and similarity search.
* Evaluation Framework: Compares retrieval and answer quality across different chunking strategies.
* REST API: Exposes pipeline functionality through FastAPI.
* Interactive Interface: Provides document querying, retrieval comparison, and evaluation through Streamlit.
* Automated Testing: Includes unit and integration tests using pytest.

**Knowledge Corpus**

The system uses the official FastAPI tutorial documentation as its knowledge corpus.

* Source: FastAPI Repository
* Version: 0.104.1
* License: MIT
* Documents: 28 Markdown files
* Evaluation Dataset: 37 manually authored question-answer pairs

The documentation is collected using scripts/fetch_docs.py, which also resolves embedded code references to produce self-contained Markdown documents.

The golden evaluation dataset contains:

Category	Questions
Direct information retrieval	15
Multi-hop questions	8
Unanswerable questions	8
Ambiguous questions	6
Total	37

Expected answers are manually prepared and checked against the source documentation.

Refer to docs_corpus/MANIFEST.md for source details and documentation provenance.

**System Architecture**

                   User Query
                       |
                       v
                Query Processing
                       |
              +--------+--------+
              |                 |
              v                 v
        Dense Retrieval    Sparse Retrieval
          ChromaDB              BM25
              |                 |
              +--------+--------+
                       |
                       v
             Reciprocal Rank Fusion
                  (RRF)
                       |
                       v
                   Reranking
                       |
                       v
              Confidence Evaluation
                       |
                +------+------+
                |             |
                v             v
          Sufficient      Insufficient
           Evidence         Evidence
                |             |
                v             v
          Answer Gen.      Abstention
                |
                v
        Citation Verification
                |
                v
        Confidence Scoring
                |
                v
            Final Answer

**Retrieval Pipeline**

1. Dense Retrieval

* Uses ChromaDB for vector storage.
* Performs cosine-similarity-based retrieval.
* Identifies semantically related document chunks.

2. Sparse Retrieval

* Uses BM25 for keyword-based retrieval.
* Captures exact terminology and technical keywords.
* Complements semantic retrieval.

3. Reciprocal Rank Fusion

Combines dense and sparse retrieval rankings using configurable weights.

Default configuration:

* Dense retrieval: 0.7
* Sparse retrieval: 0.3

4. Reranking

Retrieved candidates pass through a reranking stage to improve the relevance of the final context.

The implementation supports lexical-overlap reranking and an LLM-based reranking option.

5. Grounded Answer Generation

Generates answers using retrieved document context and includes inline citations such as [1] and [2].

6. Citation Verification

Checks individual citations against their corresponding source documents to determine whether the cited evidence supports the associated claims.

7. Retrieval Confidence

Evaluates retrieval quality before answer generation.

The confidence mechanism considers:

* Retrieval relevance.
* Citation coverage.
* Answer completeness.

When retrieval confidence falls below the configured threshold, the system abstains instead of generating an unsupported answer.

Chunking Strategies and Evaluation

Three document chunking strategies are implemented:

Strategy	Description
Fixed-size	Divides documents using predefined chunk sizes and overlap.
Structure-aware	Uses headings, paragraphs, and document boundaries.
Semantic	Uses semantic similarity to determine chunk boundaries.

The evaluation framework compares all three strategies against the 37-question golden dataset.

Evaluation metrics include:

* Pass rate
* Answer correctness
* Faithfulness
* Retrieval relevance
* Citation accuracy

Observed Offline Evaluation Results

Strategy	Pass Rate	Correctness	Faithfulness	Citation Accuracy
Fixed-size	0.24	0.32	0.62	0.56
Structure-aware	0.35	0.35	0.73	0.80
Semantic	0.19	0.27	0.70	0.71

Structure-aware chunking performed best across the reported metrics in this execution.

These results are specific to the current offline configuration and should not be interpreted as universal performance rankings.

Hallucination Prevention

The system incorporates a retrieval-confidence gate to determine whether sufficient supporting evidence exists before generating an answer.

During development, the initial implementation attempted to generate answers even when retrieval returned insufficient evidence. This produced unsupported responses for unanswerable questions.

A confidence-based abstention mechanism was introduced to address this limitation.

The configured threshold is 0.25.

When retrieval confidence falls below the threshold, the system returns an insufficient-information response without invoking the generation stage.

This approach:

* Reduces unsupported answers.
* Avoids unnecessary generation calls.
* Improves handling of unanswerable questions.
* Makes retrieval quality an explicit part of answer generation.

The threshold is calibrated against the golden evaluation dataset and may require adjustment for other corpora.

**Technology Stack**

Component	Technology
Programming Language	Python
Backend	FastAPI
Frontend	Streamlit
Orchestration	LangGraph
Vector Database	ChromaDB
Sparse Retrieval	BM25
Ranking	Reciprocal Rank Fusion
Embeddings	Hashing-based / OpenAI
Reranking	Lexical / LLM-based
Generation	Extractive / OpenAI / Anthropic
Evaluation	Custom Golden Dataset
Testing	pytest
Database	SQLite
Containerization	Docker, Docker Compose

Offline and Real Provider Configurations

The project supports offline mock implementations and real provider integrations.

Default offline configuration:

Component	Implementation
Embeddings	Hashing-based vectorization
Reranking	Lexical overlap
Generation	Extractive generation
Vector Storage	ChromaDB

The hashing-based embedding implementation produces deterministic, vocabulary-dependent vectors, allowing retrieval experiments without external API credentials.

Real provider integrations are also available for embeddings, reranking, generation, and citation verification.

**Getting Started**

Prerequisites

* Python 3.10+
* pip
* Git

1. Clone the Repository

git clone https://github.com/jkpraveena/Atlas-rag.git
cd Atlas-rag

2. Create a Virtual Environment

python3 -m venv .venv
source .venv/bin/activate

3. Install Dependencies

pip install -r requirements.txt

4. Ingest Documents

python scripts/ingest.py

This processes the documentation corpus, generates chunks, creates embeddings, performs deduplication, and indexes the documents using all three chunking strategies.

5. Run the Demonstration

python scripts/run_demo.py

The demonstration covers:

1. Grounded answer generation with citations.
2. Hybrid retrieval versus dense-only retrieval.
3. Handling questions outside the indexed corpus.
4. Chunking strategy comparison.

6. Run Automated Tests

pytest tests/ -v

7. Start the FastAPI Server

uvicorn src.api:app --reload

API documentation:

http://localhost:8000/docs

8. Start the Streamlit Application

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
GET	/v1/eval/run	Execute evaluation
GET	/v1/eval/chunking-comparison	Compare chunking strategies

Example request:

{
  "question": "What is an origin in the context of CORS?",
  "chunking_strategy": "structure_aware",
  "use_hybrid": true
}

Docker Deployment

The application supports containerized execution through Docker Compose.

docker compose up --build

The Docker configuration includes:

* An initialization service for document ingestion.
* A FastAPI backend.
* A Streamlit frontend.
* Shared storage for indexed document collections.

Optional provider credentials can be configured through environment variables in a local .env file.

**Engineering Decisions**

Hybrid Retrieval: Dense retrieval captures semantic relationships, while BM25 identifies exact technical terminology. Reciprocal Rank Fusion combines their rankings.

Multiple Chunking Strategies: Different chunking approaches can produce different retrieval and answer-quality outcomes. The evaluation framework measures these differences rather than assuming one strategy is universally optimal.

Citation Verification: Generated citations are independently checked against their source documents instead of being automatically trusted.

Confidence-Based Abstention: Retrieval sufficiency is evaluated before generation to reduce unsupported answers.

Offline-First Architecture: Mock implementations allow the pipeline to operate without external API credentials, while real provider integrations support more advanced configurations.

Per-Document Deduplication: Deduplication is scoped to individual source documents to reduce redundant chunks without expensive corpus-wide comparisons.

Asynchronous API Execution: Synchronous evaluation handlers and asynchronous question-answering handlers are separated to avoid nested event-loop execution issues.

**Project Structure**

Atlas-rag/
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

**Future Improvements**

* Evaluate retrieval performance across additional technical documentation datasets.
* Integrate domain-specific embedding models.
* Experiment with cross-encoder reranking.
* Expand the golden evaluation dataset.
* Improve confidence calibration across different document collections.
* Introduce distributed caching and scalable storage.
* Extend observability and performance monitoring.

License

The project code is licensed under the MIT License.

The documentation corpus is sourced from the MIT-licensed FastAPI repository, version 0.104.1.

Refer to LICENSE and docs_corpus/MANIFEST.md for licensing and source details.
