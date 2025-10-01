# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Faster logs, no .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Only install OS packages if you truly need them.
# (pandas wheels work without build tools; you can add back build-essential later if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the app (includes .streamlit/)
COPY . /app

# Cloud Run will set $PORT (defaults to 8080 locally)
EXPOSE 8080

# Use $PORT from the environment; keep the proxy-friendly flags you’ve been using
CMD ["sh","-c","streamlit run karaoke_app.py \
  --server.port=${PORT:-8080} \
  --server.address=0.0.0.0 \
  --server.enableCORS=false \
  --server.enableXsrfProtection=false \
  --server.enableWebsocketCompression=false \
  --logger.level=debug"]
