#!/usr/bin/env python3
"""
MCP Server for querying documents (PDFs and Word docs).

This server exposes tools that allow Claude to search and retrieve
information from a collection of documents stored in a vector database.
"""

import asyncio
import errno
import os
import socket
import sys
from contextlib import asynccontextmanager
from fastmcp import FastMCP
from app.folder_watcher import (
    start_watching_folder as start_folder_watcher_impl,
    stop_watching_folder as stop_folder_watcher_impl,
    get_last_scan_time,
    trigger_full_scan_if_needed,
    is_watching
)
from app.incremental_updater import process_incremental_changes
from app.scan_all_my_documents import scan_all
# Import the implementations under private names. The @mcp.tool() functions below
# reuse the public tool names, so importing them unprefixed would make every tool
# call itself ("maximum recursion depth exceeded").
from app.mcp_tools import (
    search_documents as _search_documents,
    list_documents as _list_documents,
    list_topics as _list_topics,
    get_collection_stats as _get_collection_stats,
    scan_all_my_documents as _scan_all_my_documents,
    start_watching_folder as _start_watching_folder,
    stop_watching_folder as _stop_watching_folder,
    get_time_of_last_folder_scan as _get_time_of_last_folder_scan
)
from app.logging_utils import log_error, log_info, log_success, log_warn
from app.log_config import log_detail, setup_logging
from app.config import (
    DOCS_DIR as CONFIGURED_DOCS_DIR,
    FULL_SCAN_ON_BOOT,
    FOLDER_WATCHER_ACTIVE_ON_BOOT
)

# Single source of truth: the same resolved folder the tools and watcher use
DOCS_DIR = str(CONFIGURED_DOCS_DIR)


def _log_scan_summary(scan_result: object) -> None:
    """Log the important scan lines, so the container log shows what was indexed."""
    keys = ("Found ", "Total documents", "Total chunks", "Successful:", "Failed:", "Problem:", "No supported")
    lines = [
        line.strip() for line in str(scan_result).splitlines()
        if line.strip() and any(key in line for key in keys)
    ]
    if not lines:
        return
    log_info("\n".join(lines), component="MCP Server")


@asynccontextmanager
async def lifespan(app):
    """Handle startup and shutdown of the MCP server."""
    if FOLDER_WATCHER_ACTIVE_ON_BOOT:
        log_info("FOLDER_WATCHER_ACTIVE_ON_BOOT is enabled, starting the folder watcher...", component="MCP Server")
        
        def scan_callback(changes, incremental):
            if incremental:
                return process_incremental_changes(changes, DOCS_DIR)
            else:
                return scan_all(DOCS_DIR)
        
        result = start_folder_watcher_impl(scan_callback, do_initial_scan=FULL_SCAN_ON_BOOT)
        
        if result["status"] == "started":
            log_success("Folder watcher started automatically", component="MCP Server")
            log_info(f"Watching: {result['watch_path']}", component="MCP Server")
            log_info(f"Debounce: {result['debounce_seconds']}s", component="MCP Server")
            log_info(f"Full scan interval: {result['full_scan_interval_days']} days", component="MCP Server")
            if result.get('scan_result'):
                log_success("Initial scan finished", component="MCP Server")
                _log_scan_summary(result['scan_result'])
        else:
            log_warn(f"Could not start the folder watcher: {result.get('message')}", component="MCP Server")
    else:
        log_info("Folder watcher auto-start disabled", component="MCP Server")
        log_info("Use the 'start_watching_folder' tool to start it manually", component="MCP Server")
    
    yield
    
    if is_watching():
        log_info("Shutting down the folder watcher...", component="MCP Server")
        result = stop_folder_watcher_impl()
        if result["status"] == "stopped":
            log_success("Folder watcher stopped", component="MCP Server")
        else:
            log_error(f"Could not stop the folder watcher: {result.get('message')}", component="MCP Server")


mcp = FastMCP("docs-to-ai", lifespan=lifespan)


@mcp.tool()
def search_documents(query: str, max_results: int = 10, topic: str | None = None,
                    phrase_search: bool = False, date_from: float | None = None,
                    date_to: float | None = None, regex_pattern: str | None = None) -> str:
    """Search across all documents using semantic similarity.
    
    Args:
        query: The search query to find relevant document chunks
        max_results: Maximum number of results to return
        topic: Optional: Filter results to documents that have this topic
        phrase_search: If True, search for exact phrase match
        date_from: Optional: Filter to documents modified after this timestamp
        date_to: Optional: Filter to documents modified before this timestamp
        regex_pattern: Optional: Filter results by regex pattern in text content
    """
    return _search_documents(query, max_results, topic, phrase_search, date_from, date_to, regex_pattern)


