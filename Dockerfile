# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Set environment variables for non-buffered Python output
ENV PYTHONUNBUFFERED=1 \
    PYTHONWONTWRITEBYTECODE=1

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory inside the container
WORKDIR /app

# Install Python dependencies first for better caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code
COPY karaoke_app.py /app/app.py
COPY logo.png /app/logo.png

# --- TEMPORARY DEBUGGING STEPS ---
# This will show you the contents of the /app directory
RUN ls -l /app 

# This will show you the contents of the root directory
RUN ls -l / 

# The EXPOSE instruction signals which port the container listens on
# Google Cloud Run expects the app to listen on the port specified by the PORT environment variable,
# which defaults to 8080.
EXPOSE 8080

# Start Streamlit with proxy-friendly flags, passing the port and address directly.
# This CMD command takes precedence over any settings in a config.toml file.
CMD ["streamlit", "run", "app.py", \
    "--server.port", "8080", \
    "--server.address", "0.0.0.0", \
    "--server.enableCORS", "true", \
    "--server.enableXsrfProtection", "false", \
    "--server.baseUrlPath", "", \
    "--server.headless", "true", \
    "--logger.level", "debug"]
