# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONWONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Python packages
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Your app files
COPY . /app

EXPOSE 8080

# Start Streamlit the same way you did before (this form always starts),
# but with CORS OFF and NO baseUrlPath.
CMD ["streamlit", "run", "karaoke_app.py",
     "--server.port", "8080",
     "--server.address", "0.0.0.0",
     "--server.enableCORS", "false",
     "--server.enableXsrfProtection", "false",
     "--server.enableWebsocketCompression", "false",
     "--logger.level", "debug"]
