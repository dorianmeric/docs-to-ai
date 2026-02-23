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
            print("\nEnvironment Variables:")
            print("  MCP_TRANSPORT        Transport type: 'stdio' or 'websocket'")
            print("  MCP_HOST             Host to bind to (websocket mode)")
            print("  MCP_PORT             Port to bind to (websocket mode)")
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
