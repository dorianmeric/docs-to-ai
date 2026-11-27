# Docs-to-AI -- Document Query System with MCP

A production-ready RAG that runs as a Model Context Protocol (MCP) server, which enables LLMs (like Claude Desktop or any other LLM that supports MCP) to query your documents using semantic search. Organizes documents by topics based on folder structure.
Supports: PDF, Word, Excel, Markdown, PowerPoint, HTML, TXT, CSV.
Supported extensions: .pdf, .docx, .doc, .xlsx, .xls, .xlsam, .xlsb, .md, .pptx, .html, .htm, .txt, .csv

The model used for document retrieval is all-MiniLM-L6-v2, with 384 dimensions for the embeddings.

## Features

- Extract text from PDF, Word, Excel, Markdown, PowerPoint, HTML, TXT, and CSV documents
- Organize documents by topics (using folder structure)
- Generate embeddings for semantic search
- Store documents in a vector database (chromadb)
- Expose MCP tools for Claude to search and retrieve documents
- Filter searches by topic/category
- Handle multiple documents with the same filename across different topics
- **Advanced Search**: Phrase matching, date-range filtering, regex pattern matching
- **Smart Chunking**: Fixed-size, by-paragraph, semantic heading-based, token-based, or embedding-based semantic chunking
- Preserve heading/section structure for smarter retrieval
- Optional re-ranker model for improved search quality
- **Fully configurable**: every setting can be overridden via environment variables, a `.env` file, or Docker build args

## Architecture

```
Documents (PDF, Word, Excel, Markdown, PowerPoint, HTML, TXT, CSV)
  → Text Extraction
    → Chunking (fixed/paragraph/heading/token/semantic)
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
- `FOLDER_WATCHER_ACTIVE_ON_BOOT` - Set to `True` to start folder watcher on startup (default: `True`)
- `MCP_PORT` - Customize HTTP port (default: `38777`)

**All configuration is overridable.** Every setting from the [Configuration](#configuration) section can be passed either as a **build arg** (baked into the image, and used when pre-downloading models) or as a **runtime environment variable** (overrides the baked value without rebuilding). The defaults match `app/config.py`.

Example with custom environment variables:
```bash
# Create a .env file (docker compose reads it automatically)
echo "FULL_SCAN_ON_BOOT=True" > .env
echo "FOLDER_WATCHER_ACTIVE_ON_BOOT=True" >> .env
echo "MCP_PORT=38777" >> .env
echo "CHUNKING_STRATEGY=semantic" >> .env
echo "CHUNK_SIZE=800" >> .env

