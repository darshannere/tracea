# Stage 1: Install dependencies
FROM python:3.12-slim AS deps
WORKDIR /app
COPY pyproject.toml .
COPY README.md .
RUN pip install --no-cache-dir --prefix=/install -e .

# Stage 2: Runtime
FROM python:3.12-slim
WORKDIR /app

# Create non-root user
RUN groupadd --gid 1000 tracea && \
    useradd --uid 1000 --gid tracea --shell /bin/bash tracea

# Copy installed packages from deps stage
COPY --from=deps /install /usr/local

# Copy application code
COPY tracea/ ./tracea/

# Create data directory
RUN mkdir -p /data && chown tracea:tracea /data

# Copy and set up entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Switch to non-root user
USER tracea

EXPOSE 8080
VOLUME ["/data"]

ENV TRACEA_DB_PATH=/data/tracea.db

ENTRYPOINT ["/app/entrypoint.sh"]
