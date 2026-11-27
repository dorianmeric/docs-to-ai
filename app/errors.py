"""
User-facing error messages.

Every message this module produces has two parts: a plain-English explanation of
what happened, and a suggestion on how to fix it. Raw exception text is kept as
a separate ``Details`` line, so users see the actionable part first.

Use :func:`explain` at the edges of the app: MCP tool return values, CLI output,
and startup failures. Use :class:`DocsToAIError` when you already know the cause
and the fix.
"""

from .logging_utils import log_error
import errno
import functools
from typing import Optional

TROUBLESHOOTING = "See 'Troubleshooting: error messages' in README.md."


class DocsToAIError(Exception):
    """An error that carries a plain-English explanation and a suggested fix."""

    def __init__(self, problem: str, cause: Optional[str] = None,
                 fix: Optional[str] = None, details: Optional[str] = None):
        self.problem = problem
        self.cause = cause
        self.fix = fix
        self.details = details
        super().__init__(self.message())

    def message(self) -> str:
        return format_message(self.problem, self.cause, self.fix, self.details)


def format_message(problem: str, cause: Optional[str] = None,
                   fix: Optional[str] = None,
                   details: Optional[str] = None) -> str:
    """Build a consistent 'Problem / Cause / Fix / Details' message."""
    lines = [f"Problem: {problem}"]
    if cause:
        lines.append(f"Cause: {cause}")
    if fix:
        lines.append(f"Fix: {fix}")
    if details:
        lines.append(f"Details: {details}")
    return "\n".join(lines)


def document_error(path: object, exc: BaseException, kind: str = "file") -> "DocsToAIError":
    """Build a friendly error for a document that could not be read."""
    name = _class_name(exc)
    text = _text(exc)
    shown = getattr(path, 'name', path)

    if isinstance(exc, FileNotFoundError):
        return DocsToAIError(
            problem=f"The {kind} '{shown}' was not found.",
            cause="The file was moved or deleted between the folder listing and the read.",
            fix="Run the scan again. Check that DOCS_DIR points at the right folder.",
            details=f"{name}: {text}",
        )

    if isinstance(exc, PermissionError):
        return DocsToAIError(
            problem=f"The {kind} '{shown}' could not be opened because of file permissions.",
            cause="The user running the server cannot read this file.",
            fix="Grant read access to the file, or move it to a folder the server can read, then run the scan again.",
            details=f"{name}: {text}",
        )

    if kind.upper() == "PDF" and name in {"FileDataError", "EmptyFileError", "FileNotDecryptedError"}:
        cause = "The PDF is encrypted, damaged, or not a real PDF."
        fix = ("Open the PDF, remove the password, and re-save the PDF. Scanned PDFs need OCR before "
               "indexing. Then run the scan again.")
    else:
        cause = f"The {kind} is damaged, password protected, or uses a format the extractor does not support."
        fix = (f"Open the {kind} in its normal application and re-save it. Remove passwords. Then run the "
               "scan again.")

    return DocsToAIError(
        problem=f"The {kind} '{shown}' could not be read.",
        cause=cause,
        fix=fix,
        details=f"{name}: {text}",
    )


def format_inline(problem: str, fix: Optional[str] = None,
                  details: Optional[str] = None) -> str:
    """One-line variant for scan reports and log lines."""
    parts = [f"Problem: {problem}"]
    if fix:
        parts.append(f"Fix: {fix}")
    if details:
        parts.append(f"Details: {details}")
    return " | ".join(parts)


def _class_name(exc: BaseException) -> str:
    return type(exc).__name__


def _text(exc: BaseException) -> str:
    return str(exc).strip() or _class_name(exc)


