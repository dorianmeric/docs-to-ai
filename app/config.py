from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.parent
CHROMA_DB_DIR = BASE_DIR / "cache/chromadb"
DOC_CACHE_DIR = BASE_DIR / "cache/doc_cache"
DOCS_DIR = BASE_DIR / "my-docs" # Default documents directory

CHROMA_DB_DIR.mkdir(exist_ok=True, parents=True)
DOC_CACHE_DIR.mkdir(exist_ok=True, parents=True)
DOCS_DIR.mkdir(exist_ok=True, parents=True)


# Embedding Configuration
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # sentence-transformers model
EMBEDDING_DIMENSION = 384  # Dimension for all-MiniLM-L6-v2

# Chunking Configuration
CHUNK_SIZE = 1000  # Characters per chunk
CHUNK_OVERLAP = 200  # Overlap between chunks

# Search Configuration
DEFAULT_SEARCH_RESULTS = 10
MAX_SEARCH_RESULTS = 20

# Topic/Folder Configuration
USE_FOLDER_AS_TOPIC = True  # Use folder hierarchy as topic tags
DEFAULT_TOPIC = "uncategorized"  # Default topic if no folder structure
TOPIC_SEPARATOR = " > "  # Separator for hierarchical topics in display

# Document Processing Configuration
SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.doc', '.md', '.xlsx', '.xls', '.xlsam', '.xlsb']  # Supported document types

# ChromaDB Configuration
CHROMA_COLLECTION_NAME = "my-documents" # you can rename this collection

