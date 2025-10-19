#!/usr/bin/env python3
"""
MCP Server for querying documents (PDFs and Word docs).

This server exposes tools that allow Claude to search and retrieve
information from a collection of documents stored in a vector database.
"""

import asyncio
import subprocess
import time
import sys
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent
from app.vector_store import VectorStore
from app.config import (
    DEFAULT_SEARCH_RESULTS,
    MAX_SEARCH_RESULTS,
    TOPIC_SEPARATOR,
    FULL_SCAN_ON_BOOT,
    FOLDER_WATCHER_ACTIVE_ON_BOOT
)
from app.folder_watcher import (
    start_watching_folder as start_folder_watcher,
    stop_watching_folder as stop_folder_watcher,
    get_last_scan_time,
    trigger_full_scan_if_needed
)
from app.incremental_updater import process_incremental_changes
from app.scan_all_my_documents import scan_all_my_documents

# Initialize server
mcp = FastMCP("docs-to-ai")

# Tool implementations using @mcp.tool() decorator

@mcp.tool()
def search_documents(
    query: str,
    max_results: int = DEFAULT_SEARCH_RESULTS,
    topic: str | None = None
) -> str:
    """Search across all documents (PDFs and Word) using semantic similarity.

    Returns the most relevant text chunks with their source information and hierarchical topics.
    Documents are tagged with all topics in their folder hierarchy.
    Optionally filter by topic to search within specific categories.

    Args:
        query: The search query to find relevant document chunks
        max_results: Maximum number of results to return (default: {DEFAULT_SEARCH_RESULTS}, max: {MAX_SEARCH_RESULTS})
        topic: Optional: Filter results to documents that have this topic (at any level in hierarchy)
    """
    vector_store = VectorStore()

    # Validate max_results
    max_results = min(max(1, max_results), MAX_SEARCH_RESULTS)

    # Perform search (get more results if filtering by topic)
    search_limit = max_results * 3 if topic else max_results
    results = vector_store.search(query, n_results=search_limit)

    # Filter by topic if specified (check if topic appears in topics list)
    if topic:
        filtered_results = []
        for r in results:
            doc_topics = r['metadata'].get('topics', [])
            if isinstance(doc_topics, str):
                doc_topics = [doc_topics]
            if topic in doc_topics:
                filtered_results.append(r)
        results = filtered_results[:max_results]

    if not results:
        filter_msg = f" with topic '{topic}'" if topic else ""
        return f"No results found for query: '{query}'{filter_msg}"

    # Format results
    filter_info = f" (filtered to topic: '{topic}')" if topic else ""
    response_parts = [f"Found {len(results)} relevant chunks for query: '{query}'{filter_info}\n"]

    for i, result in enumerate(results, 1):
        metadata = result['metadata']
        filename = metadata.get('filename', 'Unknown')
        page = metadata.get('page', 'Unknown')
        topics = metadata.get('topics', ['uncategorized'])
        filetype = metadata.get('filetype', '.pdf')

        if isinstance(topics, str):
            topics = [topics]

        topics_display = TOPIC_SEPARATOR.join(topics)

        response_parts.append(f"\n--- Result {i} ---")
        response_parts.append(f"Topics: {topics_display}")
        response_parts.append(f"Source: {filename} ({filetype}) [Page {page}]")

        if result.get('distance') is not None:
            # Lower distance = higher relevance
            relevance = max(0, 100 - (result['distance'] * 100))
            response_parts.append(f"Relevance: {relevance:.1f}%")

        response_parts.append(f"\nContent:\n{result['text']}")

    return "\n".join(response_parts)


