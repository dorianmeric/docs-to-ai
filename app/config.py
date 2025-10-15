from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.parent
CHROMA_DB_DIR = BASE_DIR / "chroma_db"
DOC_CACHE_DIR = BASE_DIR / "doc_cache"

# Embedding Configuration
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # sentence-transformers model
EMBEDDING_DIMENSION = 384  # Dimension for all-MiniLM-L6-v2

# Chunking Configuration
CHUNK_SIZE = 1000  # Characters per chunk
CHUNK_OVERLAP = 200  # Overlap between chunks

# Search Configuration
DEFAULT_SEARCH_RESULTS = 5
MAX_SEARCH_RESULTS = 20

# Topic/Folder Configuration
USE_FOLDER_AS_TOPIC = True  # Use folder hierarchy as topic tags
DEFAULT_TOPIC = "uncategorized"  # Default topic if no folder structure
TOPIC_SEPARATOR = " > "  # Separator for hierarchical topics in display

# Document Processing Configuration
SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.doc', '.md']  # Supported document types

# ChromaDB Configuration
CHROMA_COLLECTION_NAME = "my-documents" # you can rename this collection

# Create necessary directories
CHROMA_DB_DIR.mkdir(exist_ok=True)
DOC_CACHE_DIR.mkdir(exist_ok=True)

