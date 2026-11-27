from pathlib import Path
import os


def _unquote(value: str) -> str:
    """Strip surrounding quotes while keeping the inner value verbatim."""
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in ('"', "'"):
        return stripped[1:-1]
    return stripped


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable (accepts true/1/yes/on)."""
    value = os.getenv(name)
    if value is None:
        return default
    return _unquote(value).lower() in ('true', '1', 'yes', 'on')


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back to the default."""
    value = os.getenv(name)
    if value is None or not _unquote(value):
        return default
    try:
        return int(_unquote(value))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable, falling back to the default."""
    value = os.getenv(name)
    if value is None or not _unquote(value):
        return default
    try:
        return float(_unquote(value))
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    """Read a string environment variable, falling back to the default.

    Quoted values keep their inner whitespace, so ``TOPIC_SEPARATOR=" > "``
    stays ``" > "`` instead of collapsing to ``">"``.
    """
    value = os.getenv(name)
    if value is None:
        return default
    unquoted = _unquote(value)
    return unquoted if unquoted.strip() else default


# Paths
BASE_DIR = Path(__file__).parent.parent


def _load_dotenv(path: Path) -> None:
    """Load a local .env file without adding a dependency.

    Real environment variables always win, so values injected by Docker, CI,
    or the shell are never overridden by a local .env file.
    """
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, raw_value = line.partition('=')
        key = key.strip()
        value = _parse_dotenv_value(raw_value)
        if key and key not in os.environ:
            os.environ[key] = value


def _parse_dotenv_value(raw_value: str) -> str:
    """Extract a .env value, allowing quoted values and trailing ``#`` comments.

    ``CHUNK_SIZE=512   # tokens per chunk`` therefore yields ``512``, and
    ``TOPIC_SEPARATOR=" > "`` keeps its spaces.
    """
    value = raw_value.strip()
    if value[:1] in ('"', "'"):
        quote = value[0]
        end = value.find(quote, 1)
        if end != -1:
            inner = value[1:end]
            # Keep the quotes only when whitespace matters (e.g. " > "), so
            # plain values like "stdio" still reach os.environ unquoted.
            return value[:end + 1] if inner != inner.strip() else inner

    # Inline comments must be preceded by whitespace, so values may contain '#'
    for marker in (' #', '\t#'):
        index = value.find(marker)
        if index != -1:
            value = value[:index]

    return value.strip()


_load_dotenv(BASE_DIR / '.env')
CHROMADB_DIR = BASE_DIR / "cache/chromadb"
DOC_CACHE_DIR = BASE_DIR / "cache/doc_cache"
DOCS_DIR = Path(_unquote(os.getenv('DOCS_DIR', str(BASE_DIR / "my-docs")))) # Default documents directory

CHROMADB_DIR.mkdir(exist_ok=True, parents=True)
DOC_CACHE_DIR.mkdir(exist_ok=True, parents=True)
DOCS_DIR.mkdir(exist_ok=True, parents=True)

# Document Processing Configuration
SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.doc', '.md', '.xlsx', '.xls', '.xlsam', '.xlsb', '.pptx', '.html', '.htm', '.txt', '.csv']  # Supported document types

# Embedding Configuration
EMBEDDING_MODEL = _env_str('EMBEDDING_MODEL', "Qwen/Qwen3-Embedding-0.6B")  # sentence-transformers model
EMBEDDING_DIMENSION = _env_int('EMBEDDING_DIMENSION', 1024)  # Dimension for Qwen3-Embedding-0.6B
EMBEDDING_BATCH_SIZE = _env_int('EMBEDDING_BATCH_SIZE', 32)  # Texts per encode() batch
# Instruction prepended to queries. Empty = use the model's built-in 'query'
# prompt when it ships one (Qwen3-Embedding does), otherwise no prompt.
EMBEDDING_QUERY_PROMPT = _env_str('EMBEDDING_QUERY_PROMPT', '')

# Chunking Configuration
# Strategies: 'fixed_size', 'by_paragraph', 'semantic_heading', 'by_token', or 'semantic'
CHUNKING_STRATEGY = _env_str('CHUNKING_STRATEGY', 'semantic').lower()
# Size settings below are characters, or tokens when CHUNK_BY_TOKEN=True.
CHUNK_SIZE = _env_int('CHUNK_SIZE', 1024)  # Target chunk size (1024 tokens by default)
CHUNK_OVERLAP = _env_int('CHUNK_OVERLAP', 200)  # Overlap between chunks
CHUNK_BY_TOKEN = _env_bool('CHUNK_BY_TOKEN', True)  # Use token-based chunking
TOKENIZER_MODEL = _env_str('TOKENIZER_MODEL', 'cl100k_base')  # tiktoken tokenizer (cl100k_base for GPT-4/3.5, p50k_base for GPT-2)
PRESERVE_HEADINGS = _env_bool('PRESERVE_HEADINGS', True)  # Preserve heading structure in chunks
MAX_HEADING_CHUNK_SIZE = _env_int('MAX_HEADING_CHUNK_SIZE', 1024)  # Max size per heading-based chunk
MIN_CHUNK_SIZE = _env_int('MIN_CHUNK_SIZE', 50)  # Minimum chunk size to avoid tiny chunks

# Semantic Chunking Configuration (CHUNKING_STRATEGY='semantic')
# Splits text where the embedding similarity between consecutive sentences drops
# below a percentile threshold, producing topically coherent chunks.
# Sizes are always measured in tokens (approximated with the tiktoken tokenizer).
SEMANTIC_CHUNK_PERCENTILE = _env_int('SEMANTIC_CHUNK_PERCENTILE', 95)  # Similarity percentile used as the split threshold (0-100)
SEMANTIC_CHUNK_MIN_SIZE = _env_int('SEMANTIC_CHUNK_MIN_SIZE', 64)  # Minimum tokens per semantic chunk
SEMANTIC_CHUNK_MAX_SIZE = _env_int('SEMANTIC_CHUNK_MAX_SIZE', 1024)  # Maximum tokens per semantic chunk (hard split above this)
SEMANTIC_CHUNK_BUFFER_SIZE = _env_int('SEMANTIC_CHUNK_BUFFER_SIZE', 1)  # Neighbouring sentences combined when computing similarity

# Search Configuration
DEFAULT_SEARCH_RESULTS: int = _env_int('DEFAULT_SEARCH_RESULTS', 10)
MAX_SEARCH_RESULTS: int = _env_int('MAX_SEARCH_RESULTS', 20)
USE_RERANKER = _env_bool('USE_RERANKER', True)
RERANKER_MODEL = _env_str('RERANKER_MODEL', 'cross-encoder/ms-marco-MiniLM-L-6-v2')
RERANKER_TOP_N = _env_int('RERANKER_TOP_N', 50)
USE_BM25 = _env_bool('USE_BM25', True)  # Enable hybrid search (BM25 + dense, fused with RRF)
BM25_WEIGHT = _env_float('BM25_WEIGHT', 0.3)  # RRF weight for the BM25 list (0-1; 0.5 = equal weight)
BM25_K1 = _env_float('BM25_K1', 1.5)  # BM25 term-frequency saturation
BM25_B = _env_float('BM25_B', 0.75)  # BM25 length normalisation (0-1)
RRF_K = _env_int('RRF_K', 60)  # Reciprocal Rank Fusion constant (60 is the paper default)


# Topic/Folder Configuration
USE_FOLDER_AS_TOPIC = _env_bool('USE_FOLDER_AS_TOPIC', True)  # Use folder hierarchy as topic tags
DEFAULT_TOPIC = _env_str('DEFAULT_TOPIC', "uncategorized")  # Default topic if no folder structure
TOPIC_SEPARATOR = _env_str('TOPIC_SEPARATOR', " > ")  # Separator for hierarchical topics in display

# chromadb Configuration
CHROMA_COLLECTION_NAME = _env_str('CHROMA_COLLECTION_NAME', "my-documents")  # you can rename this collection
# HNSW index tuning. 'cosine' is the right space for normalized text embeddings;
# 'l2' (the ChromaDB default) is a poor fit. Higher ef_search = better recall.
CHROMA_SPACE = _env_str('CHROMA_SPACE', 'cosine').lower()  # cosine | l2 | ip
HNSW_EF_SEARCH = _env_int('HNSW_EF_SEARCH', 200)  # Query-time candidate list size (ChromaDB default is 100)
HNSW_EF_CONSTRUCTION = _env_int('HNSW_EF_CONSTRUCTION', 200)  # Build-time candidate list size

# MCP Server Startup Configuration
# Controls whether a full scan should be performed when the MCP server starts
FULL_SCAN_ON_BOOT = _env_bool('FULL_SCAN_ON_BOOT', False)

# Controls whether the folder watcher should be activated when the MCP server starts
FOLDER_WATCHER_ACTIVE_ON_BOOT = _env_bool('FOLDER_WATCHER_ACTIVE_ON_BOOT', True)

# Folder Watcher Configuration
DEBOUNCE_SECONDS = _env_int('DEBOUNCE_SECONDS', 10)  # Delay after last change before processing
FULL_SCAN_INTERVAL_DAYS = _env_int('FULL_SCAN_INTERVAL_DAYS', 7)  # Days between full scans

# MCP Server Transport Configuration
# Controls the transport method for MCP server: 'stdio' for local connections, 'websocket' for network connections
MCP_TRANSPORT = _env_str('MCP_TRANSPORT', 'stdio').lower()

# Host to bind to when using websocket/SSE transport
MCP_HOST = _env_str('MCP_HOST', '0.0.0.0')

# Port to bind to when using websocket/SSE transport
MCP_PORT = _env_int('MCP_PORT', 38777)

