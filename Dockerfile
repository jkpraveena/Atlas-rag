FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

# Runtime configuration (all optional -- with nothing set, embeddings/
# reranking/generation all run offline mock implementations, zero cost,
# zero API keys, zero network calls beyond the initial corpus fetch):
#   OPENAI_API_KEY / ANTHROPIC_API_KEY   - real embeddings + generation + reranking
#   EMBEDDING_PROVIDER / RERANKER / GENERATION_PROVIDER / CITATION_VERIFIER
#                                          - force "mock" | "openai" | "anthropic" | "llm"
EXPOSE 8000 8501

# docs_corpus/ ships baked into the image (committed to the repo -- see the
# README's data provenance note). Ingestion still needs to run once before
# first use: docker-compose.yml does this automatically via the init
# service; standalone, run:
#   docker run --rm -v rag_data:/app/data <image> python scripts/ingest.py

# Default: run the API. Override to run Streamlit instead:
#   docker run -p 8501:8501 rag-hybrid-search streamlit run streamlit_app.py --server.address 0.0.0.0
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
