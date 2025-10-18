from pathlib import Path
import os

# Paths
BASE_DIR = Path(__file__).parent.parent
CHROMADB_DIR = BASE_DIR / "cache/chromadb"
DOC_CACHE_DIR = BASE_DIR / "cache/doc_cache"
DOCS_DIR = os.getenv('DOCS_DIR', BASE_DIR / "my-docs" ) # Default documents directory

CHROMADB_DIR.mkdir(exist_ok=True, parents=True)
DOC_CACHE_DIR.mkdir(exist_ok=True, parents=True)
DOCS_DIR.mkdir(exist_ok=True, parents=True)

# Document Processing Configuration
SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.doc', '.md', '.xlsx', '.xls', '.xlsam', '.xlsb']  # Supported document types

# Embedding Configuration
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # sentence-transformers model
EMBEDDING_DIMENSION = 384  # Dimension for all-MiniLM-L6-v2

# Chunking Configuration
CHUNK_SIZE = 1000  # Characters per chunk
CHUNK_OVERLAP = 200  # Overlap between chunks

# Search Configuration
DEFAULT_SEARCH_RESULTS = os.getenv('DEFAULT_SEARCH_RESULTS', 10 )
MAX_SEARCH_RESULTS = os.getenv('MAX_SEARCH_RESULTS', 20 )

# Topic/Folder Configuration
USE_FOLDER_AS_TOPIC = True  # Use folder hierarchy as topic tags
DEFAULT_TOPIC = os.getenv('DEFAULT_TOPIC', "uncategorized" ) # Default topic if no folder structure
TOPIC_SEPARATOR = " > "  # Separator for hierarchical topics in display

# chromadb Configuration
CHROMA_COLLECTION_NAME =  os.getenv('CHROMA_COLLECTION_NAME', "my-documents" )# you can rename this collection

# MCP Server Startup Configuration
# Controls whether a full scan should be performed when the MCP server starts
FULL_SCAN_ON_BOOT = os.getenv('FULL_SCAN_ON_BOOT', 'True').lower() in ('true', '1', 'yes', 'on')

# Controls whether the folder watcher should be activated when the MCP server starts
FOLDER_WATCHER_ACTIVE_ON_BOOT = os.getenv('FOLDER_WATCHER_ACTIVE_ON_BOOT', 'True').lower() in ('true', '1', 'yes', 'on')