@mcp.tool()
def list_documents(topic: str | None = None) -> str:
    """Get a list of all available documents with their hierarchical topics.

    Shows PDFs and Word documents organized by their folder hierarchy.
    Each document shows all topics from its folder path.

    Args:
        topic: Optional: Filter to show only documents that have this topic
    """
    vector_store = VectorStore()
    documents = vector_store.list_documents()

    # Filter by topic if specified (check if topic appears in topics list)
    if topic:
        filtered_docs = []
        for doc in documents:
            doc_topics = doc.get('topics', [])
            if isinstance(doc_topics, str):
                doc_topics = [doc_topics]
            if topic in doc_topics:
                filtered_docs.append(doc)
        documents = filtered_docs

    if not documents:
        filter_msg = f" with topic '{topic}'" if topic else ""
        return f"No documents found{filter_msg}. Use 'python -m app.scan_all_my_documents' to add documents."

    # Group by first topic for display
    docs_by_first_topic = {}
    for doc in documents:
        topics = doc.get('topics', ['uncategorized'])
        if isinstance(topics, str):
            topics = [topics]
        first_topic = topics[0] if topics else 'uncategorized'

        if first_topic not in docs_by_first_topic:
            docs_by_first_topic[first_topic] = []
        docs_by_first_topic[first_topic].append(doc)

    response_parts = []
    filter_info = f" (filtered to topic: '{topic}')" if topic else ""
    response_parts.append(f"Available documents{filter_info}: {len(documents)} total\n")

    for first_topic in sorted(docs_by_first_topic.keys()):
        topic_docs = docs_by_first_topic[first_topic]
        response_parts.append(f"\n📁 {first_topic} ({len(topic_docs)} documents)")
        for doc in topic_docs:
            topics = doc.get('topics', ['uncategorized'])
            if isinstance(topics, str):
                topics = [topics]
            topics_display = TOPIC_SEPARATOR.join(topics)
            filetype = doc.get('filetype', '.pdf')

            # Format file size
            file_size = doc.get('file_size', 0)
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024*1024):.1f} MB"
            elif file_size > 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{file_size} bytes"

            # Format last modified date
            last_modified = doc.get('last_modified', 0)
            if last_modified:
                mod_time = time.ctime(last_modified)
            else:
                mod_time = "Unknown"

            response_parts.append(f"  • {doc['filename']} ({filetype}) - Size: {size_str}, Modified: {mod_time}")
            response_parts.append(f"    Topics: {topics_display}")

    return "\n".join(response_parts)


@mcp.tool()
def list_topics() -> str:
    """Get a list of all topics/categories in the document collection.

    Topics are derived from the folder hierarchy where documents are organized.
    Each folder level becomes a separate topic tag.
    """
    vector_store = VectorStore()
    topics = vector_store.list_topics()

    if not topics:
        return "No topics found. Use scan_all_my_documents.py, or ask the LLM to run scan_all_my_documents, to add documents."

    stats = vector_store.get_stats()
    topic_counts = stats['documents_per_topic']

    response = f"Available topics ({len(topics)}):\n\n"
    response += "Topics are hierarchical - each folder in the path becomes a topic.\n"
    response += "Documents can have multiple topics based on their folder location.\n\n"

    for topic in topics:
        count = topic_counts.get(topic, 0)
        response += f"  📁 {topic}: {count} document{'s' if count != 1 else ''}\n"

    return response


@mcp.tool()
def get_collection_stats() -> str:
    """Get statistics about the document collection.

    Includes total number of documents, topics, file types, and chunks stored
    in the vector database. Shows the distribution of documents across topics and file types.
    """
    vector_store = VectorStore()
    stats = vector_store.get_stats()

    response = "Document Collection Statistics:\n\n"
    response += f"Total chunks: {stats['total_chunks']}\n"
    response += f"Total documents: {stats['total_documents']}\n"
    response += f"Total topics: {stats['total_topics']}\n"
    response += f"Collection: {stats['collection_name']}\n\n"

    if 'documents_per_filetype' in stats and stats['documents_per_filetype']:
        response += "Documents per file type:\n"
        for filetype in sorted(stats['documents_per_filetype'].keys()):
            count = stats['documents_per_filetype'][filetype]
            response += f"  {filetype}: {count} document{'s' if count != 1 else ''}\n"
        response += "\n"

    if stats['topics']:
        response += "Documents per topic (hierarchical):\n"
        for topic in sorted(stats['topics']):
            count = stats['documents_per_topic'].get(topic, 0)
            response += f"  📁 {topic}: {count} document{'s' if count != 1 else ''}\n"

    # Add file size information
    if stats['documents']:
        response += "\nFile Size Information:\n"
        total_size = sum(doc.get('file_size', 0) for doc in stats['documents'])

        if total_size > 1024 * 1024:
            size_str = f"{total_size / (1024*1024):.1f} MB"
        elif total_size > 1024:
            size_str = f"{total_size / 1024:.1f} KB"
        else:
            size_str = f"{total_size} bytes"

        response += f"  Total size of all documents: {size_str}\n"

        # Show largest documents
        sorted_docs = sorted(stats['documents'], key=lambda x: x.get('file_size', 0), reverse=True)
        response += "\nLargest documents:\n"
        for doc in sorted_docs[:5]:
            file_size = doc.get('file_size', 0)
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024*1024):.1f} MB"
            elif file_size > 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{file_size} bytes"

            # Format last modified date
            last_modified = doc.get('file_size', 0)
            if last_modified:
                mod_time = time.ctime(last_modified)
            else:
                mod_time = "Unknown"

            response += f"  {doc['filename']}: {size_str}, Modified: {mod_time}\n"

    return response


