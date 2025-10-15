import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
CHROMA_DB_DIR = BASE_DIR / "chroma_db"
PDF_CACHE_DIR = BASE_DIR / "pdf_cache"

# Embedding Configuration
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # sentence-transformers model
EMBEDDING_DIMENSION = 384  # Dimension for all-MiniLM-L6-v2

# Chunking Configuration
CHUNK_SIZE = 1000  # Characters per chunk
CHUNK_OVERLAP = 200  # Overlap between chunks

# Search Configuration
DEFAULT_SEARCH_RESULTS = 5
MAX_SEARCH_RESULTS = 20

# ChromaDB Configuration
CHROMA_COLLECTION_NAME = "pdf_documents"

# Create necessary directories
CHROMA_DB_DIR.mkdir(exist_ok=True)
PDF_CACHE_DIR.mkdir(exist_ok=True)
