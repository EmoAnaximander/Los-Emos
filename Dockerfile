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

# 👇 Add this line right after the app copy
COPY .streamlit /app/.streamlit

# Streamlit runtime config
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
    STREAMLIT_LOG_LEVEL=debug

EXPOSE 8080

# Start Streamlit with proxy-friendly flags
CMD streamlit run app.py \
  --server.port=$PORT \
  --server.address=0.0.0.0 \
  --server.enableCORS=false \
  --server.enableXsrfProtection=false
  --logger.level=debug
