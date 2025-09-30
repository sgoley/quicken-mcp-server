# Multi-stage build for Quicken MCP Server

# Builder stage
FROM python:3.11-slim AS builder

# Set build arguments
ARG DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Final runtime stage
FROM python:3.11-slim

# Set runtime arguments
ARG DEBIAN_FRONTEND=noninteractive

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get autoremove -y \
    && apt-get clean

# Create non-root user
RUN groupadd --gid 1000 quicken && \
    useradd --uid 1000 --gid quicken --shell /bin/bash --create-home quicken

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application code
COPY app/ ./app/
COPY pyproject.toml ./

# Change ownership to non-root user
RUN chown -R quicken:quicken /app

# Switch to non-root user
USER quicken

# Set Python path
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Default entrypoint
ENTRYPOINT ["python", "-m", "app.main"]

# Default command (stdio mode)
CMD ["--qif", "/data/input.qif", "--server-mode", "stdio"]

# Labels
LABEL org.opencontainers.image.title="Quicken MCP Server"
LABEL org.opencontainers.image.description="MCP server for Quicken QIF financial data access"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.authors="Quicken MCP Team"