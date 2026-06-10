# =============================================================================
# yuleOSH — Multi-stage Docker build
# =============================================================================
# Usage:
#   docker build -t yuleosh:0.7.0 .
#   docker run -p 8080:8080 yuleosh:0.7.0
# =============================================================================

# Stage 1: Install dependencies + package
FROM python:3.13-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY yuleosh_cli.py ./

RUN pip install --no-cache-dir --user .

# Stage 2: Minimal runtime
FROM python:3.13-slim

LABEL org.opencontainers.image.title="yuleOSH"
LABEL org.opencontainers.image.description="Embedded AI Dev Lifecycle Platform — OpenSpec+Superpowers+Harness Engineering"
LABEL org.opencontainers.image.version="0.7.0"
LABEL org.opencontainers.image.source="https://github.com/frisky1985/yuleOSH"

# Runtime-only deps
RUN pip install --no-cache-dir pytest coverage

# Non-root user
RUN addgroup --system --gid 1001 osh && \
    adduser --system --uid 1001 --ingroup osh --no-create-home osh

WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:${PATH} \
    PYTHONPATH=/app/src:${PYTHONPATH} \
    OSH_HOME=/app \
    PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')" || exit 1

EXPOSE 8080
USER osh
ENTRYPOINT ["python3", "src/ui/server.py"]
