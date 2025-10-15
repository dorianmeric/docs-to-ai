#!/usr/bin/env python3
"""
MCP Server for querying documents (PDFs and Word docs).

This server exposes tools that allow Claude to search and retrieve
information from a collection of documents stored in a vector database.
"""

import asyncio
import subprocess
from typing import Optional
import time
from mcp.server import Server
from mcp.types import Tool, TextContent
from app.vector_store import VectorStore
from app.config import DEFAULT_SEARCH_RESULTS, MAX_SEARCH_RESULTS, TOPIC_SEPARATOR

# Initialize server
app = Server("docs-to-ai")

# Initialize vector store
vector_store: Optional[VectorStore] = None


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
            name="scan_my_documents",
            description=(
                "Scan all documents in the docs directory and update the vector database. "
                "This forces a re-indexing of all documents using the latest files."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    global vector_store
    
    if vector_store is None:
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
                    text=f"No documents found{filter_msg}. Use add_docs_to_database.py to add documents."
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
                    text="No topics found. Use add_docs_to_database.py to add documents."
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
                    last_modified = doc.get('last_modified', 0)
                    if last_modified:
                        mod_time = time.ctime(last_modified)
                    else:
                        mod_time = "Unknown"
                    
                    response += f"  {doc['filename']}: {size_str}, Modified: {mod_time}\n"
            
            return [TextContent(
                type="text",
                text=response
            )]
        
        elif name == "scan_my_documents":
            # Run the command to scan and update documents
            try:
                result = subprocess.run(
                    ["python", "app/add_docs_to_database.py", "--doc-dir", "/app/docs"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                return [TextContent(
                    type="text",
                    text=f"Successfully scanned and updated documents.\n\nOutput:\n{result.stdout}"
                )]
            except subprocess.CalledProcessError as e:
                return [TextContent(
                    type="text",
                    text=f"Error scanning documents: {e}\nError output: {e.stderr}"
                )]
            except Exception as e:
                return [TextContent(
                    type="text",
                    text=f"Unexpected error scanning documents: {str(e)}"
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


async def main():
    """Run the MCP server."""
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

    print("mcp_server.py -- MCP server is shutting down.")


if __name__ == "__main__":
    asyncio.run(main())

