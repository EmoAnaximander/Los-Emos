# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONWONTWRITEBYTECODE=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_LOG_LEVEL=debug \
    PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# COPY EVERYTHING so imports/pages/assets aren’t missing
COPY . .

# If your entry file is karaoke_app.py, keep its name and run it directly
# (no need to rename to app.py)
EXPOSE 8080

# Shell form so $PORT expands; NO baseUrlPath; CORS OFF; XSRF OFF; ws compression OFF
CMD bash -lc 'echo "Starting Streamlit on PORT=${PORT}"; \
  streamlit run karaoke_app.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --server.enableWebsocketCompression=false'
