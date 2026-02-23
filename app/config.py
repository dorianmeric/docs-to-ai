from pathlib import Path
import os

# Paths
BASE_DIR = Path(__file__).parent.parent
CHROMADB_DIR = BASE_DIR / "cache/chromadb"
DOC_CACHE_DIR = BASE_DIR / "cache/doc_cache"
DOCS_DIR = Path(os.getenv('DOCS_DIR', BASE_DIR / "my-docs")) # Default documents directory

CHROMADB_DIR.mkdir(exist_ok=True, parents=True)
DOC_CACHE_DIR.mkdir(exist_ok=True, parents=True)
DOCS_DIR.mkdir(exist_ok=True, parents=True)

# Document Processing Configuration
SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.doc', '.md', '.xlsx', '.xls', '.xlsam', '.xlsb', '.pptx', '.html', '.htm', '.txt', '.csv']  # Supported document types

# Embedding Configuration
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # sentence-transformers model
EMBEDDING_DIMENSION = 384  # Dimension for all-MiniLM-L6-v2

# Chunking Configuration
CHUNKING_STRATEGY = os.getenv('CHUNKING_STRATEGY', 'by_paragraph').lower() # 'fixed_size', 'by_paragraph', 'semantic_heading', or 'by_token'
CHUNK_SIZE = 1000  # Characters per chunk (or tokens if CHUNKING_STRATEGY='by_token')
CHUNK_OVERLAP = 200  # Overlap between chunks
CHUNK_BY_TOKEN = os.getenv('CHUNK_BY_TOKEN', 'False').lower() in ('true', '1', 'yes', 'on')  # Use token-based chunking
TOKENIZER_MODEL = os.getenv('TOKENIZER_MODEL', 'cl100k_base')  # tiktoken tokenizer (cl100k_base for GPT-4/3.5, p50k_base for GPT-2)
PRESERVE_HEADINGS = os.getenv('PRESERVE_HEADINGS', 'True').lower() in ('true', '1', 'yes', 'on')  # Preserve heading structure in chunks
MAX_HEADING_CHUNK_SIZE = int(os.getenv('MAX_HEADING_CHUNK_SIZE', '2000'))  # Max chars per heading-based chunk
MIN_CHUNK_SIZE = 50  # Minimum chunk size to avoid tiny chunks

# Search Configuration
DEFAULT_SEARCH_RESULTS: int = int(os.getenv('DEFAULT_SEARCH_RESULTS', '10'))
MAX_SEARCH_RESULTS: int = int(os.getenv('MAX_SEARCH_RESULTS', '20'))
USE_RERANKER = os.getenv('USE_RERANKER', 'True').lower() in ('true', '1', 'yes', 'on')
RERANKER_MODEL = os.getenv('RERANKER_MODEL', 'cross-encoder/ms-marco-MiniLM-L-6-v2')
RERANKER_TOP_N = int(os.getenv('RERANKER_TOP_N', '50'))
USE_BM25 = os.getenv('USE_BM25', 'False').lower() in ('true', '1', 'yes', 'on')  # Enable hybrid search with BM25
BM25_WEIGHT = float(os.getenv('BM25_WEIGHT', '0.3'))  # Weight for BM25 in hybrid search (0-1)


# Topic/Folder Configuration
USE_FOLDER_AS_TOPIC = True  # Use folder hierarchy as topic tags
DEFAULT_TOPIC = os.getenv('DEFAULT_TOPIC', "uncategorized" ) # Default topic if no folder structure
TOPIC_SEPARATOR = " > "  # Separator for hierarchical topics in display

# chromadb Configuration
CHROMA_COLLECTION_NAME =  os.getenv('CHROMA_COLLECTION_NAME', "my-documents" )# you can rename this collection

# MCP Server Startup Configuration
# Controls whether a full scan should be performed when the MCP server starts
FULL_SCAN_ON_BOOT = os.getenv('FULL_SCAN_ON_BOOT', 'False').lower() in ('true', '1', 'yes', 'on')

# Controls whether the folder watcher should be activated when the MCP server starts
FOLDER_WATCHER_ACTIVE_ON_BOOT = os.getenv('FOLDER_WATCHER_ACTIVE_ON_BOOT', 'True').lower() in ('true', '1', 'yes', 'on')

# Folder Watcher Configuration
DEBOUNCE_SECONDS = int(os.getenv('DEBOUNCE_SECONDS', '10'))  # Delay after last change before processing
FULL_SCAN_INTERVAL_DAYS = int(os.getenv('FULL_SCAN_INTERVAL_DAYS', '7'))  # Days between full scans

# MCP Server Transport Configuration
# Controls the transport method for MCP server: 'stdio' for local connections, 'websocket' for network connections
MCP_TRANSPORT = os.getenv('MCP_TRANSPORT', 'stdio').lower()

# Host to bind to when using websocket/SSE transport
MCP_HOST = os.getenv('MCP_HOST', '0.0.0.0')

# Port to bind to when using websocket/SSE transport
MCP_PORT = int(os.getenv('MCP_PORT', '38777'))

