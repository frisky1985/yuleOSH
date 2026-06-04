# =============================================================================
# Stage 1: Build / dependency install
# =============================================================================
FROM python:3.13-slim AS builder

WORKDIR /build

# Copy only dependency files first for layer caching
COPY pyproject.toml README.md ./

# Install runtime dependencies (no dev tools in production)
RUN pip install --no-cache-dir --user pytest coverage && \
    pip install --no-cache-dir --user .

# =============================================================================
# Stage 2: Runtime image
# =============================================================================
FROM python:3.13-slim

LABEL maintainer="frisky1985"
LABEL description="yuleOSH — Embedded AI Dev Lifecycle Platform"
LABEL version="0.1.0"

# Create a non-root user for security
RUN addgroup --system --gid 1001 osh && \
    adduser --system --uid 1001 --ingroup osh --no-create-home osh

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application source
COPY . .

# Ensure scripts in PATH
ENV PATH=/root/.local/bin:/app/bin:${PATH} \
    PYTHONPATH=/app:${PYTHONPATH} \
    OSH_HOME=/app

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')" || exit 1

EXPOSE 8080

# Use non-root user
USER osh

ENTRYPOINT ["python3", "src/ui/server.py"]
