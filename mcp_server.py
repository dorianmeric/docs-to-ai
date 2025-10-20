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
from fastmcp import FastMCP
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
from app.scan_all_my_documents import scan_all

# Initialize the FastMCP server with the name "docs-to-ai"
# This creates an MCP server instance that can expose tools to Claude
mcp = FastMCP("docs-to-ai")

# Tool implementations using @mcp.tool() decorator
# Each function decorated with @mcp.tool() becomes available as a tool that Claude can call

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
    # Initialize connection to the vector database
    vector_store = VectorStore()

    # Validate max_results is within acceptable bounds (1 to MAX_SEARCH_RESULTS)
    max_results = min(max(1, max_results), MAX_SEARCH_RESULTS)

    # Perform search (get 3x more results if filtering by topic to compensate for filtering)
    search_limit = max_results * 3 if topic else max_results
    results = vector_store.search(query, n_results=search_limit)

    # Filter by topic if specified
    # Documents can have multiple topics from their folder hierarchy, so check if the
    # requested topic appears in the document's topics list
    if topic:
        filtered_results = []
        for r in results:
            doc_topics = r['metadata'].get('topics', [])
            # Handle case where topics might be stored as a string instead of a list
            if isinstance(doc_topics, str):
                doc_topics = [doc_topics]
            # Include this result if the requested topic is in the document's topic list
            if topic in doc_topics:
                filtered_results.append(r)
        # Trim to requested max_results after filtering
        results = filtered_results[:max_results]

    # Return early if no results found
    if not results:
        filter_msg = f" with topic '{topic}'" if topic else ""
        return f"No results found for query: '{query}'{filter_msg}"

    # Format results for display
    filter_info = f" (filtered to topic: '{topic}')" if topic else ""
    response_parts = [f"Found {len(results)} relevant chunks for query: '{query}'{filter_info}\n"]

    # Iterate through each search result and format it for display
    for i, result in enumerate(results, 1):
        metadata = result['metadata']
        filename = metadata.get('filename', 'Unknown')
        page = metadata.get('page', 'Unknown')
        topics = metadata.get('topics', ['uncategorized'])
        filetype = metadata.get('filetype', '.pdf')

        # Handle case where topics might be stored as a string instead of a list
        if isinstance(topics, str):
            topics = [topics]

        # Join topics with the configured separator (e.g., " > " to show hierarchy)
        topics_display = TOPIC_SEPARATOR.join(topics)

        # Build result entry with metadata and content
        response_parts.append(f"\n--- Result {i} ---")
        response_parts.append(f"Topics: {topics_display}")
        response_parts.append(f"Source: {filename} ({filetype}) [Page {page}]")

        # Calculate and display relevance score if distance is available
        if result.get('distance') is not None:
            # Lower distance = higher relevance (convert to percentage)
            relevance = max(0, 100 - (result['distance'] * 100))
            response_parts.append(f"Relevance: {relevance:.1f}%")

        # Include the actual text content from the document
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
    # Initialize connection to the vector database
    vector_store = VectorStore()
    # Retrieve all documents from the database
    documents = vector_store.list_documents()

    # Filter by topic if specified (check if topic appears in topics list)
    if topic:
        filtered_docs = []
        for doc in documents:
            doc_topics = doc.get('topics', [])
            # Handle case where topics might be stored as a string instead of a list
            if isinstance(doc_topics, str):
                doc_topics = [doc_topics]
            # Include this document if it has the requested topic
            if topic in doc_topics:
                filtered_docs.append(doc)
        documents = filtered_docs

    # Return early if no documents found
    if not documents:
        filter_msg = f" with topic '{topic}'" if topic else ""
        return f"No documents found{filter_msg}. Use 'python -m app.scan_all_my_documents' to add documents."

    # Group documents by their first (primary) topic for organized display
    docs_by_first_topic = {}
    for doc in documents:
        topics = doc.get('topics', ['uncategorized'])
        # Handle case where topics might be stored as a string instead of a list
        if isinstance(topics, str):
            topics = [topics]
        # Use the first topic as the primary category
        first_topic = topics[0] if topics else 'uncategorized'

        # Create topic group if it doesn't exist
        if first_topic not in docs_by_first_topic:
            docs_by_first_topic[first_topic] = []
        docs_by_first_topic[first_topic].append(doc)

    # Build the response
    response_parts = []
    filter_info = f" (filtered to topic: '{topic}')" if topic else ""
    response_parts.append(f"Available documents{filter_info}: {len(documents)} total\n")

    # Display documents organized by topic
    for first_topic in sorted(docs_by_first_topic.keys()):
        topic_docs = docs_by_first_topic[first_topic]
        response_parts.append(f"\n📁 {first_topic} ({len(topic_docs)} documents)")
        for doc in topic_docs:
            topics = doc.get('topics', ['uncategorized'])
            # Handle case where topics might be stored as a string instead of a list
            if isinstance(topics, str):
                topics = [topics]
            # Join topics with the configured separator to show full hierarchy
            topics_display = TOPIC_SEPARATOR.join(topics)
            filetype = doc.get('filetype', '.pdf')

            # Format file size for human readability
            file_size = doc.get('file_size', 0)
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024*1024):.1f} MB"
            elif file_size > 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{file_size} bytes"

            # Format last modified timestamp as a readable date
            last_modified = doc.get('last_modified', 0)
            if last_modified:
                mod_time = time.ctime(last_modified)
            else:
                mod_time = "Unknown"

            # Display document information
            response_parts.append(f"  • {doc['filename']} ({filetype}) - Size: {size_str}, Modified: {mod_time}")
            response_parts.append(f"    Topics: {topics_display}")

    return "\n".join(response_parts)


