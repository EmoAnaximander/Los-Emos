# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Helpful defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONWONTWRITEBYTECODE=1 \
    PORT=8080 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Small system tools some wheels need
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
# (Optional but recommended in requirements.txt)
#   streamlit==1.37.1
#   tornado>=6.3,<7
RUN pip install --no-cache-dir -r requirements.txt

# Copy EVERYTHING so .streamlit/config.toml and assets are included
COPY . .

EXPOSE 8080

# Start: print config visibility + effective settings, then run a tiny hello page
CMD bash -lc '\
  echo "Starting Streamlit on PORT=${PORT}"; \
  echo "---- List .streamlit ----"; ls -la .streamlit || true; \
  echo "---- Show config.toml ----"; cat .streamlit/config.toml || true; \
  echo "---- Effective Streamlit config (first 80 lines) ----"; streamlit config show | sed -n "1,80p"; \
  echo "-----------------------------------------------"; \
  printf "import streamlit as st\nst.set_page_config(page_title=\"Ping\")\nst.title(\"Hello from Cloud Run ✔️\")\n" > app_min.py; \
  streamlit run app_min.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --server.useForwardedHeaders=true \
    --server.enableWebsocketCompression=false \
    --logger.level=debug'
