# PDF Document Query System with MCP

A Model Context Protocol (MCP) server that enables Claude to query your PDF documents using semantic search.

## Features

- Extract text from PDF documents
- Generate embeddings for semantic search
- Store documents in a vector database (ChromaDB)
- Expose MCP tools for Claude to search and retrieve documents

## Architecture

```
PDFs → Text Extraction → Chunking → Embeddings → ChromaDB
                                                      ↓
                                              MCP Server Tools
                                                      ↓
                                                  Claude
```

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your environment:
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Usage

### 1. Ingest PDFs

```bash
python ingest_pdfs.py --pdf-dir /path/to/your/pdfs
```

### 2. Start the MCP Server

```bash
python mcp_server.py
```

### 3. Configure Claude Desktop

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "pdf-documents": {
      "command": "python",
      "args": ["C:/path/to/doc-to-ai/mcp_server.py"]
    }
  }
}
```

## Project Structure

- `mcp_server.py` - Main MCP server implementation
- `pdf_processor.py` - PDF text extraction and chunking
- `vector_store.py` - Vector database operations
- `ingest_pdfs.py` - Batch PDF ingestion script
- `requirements.txt` - Python dependencies
- `config.py` - Configuration settings

## MCP Tools

- `search_documents` - Semantic search across all PDFs
- `get_document` - Retrieve specific document content
- `list_documents` - List all available documents

## Configuration

Edit `config.py` to customize:
- Chunk size and overlap
- Number of search results
- Embedding model
- ChromaDB persistence directory

## License

MIT
