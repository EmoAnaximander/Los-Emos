# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Make logs show up right away and avoid extra files
ENV PYTHONUNBUFFERED=1 \
    PYTHONWONTWRITEBYTECODE=1 \
    PORT=8080 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Where the app will live in the container
WORKDIR /app

# Small system tools some Python packages need
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your whole project (so any extra files/folders are included)
COPY . .

# Cloud Run uses this port
EXPOSE 8080

# Start Streamlit the Cloud Run–friendly way
# - Listens on the right port and address
# - Turns off checks that block Cloud Run’s proxy
# - Disables a websocket option that sometimes causes errors
CMD bash -lc 'echo "Starting Streamlit on PORT=${PORT}"; \
  streamlit run karaoke_app.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --server.enableWebsocketCompression=false \
    --logger.level=debug'
