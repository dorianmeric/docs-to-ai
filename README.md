# Docs-to-AI: local RAG to search local PDFs, Word files, and any folder

Docs-to-AI is a local RAG (retrieval-augmented generation) server for your own documents. It indexes one folder tree of PDFs, Word files, spreadsheets, Markdown, PowerPoint, HTML, TXT, and CSV, and hands the index to any LLM that speaks MCP. The LLM searches the index and answers with quotes from your files.

The recommended way to run it is the Docker image, which serves MCP over HTTP on port 38777. Start the container once and every MCP client on your network can use it. A local Python install is also supported for development and for stdio-only clients.

No cloud service and no API key are involved. The embedding and re-ranking models run on the same machine, so no document text leaves it.

Supported extensions: `.pdf`, `.docx`, `.doc`, `.xlsx`, `.xls`, `.xlsam`, `.xlsb`, `.md`, `.pptx`, `.html`, `.htm`, `.txt`, and `.csv`.

**Contents**

- [Docs-to-AI: local RAG to search local PDFs, Word files, and any folder](#docs-to-ai-local-rag-to-search-local-pdfs-word-files-and-any-folder)
  - [What you can do with it](#what-you-can-do-with-it)
  - [Quick start: Docker with HTTP](#quick-start-docker-with-http)
    - [1. Put your documents in ./my-docs](#1-put-your-documents-in-my-docs)
    - [2. Save the compose file](#2-save-the-compose-file)
    - [3. Start the container](#3-start-the-container)
    - [4. Connect your MCP client](#4-connect-your-mcp-client)
    - [5. Confirm the first scan](#5-confirm-the-first-scan)
  - [Docker reference](#docker-reference)
    - [Volumes and ports](#volumes-and-ports)
    - [Change settings without rebuilding](#change-settings-without-rebuilding)
    - [Build args and model baking](#build-args-and-model-baking)
    - [GPU inside Docker](#gpu-inside-docker)
  - [Connect an MCP client](#connect-an-mcp-client)
    - [HTTP transport](#http-transport)
    - [stdio inside the running container](#stdio-inside-the-running-container)
    - [SSE clients](#sse-clients)
    - [The URL printed at startup](#the-url-printed-at-startup)
    - [Claude Desktop with a local Python install](#claude-desktop-with-a-local-python-install)
  - [How search works](#how-search-works)
  - [Folder topics: how to search a folder](#folder-topics-how-to-search-a-folder)
  - [MCP tools](#mcp-tools)
  - [Example questions for the LLM](#example-questions-for-the-llm)
  - [Install with local Python](#install-with-local-python)
    - [Scan options](#scan-options)
    - [Transports and command-line flags](#transports-and-command-line-flags)
  - [Configuration](#configuration)
    - [Chunking](#chunking)
    - [OCR for scanned PDFs](#ocr-for-scanned-pdfs)
    - [Search](#search)
    - [Embedding model](#embedding-model)
    - [GPU acceleration](#gpu-acceleration)
    - [Topics](#topics)
    - [Storage](#storage)
    - [Startup behaviour](#startup-behaviour)
    - [Server transport](#server-transport)
    - [Example `.env`](#example-env)
  - [Disk space](#disk-space)
    - [Models](#models)
    - [Python packages](#python-packages)
    - [Totals](#totals)
    - [The index and the cache grow with your documents](#the-index-and-the-cache-grow-with-your-documents)
  - [Retrieval pipeline](#retrieval-pipeline)
  - [Production RAG settings](#production-rag-settings)
  - [Logs](#logs)
    - [Log files](#log-files)
    - [Reading the detail log](#reading-the-detail-log)
  - [Troubleshooting: error messages](#troubleshooting-error-messages)
  - [FAQ: search files and PDFs locally](#faq-search-files-and-pdfs-locally)
    - [How do I search my folder for a word or phrase?](#how-do-i-search-my-folder-for-a-word-or-phrase)
    - [How do I search my files without opening each one?](#how-do-i-search-my-files-without-opening-each-one)
    - [Can I search local PDFs offline?](#can-i-search-local-pdfs-offline)
    - [Can I find text inside a scanned PDF?](#can-i-find-text-inside-a-scanned-pdf)
    - [How do I find something in a PDF when I do not know the page?](#how-do-i-find-something-in-a-pdf-when-i-do-not-know-the-page)
    - [What file types does it index?](#what-file-types-does-it-index)
    - [Does this work as a documents RAG for Claude Desktop?](#does-this-work-as-a-documents-rag-for-claude-desktop)
    - [Do I need a GPU for local RAG?](#do-i-need-a-gpu-for-local-rag)
    - [How large can a folder be?](#how-large-can-a-folder-be)
    - [How do I keep the index current?](#how-do-i-keep-the-index-current)
    - [Why does a search return chunks instead of whole files?](#why-does-a-search-return-chunks-instead-of-whole-files)
  - [Project structure](#project-structure)
  - [License](#license)

## What you can do with it

- Search local PDFs and other files with natural language.
- Find exact phrases, invoice numbers, ticket IDs, and product codes in PDFs.
- Search your files from Claude Desktop or any other MCP client.
- Point the server at one folder and get a topic for every subfolder.
- Filter results by topic, date range, phrase, or regex.
- Search scanned PDFs. Pages without a text layer are read with OCR automatically.
- Keep the index current with a folder watcher.
- Run a fully offline documents RAG: the embedding and re-ranking models run locally.

## Quick start: Docker with HTTP

You need Docker Desktop or Docker Engine. Budget about 5 GB of disk: the image already carries the embedding and re-ranking models, and the index grows on top of that. [Disk space](#disk-space) breaks the figure down.

### 1. Put your documents in ./my-docs

Create a folder called `my-docs` next to the compose file and copy your documents into it. Subfolders become topics, so `my-docs/contracts/lease.pdf` is indexed under the topic `contracts`. The container mounts this folder read-only.

### 2. Save the compose file

Save this as `docker-compose.yaml` next to `my-docs`:

````yaml
services:
  docs-to-ai:
    image: dmeric/docs-to-ai
    container_name: docs-to-ai

    volumes:
      - ./cache/chromadb:/app/cache/chromadb   # vector store
      - ./cache/doc_cache:/app/cache/doc_cache # extracted text
      - ./my-docs:/app/my-docs:ro              # your documents, read-only
      - ./logs:/app/logs                       # server.log and detail.jsonl

    # only needed for stdio over `docker exec` (see Connect an MCP client)
    stdin_open: true
    tty: false

    environment:
      - MCP_TRANSPORT=http                     # serves http://localhost:38777/mcp
      - MCP_HOST=0.0.0.0
      - MCP_PORT=38777
      - LOG_DIR=/app/logs                      # server.log and detail.jsonl

    ports:
      - "${MCP_PORT:-38777}:${MCP_PORT:-38777}"

    restart: unless-stopped
````

The image is published on Docker Hub as [dmeric/docs-to-ai](https://hub.docker.com/r/dmeric/docs-to-ai). The repository ships its own [docker-compose.yml](docker-compose.yml), which is the same service plus a `build:` block, all build args, and a comment on every setting. Use that file when you want to build the image yourself as `mcp/docs-to-ai`, for example to change build args or run unreleased code after `docker compose build`.

### 3. Start the container

```bash
docker compose up -d
docker compose logs | grep -A4 "Listening on"                                        # macOS, Linux, WSL
docker compose logs | Select-String "Listening on" -Context 0,4                      # Windows PowerShell
```

The container keeps running and serves MCP at `http://localhost:38777/mcp`. The log line names every address a client can use:

```
2026-11-27 13:56:18 SUCCESS ✅ [MCP Server] Listening on 0.0.0.0:38777/mcp
                                           From inside the container or machine: http://172.23.0.2:38777/mcp
                                           From this Docker host or a browser on it: http://localhost:38777/mcp
                                           From another machine: http://<host-ip>:38777/mcp
```

### 4. Connect your MCP client

Point the client at the HTTP endpoint:

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

Some clients want `"type": "http"` instead of `"transport": "http"`. Use whichever key your client documents. From another machine, replace `localhost` with the host's IP address. [Connect an MCP client](#connect-an-mcp-client) covers the alternatives, including clients that only speak stdio.

### 5. Confirm the first scan

A fresh container has an empty index, so the server scans `/app/my-docs` at startup even though `FULL_SCAN_ON_BOOT` defaults to `False`. A 500-chunk corpus takes several minutes to embed on CPU. Watch the progress, and check that the mount actually contains your files:

```bash
docker exec docs-to-ai ls /app/my-docs    # must list your files
docker logs -f docs-to-ai                 # shows the scan progress
```

Once the scan reports chunks, ask the LLM in your client: "What documents do you have access to?". The answer comes from `list_all_documents`, so it proves the index is reachable.

To re-index later, ask the LLM to call `scan_all_my_documents`, or run it yourself:

```bash
docker exec docs-to-ai uv run --no-sync python -m app.scan_all_my_documents --doc-dir /app/my-docs
```

The folder watcher runs at startup by default (`FOLDER_WATCHER_ACTIVE_ON_BOOT=True`), so a file you drop into `./my-docs` is indexed after `DEBOUNCE_SECONDS` without any further action.

## Docker reference

### Volumes and ports

Four bind mounts hold everything that must survive a container rebuild:

| Host path | Container path | Why it matters |
|---|---|---|
| `./cache/chromadb` | `/app/cache/chromadb` | The vector store. Without this mount the index is rebuilt on every container start. The path must match what the app reads: `/app/chromadb` does not work. |
| `./cache/doc_cache` | `/app/cache/doc_cache` | Extracted text per document, so a second scan skips the parsing and the OCR. |
| `./my-docs` | `/app/my-docs` | Your documents. Mount it `:ro` so the server cannot modify them. |
| `./logs` | `/app/logs` | `server.log` and `detail.jsonl`. Without this mount the logs stay inside the container and disappear when it is recreated. |

Port `38777` publishes the HTTP endpoint for MCP clients. Keep the host port and `MCP_PORT` equal; if you publish a different host port, set `MCP_PUBLIC_URL` so the startup banner and the tool output show the address clients should use.

To index a folder that is not `./my-docs`, add a second mount and point `DOCS_DIR` at it inside the container:

```yaml
    volumes:
      - ./contracts:/app/contracts:ro
    environment:
      - DOCS_DIR=/app/contracts
```

### Change settings without rebuilding

The compose file passes every setting to the container as `${SETTING:-default}`, so a value in `.env` changes both the build args and the runtime environment. Copy [.env.example](.env.example), or add lines with `echo`:

```bash
echo "FULL_SCAN_ON_BOOT=True" > .env
echo "FOLDER_WATCHER_ACTIVE_ON_BOOT=True" >> .env
echo "CHUNKING_STRATEGY=by_paragraph" >> .env   # cheaper than the semantic default
echo "CHUNK_SIZE=512" >> .env
docker compose up -d
```

The container does not read `.env` itself: Compose substitutes the values into the service definition. Transport, logging, OCR, and every other setting from [Configuration](#configuration) can be changed this way, and a restart applies them without a rebuild.

Frequent runtime settings:

| Setting | Effect | Default |
|---|---|---|
| `FULL_SCAN_ON_BOOT` | Re-index every document at server start | `False` |
| `FOLDER_WATCHER_ACTIVE_ON_BOOT` | Watch the documents folder and index changes at server start | `True` |
| `MCP_PORT` | Port for the HTTP transport, inside the container and on the host | `38777` |
| `DOCS_DIR` | Folder inside the container that is scanned for documents | `/app/my-docs` |
| `EMBEDDING_BATCH_SIZE` | Texts embedded per batch; lower it when the machine runs out of memory | `32` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` | `INFO` |
| `MARKER_MODEL_CACHE` | Where Marker keeps its OCR models, for example `/app/cache/marker` on a mounted volume | empty |

### Build args and model baking

Build args bake values into the image. They exist because the build pre-downloads models: the embedding model, the re-ranker, and the tiktoken data must match the settings the container will run with. A runtime environment variable always overrides a baked value, so most build args only matter when you want a different model or OCR engine inside the image.

```bash
docker compose build --build-arg CHUNKING_STRATEGY=by_paragraph --build-arg CHUNK_SIZE=512
docker compose up -d
```

Plain `docker build` works the same way:

```bash
docker build --build-arg EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B --build-arg USE_RERANKER=True -t mcp/docs-to-ai .
```

The model, chunking, search, OCR, and startup settings are build args. The transport (`MCP_*`), logging (`LOG_*`), `DOCS_DIR`, and `EMBEDDING_QUERY_PROMPT` are runtime-only.

Rebuild the image after changing `EMBEDDING_MODEL` or `USE_RERANKER`, because those models are downloaded during the build. Chunking and search settings need a re-scan instead, not a rebuild.

Scanned PDFs need the optional OCR engine, which the default image does not include:

```bash
docker compose build --build-arg INSTALL_MARKER=True
```

That adds Marker, its PyTorch build, and the OCR models to the image: about 110 MB of models for the default `fast` mode. Leave it out if you only index files that already carry text. Without it the container logs one warning and scanned pages stay empty. `MARKER_MODE=balanced` and `vllm` also need `vllm` and an NVIDIA GPU inside the container, so build those images from a base that has `vllm`.

Changing `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`, or `CHROMA_SPACE` forces a new collection, because ChromaDB cannot change the vector size or the distance space in place. The server records the model name and dimension in the collection metadata, detects a stale collection at startup, and recreates it. Re-scan after the recreate:

```bash
docker exec docs-to-ai uv run --no-sync python -m app.scan_all_my_documents --doc-dir /app/my-docs --reset
```

The vector store is a cache built from your documents, so a recreate never touches the source files.

### GPU inside Docker

A container sees only the GPUs that Docker passes to it. Without a device reservation the log says `No GPU is visible inside this container`, even when the host has a GPU.

Docker cannot make the reservation optional in one file, because a host without a GPU fails `docker compose up`. Use the override file on GPU hosts instead:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

To keep plain `docker compose up -d` working, add one line to `.env`. The separator is `;` on Windows and `:` on Linux and macOS.

```bash
COMPOSE_FILE=docker-compose.yml;docker-compose.gpu.yml      # Windows
COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml      # Linux/macOS
```

[docker-compose.gpu.yml](docker-compose.gpu.yml) only adds the device reservation:

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

- An NVIDIA driver on the host. On Windows the normal GeForce driver is enough.
- On Linux, the NVIDIA Container Toolkit (`nvidia-container-toolkit`).
- On Docker Desktop, the WSL2 based engine, which is the default. Do not switch to Hyper-V.

Check that the container sees the GPU:

```bash
docker run --rm --gpus all mcp/docs-to-ai nvidia-smi
docker compose logs | grep "Compute device"
```

Expected log line: `Compute device: cuda:0 (NVIDIA GeForce RTX 5090, 32 GB VRAM)`. The image installs the CUDA-enabled PyTorch wheel on Linux, so no rebuild is needed.

A plain `docker run` needs `--gpus all`; add it yourself, otherwise the container starts on CPU. [GPU acceleration](#gpu-acceleration) covers the settings and the measured speed-up.

## Connect an MCP client

`MCP_TRANSPORT` selects how clients talk to the server, and one transport runs per process:

| Transport | Endpoint | Use it for |
|---|---|---|
| `http` | `MCP_HOST:MCP_PORT/mcp` | Docker and any long-running server. This is what the compose file sets. |
| `stdio` | no port, stdin and stdout | A client that starts the process itself, or `docker exec -i` into a running container. |
| `sse` | `MCP_HOST:MCP_PORT/sse` | Older HTTP clients that need Server-Sent Events. |

### HTTP transport

The container already serves HTTP, so the client only needs a URL:

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

- Some clients want `"type": "http"` instead of `"transport": "http"`. Use whichever key your client documents.
- From another machine, replace `localhost` with the host's IP address, and make sure the port is reachable through the host firewall.
- Any number of clients can share one container, and they share one index.
- Do not put `docker run -i --rm dmeric/docs-to-ai` in a client config. `docker run` starts a fresh container for every connection, with no volumes and no index, so the client sees an empty document folder and re-scans from scratch each time.

### stdio inside the running container

A client that only speaks stdio can run the server inside the running container. This reuses the same container, mounts, and index:

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

Two details matter here. The command goes through `uv run`, because the image keeps its packages in a virtualenv. It also sets `MCP_TRANSPORT=stdio`, because the container already owns the HTTP port. The container has to be running before the client connects.

### SSE clients

Older clients use `http://localhost:38777/sse` with `"transport": "sse"`. Start the server with `MCP_TRANSPORT=sse` (or `--sse`) if the client cannot use the `/mcp` endpoint.

### The URL printed at startup

With `http` or `sse`, startup prints every address a client may need:

```
2026-11-27 13:56:18 SUCCESS ✅ [MCP Server] Listening on 0.0.0.0:38777/mcp
                                           From inside the container or machine: http://172.23.0.2:38777/mcp
                                           From this Docker host or a browser on it: http://localhost:38777/mcp
                                           From another machine: http://<host-ip>:38777/mcp
```

Set `MCP_PUBLIC_URL` when the host port differs from `MCP_PORT`, or when a proxy sits in front of the server:

```bash
MCP_PUBLIC_URL=http://myserver.lan:8080/mcp
```

### Claude Desktop with a local Python install

A local install has no HTTP port unless you start one, so Claude Desktop usually launches it over stdio:

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

To use a locally started HTTP server instead, start it with `MCP_TRANSPORT=http` (or `--http`) and use the same URL config as [HTTP transport](#http-transport).

## How search works

```
Documents (PDF, Word, Excel, Markdown, PowerPoint, HTML, TXT, CSV)
  → text extraction (scanned PDF pages go through OCR)
    → chunking (semantic by default, 1024 tokens)
      → embeddings (Qwen3-Embedding-0.6B, 1024-dim)
        → ChromaDB (cosine HNSW, topic tags on every chunk)
          ↓
    hybrid retrieval: BM25 + dense → RRF → cross-encoder re-rank
          ↓
    MCP tools → Claude or any MCP client
```

Dense vectors catch meaning, BM25 catches exact strings, RRF merges both ranked lists, and a cross-encoder re-scores the merged candidates. Documents are parsed once at index time, so a search only touches the index. [Retrieval pipeline](#retrieval-pipeline) walks through the five stages, and [Production RAG settings](#production-rag-settings) explains why each stage is configured the way it is.

## Folder topics: how to search a folder

The server maps folders to topics, and a topic narrows a search. One folder tree becomes one browsable index.

- Each folder name becomes a topic.
- Nested folders become nested topics, joined with ` > `.
- Files with the same name in different folders stay separate, so two `introduction.pdf` files do not overwrite each other.

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

## MCP tools

Search and discovery:

- `search_documents` runs hybrid search over all documents. Filters: `topic`, `phrase_search`, `date_from`, `date_to`, `regex_pattern`.
- `list_all_documents` lists every indexed document, grouped by first topic. Filter with `topic`.
- `list_topic` lists the documents of one topic (folder), including its subfolders, with the full path of each file. It accepts `legal`, `legal > contracts`, or `legal/contracts`, and falls back to matching the folder name at any depth.
- `list_topics` lists topics.
- `get_collection_stats` reports chunk counts, document counts, file types, and index details.

Read documents in full:

- `read_file_metadata` returns one document's metadata: path, topics, type, size, created and last-modified dates, chunk count, page numbers with chunks, OCR pages, and whether the file changed on disk since the last scan.
- `read_file` returns one document's whole text, page by page, with the same metadata block. Use `page` to read a single page and `max_chars` to cap the response. The text is re-read from the source file, so it is complete even when the chunks are split; if the file is gone, the text is rebuilt from the indexed chunks and the response says so.
- `read_multiple_files` takes a list of names and returns the same metadata and text for each one as a JSON list. `max_chars` caps the text of each file. A name that does not resolve comes back as an entry with an `error` field, so one miss does not hide the rest.
- `read_file_raw` returns the original file as a base64 string, with MIME type, byte count, and SHA-256, so the client can save or forward the real PDF, DOCX, or image. `max_bytes` defaults to 1 MB because base64 inflates a file by a third; raise it to fetch something bigger.

All four reading tools take the same document names: a filename, a full path, or part of either, as shown by `list_all_documents` or `list_topic`. If a name matches more than one document, the tool answers with the candidates instead of guessing.

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

Read a whole document:

- "Show me the full text of the UzKor K-sure policy."
- "How big is the Commercial Terms Agreement, and when was it last changed?"
- "Send me the actual Investment Agency Agreement file."
- "Read the Commercial Terms Agreement and the Investment Agency Agreement together."

Search a folder by topic:

- "Search the Python_Programming topic for decorators."
- "List all documents under Machine_Learning, including subfolders."
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

## Install with local Python

A local install runs the same server outside Docker. It uses `uv` for Python packages.

Install `uv`:

```bash
# macOS / Linux
curl -LsS https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install dependencies, index `./my-docs`, and start the server:

```bash
uv sync                              # install dependencies
python -m app.scan_all_my_documents  # index ./my-docs
python mcp_server.py --http          # serve MCP at http://localhost:38777/mcp
```

Windows helper scripts sit in the repo root: `1.setup-python-env.ps1`, `2.scan-all-my-documents-in-python.ps1`, `3.run-mcp-server-in-python.ps1`.

The first scan downloads the embedding model (about 1.2 GB) and the re-ranker (about 90 MB). Pre-download both with `python -m app.download_models`. [Disk space](#disk-space) lists every model, its size, and the total a setup needs.

Scanned PDFs are read by Marker, which is optional: without it every other file type still indexes.

```bash
uv sync --extra marker    # adds marker-pdf, its torch build, and the OCR models
```

The `fast` mode needs no extra server and downloads about 110 MB of models on first use. `balanced` and `vllm` need `vllm` (NVIDIA GPU) or `llama.cpp`; see [OCR for scanned PDFs](#ocr-for-scanned-pdfs).

Checking the install: `python mcp_server.py --show-config` prints the effective settings, including `OCR_STATUS=ready (Marker ...)` once Marker and its models are reachable.

### Scan options

```bash
python -m app.scan_all_my_documents --doc-dir ./my-docs   # index another folder
python -m app.scan_all_my_documents --reset               # wipe the index, then re-index
```

The scan walks the folder tree, derives topics from folder names, extracts and chunks the text of each file, and stores every chunk in ChromaDB with its topic tags.

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

Inside Docker, run the same command through the container:

```bash
docker exec docs-to-ai uv run --no-sync python -m app.scan_all_my_documents --doc-dir /app/my-docs
```

### Transports and command-line flags

```bash
python mcp_server.py --http --host 0.0.0.0 --port 38777     # same as MCP_TRANSPORT=http
MCP_TRANSPORT=http MCP_PORT=38777 python mcp_server.py
MCP_TRANSPORT=sse  python mcp_server.py --port 38777
python mcp_server.py                                        # stdio, the local default
```

`--websocket` still works as an alias for `--http`. `--show-config` prints the effective configuration and exits, and `--help` prints every setting with its default. [Server transport](#server-transport) lists the transport settings, and [Connect an MCP client](#connect-an-mcp-client) shows the matching client config.

## Configuration

Every setting has a default, and you can override any of them without editing code. Values are resolved in this order:

1. Environment variables win over everything. Example: `CHUNKING_STRATEGY=semantic python mcp_server.py`.
2. A `.env` file next to `pyproject.toml` sets values for one machine. Real environment variables still win. Copy [.env.example](.env.example) and edit it: each line ends with a comment that gives what the setting does, the valid options, and the default. Inline `#` comments work, and a value with spaces needs quotes, for example `TOPIC_SEPARATOR=" > "`.
3. Docker build args bake defaults into an image. Most build args are also passed to the container as runtime variables when it starts, so a `.env` line changes both. See [Build args and model baking](#build-args-and-model-baking).

Print the effective values with `python mcp_server.py --show-config` (in Docker: `docker exec docs-to-ai uv run --no-sync python mcp_server.py --show-config`). Print every setting and default with `python mcp_server.py --help`.

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

Semantic chunking is the default. The chunker embeds consecutive sentences and cuts where the sentence similarity drops below a percentile. The sizes below are always token counts.

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

Token counts come from tiktoken, not from the embedding model tokenizer, so the two differ by a small margin.

### OCR for scanned PDFs

A scanned PDF stores a picture of each page, not text. Text extraction finds nothing and the page would be indexed empty. When a page's text layer holds fewer than `OCR_MIN_TEXT_CHARS` characters, that page is read by [Marker](https://github.com/datalab-to/marker), which runs layout analysis before OCR, so multi-column scans, tables, and forms come back in reading order. The recognised text is indexed like any other text, and each chunk records that it came from OCR, so results and `read_file` mark those pages `(OCR)`.

Marker is an optional dependency because it brings its own PyTorch build and models:

```bash
uv sync --extra marker                            # local install
docker compose build --build-arg INSTALL_MARKER=True   # Docker
```

Without it the server still runs: every other file type indexes, and one warning says how to install Marker.

| Setting | Env var | Default | Description |
|---|---|---|---|
| OCR on | `OCR_ENABLED` | `True` | Read pages that have no usable text layer |
| Scan threshold | `OCR_MIN_TEXT_CHARS` | `20` | A page below this many characters is treated as a scan |
| Pages per document | `OCR_MAX_PAGES` | `9999` | Ceiling on scanned pages read per document; `0` turns OCR off |
| Marker mode | `MARKER_MODE` | `fast` | `fast`, `balanced`, `vllm`, `no_ocr`, or `auto` |
| Marker device | `MARKER_DEVICE` | empty | `cuda`, `cuda:1`, `mps`, `cpu`; empty follows `USE_GPU_ACCELERATION_IF_AVAILABLE` |
| Model cache | `MARKER_MODEL_CACHE` | empty | `HF_HOME` for Marker's models; empty uses the Hugging Face cache |

Marker modes, from Marker's own benchmarks:

| Mode | Hardware | Speed | Best for |
|---|---|---|---|
| `fast` (default) | CPU or GPU, in-process ONNX | ~7 pages/s mixed | Everyday scans. No `vllm`, no extra server, ~110 MB of models |
| `balanced` | GPU, needs `vllm` or `llama.cpp` | ~17 pages/s | Tables, maths, and difficult scans |
| `vllm` | GPU, needs `vllm` | ~4.5 pages/s | Degraded scans, handwriting, dense formulas |
| `no_ocr` | any | fastest | Text-layer PDFs only; scans are skipped |

How it behaves:

- Only pages that need it are read. A PDF with a text layer costs nothing extra, and a mixed PDF hands Marker just its scanned pages (Marker's `page_range`).
- Blank pages are skipped, because a page with no image and no drawing has nothing to read.
- Every scanned page is read by default: `OCR_MAX_PAGES=9999` is no practical limit, and the setting stays as a ceiling for pathological files. When a document hits it, the log says how many pages were left. `OCR_MAX_PAGES=0` turns OCR off.
- OCR runs once per document. The extracted text lands in `cache/doc_cache`, so later scans and `read_file` reuse it.
- Turning OCR on, or changing `MARKER_MODE`, `OCR_MIN_TEXT_CHARS`, or `OCR_MAX_PAGES`, makes the cached text of PDFs stale. The next scan re-reads those PDFs, so previously empty scans fill in. Other file types keep their cached text.
- `MARKER_MODE=balanced` or `vllm` without `vllm` or a `llama-server` binary is reported at startup instead of failing mid-scan.
- Models live in the Hugging Face cache (about 110 MB for `fast`). Set `MARKER_MODEL_CACHE` to keep them on a mounted volume, or bake them into a Docker image by building with `INSTALL_MARKER=True`.
- Reading runs at index time, not at search time. `fast` reads a page in well under a second on CPU after the models load, and the first document of a run pays a few seconds for model loading.

The log reports the outcome per document:

```
[OCR] OCR is available: Marker 2.2.0, mode fast, device cpu
[OCR] Marker read 12 page(s) of contract.pdf in 2.4s (0.2s per page)
[OCR] OCR read 12 of 20 scanned page(s) in contract.pdf
[OCR] contract.pdf: OCR stopped after OCR_MAX_PAGES=10 page(s), so 8 more scanned page(s) stay empty.
```

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

On CPU, re-ranking 50 candidates costs about 1.8 s per search, so lower `RERANKER_TOP_N` when a search feels slow. Raise `EMBEDDING_BATCH_SIZE` to 64 or 128 on a GPU and keep the default 32 on CPU.

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

Measured on an RTX 5090 against a 16-core CPU, same models, batch size 32, bf16:

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

The chosen device is probed with a small allocation, so a CUDA build that cannot run on the installed driver falls back to CPU. Startup prints the device: `Compute device: cuda:0 (NVIDIA GeForce RTX 5090, 32 GB VRAM)`. `python mcp_server.py --show-config` prints the `DEVICE=` line.

```bash
# force CPU on a GPU machine
USE_GPU_ACCELERATION_IF_AVAILABLE=False

# use the second GPU
GPU_DEVICE_INDEX=1
```

GPU acceleration needs a CUDA-enabled PyTorch build. The CPU wheel reports no CUDA devices, so install a matching wheel:

```bash
uv pip install --index-url https://download.pytorch.org/whl/cu128 torch   # cu128 for RTX 50xx and newer
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.device_count())"
```

In Docker the CUDA wheel is already installed and the container only needs the device reservation; see [GPU inside Docker](#gpu-inside-docker).

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
| Documents dir | `DOCS_DIR` | `my-docs` | Folder scanned for documents (`/app/my-docs` in the Docker image) |
| Collection name | `CHROMA_COLLECTION_NAME` | `my-documents` | ChromaDB collection name |
| Distance space | `CHROMA_SPACE` | `cosine` | HNSW space: `cosine`, `l2`, or `ip` |
| ef_search | `HNSW_EF_SEARCH` | `200` | HNSW query candidate list size, ChromaDB default is 100 |
| ef_construction | `HNSW_EF_CONSTRUCTION` | `200` | HNSW build candidate list size, ChromaDB default is 100 |

The index uses cosine space, because the embedding model returns normalised vectors and cosine matches normalised vectors. ChromaDB defaults to `l2`, which fits them poorly. `ef_search=200` raises recall at query time and can be changed at runtime. `ef_construction` only affects newly built index segments.

In Docker the two cache folders are the bind mounts from [Volumes and ports](#volumes-and-ports), and they cannot be moved with an environment variable.

### Startup behaviour

| Setting | Env var | Default | Description |
|---|---|---|---|
| Full scan on boot | `FULL_SCAN_ON_BOOT` | `False` | Re-index every document at server start |
| Watcher on boot | `FOLDER_WATCHER_ACTIVE_ON_BOOT` | `True` | Start the folder watcher at server start |
| Debounce | `DEBOUNCE_SECONDS` | `10` | Idle time after the last file change |
| Full scan interval | `FULL_SCAN_INTERVAL_DAYS` | `7` | Days between automatic full rescans |

An empty index is scanned at startup even when `FULL_SCAN_ON_BOOT=False`, so a fresh container indexes its documents without extra configuration.

### Server transport

| Setting | Env var | Default | Description |
|---|---|---|---|
| Transport | `MCP_TRANSPORT` | `stdio` | `stdio`, `http` (`/mcp`), or `sse` (`/sse`). The compose file sets `http` |
| Host | `MCP_HOST` | `0.0.0.0` | HTTP bind address |
| Port | `MCP_PORT` | `38777` | HTTP port |
| Public URL | `MCP_PUBLIC_URL` | empty | Address printed at startup and used for client instructions |

`MCP_HOST=127.0.0.1` binds inside the container only, so the host cannot connect. Keep `0.0.0.0` unless you bind the port to loopback in the compose file.

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
OCR_ENABLED=True                  # read scanned PDFs with Marker
OCR_MAX_PAGES=9999                # ceiling per document; 0 turns OCR off
MARKER_MODE=fast                  # fast needs no extra backend; balanced/vllm need vllm
```

The same file works for Docker and for a local install. In Docker, Compose substitutes these values into the service definition; locally, `mcp_server.py` reads the file itself.

## Disk space

The code is small. The models are not: several neural models run locally, and together they need more disk than everything else combined. Budget about **2.8 GB** for a CPU install with OCR, and **7 to 16 GB** for a GPU install, depending on how much accuracy you ask Marker for. That is a one-time cost per machine, and the index and the extraction cache grow with your corpus on top of it.

### Models

| Model | What it does | Download |
|---|---|---|
| `Qwen/Qwen3-Embedding-0.6B` | Embeds chunks and queries, and the per-sentence passes of semantic chunking. 1136 MB of weights, plus tokenizer files | **1.2 GB** |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | Re-scores the fused search candidates | **0.09 GB** |
| `tiktoken cl100k_base` | Counts tokens so a chunk really is 1024 tokens | 2 MB |
| `datalab-to/indra-ocr` | Marker `fast` mode: ONNX layout and line OCR for scanned pages | **0.12 GB** |
| `datalab-to/surya-ocr-2.5` | Marker `balanced`/`vllm` mode: 650M-parameter VLM that reads scans, tables, and maths | **1.3 GB** |
| Surya layout, text-detection, and OCR-error checkpoints | Page layout and OCR confidence for Marker `balanced` | **~0.3 GB** |

A base install (embedding, re-ranker, tokenizer) is 1.3 GB of models. Marker `fast` adds 0.12 GB, because it runs its own small ONNX models and needs no VLM. Marker `balanced` or `vllm` adds about 1.6 GB of models and needs `vllm` (several GB of wheels) or `llama.cpp` on top.

Weights download on first use and stay cached:

- Linux/macOS: `~/.cache/huggingface`
- Windows: `%USERPROFILE%\.cache\huggingface`
- Marker's models follow `MARKER_MODEL_CACHE` when it is set (`HF_HOME`), so they can live on another volume.

Nothing re-downloads after that. `python -m app.download_models` fetches everything up front, which is what the Docker build does.

### Python packages

| Setup | What is installed | Disk |
|---|---|---|
| CPU, no OCR | torch (CPU), transformers, chromadb, fastmcp, sentence-transformers | ~1.2 GB |
| CPU with Marker `fast` | the above, plus Marker, Surya, ONNX runtime, torch 2.15 | ~1.4 GB (measured) |
| GPU | the CUDA torch wheel and its CUDA libraries instead of the CPU wheel | 5.5-6.5 GB |
| GPU with `MARKER_MODE=balanced` or `vllm` | plus `vllm` and its CUDA kernels | +5 to 7 GB |

### Totals

| Setup | Packages | Models | Total |
|---|---|---|---|
| CPU, text-layer PDFs only (`OCR_ENABLED=False`, no marker extra) | 1.2 GB | 1.3 GB | **~2.5 GB** |
| CPU with Marker `fast` (the default setup) | 1.4 GB | 1.4 GB | **~2.8 GB** |
| GPU with Marker `fast` | 5.5-6.5 GB | 1.4 GB | **~7-8 GB** |
| GPU with Marker `balanced` or `vllm` | 11-13 GB | 2.9 GB | **~14-16 GB** |

The GPU ranges are wide because the CUDA PyTorch wheel and `vllm` differ per CUDA version. Measure your own install with `du -sh .venv ~/.cache/huggingface` (`Get-ChildItem -Recurse | Measure-Object Length -Sum` on Windows).

Leave a couple of GB free while the models download, because the largest file (1.3 GB) is written to a temporary name before it is moved into the cache.

In Docker the embedding model, the re-ranker, and the tokenizer data are baked into the image at build time, which is why the image is about 2.5 GB before the OCR engine and about 3 GB with `INSTALL_MARKER=True`. Baked models keep `docker compose up` from downloading anything. To keep the image small instead, mount a volume for the Marker models and let them download once:

```yaml
volumes:
  - ./cache/marker:/app/cache/marker
environment:
  - MARKER_MODEL_CACHE=/app/cache/marker
```

### The index and the cache grow with your documents

| Folder | What grows | Measured |
|---|---|---|
| `cache/chromadb` | One vector (1024 floats = 4 KB) plus the chunk text and metadata, plus the HNSW graph | 18 MB for 514 chunks, about 35 KB per chunk |
| `cache/doc_cache` | The extracted text of each document, so a re-scan skips the parse | Typically 10-30% of the source documents' size |

A rough guide for the vector store: 1 GB per 30,000 chunks, so 10,000 average documents (about 100 chunks each) need around 35 GB. Removing documents does not shrink it, so run a scan with `--reset`, or delete `cache/chromadb`, to reclaim the space.

## Retrieval pipeline

1. Dense search: encode the query with Qwen3-Embedding-0.6B, then query the HNSW index in cosine space with `ef_search=200`. Queries use the model query instruction prompt.
2. Sparse search: score the query with BM25 over the same chunks. BM25 finds IDs, ticket numbers, product codes, and names.
3. Fusion: merge both ranked lists with RRF, `score = Σ weight / (RRF_K + rank)`. `BM25_WEIGHT` sets the BM25 share.
4. Filters: apply `topic`, `date_from`, `date_to`, `phrase_search`, and `regex_pattern` to the fused candidates.
5. Re-rank: score up to `RERANKER_TOP_N` candidates with the cross-encoder, and return the best `max_results`.

Search output lists topic, source file, page, and a relevance percentage. The percentage is `1 - cosine distance`; non-cosine spaces print the raw distance instead.

## Production RAG settings

The settings below come from 2026 production RAG research. The marked settings are the current defaults.

| # | Recommendation | Status | Why |
|---|---|---|---|
| 1 | Upgrade the embedding model. `all-MiniLM-L6-v2` is a prototyping model: 384-dim, 256-token context. | Done. Default is `Qwen/Qwen3-Embedding-0.6B`: 1024-dim, 32K context. `BAAI/bge-m3` also works. | Newer models retrieve better. MiniLM truncates long chunks at 256 tokens. |
| 2 | Add hybrid BM25 + dense retrieval, fuse with RRF. | Done. `USE_BM25=True`, `RRF_K=60`. Tune `BM25_WEIGHT`. | Dense-only search misses exact strings. Hybrid adds about 7% nDCG. |
| 3 | Keep cross-encoder re-ranking over a wide candidate pool. | Done. `USE_RERANKER=True`, `RERANKER_TOP_N=50`. | Re-ranking adds 15-30 points of precision@5. Test a reranker on your own corpus, because a generic reranker can hurt niche domains. |
| 4 | Reduce or drop chunk overlap. | Optional. `CHUNK_OVERLAP=0` to `100`. | Overlap showed no measurable gain in 2026 studies and raised indexing cost. Keep overlap for legal clauses and tables. |
| 5 | Target 512-1024 tokens per chunk. | Done. `CHUNK_SIZE=1024`, `CHUNK_BY_TOKEN=True`, `SEMANTIC_CHUNK_MAX_SIZE=1024`. | Quality drops past about 2.5k tokens. 512-1024 tokens works best. |
| 6 | Prefer paragraph or heading chunking. Treat semantic chunking as opt-in. | Overridden. The default is `semantic`. Switch to `by_paragraph` or `semantic_heading` when ingest cost matters. | Recursive chunking matches semantic chunking up to about 5k tokens at lower cost, and semantic chunking can over-fragment. |
| 7 | Add diversity (MMR) to result selection. | Not exposed as a setting. | MMR raised nDCG@5 by 4-11 points in 2026 benchmarks. |
| 8 | Tune ChromaDB HNSW for cosine space. | Done. `space="cosine"`, `ef_search=200`, `ef_construction=200`. | `l2` fits normalised text embeddings poorly. Higher `ef_search` raises recall. |
| 9 | Add RAG evaluation to CI. | Not implemented. Use RAGAS with 50-100 curated samples and a fixed judge model. | Component metrics separate retrieval failures from generation failures. |
| 10 | Apply metadata filters before re-ranking. | Optional. The `topic`, `date_from`, `date_to`, and `regex_pattern` filters run on fused candidates before re-ranking. | Filters shrink the candidate pool before scoring. |

Not adopted: contextual retrieval and late chunking. Contextual retrieval runs about 120× slower at indexing, and neither gain is proven on small local corpora. Late chunking can hurt short passages.

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
- `SUCCESS ✅` records something that worked: a model loaded, a folder watched, chunks added.
- `WARN ⚠️` records a fallback or a partial problem. The work continues.
- `ERROR ❌` records a failure. The message carries `Problem`, `Cause`, and `Fix` lines.

Multi-line messages (scan reports, error explanations) are indented under their first line, so `grep ERROR` finds the whole block by its first line.

stdout stays clean, because it carries the MCP protocol and the CLI reports (`--help`, `--show-config`, scan reports). Log lines never go to stdout, so they cannot corrupt the MCP stream.

### Log files

Two files sit in `logs/` (`/app/logs` in Docker, bind-mounted to `./logs` on the host):

| File | Content |
|---|---|
| `logs/server.log` | Every action of the server: startup, model loading, watcher events, scans, tool calls, searches, errors |
| `logs/detail.jsonl` | One JSON object per line for the events needed to debug retrieval: `server_start`, `tool_call`, `search`, `scan_document`, `scan_summary`, `incremental_change`, `watch_batch`, `ocr_document` |

`ocr_document` records what OCR did with one PDF: `engine` (`marker`), `total_pages`, the `ocr_pages` list with per-page characters, the pages still without text, the pages the OCR engine found nothing in, the pages skipped by `OCR_MAX_PAGES`, and the pages skipped as blank. Find the documents that needed the most OCR work with:

```bash
jq 'select(.event=="ocr_document") | {file, ocr_pages: (.ocr_pages|length), chars: ([.ocr_pages[].chars]|add), empty: (.pages_still_without_text|length)}' logs/detail.jsonl
```

Both files rotate by size: a full file is renamed to `.1`, `.2`, and so on, and the oldest file beyond `LOG_BACKUP_COUNT` is deleted.

| Setting | Env var | Default | Description |
|---|---|---|---|
| Log dir | `LOG_DIR` | `logs` | Folder for both files. Docker uses `/app/logs` |
| Level | `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| Console | `LOG_CONSOLE` | `True` | Also print to stderr, which `docker logs` shows |
| Max size | `LOG_MAX_BYTES` | `10485760` | Rotate a file after 10 MB |
| Backups | `LOG_BACKUP_COUNT` | `5` | Rotated files kept per log |
| Detail log | `LOG_DETAIL_ENABLED` | `True` | Write `detail.jsonl` |
| Chunk text | `LOG_CHUNK_TEXT_CHARS` | `2000` | Chunk text stored per result, `0` stores none |
| Slow query | `SLOW_QUERY_MS` | `20000` | A search slower than this logs a `WARN` with the step breakdown |

Docker writes the files to the host because the compose file mounts `./logs` and sets `LOG_DIR=/app/logs`. Without both lines the logs land in the container's own filesystem and vanish on the next `docker compose down` or image update:

```yaml
    volumes:
      - ./logs:/app/logs
    environment:
      - LOG_DIR=/app/logs
```

### Reading the detail log

One `search` record answers "why did the LLM get these chunks?". The record holds the query and the filters, the candidate count and the timing for every stage, and every returned chunk with its scores and text.

Every query also logs one line to `server.log` with the time of each step and the total response time, so a saturated server is visible at a glance:

```
2026-11-27 22:25:43 INFO    [MCP] Search 'PD-ROT-77' -> ok, 1 chunk(s) in 111 ms (prep 0 | encode 80 | chroma 3 | bm25_build 1 | bm25 0 | fuse 0 | dense 83 | filters 0 | rerank 26 | format 0)
2026-11-27 22:26:07 INFO    [MCP] Search 'PD-ROT-77 2' -> ok, 1 chunk(s) in 109 ms (...) [3 tool calls in flight]
2026-11-27 22:31:10 WARN  ⚠️ [MCP] Search 'annual report' -> ok, 5 chunk(s) in 24500 ms (...) - over SLOW_QUERY_MS
```

| Field | Meaning |
|---|---|
| `prep_ms` | Time to get the store and read the index size |
| `encode_ms` | Query embedding on the CPU or GPU |
| `chroma_ms` | Vector search inside ChromaDB |
| `bm25_build_ms` | Rebuilding the sparse index, `0` when it is warm |
| `bm25_ms` | BM25 scoring |
| `fuse_ms` | RRF fusion plus fetching sparse-only chunks |
| `dense_ms` | `encode_ms` + `chroma_ms` |
| `filters_ms` | Phrase, date and regex filters |
| `rerank_ms` | Cross-encoder re-ranking |
| `format_ms` | Building the text the LLM receives |
| `search_ms` | Whole retrieval pipeline |
| `response_ms` | Whole tool call, from request to response |
| `concurrent_tool_calls` | Tool calls running when this query arrived |
| `peak_concurrent_tool_calls` | Highest overlap seen in the process |
| `steps` | The same numbers as an ordered list |

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
# every query the LLM sent, newest last, with the total response time
jq -r 'select(.event=="search") | "\(.ts) \(.response_ms) ms  \(.query) -> \(.returned) chunks"' logs/detail.jsonl

# slow searches (more than 500 ms), with the step breakdown
jq 'select(.event=="search" and .response_ms > 500) | {query, response_ms, steps}' logs/detail.jsonl

# which step dominates: total time per step over all queries
jq -r 'select(.event=="search") | .steps[] | "\(.step) \(.ms)"' logs/detail.jsonl \
  | awk '{sum[$1]+=$2; n[$1]++} END {for (s in sum) printf "%-12s %8.0f ms total  %6.0f ms avg\n", s, sum[s], sum[s]/n[s]}' \
  | sort -k2 -rn

# queries that ran while other tool calls were in flight
jq 'select(.event=="search" and .concurrent_tool_calls > 1) | {ts, query, concurrent_tool_calls, response_ms}' logs/detail.jsonl

# highest concurrency seen, per tool
jq 'select(.event=="tool_call") | {tool, peak_concurrent_tool_calls}' logs/detail.jsonl | sort -u

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
- `sparse_only_candidates` above zero means BM25 rescued exact terms the vectors missed. Lowering `BM25_WEIGHT` hides those, so raise it instead.
- `after_topic_filter` at zero means the `topic` filter removed everything. Check the exact topic with `list_topics`.
- `rerank_ms` dominating `response_ms` means re-ranking is the bottleneck. Lower `RERANKER_TOP_N`, or run on a GPU.
- `response_ms` rising while `encode_ms` and `chroma_ms` stay flat means the machine is queueing work, not searching slowly. Check `peak_concurrent_tool_calls` and the `WARN ... over SLOW_QUERY_MS` lines.
- `bm25_build_ms` spiking means the sparse index was rebuilt for that query, which happens after every scan or incremental update.
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
| `The index is empty, so '<query>' could not match anything.` | Nothing is indexed yet, or the last scan failed. | Run the `scan_all_my_documents` tool, or `python -m app.scan_all_my_documents --doc-dir ./my-docs`. In Docker, add `docker exec docs-to-ai uv run --no-sync` in front. |
| `No results found for query: '<query>'.` | The words are absent from the chunks, or a filter removed every match. | Try other words. Drop the topic, date, phrase, or regex filter. Call `list_topics` to check topics. |
| `The PDF '<file>' could not be read.` | The PDF is encrypted, truncated, or not a real PDF. | Remove the password, repair the file, or re-print it to PDF. Then scan again. |
| `No text could be extracted from '<file>'.` | The file is empty, or a scanned PDF whose pages OCR could not read. | For a PDF, check `OCR_ENABLED=True`, `OCR_MAX_PAGES` above zero, and that `--show-config` reports `OCR_STATUS=ready`. See [OCR for scanned PDFs](#ocr-for-scanned-pdfs). |
| `OCR is enabled but unavailable: Marker is not installed` | The optional OCR engine is missing, so scanned pages stay empty. | Run `uv sync --extra marker`, or build the Docker image with `INSTALL_MARKER=True`. Then restart the server. |
| `OCR is enabled but unavailable: MARKER_MODE=balanced needs a VLM backend` | `balanced` and `vllm` hand pages to a Surya VLM, and neither `vllm` nor `llama-server` was found. | Install `vllm` on an NVIDIA machine or `llama.cpp`, or set `MARKER_MODE=fast`, which needs no backend. |
| `OCR stopped after OCR_MAX_PAGES=<n> page(s), so <m> more scanned page(s) stay empty` | `OCR_MAX_PAGES` was lowered below the page count of this document. | Raise `OCR_MAX_PAGES`, then re-scan. |
| `Marker found no text in <n> page(s)` | The page is blank, or `MARKER_MODE=fast` is too weak for the scan. | Try `MARKER_MODE=balanced` (needs `vllm` or `llama.cpp`) or `vllm` for degraded scans. |
| `Marker could not read '<file>' (...)` | Marker raised while converting the document. | The message names the exception. Check `--show-config` (`OCR_STATUS`, `MARKER_MODE`, `MARKER_DEVICE`), free RAM (`fast` wants a few GB), and that the models finished downloading. |
| `A Python package needed for this step is missing: <name>.` | The environment does not match `pyproject.toml`. | Run `uv sync`, then restart the server. |
| `The embedding model '<model>' could not be loaded.` | Model not downloaded, wrong `EMBEDDING_MODEL`, or the device rejected the model. | Run `python -m app.download_models` with network access. Check the model name. Check `torch.cuda.is_available()`. |
| `A network request failed.` | Hugging Face or PyPI is unreachable, or models were never downloaded. | Connect to the internet and run `python -m app.download_models` once. For offline machines, copy a warm `~/.cache/huggingface` from another machine. |
| `The machine ran out of memory.` / `CUDA out of memory` | The embedding batch is too large for the RAM or VRAM. | Lower `EMBEDDING_BATCH_SIZE` to 8 or 16. Pick another GPU with `GPU_DEVICE_INDEX`. Or set `USE_GPU_ACCELERATION_IF_AVAILABLE=False`. |
| `The vector database at '<path>' could not be opened.` | Another process holds the database, the folder is read-only, or the files are damaged. | Stop the other server or container. Check write access. Delete the cache folder and re-scan. |
| `The vector database is locked or unreadable.` | Two servers or containers use `cache/chromadb` at once. | Run one server. Stop the other with `docker compose down` or by closing the other process. |
| `InvalidDimensionException` / `The stored vector size does not match` | The index was built with another embedding model, or `EMBEDDING_DIMENSION` is stale. | Delete `cache/chromadb`, then run `python -m app.scan_all_my_documents --reset` (in Docker, through `docker exec`, as in [Scan options](#scan-options)). |
| `The tokenizer could not be loaded.` | tiktoken could not fetch its BPE data, usually because the machine is offline. | Run `python -m app.download_models` with network access, or set `TIKTOKEN_CACHE_DIR` to a filled cache. |
| `A text file could not be decoded.` | The file is not UTF-8 and has no byte-order mark. | Re-save the file as UTF-8, then scan again. |
| `Permission denied` | The server user cannot read the documents or write the cache. | Grant read access to the documents folder and write access to `cache/chromadb` and `cache/doc_cache`. |
| `The disk is full.` | The vector store or document cache cannot grow. | Free disk space, then scan again. |
| `The folder watcher could not start for '<path>'.` | The folder is missing or unreadable, or `watchdog` is not installed. | Create the folder and check `DOCS_DIR`. Run `uv sync`. Then call `start_watching_folder` again. |
| `Cached text for '<file>' is unreadable.` | A cache entry was truncated, for example by a crash. | No action needed. The scan re-extracts the file and rewrites the cache entry. |
| `Compute device: cpu (no GPU detected)` in the log | PyTorch has no CUDA device: CPU-only wheel, or no driver. | Install a CUDA wheel: `uv pip install --index-url https://download.pytorch.org/whl/cu128 torch`. |
| A new container starts for every LLM connection, and it sees no documents | The client config runs `docker run -i --rm mcp/docs-to-ai`. `docker run` creates a fresh container per connection, with no volumes and no index. | Point the client at the running container instead: `"url": "http://localhost:38777/mcp", "transport": "http"`, or use `docker exec -e MCP_TRANSPORT=stdio -i docs-to-ai uv run --no-sync python mcp_server.py` for stdio. |
| `Connection refused` or `Failed to connect to localhost:38777` | The server runs with `MCP_TRANSPORT=stdio`, so nothing listens on the port. | Start it with `MCP_TRANSPORT=http` (the compose file does this) and check the startup log for `Listening on 0.0.0.0:38777/mcp`. |
| The startup log shows `Listening on 127.0.0.1:...` and the host cannot connect | `MCP_HOST=127.0.0.1` binds inside the container only. | Set `MCP_HOST=0.0.0.0`. |
| `No GPU is visible inside this container` in the log | Docker started the container without the GPU device reservation, so `/dev/nvidia*` does not exist inside it. | Add the override: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`. Or set `COMPOSE_FILE` in `.env` (`;` between files on Windows, `:` on Linux/macOS). Or add `--gpus all` to `docker run`. |
| `docker compose up` fails with `could not select device driver "" with capabilities: [[gpu]]` | The host has no NVIDIA driver, no NVIDIA Container Toolkit, or Docker Desktop uses the Hyper-V backend. | Install the NVIDIA driver and, on Linux, the NVIDIA Container Toolkit. On Docker Desktop, enable the WSL2 based engine. Then retry. |
| `Error calling tool '<name>': maximum recursion depth exceeded` | An older build registered each MCP tool under the same name it imported, so the tool called itself. The current source imports the implementations under private names. | Rebuild the container with the current source: `docker compose build --no-cache`. |
| `[FolderWatcher] Warning: Could not check database state: name 'VectorStore' is not defined` | Older build: the watcher used the vector store without importing it, so the empty-index check failed. The watcher still ran, and the initial scan followed `FULL_SCAN_ON_BOOT`. | Rebuild the container with the current source. |

Every message also ends with a hint pointing at this section. Copy the `Details:` line when you report a bug.

The scan command exits with code `0` when every document was indexed, `2` when the report holds a problem (a missing folder, no supported files, or files that failed), and `1` on a fatal error such as an unloadable model.

## FAQ: search files and PDFs locally

### How do I search my folder for a word or phrase?

Index the folder once, then ask the LLM. The LLM calls `search_documents`. For an exact string, ask for a phrase search: the server filters result text for the quoted phrase.

### How do I search my files without opening each one?

Index the folder once, then ask the LLM for what you need. Every result lists the file name, page, and topic. List topics or documents first to narrow the search to one folder.

### Can I search local PDFs offline?

Yes. Embedding and re-ranking run on your machine, and downloads happen once, at install time or at Docker build time. No document text leaves the machine after that.

### Can I find text inside a scanned PDF?

Yes. Pages with no text layer are read by Marker at index time, so a scanned PDF becomes searchable like any other. This needs `OCR_ENABLED=True` (the default) and the optional Marker install: `uv sync --extra marker`, or a Docker build with `INSTALL_MARKER=True`. See [OCR for scanned PDFs](#ocr-for-scanned-pdfs).

Every scanned page is read. `OCR_MAX_PAGES` is only a ceiling for huge files (9999 by default, so no practical limit), and `0` turns OCR off.

### How do I find something in a PDF when I do not know the page?

Ask a question instead of a keyword. Dense search matches meaning, so "when do payments fall due" finds the payment terms clause. Each result lists the source file and page number.

### What file types does it index?

PDF, Word (`.docx`, `.doc`), Excel (`.xlsx`, `.xls`, `.xlsam`, `.xlsb`), Markdown, PowerPoint, HTML, TXT, and CSV.

### Does this work as a documents RAG for Claude Desktop?

Yes. Point Claude Desktop at the running container over HTTP, or add `mcp_server.py` to its config for a local install. Claude gets search, listing, and indexing tools, and any MCP client works the same way. See [Connect an MCP client](#connect-an-mcp-client).

### Do I need a GPU for local RAG?

No, CPU works. A GPU makes indexing about 37× faster and re-ranking about 50× faster. The server detects a usable GPU and falls back to CPU automatically.

### How large can a folder be?

The index is a local ChromaDB database. Search cost grows slowly with chunk count, while indexing cost grows linearly and semantic chunking is the slowest strategy. Chunk counts in the low hundreds of thousands are fine on a desktop machine.

### How do I keep the index current?

Start the folder watcher. Changed files are re-indexed after `DEBOUNCE_SECONDS`, and unchanged files keep their existing chunks. Run `scan_all_my_documents` for a full rebuild, or `--reset` to wipe the index first.

### Why does a search return chunks instead of whole files?

Chunks keep queries precise and contexts small. Each chunk carries its file path, page number, and topic, so the LLM can read it and cite the file.

When the whole document is needed, `read_file` returns its full text and `read_file_raw` returns the original file as base64.

## Project structure

- `mcp_server.py` runs the MCP server (FastMCP) and parses the command-line flags.
- `app/mcp_tools.py` holds the tool implementations the server exposes.
- `app/document_processor.py` extracts text and chunks documents.
- `app/extractors/` holds the per-format text extractors.
- `app/vector_store.py` runs ChromaDB operations: cosine HNSW, hybrid search, RRF fusion, re-ranking.
- `app/embeddings.py` loads one embedding model per process and encodes queries and passages.
- `app/bm25_index.py` holds the in-memory BM25 index for the sparse side of hybrid search.
- `app/device.py` picks the compute device: CUDA, MPS, or CPU.
- `app/scan_all_my_documents.py` runs batch ingestion.
- `app/ocr.py` reads scanned PDF pages with Marker (optional extra).
- `app/incremental_updater.py` applies single-file changes.
- `app/folder_watcher.py` watches folders and debounces changes.
- `app/scan_scheduler.py` tracks the last scan and triggers the periodic full scan.
- `app/config.py` holds settings and the `.env` loader.
- `app/errors.py` turns exceptions into the `Problem`, `Cause`, `Fix` messages.
- `.env.example` lists every setting with an inline comment.
- `Dockerfile`, `docker-compose.yml`, and `docker-compose.gpu.yml` build and run the container.

## License

MIT

