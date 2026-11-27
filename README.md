# Docs-to-AI: local RAG to search local PDFs, Word files, and any folder

Docs-to-AI is a local RAG server. An LLM searches your documents through MCP and answers with quotes from your own files. Search local PDFs, Word files, Excel sheets, Markdown, PowerPoint, HTML, TXT, and CSV. No cloud service. No API key. Document text stays on your machine.

Supported extensions: `.pdf`, `.docx`, `.doc`, `.xlsx`, `.xls`, `.xlsam`, `.xlsb`, `.md`, `.pptx`, `.html`, `.htm`, `.txt`, `.csv`

**Contents**

- [What you can do with it](#what-you-can-do-with-it)
- [How search works](#how-search-works)
- [Folder topics: how to search a folder](#folder-topics-how-to-search-a-folder)
- [Install with local Python](#install-with-local-python)
- [Install with Docker](#install-with-docker)
- [Project structure](#project-structure)
- [MCP tools](#mcp-tools)
- [Example questions for the LLM](#example-questions-for-the-llm)
- [Configuration](#configuration)
  - [Chunking](#chunking)
  - [Search](#search)
  - [Embedding model](#embedding-model)
  - [GPU acceleration](#gpu-acceleration)
  - [Topics](#topics)
  - [Storage](#storage)
  - [Startup behaviour](#startup-behaviour)
  - [Server transport](#server-transport)
  - [Example `.env`](#example-env)
- [Retrieval pipeline](#retrieval-pipeline)
- [Production RAG settings](#production-rag-settings)
- [Logs](#logs)
  - [Log files](#log-files)
  - [Reading the detail log](#reading-the-detail-log)
- [Troubleshooting: error messages](#troubleshooting-error-messages)
- [FAQ: search files and PDFs locally](#faq-search-files-and-pdfs-locally)
- [License](#license)

## What you can do with it

- Search local PDFs and other files with natural language.
- Find in PDF files by exact phrase, invoice number, ticket ID, or product code.
- Search my files from Claude Desktop or any MCP client.
- Point the server at one folder. Every subfolder becomes a topic.
- Ask "how do I search my folder for X" once. The LLM calls the search tool for you.
- Run a documents RAG setup fully offline. Embedding and re-ranking models run locally.
- Filter search results by topic, date range, phrase, or regex.
- Keep the index fresh with a folder watcher.

## How search works

```
Documents (PDF, Word, Excel, Markdown, PowerPoint, HTML, TXT, CSV)
  → text extraction
    → chunking (semantic by default, 1024 tokens)
      → embeddings (Qwen3-Embedding-0.6B, 1024-dim)
        → ChromaDB (cosine HNSW, topic tags on every chunk)
          ↓
    hybrid retrieval: BM25 + dense → RRF → cross-encoder re-rank
          ↓
    MCP tools → Claude or any MCP client
```

Dense vectors catch meaning. BM25 catches exact strings. RRF merges both ranked lists. A cross-encoder re-scores the merged candidates. See [Retrieval pipeline](#retrieval-pipeline) and [Production RAG settings](#production-rag-settings).

## Folder topics: how to search a folder

The server maps folders to topics. Search a topic to narrow results. One folder tree becomes one browsable index.

- Each folder name becomes a topic.
- Nested folders become nested topics, joined with ` > `.
- Files with the same name in different folders stay separate. Two `introduction.pdf` files do not overwrite each other.

```
my-docs/
├── Machine_Learning/
│   ├── neural_networks.pdf
│   └── introduction.pdf
├── Python_Programming/
│   ├── basics.pdf
│   └── introduction.pdf        # separate document, separate topic
└── Data_Science/
    └── statistics.pdf
```

## Install with local Python

The project uses `uv` for Python packages.

Install `uv`:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install dependencies and run:

```bash
uv sync                              # install dependencies
python -m app.scan_all_my_documents  # index ./my-docs
python mcp_server.py                 # start the MCP server
```

Windows helper scripts sit in the repo root: `1.setup-python-env.ps1`, `2.scan-all-my-documents-in-python.ps1`, `3.run-mcp-server-in-python.ps1`.

The first scan downloads the embedding model (about 1.2 GB) and the re-ranker (about 90 MB). Pre-download both with `python -m app.download_models`.

### Scan options

```bash
python -m app.scan_all_my_documents --doc-dir ./my-docs   # index another folder
python -m app.scan_all_my_documents --reset               # wipe the index, then re-index
```

The scan does this:

- Walk the folder tree.
- Derive topics from folder names.
- Extract and chunk text from each file.
- Embed each chunk. Store each chunk in ChromaDB with its topic tags.

Example output:

```
Found 15 PDF files
Base directory: /path/to/pdfs

Detected topics: Data_Science, Machine_Learning, Python_Programming

[1/15] Processing: neural_networks.pdf
  Topic: Machine_Learning
  ✓ Added 45 chunks

INGESTION SUMMARY
==================
Total PDFs processed: 15
Successful: 15
Failed: 0
Total chunks added: 523
```

### Pick one transport

`MCP_TRANSPORT` selects how clients talk to the server. One transport per process.

- `stdio`: the client starts the process and talks over stdin/stdout. No port. Best for local installs and for `docker exec -i`.
- `http`: the process listens on `MCP_HOST:MCP_PORT` and serves the MCP endpoint at `/mcp`. Best for Docker. This is the Docker default.
- `sse`: older HTTP transport, endpoint at `/sse`. Use it only for clients that need SSE.

```bash
python mcp_server.py --http --host 0.0.0.0 --port 38777     # same as MCP_TRANSPORT=http
MCP_TRANSPORT=http MCP_PORT=38777 python mcp_server.py
MCP_TRANSPORT=sse  mcp_server.py --port 38777
```

`--websocket` still works as an alias for `--http`.

With `http` or `sse`, startup prints every address a client may need:

```
2026-11-27 13:56:18 SUCCESS ✅ [MCP Server] Listening on 0.0.0.0:38777/mcp
                                           From inside the container or machine: http://172.23.0.2:38777/mcp
                                           From this Docker host or a browser on it: http://localhost:38777/mcp
                                           From another machine: http://<host-ip>:38777/mcp
```

Set `MCP_PUBLIC_URL` when the host port differs from `MCP_PORT`, or when a proxy sits in front:

```bash
MCP_PUBLIC_URL=http://myserver.lan:8080/mcp
```

### Claude Desktop config

stdio mode:

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

HTTP mode (server already running with `MCP_TRANSPORT=http`):

```json
{
  "mcpServers": {
    "docs-to-ai": {
      "url": "http://localhost:38777/mcp",
      "transport": "http"
    }
  }
}
```

Some clients want `"type": "http"` instead of `"transport": "http"`. Use whichever key your client documents.

SSE clients use `http://localhost:38777/sse` with `"transport": "sse"`.

## Install with Docker

You need Docker Desktop or Docker Engine. The published image is [dmeric/docs-to-ai](https://hub.docker.com/r/dmeric/docs-to-ai).

Save this as `docker-compose.yaml`:

````yaml
services:
  docs-to-ai:
    image: dmeric/docs-to-ai
    container_name: docs-to-ai

    volumes:
      - ./cache/chromadb:/app/cache/chromadb  # vector store
      - ./cache/doc_cache:/app/cache/doc_cache  # extracted text
      - ./my-docs:/app/my-docs:ro             # your documents, read-only

    # stdio MCP needs stdin/stdout
    stdin_open: true
    tty: true

    environment:
      - MCP_TRANSPORT=http                     # http://localhost:38777/mcp
      - MCP_HOST=0.0.0.0
      - MCP_PORT=38777

    ports:
      - "${MCP_PORT:-38777}:${MCP_PORT:-38777}"

    restart: unless-stopped
````

Start it:

```bash
docker compose up -d
docker compose logs | grep -A4 "Listening on"
```

The container keeps running and serves MCP at `http://localhost:38777/mcp`. Point the client there:

```json
{
  "mcpServers": {
    "docs-to-ai": {
      "url": "http://localhost:38777/mcp",
      "transport": "http"
    }
  }
}
```

A client that only speaks stdio can run the server inside the running container instead. This reuses the same container, mounts, and index. Two things matter in the command. It goes through `uv run`, because the image keeps its packages in a virtualenv. It sets `MCP_TRANSPORT=stdio`, because the container already owns the HTTP port.

```json
{
  "mcpServers": {
    "docs-to-ai": {
      "command": "docker",
      "args": ["exec", "-e", "MCP_TRANSPORT=stdio", "-i", "docs-to-ai", "uv", "run", "--no-sync", "python", "mcp_server.py"]
    }
  }
}
```

Do not use `docker run -i --rm mcp/docs-to-ai` in a client config. That command starts a **new throwaway container for every connection**. The new container has no volumes, so it cannot see `./my-docs` or the index, and it re-scans from scratch each time.

Put your documents in `./my-docs` on the host. The container sees that folder at `/app/my-docs`. Ask the LLM to run `scan_all_my_documents`, or wait for the startup scan. Ask the LLM to run `start_watching_folder` to keep the index fresh.

Check the mount before the first scan. `docker compose ls` shows the project directory, and `docker compose config` shows the host path behind `./my-docs`.

```bash
docker exec docs-to-ai ls /app/my-docs     # must list your files
docker logs -f docs-to-ai                 # shows the scan progress
```

A different folder on the host needs both a mount and `DOCS_DIR`. Example: `- ./contracts:/app/contracts:ro` plus `DOCS_DIR=/app/contracts`.

### Docker volumes, ports, and env

Volumes:

- `./cache/chromadb:/app/cache/chromadb` holds the vector store.
- `./cache/doc_cache:/app/cache/doc_cache` holds extracted text.
- `./my-docs:/app/my-docs:ro` holds your documents.

Ports:

- `38777` serves HTTP/SSE for remote MCP clients.

Frequent environment variables:

- `FULL_SCAN_ON_BOOT` scans documents at startup. Default `False`.
- `FOLDER_WATCHER_ACTIVE_ON_BOOT` starts the folder watcher at startup. Default `True`.
- `MCP_PORT` changes the HTTP port. Default `38777`.

Every setting in [Configuration](#configuration) works as a build arg or as a runtime environment variable. Build args bake values into the image and drive model pre-download. Runtime variables override baked values without a rebuild. Defaults match `app/config.py`.

Runtime variables through `.env`:

```bash
echo "FULL_SCAN_ON_BOOT=True" > .env
echo "FOLDER_WATCHER_ACTIVE_ON_BOOT=True" >> .env
echo "CHUNKING_STRATEGY=by_paragraph" >> .env   # cheaper than the semantic default
echo "CHUNK_SIZE=512" >> .env
docker compose up -d
```

Build args:

```bash
docker compose build --build-arg CHUNKING_STRATEGY=by_paragraph --build-arg CHUNK_SIZE=512
docker compose up -d
```

Plain `docker build`:

```bash
docker build --build-arg EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B --build-arg USE_RERANKER=True -t mcp/docs-to-ai .
```

Rebuild the image after changing `EMBEDDING_MODEL` or `USE_RERANKER`. Model pre-download happens at build time. Chunking and search settings need a re-scan, not a rebuild.

Changing `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`, or `CHROMA_SPACE` forces a new collection. ChromaDB cannot change vector size or distance space in place. The server records the model name and dimension in collection metadata. A stale collection is detected and recreated at startup. Re-scan after the recreate:

```bash
python -m app.scan_all_my_documents --doc-dir ./my-docs --reset
```

The vector store is a cache built from your documents. A recreate never touches the source files.

## Project structure

- `mcp_server.py` runs the MCP server (FastMCP).
- `app/document_processor.py` extracts text and chunks documents.
- `app/vector_store.py` runs ChromaDB operations: cosine HNSW, hybrid search, RRF fusion, re-ranking.
- `app/embeddings.py` loads one embedding model per process and encodes queries and passages.
- `app/bm25_index.py` holds the in-memory BM25 index for the sparse side of hybrid search.
- `app/device.py` picks the compute device: CUDA, MPS, or CPU.
- `app/scan_all_my_documents.py` runs batch ingestion.
- `app/incremental_updater.py` applies single-file changes.
- `app/folder_watcher.py` watches folders and debounces changes.
- `app/config.py` holds settings and the `.env` loader.
- `.env.example` lists every setting with an inline comment.
- `Dockerfile` and `docker-compose.yml` build and run the container.

## MCP tools

Search and discovery:

- `search_documents` runs hybrid search over all documents. Filters: `topic`, `phrase_search`, `date_from`, `date_to`, `regex_pattern`.
- `list_documents` lists indexed documents. Filter with `topic`.
- `list_topics` lists topics.
- `get_collection_stats` reports chunk counts, document counts, file types, and index details.

Document management:

- `scan_all_my_documents` re-indexes the document folder.
- `start_watching_folder` starts the folder watcher.
- `stop_watching_folder` stops the folder watcher.
- `get_time_of_last_folder_scan` reports the last scan time and the next full scan.

## Example questions for the LLM

Find something in a PDF:

- "What documents do you have access to?"
- "Which file mentions the payment terms?"
- "Find the exact phrase 'net 30 days' in my PDFs."
- "Show me the page where invoice INV-2026-0042 appears."

Search my folder by topic:

- "Search the Python_Programming topic for decorators."
- "List all documents under Machine_Learning."
- "Find data visualization notes in Data_Science."

Narrow a search with filters:

- "Search for 'neural networks' as an exact phrase."
- "Find Python documents modified after 2024-01-01."
- "Search for items matching `\d{3}-\d{4}`."

Keep the index fresh:

- "Scan all my documents."
- "Start watching my documents folder."
- "When was the last scan?"
- "Stop watching the folder."

## Configuration

Every setting has a default. Override any setting without editing code:

1. Environment variables win over everything. Example: `CHUNKING_STRATEGY=semantic python mcp_server.py`.
2. A `.env` file next to `pyproject.toml` sets values for one machine. Real environment variables still win. Copy [.env.example](.env.example) and edit it. Each line of `.env.example` ends with a comment: what the setting does, the valid options, and the default. Inline `#` comments work. Quote a value to keep spaces, for example `TOPIC_SEPARATOR=" > "`.
3. Docker build args bake defaults into an image. See [Docker volumes, ports, and env](#docker-volumes-ports-and-env).

Print the effective values with `python mcp_server.py --show-config`. Print every setting and default with `python mcp_server.py --help`.

### Chunking

| Setting | Env var | Default | Description |
|---|---|---|---|
| Strategy | `CHUNKING_STRATEGY` | `semantic` | `semantic`, `fixed_size`, `by_paragraph`, `semantic_heading`, or `by_token` |
| Chunk size | `CHUNK_SIZE` | `1024` | Tokens per chunk (`CHUNK_BY_TOKEN=True`) or characters (`CHUNK_BY_TOKEN=False`) |
| Chunk overlap | `CHUNK_OVERLAP` | `200` | Overlap between chunks, same unit as `CHUNK_SIZE` |
| Token chunking | `CHUNK_BY_TOKEN` | `True` | Measure chunk sizes in tokens instead of characters |
| Tokenizer | `TOKENIZER_MODEL` | `cl100k_base` | tiktoken tokenizer (`cl100k_base` for GPT-4/3.5, `p50k_base` for GPT-2) |
| Preserve headings | `PRESERVE_HEADINGS` | `True` | Split on headings, keep the heading in each chunk |
| Max heading chunk | `MAX_HEADING_CHUNK_SIZE` | `1024` | Max size per heading chunk, same unit as `CHUNK_SIZE` |
| Min chunk size | `MIN_CHUNK_SIZE` | `50` | Drop fragments below this size |

Semantic chunking is the default. The chunker embeds consecutive sentences and cuts where sentence similarity drops below a percentile. Size limits below are always token counts.

| Setting | Env var | Default | Description |
|---|---|---|---|
| Split percentile | `SEMANTIC_CHUNK_PERCENTILE` | `95` | Similarity percentile that becomes a cut point (0-100) |
| Min size | `SEMANTIC_CHUNK_MIN_SIZE` | `64` | Minimum tokens per chunk |
| Max size | `SEMANTIC_CHUNK_MAX_SIZE` | `1024` | Maximum tokens per chunk, hard split above this |
| Buffer size | `SEMANTIC_CHUNK_BUFFER_SIZE` | `1` | Neighbouring sentences averaged when computing similarity |

Pick a chunking strategy for your corpus:

- `semantic` gives the most coherent chunks. Ingest is slower because every sentence is embedded.
- `by_paragraph` costs the least. Published tests find paragraph chunking matches semantic chunking up to about 5k tokens.
- `semantic_heading` keeps document structure and splits long sections at `MAX_HEADING_CHUNK_SIZE`.
- `fixed_size` slices at `CHUNK_SIZE` and ignores structure.

Token counts come from tiktoken, not from the embedding model tokenizer. Counts differ by a small margin.

### Search

| Setting | Env var | Default | Description |
|---|---|---|---|
| Default results | `DEFAULT_SEARCH_RESULTS` | `10` | Results returned when the client asks for no count |
| Max results | `MAX_SEARCH_RESULTS` | `20` | Hard cap on results per search |
| Re-ranker | `USE_RERANKER` | `True` | Re-score fused candidates with a cross-encoder |
| Re-ranker model | `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder model name |
| Re-rank candidates | `RERANKER_TOP_N` | `50` | Candidates passed to the re-ranker |
| Hybrid search | `USE_BM25` | `True` | Merge a BM25 ranking with the dense ranking |
| BM25 weight | `BM25_WEIGHT` | `0.3` | RRF weight of the BM25 list, `0.5` gives equal weight |
| BM25 k1 | `BM25_K1` | `1.5` | BM25 term-frequency saturation |
| BM25 b | `BM25_B` | `0.75` | BM25 length normalisation (0-1) |
| RRF k | `RRF_K` | `60` | Reciprocal Rank Fusion constant |

### Embedding model

| Setting | Env var | Default | Description |
|---|---|---|---|
| Model | `EMBEDDING_MODEL` | `Qwen/Qwen3-Embedding-0.6B` | Sentence-transformer model, 1024-dim, 32K context |
| Dimension | `EMBEDDING_DIMENSION` | `1024` | Vector dimension, must match the model |
| Batch size | `EMBEDDING_BATCH_SIZE` | `32` | Texts encoded per batch |
| Query prompt | `EMBEDDING_QUERY_PROMPT` | empty | Instruction prefix for queries. Empty uses the model query prompt, which Qwen3 ships |

Models cache in the Hugging Face cache (`~/.cache/huggingface`). `python -m app.download_models` pre-downloads the embedding model, the re-ranker, and the tiktoken encoding. The Docker image does this at build time.

### GPU acceleration

Embedding is the expensive step. The embedding model and the cross-encoder go on a GPU automatically when a usable device exists.

| Setting | Env var | Default | Description |
|---|---|---|---|
| GPU if available | `USE_GPU_ACCELERATION_IF_AVAILABLE` | `True` | Use CUDA or Apple MPS when detected, otherwise CPU |
| GPU index | `GPU_DEVICE_INDEX` | `0` | Which CUDA GPU to use, `0` is the first GPU |

Accelerated: dense embeddings for indexing, query encoding, the per-sentence passes of semantic chunking, and cross-encoder re-ranking.

Not accelerated: BM25 scoring (pure Python) and the local ChromaDB HNSW index (CPU only).

Measured on an RTX 5090 against a 16-core CPU. Same models, batch size 32, bf16.

| Workload | CPU | GPU | Speed-up |
|---|---|---|---|
| Embedding 32 chunks at about 530 tokens each | 15.5 s | 0.42 s | 37× |
| Semantic chunking, 200 sentences | 8.9 s | 0.23 s | 38× |
| One search query, batch 1 | 114 ms | 30 ms | 3.8× |
| Re-rank 50 candidates | 1810 ms | 36 ms | 50× |

Device selection order:

1. `USE_GPU_ACCELERATION_IF_AVAILABLE=False` forces CPU.
2. CUDA present: `cuda:<GPU_DEVICE_INDEX>`. An out-of-range index logs a warning and uses GPU 0.
3. Apple Silicon: `mps`.
4. No accelerator: CPU.

The chosen device gets probed with a small allocation. A CUDA build that cannot run on the installed driver falls back to CPU. Startup prints the device: `Compute device: cuda:0 (NVIDIA GeForce RTX 5090, 32 GB VRAM)`. `python mcp_server.py --show-config` prints the `DEVICE=` line.

```bash
# force CPU on a GPU machine
USE_GPU_ACCELERATION_IF_AVAILABLE=False

# use the second GPU
GPU_DEVICE_INDEX=1
```

GPU acceleration needs a CUDA-enabled PyTorch build. The CPU wheel reports no CUDA devices. Install a matching wheel:

```bash
uv pip install --index-url https://download.pytorch.org/whl/cu128 torch   # cu128 for RTX 50xx and newer
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.device_count())"
```

Raise `EMBEDDING_BATCH_SIZE` to 64 or 128 on a GPU. Keep the default 32 on CPU.

On CPU, re-ranking 50 candidates costs about 1.8 s per search. Lower `RERANKER_TOP_N` when a search feels slow on CPU.

### GPU inside Docker

A container only sees the GPUs that Docker passes to it. Without a device reservation the log says `No GPU is visible inside this container`, even when the host has a GPU.

Docker cannot make the reservation optional in one file: a host without a GPU fails `docker compose up`. Use the override file on GPU hosts instead.

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

To keep plain `docker compose up -d`, add one line to `.env`. The separator is `;` on Windows and `:` on Linux/macOS.

```bash
COMPOSE_FILE=docker-compose.yml;docker-compose.gpu.yml      # Windows
COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml      # Linux/macOS
```

`[docker-compose.gpu.yml](docker-compose.gpu.yml)` only adds the device reservation:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all          # or device_ids: ['0'] to pin one GPU
          capabilities: [gpu]
```

Requirements:

- NVIDIA driver on the host. Windows: the normal GeForce driver is enough.
- Linux hosts: the NVIDIA Container Toolkit (`nvidia-container-toolkit`).
- Docker Desktop: the WSL2 based engine, which is the default. Do not switch to Hyper-V.

Check the container sees the GPU:

```bash
docker run --rm --gpus all mcp/docs-to-ai nvidia-smi
docker compose logs | grep "Compute device"
```

Expected log line: `Compute device: cuda:0 (NVIDIA GeForce RTX 5090, 32 GB VRAM)`. The image installs the CUDA-enabled PyTorch wheel on Linux, so no rebuild is needed.

Plain `docker run` needs `--gpus all`. Add it yourself, otherwise the container starts on CPU.

### Topics

| Setting | Env var | Default | Description |
|---|---|---|---|
| Folder as topic | `USE_FOLDER_AS_TOPIC` | `True` | Build topic tags from folder names |
| Default topic | `DEFAULT_TOPIC` | `uncategorized` | Topic for documents outside known folders |
| Separator | `TOPIC_SEPARATOR` | ` > ` | Separator for nested topics |

### Storage

| Setting | Env var | Default | Description |
|---|---|---|---|
| Vector DB dir | none | `cache/chromadb` | ChromaDB location |
| Doc cache dir | none | `cache/doc_cache` | Extracted-text cache location |
| Documents dir | `DOCS_DIR` | `my-docs` | Folder scanned for documents |
| Collection name | `CHROMA_COLLECTION_NAME` | `my-documents` | ChromaDB collection name |
| Distance space | `CHROMA_SPACE` | `cosine` | HNSW space: `cosine`, `l2`, or `ip` |
| ef_search | `HNSW_EF_SEARCH` | `200` | HNSW query candidate list size, ChromaDB default is 100 |
| ef_construction | `HNSW_EF_CONSTRUCTION` | `200` | HNSW build candidate list size, ChromaDB default is 100 |

The index uses cosine space. The embedding model returns normalised vectors, and cosine matches normalised vectors. ChromaDB defaults to `l2`, which fits them poorly. `ef_search=200` raises recall at query time. Change `ef_search` at runtime. `ef_construction` only affects newly built index segments.

### Startup behaviour

| Setting | Env var | Default | Description |
|---|---|---|---|
| Full scan on boot | `FULL_SCAN_ON_BOOT` | `False` | Re-index every document at server start |
| Watcher on boot | `FOLDER_WATCHER_ACTIVE_ON_BOOT` | `True` | Start the folder watcher at server start |
| Debounce | `DEBOUNCE_SECONDS` | `10` | Idle time after the last file change |
| Full scan interval | `FULL_SCAN_INTERVAL_DAYS` | `7` | Days between automatic full rescans |

### Server transport

| Setting | Env var | Default | Description |
|---|---|---|---|
| Transport | `MCP_TRANSPORT` | `stdio` | `stdio`, `http` (`/mcp`), or `sse` (`/sse`). The Docker image sets `http` |
| Host | `MCP_HOST` | `0.0.0.0` | HTTP bind address |
| Port | `MCP_PORT` | `38777` | HTTP port |

### Example `.env`

```bash
CHUNKING_STRATEGY=semantic        # embedding-based semantic chunking
CHUNK_SIZE=1024                   # tokens per chunk when CHUNK_BY_TOKEN=True
CHUNK_OVERLAP=100                 # lower overlap, cheaper indexing
USE_BM25=True                     # BM25 + dense, fused with RRF
BM25_WEIGHT=0.3                   # 0.5 gives equal weight
USE_RERANKER=True
DEFAULT_SEARCH_RESULTS=8
USE_GPU_ACCELERATION_IF_AVAILABLE=True
GPU_DEVICE_INDEX=0
```

## Retrieval pipeline

1. Dense search: encode the query with Qwen3-Embedding-0.6B, then query the HNSW index in cosine space with `ef_search=200`. Queries use the model query instruction prompt.
2. Sparse search: score the query with BM25 over the same chunks. BM25 finds IDs, ticket numbers, product codes, and names.
3. Fusion: merge both ranked lists with RRF. `score = Σ weight / (RRF_K + rank)`. `BM25_WEIGHT` sets the BM25 share.
4. Filters: apply `topic`, `date_from`, `date_to`, `phrase_search`, and `regex_pattern` to the fused candidates.
5. Re-rank: score up to `RERANKER_TOP_N` candidates with the cross-encoder. Return the best `max_results`.

Search output lists topic, source file, page, and a relevance percentage. The percentage is `1 - cosine distance`. Non-cosine spaces print the raw distance instead.

## Production RAG settings

The settings below come from 2026 production RAG research. The marked settings are the current defaults.


| # | Recommendation | Status | Why |
|---|---|---|---|
| 1 | Upgrade the embedding model. `all-MiniLM-L6-v2` is a prototyping model: 384-dim, 256-token context. | Done. Default is `Qwen/Qwen3-Embedding-0.6B`: 1024-dim, 32K context. `BAAI/bge-m3` also works. | Newer models retrieve better. MiniLM truncates long chunks at 256 tokens. |
| 2 | Add hybrid BM25 + dense retrieval, fuse with RRF. | Done. `USE_BM25=True`, `RRF_K=60`. Tune `BM25_WEIGHT`. | Dense-only search misses exact strings. Hybrid adds about 7% nDCG. |
| 3 | Keep cross-encoder re-ranking over a wide candidate pool. | Done. `USE_RERANKER=True`, `RERANKER_TOP_N=50`. | Re-ranking adds 15-30 points of precision@5. Test a reranker on your own corpus. A generic reranker can hurt niche domains. |
| 4 | Reduce or drop chunk overlap. | Optional. `CHUNK_OVERLAP=0` to `100`. | Overlap showed no measurable gain in 2026 studies and raised indexing cost. Keep overlap for legal clauses and tables. |
| 5 | Target 512-1024 tokens per chunk. | Done. `CHUNK_SIZE=1024`, `CHUNK_BY_TOKEN=True`, `SEMANTIC_CHUNK_MAX_SIZE=1024`. | Quality drops past about 2.5k tokens. 512-1024 tokens works best. |
| 6 | Prefer paragraph or heading chunking. Treat semantic chunking as opt-in. | Overridden. The default is `semantic`. Switch to `by_paragraph` or `semantic_heading` when ingest cost matters. | Recursive chunking matches semantic chunking up to about 5k tokens at lower cost. Semantic chunking can over-fragment. |
| 7 | Add diversity (MMR) to result selection. | Not exposed as a setting. | MMR raised nDCG@5 by 4-11 points in 2026 benchmarks. |
| 8 | Tune ChromaDB HNSW for cosine space. | Done. `space="cosine"`, `ef_search=200`, `ef_construction=200`. | `l2` fits normalised text embeddings poorly. Higher `ef_search` raises recall. |
| 9 | Add RAG evaluation to CI. | Not implemented. Use RAGAS with 50-100 curated samples and a fixed judge model. | Component metrics separate retrieval failures from generation failures. |
| 10 | Apply metadata filters before re-ranking. | Optional. The `topic`, `date_from`, `date_to`, and `regex_pattern` filters run on fused candidates before re-ranking. | Filters shrink the candidate pool before scoring. |

Not adopted: contextual retrieval and late chunking. Contextual retrieval runs about 120× slower at indexing. Neither gain is proven on small local corpora. Late chunking can hurt short passages.

## Logs

Every line the server writes to stderr starts with a timestamp, a level, and an emoji. Docker shows these lines in `docker logs`, so a slow scan or a failed file is easy to spot.

```
2026-11-27 20:45:12 INFO    [VectorStore] Loading re-ranker model: cross-encoder/ms-marco-MiniLM-L-6-v2 on cpu
2026-11-27 20:45:14 SUCCESS ✅ [FolderWatcher] Started watching: /app/my-docs
2026-11-27 20:45:14 INFO    [FolderWatcher] 9 supported document(s) under /app/my-docs
2026-11-27 20:45:15 WARN    ⚠️ [FolderWatcher] No supported documents in /app/my-docs.
2026-11-27 20:45:16 ERROR   ❌ [VectorStore] The vector database at /app/cache/chromadb could not be opened.
```

- `INFO` records normal progress. No emoji.
- `SUCCESS ✅` records something that worked: model loaded, folder watched, chunks added.
- `WARN ⚠️` records a fallback or a partial problem. The work continues.
- `ERROR ❌` records a failure. The message carries `Problem`, `Cause`, and `Fix` lines.

Multi-line messages (scan reports, error explanations) are indented under their first line. `grep ERROR` finds the whole block by its first line.

stdout stays clean. stdout carries the MCP protocol and the CLI reports (`--help`, `--show-config`, scan reports). Log lines never go to stdout, so they cannot corrupt the MCP stream.

### Log files

Two files sit in `logs/` (`/app/logs` in Docker, bind-mounted to `./logs` on the host):

| File | Content |
|---|---|
| `logs/server.log` | Every action of the server: startup, model loading, watcher events, scans, tool calls, searches, errors |
| `logs/detail.jsonl` | One JSON object per line for the events needed to debug retrieval: `server_start`, `tool_call`, `search`, `scan_document`, `scan_summary`, `incremental_change`, `watch_batch` |

Both files rotate by size. A full file is renamed to `.1`, `.2`, and so on. The oldest file beyond `LOG_BACKUP_COUNT` is deleted.

| Setting | Env var | Default | Description |
|---|---|---|---|
| Log dir | `LOG_DIR` | `logs` | Folder for both files. Docker uses `/app/logs` |
| Level | `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| Console | `LOG_CONSOLE` | `True` | Also print to stderr, which `docker logs` shows |
| Max size | `LOG_MAX_BYTES` | `10485760` | Rotate a file after 10 MB |
| Backups | `LOG_BACKUP_COUNT` | `5` | Rotated files kept per log |
| Detail log | `LOG_DETAIL_ENABLED` | `True` | Write `detail.jsonl` |
| Chunk text | `LOG_CHUNK_TEXT_CHARS` | `2000` | Chunk text stored per result, `0` stores none |

Docker writes the files to the host because `docker-compose.yml` mounts `./logs` and sets `LOG_DIR=/app/logs`:

```yaml
    volumes:
      - ./logs:/app/logs
    environment:
      - LOG_DIR=/app/logs
```

### Reading the detail log

One `search` record answers "why did the LLM get these chunks?". The record holds the query and the filters. The record holds the candidate count and the timing for every stage. The record holds every returned chunk, with its scores and text.

```json
{
  "ts": "2026-11-27T14:17:59.120",
  "event": "search",
  "query": "turkey hsr termination rights",
  "topic": null,
  "max_results": 5,
  "index_size": 514,
  "mode": "hybrid",
  "reranker": "cross-encoder/ms-marco-MiniLM-L-6-v2",
  "candidate_pool": 50,
  "dense_candidates": 50,
  "bm25_candidates": 31,
  "fused_candidates": 50,
  "sparse_only_candidates": 4,
  "before_filters": 50,
  "after_filters": 50,
  "after_topic_filter": 5,
  "reranked": 50,
  "returned": 5,
  "dense_ms": 180.6,
  "bm25_ms": 105.8,
  "total_ms": 1349.8,
  "rerank_ms": 1056.1,
  "outcome": "ok",
  "results": [
    {
      "rank": 1,
      "chunk_id": "50ae5b218c187f89c7e55ea361f3a1c6",
      "file": "MUFG HSR 2 - Commercial Terms Agreement.md",
      "page": 1,
      "topics": ["Turkey HSR 2"],
      "cosine_distance": 0.797,
      "rrf_score": 0.0101,
      "rerank_score": -9.32,
      "chars": 5585,
      "text": "..."
    }
  ]
}
```

Useful queries (any JSON Lines tool works, `jq` below):

```bash
# every query the LLM sent, newest last
jq -r 'select(.event=="search") | "\(.ts) \(.query) -> \(.returned)/\(.dense_candidates) dense, no BM25-only"' logs/detail.jsonl

# slow searches (more than 500 ms)
jq 'select(.event=="search" and .total_ms > 500) | {query, total_ms, rerank_ms}' logs/detail.jsonl

# queries where BM25 found chunks the dense search missed
jq 'select(.event=="search" and .sparse_only_candidates > 0) | {query, sparse_only_candidates}' logs/detail.jsonl

# searches that returned nothing
jq 'select(.event=="search" and .outcome != "ok")' logs/detail.jsonl

# which files the answers came from
jq -r 'select(.event=="search") | .results[] | .file' logs/detail.jsonl | sort | uniq -c | sort -rn

# documents that failed to index
jq 'select(.event=="scan_document" and .ok==false)' logs/detail.jsonl
```

What the numbers tell you:

- `dense_candidates` far above `returned` with low `rerank_score` means the re-ranker disagreed with the vector search. Try a domain-specific `RERANKER_MODEL`, or `USE_RERANKER=False` to compare.
- `sparse_only_candidates` above zero means BM25 rescued exact terms the vectors missed. Lower `BM25_WEIGHT` hides those; raise it.
- `after_topic_filter` at zero means the `topic` filter removed everything. Check the exact topic with `list_topics`.
- `rerank_ms` dominating `total_ms` means re-ranking is the bottleneck. Lower `RERANKER_TOP_N`, or run on a GPU.
- `outcome: "empty_index"` means nothing was indexed yet.

## Troubleshooting: error messages

The server explains each failure in three parts: what happened, the likely cause, and the fix. The list below covers the messages users hit most.

| Message you see | Cause | Fix |
|---|---|---|
| `The documents folder '<path>' does not exist.` | `DOCS_DIR` points at the wrong folder, or the folder is missing. | Create the folder. Set `DOCS_DIR` to it, or pass `--doc-dir <path>` to the scan. |
| `No supported documents were found in '/app/my-docs'.` or `0 supported document(s) under /app/my-docs` | The container sees an empty documents folder. The bind mount points at a different host folder, `docker compose` ran from another directory, or `DOCS_DIR` is wrong. | Run `docker compose config` and check the host side of `./my-docs:/app/my-docs:ro`. Run `docker exec docs-to-ai ls /app/my-docs` and compare. Move the files into the mounted host folder, then scan again. |
| The index is empty again after every container restart, and the first scan repeats each time | The cache volumes point at the wrong container paths, so the index is written inside the container and thrown away. | Mount `/app/cache/chromadb` and `/app/cache/doc_cache`, as in [docker-compose.yml](docker-compose.yml). Paths like `/app/chromadb` do not match what the app reads. |
| The LLM gets no answer while the first scan runs | The first scan embeds every chunk on CPU and holds the server until it finishes. A 500-chunk corpus takes several minutes. | Follow the progress with `docker logs -f docs-to-ai`. Use a GPU for a 37× faster first scan, or set `CHUNKING_STRATEGY=by_paragraph` to skip the extra sentence embeddings. |
| `The path '<path>' is a file, not a folder.` | `DOCS_DIR` points at one document. | Move the documents into a folder and point `DOCS_DIR` at that folder. |
| `No supported documents were found in '<path>'.` | The folder is empty, or the files have unreadable extensions. | Add PDF, Word, Excel, Markdown, PowerPoint, HTML, TXT, or CSV files, then scan again. |
| `The index is empty, so '<query>' could not match anything.` | Nothing is indexed yet, or the last scan failed. | Run the `scan_all_my_documents` tool, or `python -m app.scan_all_my_documents --doc-dir ./my-docs`. |
| `No results found for query: '<query>'.` | The words are absent from the chunks, or a filter removed every match. | Try other words. Drop the topic, date, phrase, or regex filter. Call `list_topics` to check topics. |
| `The PDF '<file>' could not be read.` | The PDF is encrypted, truncated, or not a real PDF. | Remove the password, repair the file, or re-print it to PDF. Then scan again. |
| `No text could be extracted from '<file>'.` | The page holds an image and no text layer. | Run OCR on the file, save a searchable PDF, then scan again. |
| `A Python package needed for this step is missing: <name>.` | The environment does not match `pyproject.toml`. | Run `uv sync`, then restart the server. |
| `The embedding model '<model>' could not be loaded.` | Model not downloaded, wrong `EMBEDDING_MODEL`, or the device rejected the model. | Run `python -m app.download_models` with network access. Check the model name. Check `torch.cuda.is_available()`. |
| `A network request failed.` | Hugging Face or PyPI is unreachable, or models were never downloaded. | Connect to the internet and run `python -m app.download_models` once. For offline machines, copy a warm `~/.cache/huggingface` from another machine. |
| `The machine ran out of memory.` / `CUDA out of memory` | The embedding batch is too large for the RAM or VRAM. | Lower `EMBEDDING_BATCH_SIZE` to 8 or 16. Pick another GPU with `GPU_DEVICE_INDEX`. Or set `USE_GPU_ACCELERATION_IF_AVAILABLE=False`. |
| `The vector database at '<path>' could not be opened.` | Another process holds the database, the folder is read-only, or the files are damaged. | Stop the other server or container. Check write access. Delete the cache folder and re-scan. |
| `The vector database is locked or unreadable.` | Two servers or containers use `cache/chromadb` at once. | Run one server. Stop the other with `docker compose down` or by closing the other process. |
| `InvalidDimensionException` / `The stored vector size does not match` | The index was built with another embedding model, or `EMBEDDING_DIMENSION` is stale. | Delete `cache/chromadb`, then run `python -m app.scan_all_my_documents --reset`. |
| `The tokenizer could not be loaded.` | tiktoken could not fetch its BPE data, usually because the machine is offline. | Run `python -m app.download_models` with network access, or set `TIKTOKEN_CACHE_DIR` to a filled cache. |
| `A text file could not be decoded.` | The file is not UTF-8 and has no byte-order mark. | Re-save the file as UTF-8, then scan again. |
| `Permission denied` | The server user cannot read the documents or write the cache. | Grant read access to the documents folder and write access to `cache/chromadb` and `cache/doc_cache`. |
| `The disk is full.` | The vector store or document cache cannot grow. | Free disk space, then scan again. |
| `The folder watcher could not start for '<path>'.` | The folder is missing or unreadable, or `watchdog` is not installed. | Create the folder and check `DOCS_DIR`. Run `uv sync`. Then call `start_watching_folder` again. |
| `Cached text for '<file>' is unreadable.` | A cache entry was truncated, for example by a crash. | No action needed. The scan re-extracts the file and rewrites the cache entry. |
| `Compute device: cpu (no GPU detected)` in the log | PyTorch has no CUDA device: CPU-only wheel, or no driver. | Install a CUDA wheel: `uv pip install --index-url https://download.pytorch.org/whl/cu128 torch`. |
| A new container starts for every LLM connection, and it sees no documents | The client config runs `docker run -i --rm mcp/docs-to-ai`. `docker run` creates a fresh container per connection, with no volumes and no index. | Point the client at the running container instead: `"url": "http://localhost:38777/mcp", "transport": "http"`, or use `docker exec -e MCP_TRANSPORT=stdio -i docs-to-ai uv run --no-sync python mcp_server.py` for stdio. |
| `Connection refused` or `Failed to connect to localhost:38777` | The server runs with `MCP_TRANSPORT=stdio`, so nothing listens on the port. | Start it with `MCP_TRANSPORT=http` (the Docker compose file does this) and check the startup log for `Listening on 0.0.0.0:38777/mcp`. |
| The startup log shows `Listening on 127.0.0.1:...` and the host cannot connect | `MCP_HOST=127.0.0.1` binds inside the container only. | Set `MCP_HOST=0.0.0.0`. |
| `No GPU is visible inside this container` in the log | Docker started the container without the GPU device reservation, so `/dev/nvidia*` does not exist inside it. | Add the override: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`. Or set `COMPOSE_FILE` in `.env` (`;` between files on Windows, `:` on Linux/macOS). Or add `--gpus all` to `docker run`. |
| `docker compose up` fails with `could not select device driver "" with capabilities: [[gpu]]` | The host has no NVIDIA driver, no NVIDIA Container Toolkit, or Docker Desktop uses the Hyper-V backend. | Install the NVIDIA driver and (on Linux) the NVIDIA Container Toolkit. On Docker Desktop, enable the WSL2 based engine. Then retry. |
| `Error calling tool '<name>': maximum recursion depth exceeded` | An older build registered each MCP tool under the same name it imported, so the tool called itself. The current source imports the implementations under private names. | Rebuild the container with the current source: `docker compose build --no-cache`. |
| `[FolderWatcher] Warning: Could not check database state: name 'VectorStore' is not defined` | Older build: the watcher used the vector store without importing it, so the empty-index check failed. The watcher still ran; the initial scan followed `FULL_SCAN_ON_BOOT`. | Rebuild the container with the current source. |

Every message also ends with a hint pointing at this section. Copy the `Details:` line when you report a bug.

The scan command exits with code `0` when every document was indexed. The scan command exits with `2` when the report holds a problem: a missing folder, no supported files, or files that failed. The scan command exits with `1` on a fatal error, such as an unloadable model.

## FAQ: search files and PDFs locally

### How do I search my folder for a word or phrase?

Index the folder once, then ask the LLM. The LLM calls `search_documents`. For an exact string, ask for a phrase search. The server filters result text for the quoted phrase.

### How do I search my files without opening each one?

Index the folder once. Ask the LLM for what you need. Every result lists the file name, page, and topic. List topics or documents first to narrow the search to one folder.

### Can I search local PDFs offline?

Yes. Embedding and re-ranking run on your machine. Downloads happen once, at install time or at Docker build time. No document text leaves the machine after that.

### Can I find text inside a scanned PDF?

No OCR. PDF text extraction reads the text layer stored in the file. A scanned PDF without a text layer yields nothing. Run OCR on the file, save a searchable PDF, then re-index the folder.

### How do I find something in a PDF when I do not know the page?

Ask a question instead of a keyword. Dense search matches meaning, so "when do payments fall due" finds the payment terms clause. Each result lists the source file and page number.

### What file types does it index?

PDF, Word (`.docx`, `.doc`), Excel (`.xlsx`, `.xls`, `.xlsam`, `.xlsb`), Markdown, PowerPoint, HTML, TXT, and CSV.

### Does this work as a documents RAG for Claude Desktop?

Yes. Add `mcp_server.py` to the Claude Desktop config. Claude gets search, listing, and indexing tools. Any MCP client works the same way.

### Do I need a GPU for local RAG?

No. CPU works. A GPU makes indexing about 37× faster and re-ranking about 50× faster. The server detects a usable GPU and falls back to CPU automatically.

### How large can a folder be?

The index is a local ChromaDB database. Search cost grows slowly with chunk count. Indexing cost grows linearly, and semantic chunking is the slowest strategy. Chunk counts in the low hundreds of thousands are fine on a desktop machine.

### How do I keep the index current?

Start the folder watcher. Changed files are re-indexed after `DEBOUNCE_SECONDS`. Unchanged files keep their existing chunks. Run `scan_all_my_documents` for a full rebuild, or `--reset` to wipe the index first.

### Why does a search return chunks instead of whole files?

Chunks keep queries precise and keep contexts small. Each chunk carries its file path, page number, and topic. The LLM reads the chunk and cites the file.

## License

MIT
