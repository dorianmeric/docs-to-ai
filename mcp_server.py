#!/usr/bin/env python3
"""
MCP Server for querying PDF documents.

This server exposes tools that allow Claude to search and retrieve
information from a collection of PDF documents stored in a vector database.
"""

import asyncio
import json
from typing import Optional
from mcp.server import Server
from mcp.types import Tool, TextContent
from vector_store import VectorStore
from config import DEFAULT_SEARCH_RESULTS, MAX_SEARCH_RESULTS

# Initialize server
app = Server("doc-to-ai")

# Initialize vector store
vector_store: Optional[VectorStore] = None


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="search_documents",
            description=(
                "Search across all PDF documents using semantic similarity. "
                "Returns the most relevant text chunks with their source information and topics. "
                "Use this when you need to find information across all documents. "
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
                        "description": "Optional: Filter results to a specific topic/category. Use list_topics to see available topics."
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="list_documents",
            description=(
                "Get a list of all available PDF documents in the system with their topics. "
                "Use this to see what documents are available to search and how they are organized."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Optional: Filter to show only documents from a specific topic"
                    }
                }
            }
        ),
        Tool(
            name="list_topics",
            description=(
                "Get a list of all topics/categories in the document collection. "
                "Topics are derived from the folder structure where PDFs are organized. "
                "Use this to see what topics are available for filtering searches."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_document_stats",
            description=(
                "Get statistics about the document collection, including total number "
                "of documents, topics, and chunks stored in the vector database. "
                "Shows the distribution of documents across topics."
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
            
            # Validate max_results
            max_results = min(max(1, max_results), MAX_SEARCH_RESULTS)
            
            results = vector_store.search(query, n_results=max_results)
            
            if not results:
                return [TextContent(
                    type="text",
                    text=f"No results found for query: '{query}'"
                )]
            
            # Format results
            response_parts = [f"Found {len(results)} relevant chunks for query: '{query}'\n"]
            
            for i, result in enumerate(results, 1):
                metadata = result['metadata']
                filename = metadata.get('filename', 'Unknown')
                page = metadata.get('page', 'Unknown')
                
                response_parts.append(f"\n--- Result {i} ---")
                response_parts.append(f"Source: {filename} (Page {page})")
                
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
            documents = vector_store.list_documents()
            
            if not documents:
                return [TextContent(
                    type="text",
                    text="No documents found in the vector store. Use ingest_pdfs.py to add documents."
                )]
            
            response = f"Available documents ({len(documents)}):\n\n"
            for i, doc in enumerate(documents, 1):
                response += f"{i}. {doc}\n"
            
            return [TextContent(
                type="text",
                text=response
            )]
        
        elif name == "get_document_stats":
            stats = vector_store.get_stats()
            
            response = "Document Collection Statistics:\n\n"
            response += f"Total chunks: {stats['total_chunks']}\n"
            response += f"Total documents: {len(stats['documents'])}\n"
            response += f"Collection: {stats['collection_name']}\n\n"
            
            if stats['documents']:
                response += "Documents:\n"
                for doc in stats['documents']:
                    response += f"  - {doc}\n"
            
            return [TextContent(
                type="text",
                text=response
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


if __name__ == "__main__":
    asyncio.run(main())
