# Dell iDRAC Redfish MCP Server - Dockerfile
#
# This Dockerfile creates a containerized version of the MCP server
# for easy deployment and distribution.

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies (if needed)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src/ ./src/
COPY config/ ./config/

# Create volume mount points for configuration
VOLUME ["/app/config"]

# Expose MCP server port for streamable-http transport
EXPOSE 8000

# Health check (optional - can be customized based on your health endpoint)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Use STOPSIGNAL to ensure proper signal handling
STOPSIGNAL SIGTERM

# Set the entrypoint to run the MCP server
# Using exec form to ensure proper signal propagation
ENTRYPOINT ["python", "-u", "-m", "src"]

# Default command arguments - using streamable-http transport for Docker
CMD ["--openapi", "config/openapi.yaml", "--config", "config/tools.yaml", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
