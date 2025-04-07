FROM python:3.9-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RSS_DB_PATH=/data/rss_aggregator.db \
    RSS_FETCH_INTERVAL=3600 \
    PORT=5000

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Create a non-root user and set permissions
RUN useradd -m appuser && \
    mkdir -p /data && \
    chown -R appuser:appuser /app /data

# Switch to non-root user
USER appuser

# Create a volume for persistent data
VOLUME /data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:$PORT/api/health || exit 1

# Expose the API port
EXPOSE $PORT

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "src.api.app:app"]