@mcp.tool()
def list_documents(topic: str | None = None) -> str:
    """Get a list of all available documents with their hierarchical topics."""
    return _list_documents(topic)


@mcp.tool()
def list_topics() -> str:
    """Get a list of all topics/categories in the document collection."""
    return _list_topics()


@mcp.tool()
def get_collection_stats() -> str:
    """Get statistics about the document collection."""
    return _get_collection_stats()


@mcp.tool()
def scan_all_my_documents() -> str:
    """Scan all documents in the docs directory and update the vector database."""
    return _scan_all_my_documents()


@mcp.tool()
def start_watching_folder() -> str:
    """Start watching the documents folder for changes."""
    return _start_watching_folder()


@mcp.tool()
def stop_watching_folder() -> str:
    """Stop watching the folder for changes."""
    return _stop_watching_folder()


@mcp.tool()
def get_time_of_last_folder_scan() -> str:
    """Get the timestamp of when the last folder scan was started and finished."""
    return _get_time_of_last_folder_scan()


MCP_HTTP_PATH = {"http": "/mcp", "sse": "/sse"}


def _transport_mode(raw: str) -> str:
    """Map MCP_TRANSPORT to 'stdio', 'http', or 'sse'.

    'websocket' is kept as an alias for 'http' because older versions of this
    project used that name.
    """
    value = (raw or "stdio").strip().lower()
    if value in {"stdio", ""}:
        return "stdio"
    if value in {"http", "streamable-http", "streamable_http", "websocket", "ws"}:
        return "http"
    if value == "sse":
        return "sse"
    log_warn(
        f"Unknown MCP_TRANSPORT '{raw}', using stdio. Valid values: stdio, http, sse.",
        component="MCP Server",
    )
    return "stdio"


