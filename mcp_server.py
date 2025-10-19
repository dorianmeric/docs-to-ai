#!/usr/bin/env python3
"""
MCP Server for querying documents (PDFs and Word docs).

This server exposes tools that allow Claude to search and retrieve
information from a collection of documents stored in a vector database.
"""

import asyncio
import subprocess
import time
from mcp.server import Server
from mcp.types import Tool, TextContent
from app.vector_store import VectorStore
from app.config import (
    DEFAULT_SEARCH_RESULTS,
    MAX_SEARCH_RESULTS,
    TOPIC_SEPARATOR,
    FULL_SCAN_ON_BOOT,
    FOLDER_WATCHER_ACTIVE_ON_BOOT
)
from app.folder_watcher import (
    start_watching_folder, 
    stop_watching_folder, 
    get_last_scan_time,
    trigger_full_scan_if_needed
)
from app.incremental_updater import process_incremental_changes
from app.scan_all_my_documents import scan_all_my_documents

# Initialize server
app = Server("docs-to-ai")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="search_documents",
            description=(
                "Search across all documents (PDFs and Word) using semantic similarity. "
                "Returns the most relevant text chunks with their source information and hierarchical topics. "
                "Documents are tagged with all topics in their folder hierarchy. "
                "Optionally filter by topic to search within specific categories."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find relevant document chunks"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": f"Maximum number of results to return (default: {DEFAULT_SEARCH_RESULTS}, max: {MAX_SEARCH_RESULTS})",
                        "default": DEFAULT_SEARCH_RESULTS,
                        "minimum": 1,
                        "maximum": MAX_SEARCH_RESULTS
                    },
                    "topic": {
                        "type": "string",
                        "description": "Optional: Filter results to documents that have this topic (at any level in hierarchy)"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="list_documents",
            description=(
                "Get a list of all available documents with their hierarchical topics. "
                "Shows PDFs and Word documents organized by their folder hierarchy. "
                "Each document shows all topics from its folder path."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Optional: Filter to show only documents that have this topic"
                    }
                }
            }
        ),
        Tool(
            name="list_topics",
            description=(
                "Get a list of all topics/categories in the document collection. "
                "Topics are derived from the folder hierarchy where documents are organized. "
                "Each folder level becomes a separate topic tag."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_collection_stats",
            description=(
                "Get statistics about the document collection, including total number "
                "of documents, topics, file types, and chunks stored in the vector database. "
                "Shows the distribution of documents across topics and file types."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="scan_all_my_documents",
            description=(
                "Scan all documents in the docs directory and update the vector database. "
                "This forces a complete re-indexing: the database is cleared first to prevent duplicates, "
                "then all documents are processed from scratch."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="start_watching_folder",
            description=(
                "Start watching the documents folder for changes and automatically trigger incremental updates. "
                "Uses intelligent change detection to only process modified files. "
                "Performs a full scan (with database reset) once per week and on initial startup to prevent duplicates."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="stop_watching_folder",
            description=(
                "Stop watching the folder for changes. Does nothing if no folder is currently being watched."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_time_of_last_folder_scan",
            description=(
                "Get the timestamp of when the last folder scan was started and finished. "
                "Also shows information about the last full scan and when the next one is due."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),

    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    # VectorStore is a singleton - get the shared instance
    vector_store = VectorStore()
    
    try:
        if name == "search_documents":
            query = arguments.get("query")
            max_results = arguments.get("max_results", DEFAULT_SEARCH_RESULTS)
            topic_filter = arguments.get("topic")
            
            # Validate max_results
            max_results = min(max(1, max_results), MAX_SEARCH_RESULTS)
            
            # Perform search (get more results if filtering by topic)
            search_limit = max_results * 3 if topic_filter else max_results
            results = vector_store.search(query, n_results=search_limit)
            
            # Filter by topic if specified (check if topic appears in topics list)
            if topic_filter:
                filtered_results = []
                for r in results:
                    doc_topics = r['metadata'].get('topics', [])
                    if isinstance(doc_topics, str):
                        doc_topics = [doc_topics]
                    if topic_filter in doc_topics:
                        filtered_results.append(r)
                results = filtered_results[:max_results]
            
            if not results:
                filter_msg = f" with topic '{topic_filter}'" if topic_filter else ""
                return [TextContent(
                    type="text",
                    text=f"No results found for query: '{query}'{filter_msg}"
                )]
            
            # Format results
            filter_info = f" (filtered to topic: '{topic_filter}')" if topic_filter else ""
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
            
            return [TextContent(
                type="text",
                text="\n".join(response_parts)
            )]
        
        elif name == "list_documents":
            topic_filter = arguments.get("topic")
            documents = vector_store.list_documents()
            
            # Filter by topic if specified (check if topic appears in topics list)
            if topic_filter:
                filtered_docs = []
                for doc in documents:
                    doc_topics = doc.get('topics', [])
                    if isinstance(doc_topics, str):
                        doc_topics = [doc_topics]
                    if topic_filter in doc_topics:
                        filtered_docs.append(doc)
                documents = filtered_docs
            
            if not documents:
                filter_msg = f" with topic '{topic_filter}'" if topic_filter else ""
                return [TextContent(
                    type="text",
                    text=f"No documents found{filter_msg}. Use 'python -m app.scan_all_my_documents' to add documents."
                )]
            
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
            filter_info = f" (filtered to topic: '{topic_filter}')" if topic_filter else ""
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
            
            return [TextContent(
                type="text",
                text="\n".join(response_parts)
            )]
        
        elif name == "list_topics":
            topics = vector_store.list_topics()
            
            if not topics:
                return [TextContent(
                    type="text",
                    text="No topics found. Use scan_all_my_documents.py to add documents."
                )]
            
            stats = vector_store.get_stats()
            topic_counts = stats['documents_per_topic']
            
            response = f"Available topics ({len(topics)}):\n\n"
            response += "Topics are hierarchical - each folder in the path becomes a topic.\n"
            response += "Documents can have multiple topics based on their folder location.\n\n"
            
            for topic in topics:
                count = topic_counts.get(topic, 0)
                response += f"  📁 {topic}: {count} document{'s' if count != 1 else ''}\n"
            
            return [TextContent(
                type="text",
                text=response
            )]
        
        elif name == "get_collection_stats":
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
            
            return [TextContent(
                type="text",
                text=response
            )]
        
        elif name == "scan_all_my_documents":
            # Run the full scan function directly with database reset
            try:
                doc_dir = "/app/my-docs"  # Docker path
                # scan_all_my_documents uses the singleton VectorStore internally
                # Returns list[TextContent] with debug info
                return scan_all_my_documents(doc_dir)
            except Exception as e:
                return [TextContent(
                    type="text",
                    text=f"✗ Error scanning documents: {str(e)}"
                )]
            
        elif name == "start_watching_folder":
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
                            # scan_all_my_documents uses singleton VectorStore
                            return scan_all_my_documents(doc_dir)
                    except Exception as e:
                        # Return error as TextContent for MCP response
                        print(f"[MCP] Error during scan: {e}")
                        import traceback
                        traceback.print_exc()
                        return [TextContent(
                            type="text",
                            text=f"✗ Error during scan: {str(e)}"
                        )]
                
                # Start watching the folder with initial scan
                result = start_watching_folder(scan_callback, do_initial_scan=True)

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

                    return [TextContent(
                        type="text",
                        text="\n".join(response_parts)
                    )]
                elif result['status'] == 'already_watching':
                    return [TextContent(
                        type="text",
                        text=f"ℹ Folder watcher is already active (started automatically on server startup)\n\nWatching: {result['watch_path']}"
                    )]
                else:
                    return [TextContent(
                        type="text",
                        text=f"✗ Failed to start folder watcher\n\nError: {result.get('message', 'Unknown error')}"
                    )]
            except Exception as e:
                return [TextContent(
                    type="text",
                    text=f"✗ Error starting folder watcher: {str(e)}"
                )]
        
        elif name == "stop_watching_folder":
            try:
                result = stop_watching_folder()
                
                if result['status'] == 'stopped':
                    return [TextContent(
                        type="text",
                        text="✓ Folder watcher stopped successfully"
                    )]
                elif result['status'] == 'not_watching':
                    return [TextContent(
                        type="text",
                        text="ℹ Folder watcher is not currently active"
                    )]
                else:
                    return [TextContent(
                        type="text",
                        text=f"✗ Error stopping folder watcher: {result.get('message', 'Unknown error')}"
                    )]
            except Exception as e:
                return [TextContent(
                    type="text",
                    text=f"✗ Error stopping folder watcher: {str(e)}"
                )]
        
        elif name == "get_time_of_last_folder_scan":
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
                    
                    return [TextContent(
                        type="text",
                        text="\n".join(response_parts)
                    )]
                elif result["status"] == "not_watching":
                    return [TextContent(
                        type="text",
                        text="ℹ Folder watcher is not currently active"
                    )]
                elif result["status"] == "no_scans_yet":
                    return [TextContent(
                        type="text",
                        text="ℹ Folder watcher is active but no scans have been triggered yet"
                    )]
                else:
                    return [TextContent(
                        type="text",
                        text=f"✗ Error: {result.get('message', 'Unknown error')}"
                    )]
            except Exception as e:
                return [TextContent(
                    type="text",
                    text=f"✗ Error getting last scan time: {str(e)}"
                )]
        


        else:
            return [TextContent(
                type="text",
                text=f"Unknown tool: {name}"
            )]
    
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error executing tool {name}: {str(e)}"
        )]


async def startup_initialization():
    """Perform initial scan and start folder watcher on server startup based on environment variables."""
    try:
        # Initialize the singleton VectorStore (will only initialize once)
        VectorStore()

        # print("[MCP] Starting initialization...")
        # print(f"[MCP]   FULL_SCAN_ON_BOOT: {FULL_SCAN_ON_BOOT}")
        # print(f"[MCP]   FOLDER_WATCHER_ACTIVE_ON_BOOT: {FOLDER_WATCHER_ACTIVE_ON_BOOT}")

        doc_dir = "/app/my-docs"  # Docker path

        # Check if we should do anything on boot
        if not FULL_SCAN_ON_BOOT and not FOLDER_WATCHER_ACTIVE_ON_BOOT:
            # print("[MCP] ℹ Skipping startup scan and folder watcher (disabled via environment variables)")
            # print("[MCP]   You can manually trigger scanning using the 'scan_all_my_documents' tool")
            # print("[MCP]   You can manually start folder watching using the 'start_watching_folder' tool")
            return

        # Create a callback function for the folder watcher
        # Uses the singleton VectorStore internally
        def scan_callback(changes, incremental):
            try:
                if incremental and changes:
                    # Process only the changed files
                    return process_incremental_changes(changes, doc_dir)
                else:
                    # Do a full scan with database reset
                    # scan_all_my_documents uses singleton VectorStore
                    return scan_all_my_documents(doc_dir)
            except Exception as e:
                print(f"[MCP] Error during scan: {e}")
                import traceback
                traceback.print_exc()
                from mcp.types import TextContent
                return [TextContent(
                    type="text",
                    text=f"✗ Error during scan: {str(e)}"
                )]

        # Handle different combinations of environment variables
        if FOLDER_WATCHER_ACTIVE_ON_BOOT:
            # Start folder watcher with or without initial scan
            print(f"[MCP] Starting folder watcher (initial scan: {FULL_SCAN_ON_BOOT})...")
            result = start_watching_folder(scan_callback, do_initial_scan=FULL_SCAN_ON_BOOT)

            if result['status'] == 'started':
                print(f"[MCP] ✓ Folder watcher started successfully")
                print(f"[MCP]   Watching: {result['watch_path']}")
                print(f"[MCP]   Debounce: {result['debounce_seconds']} seconds")
                print(f"[MCP]   Full scan interval: {result['full_scan_interval_days']} days")

                # Log scan result summary if available
                if FULL_SCAN_ON_BOOT and 'scan_result' in result and result['scan_result']:
                    print(f"[MCP] ✓ Initial scan completed. Result:")
                    print(f"{result['scan_result']}")
            else:
                print(f"[MCP] ⚠ Warning: Failed to start folder watcher: {result.get('message', 'Unknown error')}")
                print(f"[MCP]   You can manually start it using the 'start_watching_folder' tool")

        elif FULL_SCAN_ON_BOOT:
            # Only do a full scan without starting the watcher
            print("[MCP] Performing full scan (folder watcher disabled)...")
            scan_result = scan_all_my_documents(doc_dir)
            if scan_result:
                print(f"[MCP] ✓ Full scan completed")
            print(f"[MCP]   Folder watcher is not active (disabled via environment variable)")
            print(f"[MCP]   You can manually start it using the 'start_watching_folder' tool")

        

    except Exception as e:
        print(f"[MCP] ⚠ Warning: Error during startup initialization: {e}")
        print(f"[MCP]   The server will continue, but automatic scanning/watching may not be active")
        print(f"[MCP]   You can manually start features using the available tools")
        import traceback
        traceback.print_exc()


async def main_stdio():
    """Run the MCP server via stdio."""
    from mcp.server.stdio import stdio_server

    # Perform startup initialization
    await startup_initialization()

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

    print("mcp_server.py -- MCP server is shutting down.")

    # Stop folder watcher on shutdown
    try:
        stop_watching_folder()
        print("[MCP] Folder watcher stopped")
    except Exception as e:
        print(f"[MCP] Error stopping folder watcher: {e}")


async def main_websocket(host: str = "0.0.0.0", port: int = 38777):
    """Run the MCP server via SSE/WebSocket over HTTP."""
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.responses import Response
    import uvicorn

    # Perform startup initialization
    await startup_initialization()

    # Create SSE transport
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        """Handle SSE connection requests."""
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await app.run(
                streams[0], streams[1], app.create_initialization_options()
            )
        return Response()

    # Create Starlette routes
    routes = [
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Mount("/messages/", app=sse.handle_post_message),
    ]

    # Create Starlette app
    starlette_app = Starlette(
        routes=routes,
        on_shutdown=[shutdown_handler]
    )

    print(f"[MCP] Starting SSE/WebSocket server on {host}:{port}")
    print(f"[MCP] SSE endpoint: http://{host}:{port}/sse")
    print(f"[MCP] Messages endpoint: http://{host}:{port}/messages/")

    # Run the server
    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


async def shutdown_handler():
    """Handle server shutdown."""
    print("[MCP] Server is shutting down...")
    try:
        stop_watching_folder()
        print("[MCP] Folder watcher stopped")
    except Exception as e:
        print(f"[MCP] Error stopping folder watcher: {e}")


def main():
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
    if transport == "websocket":
        asyncio.run(main_websocket(host=host, port=port))
    else:
        asyncio.run(main_stdio())


if __name__ == "__main__":
    main()

