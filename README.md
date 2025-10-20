# Docs-to-AI -- PDF/Word Document Query System with MCP

A Model Context Protocol (MCP) server that enables LLMs (like Clause or any other LLM that supports MCP) to query your documents using semantic search. Organizes documents by topics based on folder structure.
Supports: PDF, Word, Excel, Markdown.
Supported extensions: .pdf, .docx, .doc, .xlsx, .xls, .xlsam, .xlsb, .md

The model used for document retrieval is all-MiniLM-L6-v2, with 384 dimensions for the embeddings.

## Features

- Extract text from PDF documents
- Organize documents by topics (using folder structure)
- Generate embeddings for semantic search
- Store documents in a vector database (chromadb)
- Expose MCP tools for Claude to search and retrieve documents
- Filter searches by topic/category
- Handle multiple documents with the same filename across different topics

## Architecture

```
PDFs (organized by topic folders)
  → Text Extraction
    → Chunking
      → Embeddings
        → chromadb (with topic tags)
          ↓
    MCP Server Tools
          ↓
       Claude
```

## Document Organization

This system is designed to work with PDFs organized in a folder structure where:
- Each folder represents a **topic** or **category**
- PDFs in that folder are automatically tagged with the topic name
- Documents with the same filename in different folders are handled correctly

Example structure:
```
pdfs/
├── Machine_Learning/
│   ├── neural_networks.pdf
│   ├── deep_learning.pdf
│   └── introduction.pdf
├── Python_Programming/
│   ├── basics.pdf
│   ├── advanced.pdf
│   └── introduction.pdf  # Different from ML's introduction.pdf
└── Data_Science/
    ├── statistics.pdf
    └── visualization.pdf
```

## 1. Installation, with local python

This project uses `uv` for fast, reliable Python package management.

### Install uv (if not already installed)
```bash
# On macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Install and run
```bash
uv sync                              # Install dependencies from pyproject.toml
python -m app.scan_all_my_documents  # Ingest documents
python mcp_server.py                 # Start the MCP Server
```

### Dual Transport Mode

The MCP server now runs **BOTH transports concurrently** (thanks to FastMCP):
- **stdio mode** - For local connections via Claude Desktop
- **HTTP/SSE mode** - For remote connections over HTTP

Both are active simultaneously by default. The server automatically exposes:
- SSE endpoint: `http://localhost:38777/sse` (for establishing connections)
- Messages endpoint: `http://localhost:38777/messages/` (for sending requests)

You can customize the HTTP transport using command line arguments or environment variables:

```bash
# Using command line arguments
python mcp_server.py --host 0.0.0.0 --port 38777

# Or using environment variables
export MCP_HOST=0.0.0.0
export MCP_PORT=38777
python mcp_server.py
```

The script will:
- Recursively scan the directory
- Detect topics from folder names
- Extract and chunk text from each PDF/Words/Markdown/Excel
- Tag chunks with their topic
- Store everything in chromadb

Example output:
```
Found 15 PDF files
Base directory: /path/to/pdfs

Detected topics: Data_Science, Machine_Learning, Python_Programming

[1/15] Processing: neural_networks.pdf
  Topic: Machine_Learning
  ✓ Added 45 chunks
...

INGESTION SUMMARY
==================
Total PDFs processed: 15
Successful: 15
Failed: 0
Total chunks added: 523

Documents per topic:
  Data_Science: 4 documents, 156 chunks
  Machine_Learning: 6 documents, 234 chunks
  Python_Programming: 5 documents, 133 chunks
```

Add to your Claude Desktop config (`%APPDATA%/Claude/claude_desktop_config.json`):

**For stdio mode (local):**
```json
{
  "mcpServers": {
    "docs-to-ai": {
      "command": "python",
      "args": ["C:/[UPDATE_PATH_TO_DOCS-TO-AI]/docs-to-ai/mcp_server.py"]
    }
  }
}
```

**For HTTP/SSE mode (remote):**
```json
{
  "mcpServers": {
    "docs-to-ai": {
      "url": "http://localhost:38777/sse",
      "transport": "sse"
    }
  }
}
```


## 2. Installation, with Docker

You need Docker Desktop, or Docker Engine, running. Then just write the following into a file called "docker-compose.yaml" and it will pull and run the image from Docker Hub (Image: https://hub.docker.com/r/dmeric/docs-to-ai ):
````yaml
services:
  docs-to-ai:
    image: dmeric/docs-to-ai
    container_name: docs-to-ai
    
    volumes:
      - ./cache/chromadb:/app/chromadb        # chromadb database (persists the vector store)
      - ./cache/doc_cache:/app/doc_cache      # Document cache (persists extracted text)
      - ./my-docs:/app/my-docs:ro             # Documents directory (your PDFs and Word docs). Read-only to prevent accidental modifications
    
    # Stdin/stdout - required for MCP protocol in stdio mode
    stdin_open: true
    tty: true

    ports:
      - "${MCP_PORT:-38777}:38777"            # for http/sse transport, on http://localhost:38777/sse

    # Restart policy
    restart: unless-stopped
    
    # # Resource limits (optional - adjust based on your needs)
    # deploy:
    #   resources:
    #     limits:
    #       cpus: '2'
    #       memory: 4G
    #     reservations:
    #       cpus: '1'
    #       memory: 2G
    
````
then run, in bash or in Powershell:
```bash
docker compose up -d
````

### Docker Configuration

The `docker-compose.yml` configures:

**Volumes:**
- `./cache/chromadb:/app/cache/chromadb` - Vector store database (persistent)
- `./cache/doc_cache:/app/cache/doc_cache` - Document cache (persistent)
- `./my-docs:/app/my-docs:ro` - Your documents directory (read-only)

**Ports:**
- `38777` - HTTP/SSE endpoint for remote MCP connections

**Environment Variables:**
- `FULL_SCAN_ON_BOOT` - Set to `True` to scan documents on startup (default: `False`)
- `FOLDER_WATCHER_ACTIVE_ON_BOOT` - Set to `True` to start folder watcher on startup (default: `False`)
- `MCP_PORT` - Customize HTTP port (default: `38777`)

Example with custom environment variables:
```bash
# Create a .env file
echo "FULL_SCAN_ON_BOOT=True" > .env
echo "FOLDER_WATCHER_ACTIVE_ON_BOOT=True" >> .env
echo "MCP_PORT=38777" >> .env

# Start with environment variables
docker compose up -d
```

Add to your Claude Desktop config (`%APPDATA%/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {

    "docs-to-ai": {
      "command": "docker",
      "args": [
        "exec",
        "-i",
        "docs-to-ai",
        "python",
        "mcp_server.py"
      ]
    }

  }
}