def explain(exc: BaseException, context: Optional[str] = None) -> str:
    """Turn an exception into a message that says what happened and how to fix it."""
    if isinstance(exc, DocsToAIError):
        return exc.message()

    name = _class_name(exc)
    text = _text(exc)
    where = f" while running '{context}'" if context else ""

    if isinstance(exc, ModuleNotFoundError):
        missing = exc.name or "a required package"
        return format_message(
            f"A Python package needed for this step is missing{where}: {missing}.",
            cause="The environment does not match pyproject.toml.",
            fix="Run 'uv sync' in the project folder, then start the server again.",
            details=text,
        )

    if isinstance(exc, ImportError):
        return format_message(
            f"A Python package could not be imported{where}.",
            cause="The installed package version does not match what the code expects.",
            fix="Run 'uv sync' to reinstall the locked versions, then retry.",
            details=text,
        )

    if "OutOfMemoryError" in name or isinstance(exc, MemoryError):
        return format_message(
            f"The machine ran out of memory{where}.",
            cause="The embedding batch or the chunk size is too large for the available RAM or VRAM.",
            fix="Lower EMBEDDING_BATCH_SIZE (try 8 or 16). If a GPU ran out of memory, set GPU_DEVICE_INDEX "
                "to a card with more VRAM or USE_GPU_ACCELERATION_IF_AVAILABLE=False. Then retry.",
            details=text,
        )

    if isinstance(exc, PermissionError):
        return format_message(
            f"A file or folder could not be opened because of missing permissions{where}.",
            cause="The user running the server does not have read access to the documents, or write access "
                  "to the cache folder.",
            fix="Grant read access to the documents folder and write access to cache/chromadb and "
                "cache/doc_cache, or move the documents to a readable folder and set DOCS_DIR.",
            details=text,
        )

    if isinstance(exc, FileNotFoundError):
        return format_message(
            f"A file or folder was not found{where}.",
            cause="The path moved, was deleted, or DOCS_DIR points at the wrong folder.",
            fix="Check the path. Set DOCS_DIR to the folder that holds your documents, then run the scan again.",
            details=text,
        )

    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return format_message(
            f"The disk is full{where}.",
            cause="The vector database or the document cache cannot grow any further.",
            fix="Free disk space, or point the cache at another disk. Then run the scan again.",
            details=text,
        )

    if isinstance(exc, OSError) and exc.errno == errno.ELOOP:
        return format_message(
            f"A path could not be read because it loops{where}.",
            cause="A symbolic link in the documents folder points back at a parent folder.",
            fix="Remove the looping symlink, then run the scan again.",
            details=text,
        )

    if isinstance(exc, (ConnectionError, TimeoutError)) or name in {
        "ConnectError", "ReadTimeout", "ConnectTimeout", "HTTPError", "LocalEntryNotFoundError",
        "MaxRetryError", "NewConnectionError",
    }:
        return format_message(
            f"A network request failed{where}.",
            cause="Hugging Face or PyPI could not be reached. Model files were probably not downloaded yet.",
            fix="Connect to the internet and run 'python -m app.download_models' once. Offline machines can "
                "copy a warm ~/.cache/huggingface and TIKTOKEN_CACHE_DIR from another machine.",
            details=text,
        )

    lowered = text.lower()
    looks_like_dimension = (
        "invaliddimension" in lowered.replace(" ", "")
        or "dimensionmismatch" in lowered.replace(" ", "")
        or ("dimension" in lowered and ("does not match" in lowered or "invalid" in lowered))
    )

    if looks_like_dimension:
        return format_message(
            f"The vector database rejected the embeddings because the vector size does not match{where}.",
            cause="The index was built with a different embedding model, or EMBEDDING_DIMENSION is stale.",
            fix="Delete cache/chromadb (it is a cache) and re-scan: "
                "'python -m app.scan_all_my_documents --doc-dir ./my-docs --reset'.",
            details=text,
        )

    if "database is locked" in lowered or "unable to open database file" in lowered:
        return format_message(
            f"The vector database is locked or unreadable{where}.",
            cause="Another Docs-to-AI process or container is using cache/chromadb.",
            fix="Stop the other server (or 'docker compose down'), make sure the cache folder is writable, "
                "then start one server only.",
            details=text,
        )

    if "an instance of chroma already exists" in lowered:
        return format_message(
            f"ChromaDB was opened twice with different settings{where}.",
            cause="Two clients were created for the same database path in one process.",
            fix="Restart the server. If the error persists, delete cache/chromadb and re-scan.",
            details=text,
        )

    if name in {"FileDataError", "EmptyFileError", "FileNotDecryptedError", "PdfReadError"} \
            or "cannot open" in lowered and "pdf" in lowered:
        return format_message(
            f"The PDF could not be read{where}.",
            cause="The file is encrypted, truncated, or not a real PDF.",
            fix="Open the PDF in a reader. Remove the password or repair the file. Scanned PDFs also need OCR "
                "before indexing.",
            details=text,
        )

    if isinstance(exc, UnicodeDecodeError):
        return format_message(
            f"A text file could not be decoded{where}.",
            cause="The file is not UTF-8 and has no byte-order mark.",
            fix="Re-save the file as UTF-8, then run the scan again.",
            details=text,
        )

    if "tiktoken" in lowered or "tokenizer" in lowered:
        return format_message(
            f"The tokenizer could not be loaded{where}.",
            cause="tiktoken could not fetch its BPE data, usually because the machine is offline.",
            fix="Run 'python -m app.download_models' with network access, or set TIKTOKEN_CACHE_DIR to a "
                "pre-filled cache folder.",
            details=text,
        )

    return format_message(
        f"The step failed{where}.",
        cause=f"{name}: {text}",
        fix="Check 'python mcp_server.py --show-config' for unexpected settings, retry, and report the "
            f"message above if it repeats. {TROUBLESHOOTING}",
    )


def friendly_errors(func):
    """Wrap a tool or command so any exception becomes a plain-English message."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - user-facing boundary
            return explain(exc, context=func.__name__)

    return wrapper


def warn(exc: BaseException, context: Optional[str] = None) -> None:
    """Print a friendly message on stderr (used for non-fatal failures)."""
    log_error(explain(exc, context=context), component="Error")