# Start with environment variables
docker compose up -d
```

Example overriding a build arg (rebuilds the image with the new default):
```bash
docker compose build --build-arg CHUNKING_STRATEGY=semantic --build-arg CHUNK_SIZE=800
docker compose up -d
```

Or with plain `docker build`:
```bash
docker build --build-arg EMBEDDING_MODEL=all-MiniLM-L6-v2 --build-arg USE_RERANKER=True -t mcp/docs-to-ai .
```

> **Tip:** If you change `EMBEDDING_MODEL` or `USE_RERANKER`, rebuild the image so the new models are pre-downloaded and baked in. Changing chunking/search settings only needs a runtime env var (no rebuild), but you must re-scan your documents for chunking changes to take effect.

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
- `app/embeddings.py` - Shared embedding-model access (single instance per process)
- `app/scan_all_my_documents.py` - Batch document ingestion script
- `app/incremental_updater.py` - Incremental document update logic
- `app/folder_watcher.py` - Automatic folder monitoring and change detection
- `app/config.py` - Configuration settings (all overridable via env vars / `.env`)
- `.env.example` - Template for local configuration overrides
- `pyproject.toml` - Python dependencies and project metadata (using `uv`)
- `Dockerfile` - Docker container configuration (configurable via build args)
- `docker-compose.yml` - Docker Compose configuration (build args + runtime env)

## MCP Tools

The server exposes the following tools for LLMs:

**Search & Discovery:**
- `search_documents` - Semantic search across all documents with optional filters:
  - `topic` - Filter by topic/category
  - `phrase_search` - Exact phrase matching
  - `date_from` / `date_to` - Filter by last_modified timestamp (Unix)
  - `regex_pattern` - Filter by regex pattern in text
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

**Advanced search (with filters):**
- "Search for 'neural networks' as exact phrase" - Phrase search
- "Find documents about Python modified after 2024-01-01" - Date filtering
- "Search for items matching pattern \d{3}-\d{4}" - Regex pattern search

**Document management:**
- "Scan all my documents" - Triggers a full re-index
- "Start watching my documents folder for changes" - Enables automatic updates
- "When was the last scan?" - Check folder monitoring status
- "Stop watching the folder" - Disable automatic updates

## Configuration

Every setting has a built-in default (shown below) and can be overridden **without editing code** in three ways:

1. **Environment variables** — highest priority, e.g. `CHUNKING_STRATEGY=semantic python mcp_server.py`
2. **A `.env` file** — copy [.env.example](.env.example) to `.env` next to `pyproject.toml` and edit it. Real environment variables always win over `.env`.
3. **Docker build args** — see [Docker Configuration](#docker-configuration) below.

Run `python mcp_server.py --show-config` to print the effective values, or `python mcp_server.py --help` for the full list with defaults.

### Chunking

| Setting | Env var | Default | Description |
|---|---|---|---|
| Strategy | `CHUNKING_STRATEGY` | `by_paragraph` | `fixed_size`, `by_paragraph`, `semantic_heading`, `by_token`, or `semantic` |
| Chunk size | `CHUNK_SIZE` | `1000` | Characters per chunk (tokens when `CHUNK_BY_TOKEN=true`) |
| Chunk overlap | `CHUNK_OVERLAP` | `200` | Overlap between chunks |
| Token chunking | `CHUNK_BY_TOKEN` | `False` | Use token-based chunking instead of character-based |
| Tokenizer | `TOKENIZER_MODEL` | `cl100k_base` | tiktoken tokenizer (`cl100k_base` for GPT-4/3.5, `p50k_base` for GPT-2) |
| Preserve headings | `PRESERVE_HEADINGS` | `True` | Preserve heading structure in chunks |
| Max heading chunk | `MAX_HEADING_CHUNK_SIZE` | `2000` | Max chars per heading-based chunk |
| Min chunk size | `MIN_CHUNK_SIZE` | `50` | Minimum chunk size to avoid tiny chunks |

**Semantic chunking** (`CHUNKING_STRATEGY=semantic`) splits text where the embedding similarity between consecutive sentences drops below a percentile threshold, producing topically coherent chunks:

| Setting | Env var | Default | Description |
|---|---|---|---|
| Split percentile | `SEMANTIC_CHUNK_PERCENTILE` | `95` | Similarity percentile used as the split threshold (0–100) |
| Min size | `SEMANTIC_CHUNK_MIN_SIZE` | `200` | Minimum characters per semantic chunk |
| Max size | `SEMANTIC_CHUNK_MAX_SIZE` | `2000` | Maximum characters per semantic chunk (hard split above this) |
| Buffer size | `SEMANTIC_CHUNK_BUFFER_SIZE` | `1` | Neighbouring sentences combined when computing similarity |

> **Note on chunking strategy:** recent (2026) production studies find that sentence/recursive chunking matches embedding-based semantic chunking up to ~5k tokens at a fraction of the cost, and that semantic chunking can over-fragment. Semantic chunking is therefore offered as an **opt-in** strategy — start with `by_paragraph` or `semantic_heading` and switch only if your own retrieval metrics justify it.

### Search

| Setting | Env var | Default | Description |
|---|---|---|---|
| Default results | `DEFAULT_SEARCH_RESULTS` | `10` | Default number of results returned |
| Max results | `MAX_SEARCH_RESULTS` | `20` | Maximum allowed results |
| Re-ranker | `USE_RERANKER` | `True` | Enable cross-encoder re-ranking for improved results |
| Re-ranker model | `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder model name |
| Re-rank candidates | `RERANKER_TOP_N` | `50` | Number of candidates to re-rank |
| Hybrid BM25 | `USE_BM25` | `False` | Enable hybrid search with BM25 |
| BM25 weight | `BM25_WEIGHT` | `0.3` | Weight for BM25 in hybrid search (0–1) |

### Embedding model

