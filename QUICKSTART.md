# Quick Start Guide

Get your PDF document query system up and running in 5 minutes!

## Overview

This system helps you organize and search your PDF documents by:
1. Organizing PDFs by **topic** (using folder structure)
2. Converting text to **embeddings** for semantic search
3. Storing everything in a **vector database**
4. Letting **Claude** search through your documents

## Document Organization

**Important:** Organize your PDFs in folders by topic:

```
pdfs/
├── Machine_Learning/      ← Topic
│   ├── neural_networks.pdf
│   └── deep_learning.pdf
├── Python/               ← Topic
│   ├── basics.pdf
│   └── advanced.pdf
└── Data_Science/         ← Topic
    └── statistics.pdf
```

The folder names become **topic tags** that help organize and filter searches.

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- ChromaDB (vector database)
- sentence-transformers (embeddings)
- PyMuPDF (PDF processing)
- MCP SDK (server framework)

### 2. Run Setup

```bash
python setup.py
```

This will:
- Create necessary directories
- Download the embedding model
- Verify all dependencies

## Ingesting PDFs

### Step 1: Organize Your PDFs

Create folders for each topic and place related PDFs inside:

```bash
mkdir -p pdfs/Machine_Learning
mkdir -p pdfs/Python_Programming
mkdir -p pdfs/Data_Science

# Move your PDFs into the appropriate folders
```

### Step 2: Run Ingestion

```bash
python ingest_pdfs.py --pdf-dir ./pdfs
```

The script will:
- Find all PDFs in subdirectories
- Extract the topic from folder names
- Process and store each document

You'll see output like:
```
Found 12 PDF files
Detected topics: Data_Science, Machine_Learning, Python_Programming

[1/12] Processing: neural_networks.pdf
  Topic: Machine_Learning
  ✓ Added 45 chunks
```

## Testing

Run the test suite to verify everything works:

```bash
python test_system.py
```

## Configure Claude Desktop

### 1. Find your Claude Desktop config file

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Linux:**
```
~/.config/Claude/claude_desktop_config.json
```

### 2. Add the MCP server configuration

Open `claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "doc-to-ai": {
      "command": "python",
      "args": ["C:/D/code/ai-tools/Claude-Controlled/doc-to-ai/mcp_server.py"]
    }
  }
}
```

**Important:** Update the path to match where you installed the project!

### 3. Restart Claude Desktop

Close and reopen Claude Desktop for the changes to take effect.

## Using the System

Once configured, you can ask Claude questions like:

### General Queries
- "What documents do you have access to?"
- "What topics are available?"
- "Give me statistics about the document collection"

### Search Queries
- "Search for information about neural networks"
- "Find mentions of data visualization"
- "What do the documents say about Python decorators?"

### Topic-Specific Queries
- "Search for machine learning concepts in the Machine_Learning topic"
- "Show me all Python_Programming documents"
- "Find information about statistics in the Data_Science topic"

### Advanced Queries
- "Compare what different topics say about optimization"
- "Find all documents that mention both Python and data science"
- "Summarize the key concepts from the Machine_Learning documents"

Claude will use the MCP tools to:
1. Search through your organized documents
2. Filter by topic when needed
3. Return relevant information with source citations

## Troubleshooting

### "No module named 'mcp'"

Install the MCP SDK:
```bash
pip install mcp
```

### "No documents found"

Make sure you've run the ingestion script:
```bash
python ingest_pdfs.py --pdf-dir ./pdfs
```

### MCP server not appearing in Claude

1. Check that the path in `claude_desktop_config.json` is correct
2. Make sure you restarted Claude Desktop
3. Check Claude Desktop logs for errors

### Slow embedding generation

The first time you run the system, it will download the embedding model (~80MB). Subsequent runs will be much faster.

## Advanced Usage

### Reset the vector database

```bash
python ingest_pdfs.py --pdf-dir ./pdfs --reset
```

### Adjust chunk size

Edit `config.py` and modify:
```python
CHUNK_SIZE = 1000  # Increase for larger chunks
CHUNK_OVERLAP = 200  # Increase for more context
```

### Use a different embedding model

Edit `config.py`:
```python
EMBEDDING_MODEL = "all-mpnet-base-v2"  # More accurate but slower
```

## What's Next?

- Add more PDFs to expand your knowledge base
- Experiment with different search queries
- Check the main README.md for more detailed information

Happy querying! 🚀