@mcp.tool()
def scan_all_my_documents() -> str:
    """Scan all documents in the docs directory and update the vector database.

    This forces a complete re-indexing: the database is cleared first to prevent duplicates,
    then all documents are processed from scratch.
    """
    try:
        doc_dir = "/app/my-docs"  # Docker path
        # scan_all_my_documents uses the singleton VectorStore internally
        # Returns list[TextContent] with debug info
        result = scan_all_my_documents(doc_dir)
        # Extract text from TextContent objects
        if isinstance(result, list) and result:
            return "\n".join(item.text for item in result if hasattr(item, 'text'))
        return str(result)
    except Exception as e:
        return f"✗ Error scanning documents: {str(e)}"


@mcp.tool()
def start_watching_folder() -> str:
    """Start watching the documents folder for changes and automatically trigger incremental updates.

    Uses intelligent change detection to only process modified files.
    Performs a full scan (with database reset) once per week and on initial startup to prevent duplicates.
    """
    try:
        # Define the base directory for documents
        doc_dir = "/app/my-docs"  # Docker path, adjust if needed

        # Create a callback function that will trigger incremental or full scans
        # The callback returns list[TextContent] with debug info for MCP response
        # Uses the singleton VectorStore internally
        def scan_callback(changes, incremental):
            try:
                if incremental and changes:
                    # Process only the changed files
                    # process_incremental_changes returns list[TextContent]
                    return process_incremental_changes(changes, doc_dir)
                else:
                    # Do a full scan with database reset to prevent duplicates
                    # run_full_document_scan uses singleton VectorStore
                    return scan_all_my_documents(doc_dir)
            except Exception as e:
                # Return error as TextContent for MCP response
                print(f"[MCP] Error during scan: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc()
                return [TextContent(
                    type="text",
                    text=f"✗ Error during scan: {str(e)}"
                )]

        # Start watching the folder with initial scan
        result = start_folder_watcher(scan_callback, do_initial_scan=True)

        if result['status'] == 'started':
            # Build response with watcher info
            response_parts = []
            response_parts.append("✓ Folder watcher started successfully\n")
            response_parts.append(f"Watching: {result['watch_path']}")
            response_parts.append(f"Debounce: {result['debounce_seconds']} seconds")
            response_parts.append(f"Full scan interval: {result['full_scan_interval_days']} days")
            response_parts.append("Mode: Incremental updates enabled")

            # If initial scan was performed, include its results
            if 'scan_result' in result and result['scan_result']:
                response_parts.append("\n" + "="*60)
                response_parts.append("INITIAL SCAN RESULTS:")
                response_parts.append("="*60)
                # scan_result is list[TextContent], extract the text
                for content in result['scan_result']:
                    if hasattr(content, 'text'):
                        response_parts.append(content.text)

            return "\n".join(response_parts)
        elif result['status'] == 'already_watching':
            return f"ℹ Folder watcher is already active (started automatically on server startup)\n\nWatching: {result['watch_path']}"
        else:
            return f"✗ Failed to start folder watcher\n\nError: {result.get('message', 'Unknown error')}"
    except Exception as e:
        return f"✗ Error starting folder watcher: {str(e)}"


@mcp.tool()
def stop_watching_folder() -> str:
    """Stop watching the folder for changes.

    Does nothing if no folder is currently being watched.
    """
    try:
        result = stop_folder_watcher()

        if result['status'] == 'stopped':
            return "✓ Folder watcher stopped successfully"
        elif result['status'] == 'not_watching':
            return "ℹ Folder watcher is not currently active"
        else:
            return f"✗ Error stopping folder watcher: {result.get('message', 'Unknown error')}"
    except Exception as e:
        return f"✗ Error stopping folder watcher: {str(e)}"


@mcp.tool()
def get_time_of_last_folder_scan() -> str:
    """Get the timestamp of when the last folder scan was started and finished.

    Also shows information about the last full scan and when the next one is due.
    """
    try:
        result = get_last_scan_time()

        if result["status"] == "success":
            response_parts = ["Last Folder Scan Information:\n"]
            response_parts.append(f"Started:  {result['scan_start_time_formatted']}")

            if 'scan_end_time_formatted' in result:
                response_parts.append(f"Finished: {result['scan_end_time_formatted']}")
                response_parts.append(f"Duration: {result['duration_seconds']} seconds")
            else:
                response_parts.append("Status: Scan in progress...")

            # Add full scan info
            if 'last_full_scan_time_formatted' in result:
                response_parts.append(f"\nLast Full Scan: {result['last_full_scan_time_formatted']}")
                response_parts.append(f"Days since full scan: {result['days_since_full_scan']}")
                if result.get('next_full_scan_due'):
                    response_parts.append("Next full scan: DUE NOW")
                else:
                    days_remaining = 7 - result['days_since_full_scan']
                    response_parts.append(f"Next full scan in: {days_remaining} days")

            return "\n".join(response_parts)
        elif result["status"] == "not_watching":
            return "ℹ Folder watcher is not currently active"
        elif result["status"] == "no_scans_yet":
            return "ℹ Folder watcher is active but no scans have been triggered yet"
        else:
            return f"✗ Error: {result.get('message', 'Unknown error')}"
    except Exception as e:
        return f"✗ Error getting last scan time: {str(e)}"


# async def startup_initialization():
#     """Perform initial scan and start folder watcher on server startup based on environment variables."""
#     try:
#         # Initialize the singleton VectorStore (will only initialize once)
#         VectorStore()

#         # print(f"[MCP] Starting initialization...", file=sys.stderr)
#         print(f"[MCP]   FULL_SCAN_ON_BOOT: {FULL_SCAN_ON_BOOT}", file=sys.stderr)
#         print(f"[MCP]   FOLDER_WATCHER_ACTIVE_ON_BOOT: {FOLDER_WATCHER_ACTIVE_ON_BOOT}", file=sys.stderr)

#         doc_dir = "/app/my-docs"  # Docker path

#         # Check if we should do anything on boot
#         if not FULL_SCAN_ON_BOOT and not FOLDER_WATCHER_ACTIVE_ON_BOOT:
#             # print("[MCP]   Skipping startup scan and folder watcher (disabled via environment variables)", file=sys.stderr)
#             # print("[MCP]   You can manually trigger scanning using the 'scan_all_my_documents' tool", file=sys.stderr)
#             # print("[MCP]   You can manually start folder watching using the 'start_watching_folder' tool", file=sys.stderr)
#             return

#         # Create a callback function for the folder watcher
#         # Uses the singleton VectorStore internally
#         def scan_callback(changes, incremental):
#             try:
#                 if incremental and changes:
#                     # Process only the changed files
#                     return process_incremental_changes(changes, doc_dir)
#                 else:
#                     # Do a full scan with database reset
#                     # run_full_document_scan uses singleton VectorStore
#                     return scan_all_my_documents(doc_dir)
#             except Exception as e:
#                 print(f"[MCP] Error during scan: {e}", file=sys.stderr)
#                 import traceback
#                 traceback.print_exc()
#                 from mcp.types import TextContent
#                 return [TextContent(
#                     type="text",
#                     text=f"✗ Error during scan: {str(e)}"
#                 )]

#         # Handle different combinations of environment variables
#         if FOLDER_WATCHER_ACTIVE_ON_BOOT:
#             # Start folder watcher with or without initial scan
#             print(f"[MCP] Starting folder watcher (initial scan: {FULL_SCAN_ON_BOOT})...", file=sys.stderr)
#             result = start_folder_watcher(scan_callback, do_initial_scan=FULL_SCAN_ON_BOOT)

#             if result['status'] == 'started':
#                 print(f"[MCP] ✓ Folder watcher started successfully", file=sys.stderr)
#                 print(f"[MCP]   Watching: {result['watch_path']}", file=sys.stderr)
#                 print(f"[MCP]   Debounce: {result['debounce_seconds']} seconds", file=sys.stderr)
#                 print(f"[MCP]   Full scan interval: {result['full_scan_interval_days']} days", file=sys.stderr)

#                 # Log scan result summary if available
#                 if FULL_SCAN_ON_BOOT and 'scan_result' in result and result['scan_result']:
#                     print(f"[MCP] ✓ Initial scan completed. Result:", file=sys.stderr)
#                     print(f"{result['scan_result']}", file=sys.stderr)
#             else:
#                 print(f"[MCP] ⚠ Warning: Failed to start folder watcher: {result.get('message', 'Unknown error')}", file=sys.stderr)
#                 print(f"[MCP]   You can manually start it using the 'start_watching_folder' tool", file=sys.stderr)

#         elif FULL_SCAN_ON_BOOT:
#             # Only do a full scan without starting the watcher
#             print("[MCP] Performing full scan (folder watcher disabled)...", file=sys.stderr)
#             scan_result = scan_all_my_documents(doc_dir)
#             if scan_result:
#                 print(f"[MCP] ✓ Full scan completed", file=sys.stderr)
#             print(f"[MCP]   Folder watcher is not active (disabled via environment variable)", file=sys.stderr)
#             print(f"[MCP]   You can manually start it using the 'start_watching_folder' tool", file=sys.stderr)

        

#     except Exception as e:
#         print(f"[MCP] ⚠ Warning: Error during startup initialization: {e}", file=sys.stderr)
#         print(f"[MCP]   The server will continue, but automatic scanning/watching may not be active", file=sys.stderr)
#         print(f"[MCP]   You can manually start features using the available tools", file=sys.stderr)
#         import traceback
#         traceback.print_exc()


# async def main_stdio():
#     """Run the MCP server via stdio."""
#     from mcp.server.stdio import stdio_server

#     # Perform startup initialization
#     await startup_initialization()

#     async with stdio_server() as (read_stream, write_stream):
#         await mcp.run(
#             read_stream,
#             write_stream
#         )

#     print("mcp_server.py -- MCP server is shutting down.", file=sys.stderr)


# async def main_websocket(host: str = "0.0.0.0", port: int = 38777):
#     """Run the MCP server via SSE/WebSocket over HTTP."""
#     from mcp.server.sse import SseServerTransport
#     from starlette.applications import Starlette
#     from starlette.routing import Route, Mount
#     from starlette.responses import Response
#     import uvicorn

#     # Perform startup initialization
#     await startup_initialization()

#     # Create SSE transport
#     sse = SseServerTransport("/messages/")

#     async def handle_sse(request):
#         """Handle SSE connection requests."""
#         async with sse.connect_sse(
#             request.scope, request.receive, request._send
#         ) as streams:
#             await mcp.run(
#                 streams[0], streams[1]
#             )
#         return Response()

#     # Create Starlette routes
#     routes = [
#         Route("/sse", endpoint=handle_sse, methods=["GET"]),
#         Mount("/messages/", app=sse.handle_post_message),
#     ]

#     # Create Starlette app
#     starlette_app = Starlette(
#         routes=routes,
#         on_shutdown=[shutdown_handler]
#     )

#     print(f"[MCP] Starting SSE/WebSocket server on {host}:{port}", file=sys.stderr)
#     print(f"[MCP] SSE endpoint: http://{host}:{port}/sse", file=sys.stderr)
#     print(f"[MCP] Messages endpoint: http://{host}:{port}/messages/", file=sys.stderr)

#     # Run the server
#     config = uvicorn.Config(
#         starlette_app,
#         host=host,
#         port=port,
#         log_level="info"
#     )
#     server = uvicorn.Server(config)
#     await server.serve()


# async def shutdown_handler():
#     """Handle server shutdown."""
#     print("[MCP] Server is shutting down...", file=sys.stderr)
#     # try:
#     #     stop_watching_folder()
#     #     print("[MCP] Folder watcher stopped")
#     # except Exception as e:
#     #     print(f"[MCP] Error stopping folder watcher: {e}")


async def main():
    """Main entry point - determine transport type from environment or arguments."""
    import sys
    import os

    # Check for transport type from environment variable or command line
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()

    # Allow command line override
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

    # Get host and port for websocket mode
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "38777"))

    # Parse additional command line arguments
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

    # Run the appropriate transport
    stdio_task = asyncio.create_task(app.run_stdio())
    http_task = asyncio.create_task(app.run_http(host=host, port=port))
    
    # Wait for either to stop
    await asyncio.wait([stdio_task, http_task], return_when=asyncio.FIRST_COMPLETED)



if __name__ == "__main__":
    asyncio.run(main())

