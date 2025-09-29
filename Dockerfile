# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONWONTWRITEBYTECODE=1 \
    PORT=8080 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# minimal OS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# ---- Python deps ----
# 1) Install your deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || true
# 2) Ensure Streamlit + Tornado are present at known-good versions
RUN pip install --no-cache-dir "streamlit==1.37.1" "tornado>=6.3,<7"

# bring your code + .streamlit/config.toml
COPY . .

EXPOSE 8080

# Create a tiny hello app at runtime and start Streamlit
# Keep startup simple so the container always binds to the port quickly.
CMD bash -lc '\
  printf "import streamlit as st\nst.set_page_config(page_title=\"Ping\")\nst.title(\"Hello from Cloud Run ✔️\")\n" > app_min.py; \
  echo \"Starting Streamlit on PORT=${PORT}\"; \
  exec streamlit run app_min.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --server.useForwardedHeaders=true \
    --server.enableWebsocketCompression=false \
    --logger.level=debug'
