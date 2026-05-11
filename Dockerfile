# ── Stage 1: build dependencies ──────────────────────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --no-deps --prefix=/install -r requirements.lock

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim
WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Ensure project root is on PYTHONPATH so all package imports resolve correctly
ENV PYTHONPATH=/app

# Bake synthetic dataset + trained demand model into the image.
# Uses SQLite/YAML fallback path — no DATABASE_URL required at build time.
# The knowledge index is built lazily at runtime (requires OPENAI_API_KEY).
RUN python data/generate_data.py && \
    python models/train_demand_model.py

# API is the primary interface (Directive 3 — API-first).
# To run Streamlit: docker compose run --rm api streamlit run streamlit_app.py --server.port=8501
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
