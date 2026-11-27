#!/usr/bin/env python3
"""
MCP Server for querying documents (PDFs and Word docs).

This server exposes tools that allow Claude to search and retrieve
information from a collection of documents stored in a vector database.
"""

import asyncio
import sys
import os
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
from app.mcp_tools import (
    search_documents,
    list_documents,
    list_topics,
    get_collection_stats,
    scan_all_my_documents,
    start_watching_folder,
    stop_watching_folder,
    get_time_of_last_folder_scan
)
from app.config import (
    FULL_SCAN_ON_BOOT,
    FOLDER_WATCHER_ACTIVE_ON_BOOT
)

DOCS_DIR = os.getenv("DOCS_DIR", "/app/my-docs")


@asynccontextmanager
async def lifespan(app):
    """Handle startup and shutdown of the MCP server."""
    if FOLDER_WATCHER_ACTIVE_ON_BOOT:
        print(f"[MCP Server] FOLDER_WATCHER_ACTIVE_ON_BOOT is enabled, starting folder watcher...", file=sys.stderr)
        
        def scan_callback(changes, incremental):
            if incremental:
                return process_incremental_changes(changes, DOCS_DIR)
            else:
                return scan_all(DOCS_DIR)
        
        result = start_folder_watcher_impl(scan_callback, do_initial_scan=FULL_SCAN_ON_BOOT)
        
        if result["status"] == "started":
            print(f"[MCP Server] Folder watcher started automatically", file=sys.stderr)
            print(f"[MCP Server]   Watching: {result['watch_path']}", file=sys.stderr)
            print(f"[MCP Server]   Debounce: {result['debounce_seconds']}s", file=sys.stderr)
            print(f"[MCP Server]   Full scan interval: {result['full_scan_interval_days']} days", file=sys.stderr)
            if result.get('scan_result'):
                print(f"[MCP Server]   Initial scan completed", file=sys.stderr)
        else:
            print(f"[MCP Server] Warning: Could not start folder watcher: {result.get('message')}", file=sys.stderr)
    else:
        print(f"[MCP Server] Folder watcher auto-start disabled", file=sys.stderr)
        print(f"[MCP Server] Use the 'start_watching_folder' tool to start it manually", file=sys.stderr)
    
    yield
    
    if is_watching():
        print("[MCP Server] Shutting down folder watcher...", file=sys.stderr)
        result = stop_folder_watcher_impl()
        if result["status"] == "stopped":
            print("[MCP Server] Folder watcher stopped", file=sys.stderr)
        else:
            print(f"[MCP Server] Warning: Error stopping folder watcher: {result.get('message')}", file=sys.stderr)


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
    return search_documents(query, max_results, topic, phrase_search, date_from, date_to, regex_pattern)


@mcp.tool()
def list_documents(topic: str | None = None) -> str:
    """Get a list of all available documents with their hierarchical topics."""
    return list_documents(topic)


@mcp.tool()
def list_topics() -> str:
    """Get a list of all topics/categories in the document collection."""
    return list_topics()


@mcp.tool()
def get_collection_stats() -> str:
    """Get statistics about the document collection."""
    return get_collection_stats()


@mcp.tool()
def scan_all_my_documents() -> str:
    """Scan all documents in the docs directory and update the vector database."""
    return scan_all_my_documents()


@mcp.tool()
def start_watching_folder() -> str:
    """Start watching the documents folder for changes."""
    return start_watching_folder()


@mcp.tool()
def stop_watching_folder() -> str:
    """Stop watching the folder for changes."""
    return stop_watching_folder()


@mcp.tool()
def get_time_of_last_folder_scan() -> str:
    """Get the timestamp of when the last folder scan was started and finished."""
    return get_time_of_last_folder_scan()


