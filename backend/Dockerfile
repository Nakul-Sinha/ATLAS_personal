# ATLAS backend relay
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ATLAS_BACKEND_HOST=0.0.0.0 \
    ATLAS_BACKEND_PORT=8000 \
    ATLAS_AGENT_MODE=mock

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend source.
COPY . ./

EXPOSE 8000

# The container has no desktop session, so it defaults to mock mode. Override
# ATLAS_AGENT_MODE and point OLLAMA_BASE_URL at a reachable host to run for real.
CMD ["python", "server.py"]
