# Multi-stage build for docs-to-ai MCP server
# Stage 1: Build stage
FROM python:3.13-slim AS builder

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y build-essential  && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependenciess
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime stage
FROM python:3.13-slim

# Install runtime dependencies (needed for PyMuPDF)
RUN apt-get update && apt-get install -y libmupdf-dev  && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser *.py ./
COPY --chown=appuser:appuser app/*.py ./app/
COPY --chown=appuser:appuser LICENSE ./
COPY --chown=appuser:appuser README.md ./

# Copy entrypoint script and ensure Unix line endings (important for Windows)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && \
    # Convert Windows line endings (CRLF) to Unix (LF) if present
    sed -i 's/\r$//' /entrypoint.sh || true

# Create necessary directories with proper permissions
RUN mkdir -p /app/cache/chromadb /app/cache/doc_cache /app/my-docs && \
    chown -R appuser:appuser /app/cache /app/my-docs

# Switch to non-root user
USER appuser

# Add local Python packages to PATH
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Expose any ports if needed (not required for MCP stdio)
# EXPOSE 8000

# Health check (optional - checks if Python imports work)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD python -c "import mcp, chromadb, sentence_transformers" || exit 1

# Use entrypoint to handle directory creation
ENTRYPOINT ["/entrypoint.sh"]

# Default command: run the MCP server
CMD ["python", "mcp_server.py"]