async def main():
    """Main entry point - determine transport type from environment or arguments."""
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()

    if len(sys.argv) > 1:
        if sys.argv[1] in ["--websocket", "--sse", "--http"]:
            transport = "websocket"
        elif sys.argv[1] == "--stdio":
            transport = "stdio"
        elif sys.argv[1] == "--help":
            print("Usage: python mcp_server.py [OPTIONS]")
            print("\nOptions:")
            print("  --stdio              Use stdio transport (default)")
            print("  --websocket, --sse   Use SSE/WebSocket transport over HTTP")
            print("  --host HOST          Host to bind to (default: 0.0.0.0)")
            print("  --port PORT          Port to bind to (default: 38777)")
            print("  --show-config        Print the effective configuration and exit")
            print("\nEnvironment Variables (defaults shown):")
            print("  MCP_TRANSPORT        Transport type: 'stdio' or 'websocket' (default: stdio)")
            print("  MCP_HOST             Host to bind to, websocket mode (default: 0.0.0.0)")
            print("  MCP_PORT             Port to bind to, websocket mode (default: 38777)")
            print("\nChunking (defaults shown):")
            print("  CHUNKING_STRATEGY    fixed_size | by_paragraph | semantic_heading | by_token | semantic (default: by_paragraph)")
            print("  CHUNK_SIZE           Characters per chunk, or tokens when CHUNK_BY_TOKEN=True (default: 1000)")
            print("  CHUNK_OVERLAP        Overlap between chunks (default: 200)")
            print("  CHUNK_BY_TOKEN       Use token-based chunking (default: False)")
            print("  TOKENIZER_MODEL      tiktoken tokenizer (default: cl100k_base)")
            print("  PRESERVE_HEADINGS    Preserve heading structure (default: True)")
            print("  MAX_HEADING_CHUNK_SIZE  Max chars per heading chunk (default: 2000)")
            print("  MIN_CHUNK_SIZE       Minimum chunk size (default: 50)")
            print("  SEMANTIC_CHUNK_PERCENTILE  Similarity percentile split threshold (default: 95)")
            print("  SEMANTIC_CHUNK_MIN_SIZE    Min chars per semantic chunk (default: 200)")
            print("  SEMANTIC_CHUNK_MAX_SIZE    Max chars per semantic chunk (default: 2000)")
            print("  SEMANTIC_CHUNK_BUFFER_SIZE Neighbouring sentences combined for similarity (default: 1)")
            print("\nSearch (defaults shown):")
            print("  DEFAULT_SEARCH_RESULTS  Default number of results (default: 10)")
            print("  MAX_SEARCH_RESULTS      Maximum allowed results (default: 20)")
            print("  USE_RERANKER            Enable cross-encoder re-ranking (default: True)")
            print("  RERANKER_MODEL          Re-ranker model (default: cross-encoder/ms-marco-MiniLM-L-6-v2)")
            print("  RERANKER_TOP_N          Candidates to re-rank (default: 50)")
            print("  USE_BM25                Enable hybrid BM25 search (default: False)")
            print("  BM25_WEIGHT             BM25 weight in hybrid search (default: 0.3)")
            print("\nEmbedding / storage / topics (defaults shown):")
            print("  EMBEDDING_MODEL         Sentence-transformer model (default: all-MiniLM-L6-v2)")
            print("  EMBEDDING_DIMENSION     Vector dimension (default: 384)")
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
                DEFAULT_SEARCH_RESULTS, MAX_SEARCH_RESULTS, USE_RERANKER, RERANKER_MODEL,
                RERANKER_TOP_N, USE_BM25, BM25_WEIGHT, USE_FOLDER_AS_TOPIC, DEFAULT_TOPIC,
                CHROMA_COLLECTION_NAME, FULL_SCAN_ON_BOOT, FOLDER_WATCHER_ACTIVE_ON_BOOT,
                DEBOUNCE_SECONDS, FULL_SCAN_INTERVAL_DAYS, DOCS_DIR
            )
            print("Effective configuration:")
            print(f"  EMBEDDING_MODEL={EMBEDDING_MODEL}")
            print(f"  EMBEDDING_DIMENSION={EMBEDDING_DIMENSION}")
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
            print(f"  USE_FOLDER_AS_TOPIC={USE_FOLDER_AS_TOPIC}")
            print(f"  DEFAULT_TOPIC={DEFAULT_TOPIC}")
            print(f"  CHROMA_COLLECTION_NAME={CHROMA_COLLECTION_NAME}")
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

    if transport == "websocket":
        await mcp.run_http_async(host=host, port=port)
    else:
        await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
