# ── API (FastAPI orchestration engine) ───────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# fonts-dejavu-core gives the PDF generator Hebrew glyph coverage.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ml.txt ./

# INSTALL_ML=false → lean image: deterministic hashing-embedding fallback + the pypdf
#                    "basic" PDF parser (with a deterministic parse-confidence signal).
# INSTALL_ML=true  → adds sentence-transformers + torch (BGE-M3 multilingual embeddings +
#                    cross-encoder reranker) AND Docling (robust tables / multi-column /
#                    scans-via-OCR). Set ABA_PDF_PARSER=auto|docling to use Docling. Multi-GB.
ARG INSTALL_ML=false
RUN pip install -r requirements.txt \
 && if [ "$INSTALL_ML" = "true" ]; then pip install -r requirements-ml.txt; fi

COPY app ./app
COPY scripts ./scripts

# Build the demo corpus + database into the image so the container is self-contained.
RUN python scripts/seed_data.py && python scripts/make_pdfs.py

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
