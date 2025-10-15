# Documentation Index

Welcome to the PDF Document Query System with Topic-Based Organization! This index helps you find the right documentation for your needs.

## Quick Links

- 🚀 **[QUICKSTART.md](QUICKSTART.md)** - Get started in 5 minutes
- 📖 **[README.md](README.md)** - Complete system documentation
- 📚 **[TOPICS.md](TOPICS.md)** - Topic-based organization guide
- 💡 **[EXAMPLE.md](EXAMPLE.md)** - Complete usage example
- 🔄 **[UPDATE_SUMMARY.md](UPDATE_SUMMARY.md)** - What's new in this version

## For New Users

Start here if this is your first time:

1. **[QUICKSTART.md](QUICKSTART.md)** - Installation and basic setup
2. **[EXAMPLE.md](EXAMPLE.md)** - See a complete worked example
3. **[README.md](README.md)** - Learn about all features

## Documentation by Topic

### Getting Started
- **[QUICKSTART.md](QUICKSTART.md)** - Installation, setup, first steps
- **[README.md](README.md)** - Overview, architecture, installation

### Topic Organization
- **[TOPICS.md](TOPICS.md)** - Everything about organizing PDFs by topic
  - How topic extraction works
  - Folder naming best practices
  - Topic filtering and search
  - Use cases and examples

### Usage Examples
- **[EXAMPLE.md](EXAMPLE.md)** - Complete walkthrough
  - Setting up folders
  - Ingesting PDFs
  - Querying with Claude
  - Real conversation examples

### Updates and Changes
- **[UPDATE_SUMMARY.md](UPDATE_SUMMARY.md)** - What changed in this version
  - New features
  - Modified files
  - Migration guide
  - Breaking changes

## File Reference

### Core Python Files

| File | Purpose |
|------|---------|
| `mcp_server.py` | MCP server that Claude connects to |
| `pdf_processor.py` | PDF text extraction and chunking |
| `vector_store.py` | ChromaDB vector database operations |
| `config.py` | Configuration settings |
| `ingest_pdfs.py` | Batch PDF ingestion script |
| `setup.py` | Initial setup and verification |
| `test_system.py` | Test suite |

### Configuration Files

| File | Purpose |
|------|---------|
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variables template |
| `claude_desktop_config.example.json` | Claude Desktop configuration |
| `config.py` | System configuration |

### Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | Main documentation |
| `QUICKSTART.md` | Quick start guide |
| `TOPICS.md` | Topic organization guide |
| `EXAMPLE.md` | Complete usage example |
| `UPDATE_SUMMARY.md` | Update notes |
| `INDEX.md` | This file |
| `LICENSE` | MIT license |

## Common Tasks

### I want to...

**...get started quickly**
→ Read [QUICKSTART.md](QUICKSTART.md)

**...understand the topic system**
→ Read [TOPICS.md](TOPICS.md)

**...see a complete example**
→ Read [EXAMPLE.md](EXAMPLE.md)

**...configure the system**
→ Edit `config.py` and see [README.md](README.md#configuration)

**...understand what changed**
→ Read [UPDATE_SUMMARY.md](UPDATE_SUMMARY.md)

**...troubleshoot issues**
→ See [QUICKSTART.md](QUICKSTART.md#troubleshooting) or [README.md](README.md#troubleshooting)

**...add custom features**
→ Study the core Python files and [TOPICS.md](TOPICS.md#advanced-custom-topic-logic)

## MCP Tools Reference

Quick reference for the tools Claude can use:

### search_documents
Search PDFs with optional topic filter
```json
{
  "query": "neural networks",
  "topic": "Machine_Learning",  // optional
  "max_results": 5
}
```

### list_documents
List all documents, optionally by topic
```json
{
  "topic": "Python_Programming"  // optional
}
```

### list_topics
Get all available topics
```json
{}
```

### get_document_stats
Get collection statistics
```json
{}
```

## Architecture Overview

```
PDFs (organized by topic folders)
  ↓
pdf_processor.py (extract text + detect topics)
  ↓
vector_store.py (generate embeddings + store in ChromaDB)
  ↓
mcp_server.py (expose MCP tools)
  ↓
Claude Desktop (query and search)
```

## System Requirements

- Python 3.8+
- ~500MB disk space (for models and database)
- ChromaDB for vector storage
- sentence-transformers for embeddings
- PyMuPDF for PDF processing

## Support Resources

### Documentation
- All markdown files in this directory
- Inline code comments
- Example configurations

### Testing
- Run `python test_system.py` to verify setup
- Check logs for debugging
- Use example PDFs to test functionality

### Community
- Check GitHub issues (if applicable)
- Review example use cases in [EXAMPLE.md](EXAMPLE.md)
- Study topic organization in [TOPICS.md](TOPICS.md)

## Quick Command Reference

```bash
# Setup
pip install -r requirements.txt
python setup.py

# Ingest PDFs
python ingest_pdfs.py --pdf-dir ./pdfs

# Test system
python test_system.py

# Reset and re-ingest
python ingest_pdfs.py --pdf-dir ./pdfs --reset
```

## Version Information

- **Current Version**: Topic-Based Organization (2025-10-15)
- **Previous Version**: Single flat document list
- **License**: MIT

## Contributing

To modify or extend the system:

1. Study the core files (especially `pdf_processor.py` and `vector_store.py`)
2. Review [TOPICS.md](TOPICS.md) for topic system details
3. Test changes with `test_system.py`
4. Update documentation as needed

## Next Steps

1. **New users**: Start with [QUICKSTART.md](QUICKSTART.md)
2. **Returning users**: Check [UPDATE_SUMMARY.md](UPDATE_SUMMARY.md)
3. **Power users**: Read [TOPICS.md](TOPICS.md) for advanced features
4. **Developers**: Study the Python files and architecture

---

**Happy document querying! 🚀📚**

For questions or issues, refer to the troubleshooting sections in [QUICKSTART.md](QUICKSTART.md#troubleshooting) and [README.md](README.md).
