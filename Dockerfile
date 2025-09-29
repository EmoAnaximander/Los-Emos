# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Install Streamlit directly (skip requirements.txt for now to reduce risk)
RUN pip install --no-cache-dir "streamlit==1.37.1" "tornado>=6.3,<7"

# Create a minimal hello app inside the image
RUN printf "import streamlit as st\nst.set_page_config(page_title='Ping')\nst.title('Hello from Cloud Run ✔️')\n" > /app/app_min.py

EXPOSE 8080

# Start Streamlit in the simplest way possible
CMD streamlit run /app/app_min.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --server.useForwardedHeaders=true \
    --server.enableWebsocketCompression=false \
    --logger.level=debug