def _local_address() -> str | None:
    """Best-effort IP of this machine/container, used only for the startup log."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))  # UDP connect sends no packets
            return sock.getsockname()[0]
    except OSError:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return None


def _port_in_use(host: str, port: int) -> bool:
    """True when something already accepts connections on host:port."""
    target = "127.0.0.1" if host in {"", "0.0.0.0", "::"} else host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            return sock.connect_ex((target, port)) == 0
    except OSError:
        return False


def _log_listen_addresses(host: str, port: int, mode: str) -> None:
    """Say where the server listens, inside the container and from the host."""
    path = MCP_HTTP_PATH.get(mode, "/mcp")
    address = _local_address()
    lines = [f"Listening on {host}:{port}{path} (the port opens once the models finish loading)"]
    if address and address not in {"0.0.0.0", "127.0.0.1"}:
        lines.append(f"From inside the container or machine: http://{address}:{port}{path}")
    lines.append(f"From this Docker host or a browser on it: http://localhost:{port}{path}")
    lines.append(f"From another machine: http://<host-ip>:{port}{path}")
    public_url = os.getenv("MCP_PUBLIC_URL", "").strip()
    if public_url:
        lines.append(f"Configured client URL (MCP_PUBLIC_URL): {public_url}")
    if host == "127.0.0.1":
        lines.append("MCP_HOST is 127.0.0.1, so only this container can connect. Use 0.0.0.0 to expose it.")
    log_success("\n".join(lines), component="MCP Server")


def _log_startup_detail(transport: str, host: str, port: int) -> None:
    """Record the effective configuration once, so a log shows how the run started."""
    from app.config import (
        CHROMA_COLLECTION_NAME, CHUNKING_STRATEGY, EMBEDDING_MODEL, FOLDER_WATCHER_ACTIVE_ON_BOOT,
        FULL_SCAN_ON_BOOT, LOG_CHUNK_TEXT_CHARS, LOG_DETAIL_ENABLED, LOG_DIR, RERANKER_MODEL,
        USE_BM25, USE_RERANKER,
    )
    log_detail(
        "server_start",
        transport=transport,
        host=host if transport != "stdio" else None,
        port=port if transport != "stdio" else None,
        docs_dir=DOCS_DIR,
        collection=CHROMA_COLLECTION_NAME,
        embedding_model=EMBEDDING_MODEL,
        chunking_strategy=CHUNKING_STRATEGY,
        hybrid_search=USE_BM25,
        reranker=RERANKER_MODEL if USE_RERANKER else None,
        full_scan_on_boot=FULL_SCAN_ON_BOOT,
        folder_watcher=FOLDER_WATCHER_ACTIVE_ON_BOOT,
        log_dir=str(LOG_DIR),
        detail_log=LOG_DETAIL_ENABLED,
        chunk_text_chars=LOG_CHUNK_TEXT_CHARS,
    )


async def main():
    """Main entry point - determine transport type from environment or arguments."""
    setup_logging()
    transport = _transport_mode(os.getenv("MCP_TRANSPORT", "stdio"))

    if len(sys.argv) > 1:
        if sys.argv[1] in ["--websocket", "--sse", "--http"]:
            transport = _transport_mode(sys.argv[1].lstrip("-"))
        elif sys.argv[1] == "--stdio":
            transport = "stdio"
        elif sys.argv[1] == "--help":
            print("Usage: python mcp_server.py [OPTIONS]")
            print("\nOptions:")
            print("  --stdio              Use stdio transport (default)")
            print("  --http               Serve MCP over HTTP on MCP_HOST:MCP_PORT at /mcp")
            print("  --sse                Serve MCP over HTTP with SSE at /sse")
            print("  --websocket          Alias for --http (kept for backwards compatibility)")
            print("  --host HOST          Host to bind to (default: 0.0.0.0)")
            print("  --port PORT          Port to bind to (default: 38777)")
            print("  --show-config        Print the effective configuration and exit")
            print("\nEnvironment Variables (defaults shown):")
            print("  MCP_TRANSPORT        Transport type: 'stdio', 'http', or 'sse' (default: stdio; the Docker image uses http)")
            print("  MCP_HOST             Host to bind to, websocket mode (default: 0.0.0.0)")
            print("  MCP_PORT             Port to bind to, websocket mode (default: 38777)")
            print("\nChunking (defaults shown):")
            print("  CHUNKING_STRATEGY    fixed_size | by_paragraph | semantic_heading | by_token | semantic (default: semantic)")
            print("  CHUNK_SIZE           Size per chunk: tokens when CHUNK_BY_TOKEN=True, else characters (default: 1024)")
            print("  CHUNK_OVERLAP        Overlap between chunks, same unit as CHUNK_SIZE (default: 200)")
            print("  CHUNK_BY_TOKEN       Measure chunk sizes in tokens instead of characters (default: True)")
            print("  TOKENIZER_MODEL      tiktoken tokenizer (default: cl100k_base)")
            print("  PRESERVE_HEADINGS    Preserve heading structure (default: True)")
            print("  MAX_HEADING_CHUNK_SIZE  Max size per heading chunk (default: 1024)")
            print("  MIN_CHUNK_SIZE       Minimum chunk size (default: 50)")
            print("  SEMANTIC_CHUNK_PERCENTILE  Similarity percentile split threshold (default: 95)")
            print("  SEMANTIC_CHUNK_MIN_SIZE    Min tokens per semantic chunk (default: 64)")
            print("  SEMANTIC_CHUNK_MAX_SIZE    Max tokens per semantic chunk (default: 1024)")
            print("  SEMANTIC_CHUNK_BUFFER_SIZE Neighbouring sentences combined for similarity (default: 1)")
            print("\nSearch (defaults shown):")
            print("  DEFAULT_SEARCH_RESULTS  Default number of results (default: 10)")
            print("  MAX_SEARCH_RESULTS      Maximum allowed results (default: 20)")
            print("  USE_RERANKER            Enable cross-encoder re-ranking (default: True)")
            print("  RERANKER_MODEL          Re-ranker model (default: cross-encoder/ms-marco-MiniLM-L-6-v2)")
            print("  RERANKER_TOP_N          Candidates to re-rank (default: 50)")
            print("  USE_BM25                Enable hybrid BM25 + dense search (default: True)")
            print("  BM25_WEIGHT             RRF weight of the BM25 list, 0.5 = equal (default: 0.3)")
            print("  BM25_K1 / BM25_B        BM25 term saturation / length normalisation (default: 1.5 / 0.75)")
            print("  RRF_K                   Reciprocal Rank Fusion constant (default: 60)")
            print("\nEmbedding / GPU (defaults shown):")
            print("  EMBEDDING_MODEL         Sentence-transformer model (default: Qwen/Qwen3-Embedding-0.6B)")
            print("  EMBEDDING_DIMENSION     Vector dimension (default: 1024)")
            print("  EMBEDDING_BATCH_SIZE    Texts per encode batch (default: 32)")
            print("  EMBEDDING_QUERY_PROMPT  Query instruction prefix (default: model's built-in 'query' prompt)")
            print("  USE_GPU_ACCELERATION_IF_AVAILABLE  Use CUDA/MPS for the embedding model and re-ranker, else CPU (default: True)")
            print("  GPU_DEVICE_INDEX        0-based index of the CUDA GPU to use (default: 0)")
            print("\nStorage / topics (defaults shown):")
            print("  CHROMA_SPACE            HNSW distance space: cosine | l2 | ip (default: cosine)")
            print("  HNSW_EF_SEARCH          HNSW query-time candidate list size (default: 200)")
            print("  HNSW_EF_CONSTRUCTION    HNSW build-time candidate list size (default: 200)")
            print("  CHROMA_COLLECTION_NAME  ChromaDB collection name (default: my-documents)")
            print("  USE_FOLDER_AS_TOPIC     Use folder hierarchy as topics (default: True)")
            print("  DEFAULT_TOPIC           Topic for uncategorized docs (default: uncategorized)")
            print("  DOCS_DIR                Documents directory (default: ./my-docs)")
            print("\nStartup (defaults shown):")
            print("  FULL_SCAN_ON_BOOT              Full scan on server start (default: False)")
            print("  FOLDER_WATCHER_ACTIVE_ON_BOOT  Start folder watcher on boot (default: True)")
            print("  DEBOUNCE_SECONDS               Delay after last change (default: 10)")
            print("  FULL_SCAN_INTERVAL_DAYS        Days between full scans (default: 7)")
            print("\nAll settings can also be set in a .env file next to pyproject.toml.")
            sys.exit(0)
        elif sys.argv[1] == "--show-config":
            from app.config import (
                CHUNKING_STRATEGY, CHUNK_SIZE, CHUNK_OVERLAP, CHUNK_BY_TOKEN,
                TOKENIZER_MODEL, PRESERVE_HEADINGS, MAX_HEADING_CHUNK_SIZE, MIN_CHUNK_SIZE,
                SEMANTIC_CHUNK_PERCENTILE, SEMANTIC_CHUNK_MIN_SIZE, SEMANTIC_CHUNK_MAX_SIZE,
                SEMANTIC_CHUNK_BUFFER_SIZE, EMBEDDING_MODEL, EMBEDDING_DIMENSION,
                EMBEDDING_BATCH_SIZE, EMBEDDING_QUERY_PROMPT,
                USE_GPU_ACCELERATION_IF_AVAILABLE, GPU_DEVICE_INDEX,
                DEFAULT_SEARCH_RESULTS, MAX_SEARCH_RESULTS, USE_RERANKER, RERANKER_MODEL,
                RERANKER_TOP_N, USE_BM25, BM25_WEIGHT, BM25_K1, BM25_B, RRF_K,
                USE_FOLDER_AS_TOPIC, DEFAULT_TOPIC,
                CHROMA_COLLECTION_NAME, CHROMA_SPACE, HNSW_EF_SEARCH, HNSW_EF_CONSTRUCTION,
                FULL_SCAN_ON_BOOT, FOLDER_WATCHER_ACTIVE_ON_BOOT,
                DEBOUNCE_SECONDS, FULL_SCAN_INTERVAL_DAYS, DOCS_DIR
            )
            print("Effective configuration:")
            print(f"  EMBEDDING_MODEL={EMBEDDING_MODEL}")
            print(f"  EMBEDDING_DIMENSION={EMBEDDING_DIMENSION}")
            print(f"  EMBEDDING_BATCH_SIZE={EMBEDDING_BATCH_SIZE}")
            print(f"  EMBEDDING_QUERY_PROMPT={EMBEDDING_QUERY_PROMPT or '(model default)'}")
            print(f"  USE_GPU_ACCELERATION_IF_AVAILABLE={USE_GPU_ACCELERATION_IF_AVAILABLE}")
            print(f"  GPU_DEVICE_INDEX={GPU_DEVICE_INDEX}")
            try:
                from app.device import describe_device, resolve_device
                print(f"  DEVICE={describe_device(resolve_device())}")
            except Exception as e:  # torch missing or broken - not fatal
                print(f"  DEVICE=unknown ({e})")
            print(f"  CHUNKING_STRATEGY={CHUNKING_STRATEGY}")
            print(f"  CHUNK_SIZE={CHUNK_SIZE}")
            print(f"  CHUNK_OVERLAP={CHUNK_OVERLAP}")
            print(f"  CHUNK_BY_TOKEN={CHUNK_BY_TOKEN}")
            print(f"  TOKENIZER_MODEL={TOKENIZER_MODEL}")
            print(f"  PRESERVE_HEADINGS={PRESERVE_HEADINGS}")
            print(f"  MAX_HEADING_CHUNK_SIZE={MAX_HEADING_CHUNK_SIZE}")
            print(f"  MIN_CHUNK_SIZE={MIN_CHUNK_SIZE}")
            print(f"  SEMANTIC_CHUNK_PERCENTILE={SEMANTIC_CHUNK_PERCENTILE}")
            print(f"  SEMANTIC_CHUNK_MIN_SIZE={SEMANTIC_CHUNK_MIN_SIZE}")
            print(f"  SEMANTIC_CHUNK_MAX_SIZE={SEMANTIC_CHUNK_MAX_SIZE}")
            print(f"  SEMANTIC_CHUNK_BUFFER_SIZE={SEMANTIC_CHUNK_BUFFER_SIZE}")
            print(f"  DEFAULT_SEARCH_RESULTS={DEFAULT_SEARCH_RESULTS}")
            print(f"  MAX_SEARCH_RESULTS={MAX_SEARCH_RESULTS}")
            print(f"  USE_RERANKER={USE_RERANKER}")
            print(f"  RERANKER_MODEL={RERANKER_MODEL}")
            print(f"  RERANKER_TOP_N={RERANKER_TOP_N}")
            print(f"  USE_BM25={USE_BM25}")
            print(f"  BM25_WEIGHT={BM25_WEIGHT}")
            print(f"  BM25_K1={BM25_K1}")
            print(f"  BM25_B={BM25_B}")
            print(f"  RRF_K={RRF_K}")
            print(f"  USE_FOLDER_AS_TOPIC={USE_FOLDER_AS_TOPIC}")
            print(f"  DEFAULT_TOPIC={DEFAULT_TOPIC}")
            print(f"  CHROMA_COLLECTION_NAME={CHROMA_COLLECTION_NAME}")
            print(f"  CHROMA_SPACE={CHROMA_SPACE}")
            print(f"  HNSW_EF_SEARCH={HNSW_EF_SEARCH}")
            print(f"  HNSW_EF_CONSTRUCTION={HNSW_EF_CONSTRUCTION}")
            print(f"  DOCS_DIR={DOCS_DIR}")
            print(f"  FULL_SCAN_ON_BOOT={FULL_SCAN_ON_BOOT}")
            print(f"  FOLDER_WATCHER_ACTIVE_ON_BOOT={FOLDER_WATCHER_ACTIVE_ON_BOOT}")
            print(f"  DEBOUNCE_SECONDS={DEBOUNCE_SECONDS}")
            print(f"  FULL_SCAN_INTERVAL_DAYS={FULL_SCAN_INTERVAL_DAYS}")
            sys.exit(0)

    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "38777"))

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--host" and i + 1 < len(sys.argv):
            host = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
            i += 2
        else:
            i += 1

    _log_startup_detail(transport, host, port)

    if transport in {"http", "sse"}:
        if _port_in_use(host, port):
            from app.errors import explain
            log_error(
                explain(
                    OSError(errno.EADDRINUSE, "address already in use"),
                    context=f"MCP server on port {port}",
                ),
                component="MCP Server",
            )
            raise SystemExit(1)
        _log_listen_addresses(host, port, transport)
        try:
            await mcp.run_http_async(
                transport="sse" if transport == "sse" else "http",
                host=host,
                port=port,
                path=MCP_HTTP_PATH[transport],
            )
        except OSError as exc:
            from app.errors import explain
            log_error(explain(exc, context=f"MCP server on port {port}"), component="MCP Server")
            raise SystemExit(1)
    else:
        log_info(
            "Transport: stdio. The client starts this process and talks over stdin/stdout; "
            "no network port is opened. Set MCP_TRANSPORT=http to listen on a port instead.",
            component="MCP Server",
        )
        await mcp.run_stdio_async()


if __name__ == "__main__":
    from app.errors import DocsToAIError, explain

    try:
        asyncio.run(main())
    except DocsToAIError as exc:
        log_error(exc.message(), component="MCP Server")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        log_error(explain(exc, context="mcp_server"), component="MCP Server")
        sys.exit(1)
