# Docs-to-AI -- PDF/Word Document Query System with MCP

A Model Context Protocol (MCP) server that enables LLMs (like Clause or any other LLM that supports MCP) to query your documents using semantic search. Organizes documents by topics based on folder structure.
Supports: PDF, Word, Excel, Markdown.
Supported extensions: .pdf, .docx, .doc, .xlsx, .xls, .xlsam, .xlsb, .md

The model used for document retrieval is all-MiniLM-L6-v2, with 384 dimensions for the embeddings.

## Features

- Extract text from PDF documents
- Organize documents by topics (using folder structure)
- Generate embeddings for semantic search
- Store documents in a vector database (ChromaDB)
- Expose MCP tools for Claude to search and retrieve documents
- Filter searches by topic/category
- Handle multiple documents with the same filename across different topics

## Architecture

```
PDFs (organized by topic folders)
  → Text Extraction
    → Chunking
      → Embeddings
        → ChromaDB (with topic tags)
          ↓
    MCP Server Tools
          ↓
       Claude
```

## Document Organization

This system is designed to work with PDFs organized in a folder structure where:
- Each folder represents a **topic** or **category**
- PDFs in that folder are automatically tagged with the topic name
- Documents with the same filename in different folders are handled correctly

Example structure:
```
pdfs/
├── Machine_Learning/
│   ├── neural_networks.pdf
│   ├── deep_learning.pdf
│   └── introduction.pdf
├── Python_Programming/
│   ├── basics.pdf
│   ├── advanced.pdf
│   └── introduction.pdf  # Different from ML's introduction.pdf
└── Data_Science/
    ├── statistics.pdf
    └── visualization.pdf
```

## 1. Installation, with local python

```bash
pip install -r requirements.txt  # Install dependencies:
python -m app.scan_all_my_documents  #  Ingest PDFs
python mcp_server.py #  Start the MCP Server
```

The script will:
- Recursively scan the directory
- Detect topics from folder names
- Extract and chunk text from each PDF
- Tag chunks with their topic
- Store everything in ChromaDB

Example output:
```
Found 15 PDF files
Base directory: /path/to/pdfs

Detected topics: Data_Science, Machine_Learning, Python_Programming

[1/15] Processing: neural_networks.pdf
  Topic: Machine_Learning
  ✓ Added 45 chunks
...

INGESTION SUMMARY
==================
Total PDFs processed: 15
Successful: 15
Failed: 0
Total chunks added: 523

Documents per topic:
  Data_Science: 4 documents, 156 chunks
  Machine_Learning: 6 documents, 234 chunks
  Python_Programming: 5 documents, 133 chunks
```

Add to your Claude Desktop config (`claude_desktop_config.json`):

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


## 2. Installation, with docker
You need Docker Desktop, or Docker Engine, running. Then just write the following into a file called "docker-compose.yaml":
````yaml
services:
  docs-to-ai:
    image: dmeric/docs-to-ai
    container_name: docs-to-ai
    
    volumes:
      - ./cache/chromadb:/app/chroma_db       # ChromaDB database (persists the vector store)
      - ./cache/doc_cache:/app/doc_cache      # Document cache (persists extracted text)
      - ./my-docs:/app/my-docs:ro             # Documents directory (your PDFs and Word docs). Read-only to prevent accidental modifications
    
    # Stdin/stdout - required for MCP protocol
    stdin_open: true
    tty: true

    # Restart policy
    restart: unless-stopped
    
    # # Resource limits (optional - adjust based on your needs)
    # deploy:
    #   resources:
    #     limits:
    #       cpus: '2'
    #       memory: 4G
    #     reservations:
    #       cpus: '1'
    #       memory: 2G
    
````
then run, in bash or in Powershell:
```bash
docker compose up -d
````

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {

    "docs-to-ai": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "dmeric/docs-to-ai"
      ]
    }

  }
}

```

Finally, put your documents in the folder /my-docs, and ask the server to scan the documents, and optionally to start the folder watcher.
You should now be able to ask your LLM questions about the documents.

## Project Structure

- `mcp_server.py` - Main MCP server implementation
- `document_processor.py` - PDF text extraction and chunking
- `vector_store.py` - Vector database operations
- `scan_all_my_documentss.py` - Batch PDF ingestion script
- `requirements.txt` - Python dependencies
- `config.py` - Configuration settings

## MCP Tools

- `search_documents` - Semantic search across all PDFs (with optional topic filter)
- `list_documents` - List all available documents (with optional topic filter)
- `list_topics` - List all topics/categories
- `get_collection_stats` - Get statistics about the collection

### Example Queries for Claude

Once configured, you can ask Claude:

**General queries:**
- "What documents do you have access to?"
- "What topics are available?"
- "Search for information about neural networks"

**Topic-specific queries:**
- "Search for Python programming concepts in the Python_Programming topic"
- "Show me all documents about Machine Learning"
- "Find information about data visualization in the Data_Science topic"

**Complex queries:**
- "Compare what different documents say about deep learning"
- "Find all mentions of pandas across all documents"
- "What are the key concepts in the Machine_Learning documents?"

## Configuration

Edit `config.py` to customize:
- Chunk size and overlap
- Number of search results
- Embedding model
- ChromaDB persistence directory
- Topic extraction behavior (enable/disable folder-based topics)

### Topic Configuration

By default, the system uses folder names as topics. To modify:

```python
# config.py
USE_FOLDER_AS_TOPIC = True  # Set to False to disable topic extraction
DEFAULT_TOPIC = "uncategorized"  # Default topic for PDFs not in folders
```

## License

MIT
