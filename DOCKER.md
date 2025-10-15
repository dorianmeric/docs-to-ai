# Docker Setup for docs-to-ai

This document explains how to use the Dockerized version of docs-to-ai.

## Prerequisites

- Docker installed (Docker Desktop on Windows/Mac, or Docker Engine on Linux)
- Docker Compose (included with Docker Desktop)

## Quick Start

### 1. Build the Docker Image

```bash
docker-compose build
```

This will create the `docs-to-ai:latest` image.

### 2. Add Documents to the Database

Place your PDF and Word documents in the `my-docs/` directory, organized by topic folders:

```
docs/
├── Machine_Learning/
│   ├── paper1.pdf
│   └── paper2.pdf
└── Python_Programming/
    └── guide.docx
```

Then run the ingestion service:

```bash
docker-compose --profile ingestion up docs-ingestion
```

Or use the shorthand:

```bash
docker-compose run --rm docs-ingestion
```

### 3. Start the MCP Server

```bash
docker-compose up -d docs-to-ai
```

The `-d` flag runs it in detached mode (background).

### 4. View Logs

```bash
docker-compose logs -f docs-to-ai
```

### 5. Stop the Server

```bash
docker-compose down
```

## Docker Commands Reference

### Building

```bash
# Build the image
docker-compose build

# Build without cache (clean build)
docker-compose build --no-cache

# Build and start immediately
docker-compose up --build
```

### Running

```bash
# Start in foreground
docker-compose up docs-to-ai

# Start in background (detached)
docker-compose up -d docs-to-ai

# Start and rebuild if needed
docker-compose up --build docs-to-ai
```

### Managing

```bash
# Stop services
docker-compose stop

# Stop and remove containers
docker-compose down

# Stop and remove containers + volumes (WARNING: deletes database!)
docker-compose down -v

# Restart services
docker-compose restart
```

### Ingestion

```bash
# Run document ingestion (one-time)
docker-compose run --rm docs-addfiles

# Run with reset flag
docker-compose run --rm docs-addfiles python add_docs_to_database.py --doc-dir /app/docs --reset
```

### Logs and Debugging

```bash
# View logs
docker-compose logs docs-to-ai

# Follow logs in real-time
docker-compose logs -f docs-to-ai

# View last 50 lines
docker-compose logs --tail=50 docs-to-ai

# Execute commands in running container
docker-compose exec docs-to-ai bash

# Execute Python commands
docker-compose exec docs-to-ai python -c "from vector_store import VectorStore; store = VectorStore(); print(store.get_stats())"
```

## Volume Management

The Docker setup uses three volumes for persistent data:

1. **chroma_db/** - Vector database (ChromaDB)
2. **doc_cache/** - Cached extracted text
3. **my-docs/** - Your source documents

### Backup Data

```bash
# Create backup directory
mkdir backup

# Backup ChromaDB
docker cp docs-to-ai-mcp:/app/chroma_db ./backup/chroma_db

# Backup cache
docker cp docs-to-ai-mcp:/app/doc_cache ./backup/doc_cache
```

### Restore Data

```bash
# Restore ChromaDB
docker cp ./backup/chroma_db docs-to-ai-mcp:/app/

# Restore cache
docker cp ./backup/doc_cache docs-to-ai-mcp:/app/
```

### Clear Data

```bash
# Stop container
docker-compose down

# Remove volumes (WARNING: deletes all data!)
rm -rf chroma_db/* doc_cache/*

# Or let Docker Compose remove them
docker-compose down -v
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

Edit `.env`:

```env
EMBEDDING_MODEL=all-MiniLM-L6-v2
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
```

Then restart the container:

```bash
docker-compose restart
```

### Resource Limits

Edit `docker-compose.yml` to adjust CPU and memory limits:

```yaml
deploy:
  resources:
    limits:
      cpus: '4'      # Maximum CPUs
      memory: 8G     # Maximum memory
    reservations:
      cpus: '2'      # Minimum CPUs
      memory: 4G     # Minimum memory
```

## Claude Desktop Integration

To use the Dockerized MCP server with Claude Desktop, update your config:

### Windows

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "docs-to-ai": {
      "command": "docker",
      "args": [
        "compose",
        "-f",
        "C:/D/code/ai-tools/Claude-Controlled/doc-to-ai/docker-compose.yml",
        "run",
        "--rm",
        "docs-to-ai"
      ]
    }
  }
}
```

### Linux/Mac

Edit `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "docs-to-ai": {
      "command": "docker",
      "args": [
        "compose",
        "-f",
        "/path/to/doc-to-ai/docker-compose.yml",
        "run",
        "--rm",
        "docs-to-ai"
      ]
    }
  }
}
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs docs-to-ai

# Check if port is in use
docker ps

# Remove and recreate container
docker-compose down
docker-compose up -d
```

### Out of Memory

```bash
# Check resource usage
docker stats docs-to-ai-mcp

# Increase memory limit in docker-compose.yml
# Or restart Docker Desktop with more resources
```

### Permission Issues

```bash
# Fix file permissions
sudo chown -R 1000:1000 chroma_db doc_cache docs

# Or run with current user
docker-compose run --user $(id -u):$(id -g) docs-to-ai
```

### Database Corruption

```bash
# Reset database and re-ingest
docker-compose down
rm -rf chroma_db/*
docker-compose run --rm docs-addfiles
docker-compose up -d docs-to-ai
```

## Development

### Rebuild After Code Changes

```bash
# Rebuild and restart
docker-compose up --build -d

# Or
docker-compose build
docker-compose restart
```

### Run Tests in Container

```bash
docker-compose run --rm docs-to-ai python -m pytest
```

### Access Python Shell

```bash
docker-compose run --rm docs-to-ai python
```

```python
from vector_store import VectorStore
store = VectorStore()
stats = store.get_stats()
print(stats)
```

## Production Considerations

### Security

1. **Don't run as root** - The Dockerfile already creates a non-root user
2. **Use secrets** - For sensitive data, use Docker secrets instead of environment variables
3. **Network isolation** - Consider using Docker networks to isolate containers
4. **Read-only filesystem** - Mount docs volume as read-only (`:ro`)

### Performance

1. **Resource limits** - Set appropriate CPU and memory limits
2. **Volume performance** - Use named volumes for better I/O performance on Mac/Windows
3. **Caching** - The doc_cache volume improves performance for re-processing

### Monitoring

```bash
# Resource usage
docker stats docs-to-ai-mcp

# Health checks
docker inspect --format='{{.State.Health}}' docs-to-ai-mcp
```

## Multi-Architecture Builds

To build for different architectures (e.g., ARM for Mac M1/M2):

```bash
# Enable buildx
docker buildx create --use

# Build for multiple platforms
docker buildx build --platform linux/amd64,linux/arm64 -t docs-to-ai:latest .
```

## License

MIT
