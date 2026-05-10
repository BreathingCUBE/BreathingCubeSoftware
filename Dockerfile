# Base stage - dependencies only
FROM python:3.11-slim as base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
# This layer is cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Development stage
FROM base as development

# Copy application code
COPY . .

ENV FLASK_DEBUG=1
ENV FLASK_APP=run.py
ENV APP_TYPE=web

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

CMD ["python", "run.py"]

# Production stage
FROM base as production

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 flask && chown -R flask:flask /app
USER flask

ENV FLASK_DEBUG=0
ENV APP_TYPE=web

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "run:app"]