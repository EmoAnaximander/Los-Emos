# syntax=docker/dockerfile:1

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Minimal system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY karaoke_app.py /app/app.py
COPY logo.png /app/logo.png

# Create Streamlit config directly inside the image
RUN mkdir -p /app/.streamlit && printf "%s\n" \
  "[server]" \
  "headless = true" \
  "address = \"0.0.0.0\"" \
  "enableCORS = false" \
  "enableXsrfProtection = false" \
  "enableWebsocketCompression = false" \
  "maxUploadSize = 200" \
  "" \
  "[browser]" \
  "gatherUsageStats = false" \
  > /app/.streamlit/config.toml

# Extra logging so startup shows config in Cloud Run logs
ENV STREAMLIT_LOG_LEVEL=debug

# Streamlit runtime config (don’t set STREAMLIT_SERVER_PORT here)
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8080

# Start Streamlit with proxy-friendly flags
CMD streamlit run app.py \
  --server.port=$PORT \
  --server.address=0.0.0.0 \
  --server.enableCORS=false \
  --server.enableXsrfProtection=false \
  --server.enableWebsocketCompression=false
