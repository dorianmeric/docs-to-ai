# Quick Reference - Updated System

## What Changed

### 1. Hierarchical Topics
Documents now get ALL folder names as topics:
```
docs/Project_A/Legal/Contracts/file.pdf
→ Topics: ["Project_A", "Legal", "Contracts"]
```

### 2. Word Document Support
Now processes:
- ✅ PDF files (.pdf)
- ✅ Word files (.docx, .doc)

### 3. New File Names
- `document_processor.py` (was: pdf_processor.py)
- `ingest_documents.py` (was: ingest_pdfs.py)
- `doc_cache/` (was: pdf_cache/)

## Quick Start

### Install
```bash
pip install -r requirements.txt
python setup.py
```

### Organize Documents
```
docs/
├── Deal_Name/
│   ├── Legal_Documents/
│   │   ├── contract.pdf
│   │   └── agreement.docx
│   └── Financial/
│       └── report.pdf
```

### Ingest
```bash
python ingest_documents.py --doc-dir ./docs
```

### Use with Claude
Claude can now:
- Search by any topic in the hierarchy
- Find PDFs and Word docs
- See full topic path for each result

## Topic Examples

**Document:** `docs/Nova_Deal/Legal_Docs/Loan_Agreement/contract.pdf`
**Topics:** `["Nova_Deal", "Legal_Docs", "Loan_Agreement"]`

**Searchable by:**
- "Nova_Deal"
- "Legal_Docs"  
- "Loan_Agreement"

## MCP Tools

### search_documents
```python
{
  "query": "payment terms",
  "topic": "Legal_Docs",  # Finds all docs with this topic
  "max_results": 5
}
```

### list_documents
Shows all docs with their full topic hierarchy

### list_topics
Shows all unique topics (flattened from all hierarchies)

### get_document_stats
Shows counts by topic and file type

## Migration from Old System

If you have existing data:

1. **Keep old system:**
   - Old files still work
   - `pdf_processor.py` and `ingest_pdfs.py` still present

2. **Use new system:**
   - Organize docs in topic folders
   - Run: `python ingest_documents.py --doc-dir ./docs --reset`

## Key Differences

| Old | New |
|-----|-----|
| Single topic per doc | Multiple topics per doc |
| Parent folder only | Full folder hierarchy |
| PDFs only | PDFs + Word docs |
| `topic` (string) | `topics` (list) |
| `ingest_pdfs.py` | `ingest_documents.py` |

## Example Queries for Claude

**General:**
- "What documents do you have?"
- "List all topics"

**Topic-specific:**
- "Find contract terms in Legal_Docs"
- "Show all documents about Nova_Deal"
- "Search for payment clauses in Loan_Agreement"

**Multi-topic:**
- "Compare Legal_Docs across different deals"
- "Find all Financial documents"

## Supported File Types

- `.pdf` - Full support
- `.docx` - Full support  
- `.doc` - Full support

## Notes

- Each folder level becomes a separate topic
- Documents can be found by ANY topic in their path
- Word docs are chunked by paragraphs
- All processing is same as PDFs after text extraction
