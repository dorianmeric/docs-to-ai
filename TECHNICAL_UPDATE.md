# Technical Update Summary

## Changes Made

### 1. Hierarchical Topics Support

**Old Behavior:**
- Single topic per document from parent folder name
- Example: `pdfs/Machine_Learning/doc.pdf` → Topic: "Machine_Learning"

**New Behavior:**
- Multiple topics per document from full folder hierarchy
- Example: `docs/Nova_Deal/Legal_Docs/Loan_Agreement/contract.pdf`
  → Topics: ["Nova_Deal", "Legal_Docs", "Loan_Agreement"]

**Implementation:**
- `extract_topics_from_path()` in `document_processor.py` now extracts all folder names from base to document
- Metadata field changed from `topic` (string) to `topics` (list)
- All database queries updated to check if topic exists in topics list

### 2. Word Document Support

**Supported Formats:**
- PDF (.pdf) - using PyMuPDF
- Word (.docx, .doc) - using python-docx

**Implementation:**
- New `extract_text_from_docx()` method in `document_processor.py`
- Groups paragraphs into "pages" (10 paragraphs per page)
- Metadata includes `filetype` field
- Same chunking and embedding process as PDFs

### 3. File Renames and Refactoring

**Renamed Files:**
- `pdf_processor.py` → `document_processor.py`
- `PDFProcessor` class → `DocumentProcessor` class
- `ingest_pdfs.py` → `ingest_documents.py`
- `pdf_cache/` → `doc_cache/`

**Config Changes:**
- Added `SUPPORTED_EXTENSIONS` = ['.pdf', '.docx', '.doc']
- Added `TOPIC_SEPARATOR` = " > " for display
- Changed `PDF_CACHE_DIR` → `DOC_CACHE_DIR`
- Changed collection name to "documents"

### 4. Database Schema Updates

**Metadata Structure:**
```python
{
    'filename': str,           # e.g., "contract.pdf"
    'filepath': str,           # Full path
    'topics': List[str],       # e.g., ["Nova_Deal", "Legal_Docs", "Loan_Agreement"]
    'filetype': str,           # e.g., ".pdf" or ".docx"
    'page': int,               # Page number
    'total_pages': int,        # Total pages (or -1 for Word)
    'chunk_start': int,        # Chunk position
    'chunk_end': int           # Chunk end position
}
```

**Backward Compatibility:**
- Code handles old single-topic format (string)
- Converts to list format when encountered

### 5. MCP Server Updates

**Tool Changes:**

**search_documents:**
- Filters by checking if topic exists in `topics` list
- Displays all topics in results with TOPIC_SEPARATOR
- Shows filetype in source info

**list_documents:**
- Groups by first topic for display
- Shows full topic hierarchy for each document
- Displays filetype for each document

**list_topics:**
- Returns flattened list of all unique topics
- Notes that topics are hierarchical

**get_document_stats:**
- Added `documents_per_filetype` statistics
- Topic counts now reflect that documents can have multiple topics

### 6. Dependencies Added

```
python-docx>=1.1.0
```

## Testing Updates

- `test_system.py` updated to use `DocumentProcessor`
- Tests now work with both PDFs and Word documents
- Topic display shows hierarchical structure

## Usage Changes

**Old Command:**
```bash
python ingest_pdfs.py --pdf-dir ./pdfs
```

**New Command:**
```bash
python ingest_documents.py --doc-dir ./docs
```

**Folder Structure Example:**
```
docs/
├── Nova_Deal/
│   ├── Legal_Docs/
│   │   ├── Loan_Agreement/
│   │   │   ├── contract.pdf
│   │   │   └── terms.docx
│   │   └── Insurance/
│   │       └── policy.pdf
│   └── Financial/
│       └── projections.xlsx  (not supported yet)
└── Other_Project/
    └── notes.docx
```

**Topic Extraction:**
- `contract.pdf` → ["Nova_Deal", "Legal_Docs", "Loan_Agreement"]
- `policy.pdf` → ["Nova_Deal", "Legal_Docs", "Insurance"]
- `notes.docx` → ["Other_Project"]

## Key Functions Modified

### document_processor.py
- `extract_topics_from_path()` - Returns List[str] instead of str
- `extract_text_from_docx()` - NEW: Handles Word documents
- `extract_text_from_document()` - Routes to PDF or Word extractor
- Chunk IDs now include all topics for uniqueness

### vector_store.py
- `list_documents()` - Returns documents with `topics` list
- `list_topics()` - Flattens all topic lists
- `get_stats()` - Counts by filetype and handles multi-topic docs
- `delete_topic()` - Checks if topic in topics list

### ingest_documents.py
- Finds all supported file types
- Shows detected topics from hierarchy
- Statistics per topic and filetype

### mcp_server.py
- Topic filtering checks topics list
- Displays hierarchical topics with separator
- Shows filetype in results

## Breaking Changes

1. **Metadata field renamed:**
   - Old: `metadata['topic']` (string)
   - New: `metadata['topics']` (list)

2. **Ingestion script renamed:**
   - Old: `ingest_pdfs.py --pdf-dir`
   - New: `ingest_documents.py --doc-dir`

3. **Cache directory renamed:**
   - Old: `pdf_cache/`
   - New: `doc_cache/`

4. **Topic filtering logic:**
   - Old: `topic == filter`
   - New: `filter in topics`

## Migration Notes

- Existing vector stores will continue to work
- Old single-topic metadata is auto-converted to list format
- Re-ingestion recommended to get hierarchical topics
- Use `--reset` flag to clear old data

## Files Not Modified

Documentation files (*.md) were intentionally not updated per user request.