@mcp.tool()
def list_topics() -> str:
    """Get a list of all topics/categories in the document collection.

    Topics are derived from the folder hierarchy where documents are organized.
    Each folder level becomes a separate topic tag.
    """
    # Initialize connection to the vector database
    vector_store = VectorStore()
    # Get all unique topics from the database
    topics = vector_store.list_topics()

    # Return early if no topics exist
    if not topics:
        return "No topics found. Use scan_all_my_documents.py, or ask the LLM to run scan_all_my_documents, to add documents."

    # Get statistics to show document counts per topic
    stats = vector_store.get_stats()
    topic_counts = stats['documents_per_topic']

    # Build response with topic hierarchy explanation
    response = f"Available topics ({len(topics)}):\n\n"
    response += "Topics are hierarchical - each folder in the path becomes a topic.\n"
    response += "Documents can have multiple topics based on their folder location.\n\n"

    # List each topic with its document count
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
    # Initialize connection to the vector database
    vector_store = VectorStore()
    # Get comprehensive statistics about the collection
    stats = vector_store.get_stats()

    # Build the main statistics section
    response = "Document Collection Statistics:\n\n"
    response += f"Total chunks: {stats['total_chunks']}\n"  # Number of text chunks stored
    response += f"Total documents: {stats['total_documents']}\n"  # Number of unique documents
    response += f"Total topics: {stats['total_topics']}\n"  # Number of unique topics
    response += f"Collection: {stats['collection_name']}\n\n"  # Vector database collection name

    # Show breakdown by file type if available
    if 'documents_per_filetype' in stats and stats['documents_per_filetype']:
        response += "Documents per file type:\n"
        for filetype in sorted(stats['documents_per_filetype'].keys()):
            count = stats['documents_per_filetype'][filetype]
            response += f"  {filetype}: {count} document{'s' if count != 1 else ''}\n"
        response += "\n"

    # Show breakdown by topic if available
    if stats['topics']:
        response += "Documents per topic (hierarchical):\n"
        for topic in sorted(stats['topics']):
            count = stats['documents_per_topic'].get(topic, 0)
            response += f"  📁 {topic}: {count} document{'s' if count != 1 else ''}\n"

    # Add file size information if documents exist
    if stats['documents']:
        response += "\nFile Size Information:\n"
        # Calculate total size across all documents
        total_size = sum(doc.get('file_size', 0) for doc in stats['documents'])

        # Format total size for human readability
        if total_size > 1024 * 1024:
            size_str = f"{total_size / (1024*1024):.1f} MB"
        elif total_size > 1024:
            size_str = f"{total_size / 1024:.1f} KB"
        else:
            size_str = f"{total_size} bytes"

        response += f"  Total size of all documents: {size_str}\n"

        # Show the 5 largest documents
        sorted_docs = sorted(stats['documents'], key=lambda x: x.get('file_size', 0), reverse=True)
        response += "\nLargest documents:\n"
        for doc in sorted_docs[:5]:
            # Format file size for human readability
            file_size = doc.get('file_size', 0)
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024*1024):.1f} MB"
            elif file_size > 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{file_size} bytes"

            # Format last modified timestamp (note: this was incorrectly getting 'file_size')
            last_modified = doc.get('last_modified', 0)  # Fixed: was 'file_size'
            if last_modified:
                mod_time = time.ctime(last_modified)
            else:
                mod_time = "Unknown"

            # Display document information
            response += f"  {doc['filename']}: {size_str}, Modified: {mod_time}\n"

    return response


