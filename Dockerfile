FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt

# Compose defaults to deterministic hash embeddings so the image starts
# without downloading a model. Enable BGE explicitly for semantic recall.
ARG INSTALL_BGE=false
RUN if [ "$INSTALL_BGE" = "true" ]; then \
      pip install -r /tmp/requirements.txt; \
    else \
      grep -v '^sentence-transformers' /tmp/requirements.txt > /tmp/runtime-requirements.txt && \
      pip install -r /tmp/runtime-requirements.txt; \
    fi

COPY . /app

RUN mkdir -p /app/runtime/qdrant && \
    useradd --create-home --uid 10001 medpulse && \
    chown -R medpulse:medpulse /app/runtime

USER medpulse

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

CMD ["python", "-m", "server.app", "--host", "0.0.0.0", "--port", "8000", "--answer-mode", "llm"]