```

Finally, put your documents in the folder /my-docs, and ask the server to scan the documents, and optionally to start the folder watcher.
You should now be able to ask your LLM questions about the documents.

## Project Structure

- `mcp_server.py` - Main MCP server implementation (FastMCP-based)
- `app/document_processor.py` - Document text extraction and chunking (PDF, Word, Excel, Markdown)
- `app/vector_store.py` - Vector database operations (ChromaDB)
- `app/scan_all_my_documents.py` - Batch document ingestion script
- `app/incremental_updater.py` - Incremental document update logic
- `app/folder_watcher.py` - Automatic folder monitoring and change detection
- `app/config.py` - Configuration settings
- `pyproject.toml` - Python dependencies and project metadata (using `uv`)
- `Dockerfile` - Docker container configuration
- `docker-compose.yml` - Docker Compose configuration

## MCP Tools

The server exposes the following tools for LLMs:

**Search & Discovery:**
- `search_documents` - Semantic search across all documents (with optional topic filter)
- `list_documents` - List all available documents (with optional topic filter)
- `list_topics` - List all topics/categories
- `get_collection_stats` - Get statistics about the collection (file types, sizes, counts)

**Document Management:**
- `scan_all_my_documents` - Manually trigger a full document scan and re-index
- `start_watching_folder` - Start automatic folder monitoring with incremental updates
- `stop_watching_folder` - Stop the folder watcher
- `get_time_of_last_folder_scan` - Check when the last scan occurred and status

### Example Queries for Claude

Once configured, you can ask Claude:

**General queries:**
- "What documents do you have access to?"
- "What topics are available?"
- "Search for information about neural networks"
- "Show me the collection statistics"

**Topic-specific queries:**
- "Search for Python programming concepts in the Python_Programming topic"
- "Show me all documents about Machine Learning"
- "Find information about data visualization in the Data_Science topic"

**Complex queries:**
- "Compare what different documents say about deep learning"
- "Find all mentions of pandas across all documents"
- "What are the key concepts in the Machine_Learning documents?"

**Document management:**
- "Scan all my documents" - Triggers a full re-index
- "Start watching my documents folder for changes" - Enables automatic updates
- "When was the last scan?" - Check folder monitoring status
- "Stop watching the folder" - Disable automatic updates

## Configuration

Edit [app/config.py](app/config.py) to customize:

**Document Processing:**
- `SUPPORTED_EXTENSIONS` - File types to process (default: `.pdf`, `.docx`, `.doc`, `.md`, `.xlsx`, `.xls`, `.xlsam`, `.xlsb`)
- `CHUNK_SIZE` - Characters per chunk (default: `1000`)
- `CHUNK_OVERLAP` - Overlap between chunks (default: `200`)

**Search Configuration:**
- `DEFAULT_SEARCH_RESULTS` - Default number of results (default: `10`)
- `MAX_SEARCH_RESULTS` - Maximum allowed results (default: `20`)

**Embedding Model:**
- `EMBEDDING_MODEL` - Sentence transformer model (default: `all-MiniLM-L6-v2`)
- `EMBEDDING_DIMENSION` - Vector dimension (default: `384`)

**Topic Configuration:**
- `USE_FOLDER_AS_TOPIC` - Use folder hierarchy as topics (default: `True`)
- `DEFAULT_TOPIC` - Default topic for uncategorized docs (default: `uncategorized`)
- `TOPIC_SEPARATOR` - Display separator for hierarchical topics (default: ` > `)

**Storage:**
- `CHROMADB_DIR` - Vector database location (default: `cache/chromadb`)
- `DOC_CACHE_DIR` - Document cache location (default: `cache/doc_cache`)
- `DOCS_DIR` - Documents directory (default: `my-docs`, configurable via `DOCS_DIR` env var)
- `CHROMA_COLLECTION_NAME` - Collection name (default: `my-documents`)

**Startup Behavior:**
- `FULL_SCAN_ON_BOOT` - Scan documents on server startup (env var, default: `False`)
- `FOLDER_WATCHER_ACTIVE_ON_BOOT` - Start folder watcher on startup (env var, default: `False`)

**Server Transport:**
- `MCP_HOST` - HTTP server host (env var, default: `0.0.0.0`)
- `MCP_PORT` - HTTP server port (env var, default: `38777`)

## License

MIT