| Setting | Env var | Default | Description |
|---|---|---|---|
| Model | `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer model |
| Dimension | `EMBEDDING_DIMENSION` | `384` | Vector dimension (must match the model) |

### Topics

| Setting | Env var | Default | Description |
|---|---|---|---|
| Folder as topic | `USE_FOLDER_AS_TOPIC` | `True` | Use folder hierarchy as topic tags |
| Default topic | `DEFAULT_TOPIC` | `uncategorized` | Topic for uncategorized docs |
| Separator | `TOPIC_SEPARATOR` | ` > ` | Display separator for hierarchical topics |

### Storage

| Setting | Env var | Default | Description |
|---|---|---|---|
| Vector DB dir | — | `cache/chromadb` | ChromaDB location |
| Doc cache dir | — | `cache/doc_cache` | Extracted-text cache location |
| Documents dir | `DOCS_DIR` | `my-docs` | Documents directory |
| Collection name | `CHROMA_COLLECTION_NAME` | `my-documents` | ChromaDB collection name |

### Startup behaviour

| Setting | Env var | Default | Description |
|---|---|---|---|
| Full scan on boot | `FULL_SCAN_ON_BOOT` | `False` | Scan documents on server startup |
| Watcher on boot | `FOLDER_WATCHER_ACTIVE_ON_BOOT` | `True` | Start folder watcher on startup |
| Debounce | `DEBOUNCE_SECONDS` | `10` | Delay after last change before processing |
| Full scan interval | `FULL_SCAN_INTERVAL_DAYS` | `7` | Days between full scans |

### Server transport

| Setting | Env var | Default | Description |
|---|---|---|---|
| Transport | `MCP_TRANSPORT` | `stdio` | `stdio` or `websocket` |
| Host | `MCP_HOST` | `0.0.0.0` | HTTP server host (websocket mode) |
| Port | `MCP_PORT` | `38777` | HTTP server port (websocket mode) |

### Example `.env`

```bash
# Copy .env.example to .env and uncomment what you need
CHUNKING_STRATEGY=semantic
CHUNK_SIZE=800
CHUNK_OVERLAP=100
USE_RERANKER=True
DEFAULT_SEARCH_RESULTS=8
```

## Production RAG Recommendations

The defaults in this project are deliberately conservative and run entirely locally. Based on recent (2026) production RAG research, the following changes give the largest quality gains, roughly in order of impact. Each is already configurable — no code changes needed.

| # | Recommendation | How to enable | Why |
|---|---|---|---|
| 1 | **Upgrade the embedding model.** `all-MiniLM-L6-v2` is now a prototyping-tier model (384-dim, 256-token context). | `EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B` (1024-dim, 32K context) or `BAAI/bge-m3` (native dense+sparse hybrid). Set `EMBEDDING_DIMENSION` to match, then re-scan. | Newer models deliver large retrieval gains; MiniLM's 256-token context truncates document chunks. |
| 2 | **Add hybrid BM25 + dense retrieval** and fuse with Reciprocal Rank Fusion. | `USE_BM25=True`, tune `BM25_WEIGHT`. | Dense-only retrieval misses exact terms (IDs, names, codes); hybrid lifts nDCG ~7%. |
| 3 | **Keep cross-encoder re-ranking** over a wide candidate pool. | `USE_RERANKER=True`, `RERANKER_TOP_N=50`. | Highest-ROI layer: +15–30pp precision@5. Validate on your own corpus — a generic reranker can hurt on niche domains. |
| 4 | **Reduce or drop chunk overlap.** | `CHUNK_OVERLAP=0`–`100`. | 2026 studies found overlap gave no measurable benefit while raising indexing cost. Keep some overlap only for corpora where facts straddle boundaries (legal clauses, tables). |
| 5 | **Target 512–1024 tokens per chunk.** | `CHUNK_SIZE=800` (with `CHUNK_BY_TOKEN=True` for token units). | Quality degrades past ~2.5k tokens ("context cliff"); 512–1024 is the practical sweet spot. |
| 6 | **Prefer paragraph/heading chunking; treat semantic chunking as opt-in.** | Keep `CHUNKING_STRATEGY=by_paragraph` or `semantic_heading`; try `semantic` only if metrics justify it. | Sentence/recursive chunking matches embedding-based semantic chunking up to ~5k tokens at far lower cost; semantic chunking can over-fragment. |
| 7 | **Add diversity (MMR) to result selection.** | Not yet exposed as a setting — see roadmap. | MMR raised nDCG@5 by +4–11pp in 2026 benchmarks. |
| 8 | **Tune ChromaDB HNSW for cosine space.** | Set collection `space="cosine"` and raise `ef_search` (100–200). | Default `l2` space is a poor fit for normalized text embeddings; higher `ef_search` improves recall. |
| 9 | **Add RAG evaluation to CI.** | Use RAGAS (faithfulness, answer relevancy, context precision/recall) with ≥50–100 curated samples and a fixed judge model. | Component metrics separate retrieval failures from generation failures. |
| 10 | **Apply metadata filters before re-ranking.** | Use the `topic`, `date_from`/`date_to`, and `regex_pattern` search filters. | Shrinks the candidate pool before expensive scoring. |

**Deliberately not adopted:** *contextual retrieval* (LLM-written chunk prefixes) and *late chunking* — both add large indexing cost (contextual retrieval ~120× slower) for gains that are unproven on small local corpora, and late chunking can hurt short passages.

## License

MIT