@mcp.tool()
def scan_all_my_documents() -> str:
    """Scan all documents in the docs directory and update the vector database.

    This forces a complete re-indexing: the database is cleared first to prevent duplicates,
    then all documents are processed from scratch.
    """
    try:
        # Set the document directory (Docker path)
        doc_dir = "/app/my-docs"

        # Call the scan_all function which:
        # 1. Clears the existing database to prevent duplicates
        # 2. Scans all PDFs and Word docs in the directory
        # 3. Processes them into chunks and stores in the vector database
        # Returns list[TextContent] with debug info
        result = scan_all(doc_dir)

        # Extract text from TextContent objects for display
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
        # Define the base directory for documents (Docker path)
        doc_dir = "/app/my-docs"

        # Create a callback function that will be triggered when file changes are detected
        # The callback determines whether to do an incremental update or a full scan
        # Returns list[TextContent] with debug info for MCP response
        def scan_callback(changes, incremental):
            try:
                if incremental and changes:
                    # Process only the files that have changed (added, modified, deleted)
                    # This is more efficient than rescanning everything
                    return process_incremental_changes(changes, doc_dir)
                else:
                    # Do a full scan with database reset to prevent duplicates
                    # Full scans are triggered weekly or on initial startup
                    return scan_all(doc_dir)
            except Exception as e:
                # Return error message on scan failure
                print(f"[MCP] Error during scan: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc()
                return f"✗ Error during scan: {str(e)}"

        # Start watching the folder for changes
        # do_initial_scan=True performs an immediate scan when the watcher starts
        result = start_folder_watcher(scan_callback, do_initial_scan=True)

        # Process the result from starting the folder watcher
        if result['status'] == 'started':
            # Build a successful response with configuration details
            response_parts = []
            response_parts.append("✓ Folder watcher started successfully\n")
            response_parts.append(f"Watching: {result['watch_path']}")
            response_parts.append(f"Debounce: {result['debounce_seconds']} seconds")  # Delay before processing changes
            response_parts.append(f"Full scan interval: {result['full_scan_interval_days']} days")  # Weekly full scans
            response_parts.append("Mode: Incremental updates enabled")

            # If an initial scan was performed, include its results
            if 'scan_result' in result and result['scan_result']:
                response_parts.append("\n" + "="*60)
                response_parts.append("INITIAL SCAN RESULTS:")
                response_parts.append("="*60)
                # scan_result is a string containing the scan summary
                response_parts.append(result['scan_result'])

            return "\n".join(response_parts)
        elif result['status'] == 'already_watching':
            # Watcher is already running (possibly started automatically on server boot)
            return f"ℹ Folder watcher is already active (started automatically on server startup)\n\nWatching: {result['watch_path']}"
        else:
            # Failed to start the watcher
            return f"✗ Failed to start folder watcher\n\nError: {result.get('message', 'Unknown error')}"
    except Exception as e:
        return f"✗ Error starting folder watcher: {str(e)}"


@mcp.tool()
def stop_watching_folder() -> str:
    """Stop watching the folder for changes.

    Does nothing if no folder is currently being watched.
    """
    try:
        # Call the folder watcher stop function
        result = stop_folder_watcher()

        # Process the result
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
        # Get the scan timing information from the folder watcher
        result = get_last_scan_time()

        if result["status"] == "success":
            # Build response with scan timing details
            response_parts = ["Last Folder Scan Information:\n"]
            response_parts.append(f"Started:  {result['scan_start_time_formatted']}")

            # Show end time if scan has completed
            if 'scan_end_time_formatted' in result:
                response_parts.append(f"Finished: {result['scan_end_time_formatted']}")
                response_parts.append(f"Duration: {result['duration_seconds']} seconds")
            else:
                response_parts.append("Status: Scan in progress...")

            # Add information about full scan schedule
            # Full scans clear the database and rescan everything to prevent duplicates
            if 'last_full_scan_time_formatted' in result:
                response_parts.append(f"\nLast Full Scan: {result['last_full_scan_time_formatted']}")
                days_since = int(result['days_since_full_scan'])
                response_parts.append(f"Days since full scan: {days_since}")
                if result.get('next_full_scan_due'):
                    response_parts.append("Next full scan: DUE NOW")
                else:
                    days_remaining = 7 - days_since  # Full scans occur weekly
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
    """Main entry point - determine transport type from environment or arguments.

    The MCP server can run in two modes:
    1. stdio - Communicates via standard input/output (default, used by Claude Desktop)
    2. websocket/http - Runs an HTTP server with SSE for web-based clients
    """
    import sys
    import os

    # Check for transport type from environment variable or command line
    # Default to stdio mode which is used by Claude Desktop
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()

    # Allow command line arguments to override the transport type
    if len(sys.argv) > 1:
        if sys.argv[1] in ["--websocket", "--sse", "--http"]:
            transport = "websocket"
        elif sys.argv[1] == "--stdio":
            transport = "stdio"
        elif sys.argv[1] == "--help":
            # Display help information
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

    # Get host and port configuration for websocket/HTTP mode
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "38777"))

    # Parse additional command line arguments for host/port
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

    # Run both transports concurrently (FastMCP supports dual-mode operation)
    # Create async tasks for both stdio and HTTP transports
    stdio_task = asyncio.create_task(mcp.run_stdio_async())
    http_task = asyncio.create_task(mcp.run_http_async(host=host, port=port))

    # Wait for either transport to stop (typically runs indefinitely until interrupted)
    await asyncio.wait([stdio_task, http_task], return_when=asyncio.FIRST_COMPLETED)

if __name__ == "__main__":
    # Run the main async function when script is executed directly
    asyncio.run(main())

