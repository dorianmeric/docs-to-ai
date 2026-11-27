"""
MCP Tools Module - Tool definitions for the MCP server.

This module contains all the tool function definitions that are exposed
via the MCP protocol.
"""

from .logging_utils import log_error, log_info, log_warn
import base64
import contextvars
import hashlib
import mimetypes
import os
import threading
import time
import sys
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.errors import explain, format_message, friendly_errors
from app.log_config import log_detail, truncate
from app.vector_store import VectorStore
from app.config import (
    DOCS_DIR as CONFIGURED_DOCS_DIR,
    DEFAULT_SEARCH_RESULTS,
    MAX_SEARCH_RESULTS,
    CHROMA_SPACE,
    CHROMA_COLLECTION_NAME,
    LOG_CHUNK_TEXT_CHARS,
    SLOW_QUERY_MS,
    TOPIC_SEPARATOR,
    FULL_SCAN_ON_BOOT,
    FOLDER_WATCHER_ACTIVE_ON_BOOT
)
from app.folder_watcher import (
    start_watching_folder as start_folder_watcher,
    stop_watching_folder as stop_folder_watcher,
    get_last_scan_time,
    trigger_full_scan_if_needed,
    is_watching
)
from app.incremental_updater import process_incremental_changes
from app.scan_all_my_documents import scan_all
from app.scan_scheduler import is_scan_in_progress


# The tools must use the same folder the rest of the app uses, including a
# DOCS_DIR override from the environment, .env, or the Docker compose file.
DOCS_DIR = str(CONFIGURED_DOCS_DIR)


# Per-call context (start time, how many tool calls run at once) so search_documents
# can report the total response time and spot a saturated server.
_tool_context: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "tool_context", default=None
)
_in_flight = 0
_in_flight_peak = 0
_in_flight_lock = threading.Lock()


def logged_tool(func):
    """Record every tool call in server.log and detail.jsonl, with its duration."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        global _in_flight, _in_flight_peak

        with _in_flight_lock:
            _in_flight += 1
            _in_flight_peak = max(_in_flight_peak, _in_flight)
            in_flight = _in_flight

        started = time.perf_counter()
        token = _tool_context.set({'started': started, 'in_flight': in_flight})
        call_args = {name: value for name, value in zip(func.__code__.co_varnames, args)}
        call_args.update(kwargs)

        def duration_ms() -> float:
            return round((time.perf_counter() - started) * 1000, 2)

        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            log_detail("tool_call", tool=func.__name__, args=call_args, ok=False,
                       error=f"{type(exc).__name__}: {exc}", duration_ms=duration_ms(),
                       concurrent_tool_calls=in_flight, peak_concurrent_tool_calls=_in_flight_peak)
            raise
        finally:
            _tool_context.reset(token)
            with _in_flight_lock:
                _in_flight -= 1

        text = str(result)
        log_info(f"Tool {func.__name__} finished in {duration_ms()} ms", component="MCP")
        log_detail("tool_call", tool=func.__name__, args=call_args, ok=True,
                   duration_ms=duration_ms(), result_chars=len(text),
                   concurrent_tool_calls=in_flight, peak_concurrent_tool_calls=_in_flight_peak)
        return result

    return wrapper


def _chunk_record(rank: int, result: Dict[str, Any]) -> Dict[str, Any]:
    """One returned chunk as it goes into the detail log."""
    metadata = result.get('metadata', {})
    text = result.get('text', '')
    return {
        'rank': rank,
        'chunk_id': result.get('id'),
        'file': metadata.get('filename'),
        'path': metadata.get('filepath'),
        'page': metadata.get('page'),
        'topics': metadata.get('topics'),
        'chunk_index': metadata.get('chunk_index'),
        'cosine_distance': result.get('distance'),
        'rrf_score': result.get('rrf_score'),
        'rerank_score': result.get('relevance_score'),
        'chars': len(text),
        'text': truncate(text, LOG_CHUNK_TEXT_CHARS),
    }


def _format_file_size(size_in_bytes: int) -> str:
    """Helper to format file size."""
    if size_in_bytes > 1024 * 1024:
        return f"{size_in_bytes / (1024*1024):.1f} MB"
    elif size_in_bytes > 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    else:
        return f"{size_in_bytes} bytes"


def _format_timestamp(timestamp: float) -> str:
    """Helper to format timestamp."""
    if timestamp:
        return time.ctime(timestamp)
    return "Unknown"


@friendly_errors
@logged_tool
def search_documents(
    query: str,
    max_results: int = DEFAULT_SEARCH_RESULTS,
    topic: Optional[str] = None,
    phrase_search: bool = False,
    date_from: Optional[float] = None,
    date_to: Optional[float] = None,
    regex_pattern: Optional[str] = None
) -> str:
    """Search across all documents using semantic similarity.

    Returns the most relevant text chunks with their source information and hierarchical topics.
    Optionally filter by topic, date range, or regex pattern.

    Args:
        query: The search query to find relevant document chunks
        max_results: Maximum number of results to return
        topic: Optional: Filter results to documents that have this topic
        phrase_search: If True, search for exact phrase match
        date_from: Optional: Filter to documents modified after this timestamp
        date_to: Optional: Filter to documents modified before this timestamp
        regex_pattern: Optional: Filter results by regex pattern in text content
    """
    tool_context = _tool_context.get() or {}
    tool_started = tool_context.get('started', time.perf_counter())
    concurrent = tool_context.get('in_flight')

    prep_started = time.perf_counter()
    vector_store = VectorStore()
    index_size = vector_store.collection.count()
    prep_ms = round((time.perf_counter() - prep_started) * 1000, 2)

    trace: Dict[str, Any] = {
        'query': query,
        'query_chars': len(query),
        'topic': topic,
        'max_results': max_results,
        'phrase_search': phrase_search,
        'date_from': date_from,
        'date_to': date_to,
        'regex_pattern': regex_pattern,
        'index_size': index_size,
        'prep_ms': prep_ms,
        'concurrent_tool_calls': concurrent,
    }

    step_order = (
        'prep_ms', 'encode_ms', 'chroma_ms', 'bm25_build_ms', 'bm25_ms', 'fuse_ms',
        'dense_ms', 'filters_ms', 'rerank_ms', 'format_ms',
    )

    def log_search(outcome: str, results: list) -> None:
        trace['outcome'] = outcome
        trace['results'] = [_chunk_record(rank, item) for rank, item in enumerate(results, 1)]
        trace['search_ms'] = trace.get('total_ms')
        trace['response_ms'] = round((time.perf_counter() - tool_started) * 1000, 2)
        trace['steps'] = [
            {'step': name[:-3], 'ms': trace[name]} for name in step_order if name in trace
        ]

        log_detail("search", **trace)

        breakdown = " | ".join(f"{item['step']} {item['ms']:.0f}" for item in trace['steps'])
        summary = (
            f"Search '{query[:60]}' -> {outcome}, {len(results)} chunk(s) in "
            f"{trace['response_ms']:.0f} ms ({breakdown})"
        )
        if concurrent and concurrent > 1:
            summary += f" [{concurrent} tool calls in flight]"

        if trace['response_ms'] > SLOW_QUERY_MS:
            log_warn(summary + " - over SLOW_QUERY_MS", component="MCP")
        else:
            log_info(summary, component="MCP")

    if index_size == 0:
        log_search("empty_index", [])
        return format_message(
            f"The index is empty, so '{query}' could not match anything.",
            cause="No documents have been indexed yet, or the last scan failed.",
            fix="Run the 'scan_all_my_documents' tool, or run "
                "'python -m app.scan_all_my_documents --doc-dir ./my-docs' on the server machine.",
        )

    max_results = min(max(1, max_results), MAX_SEARCH_RESULTS)
    trace['max_results'] = max_results

    search_limit = max_results * 3 if topic or phrase_search or regex_pattern else max_results
    results = vector_store.search(
        query, 
        n_results=search_limit,
        phrase_search=phrase_search,
        date_from=date_from,
        date_to=date_to,
        regex_pattern=regex_pattern,
        trace=trace,
    )

    if topic:
        filtered_results = []
        for r in results:
            doc_topics = r['metadata'].get('topics', [])
            if isinstance(doc_topics, str):
                doc_topics = [doc_topics]
            if topic in doc_topics:
                filtered_results.append(r)
        results = filtered_results[:max_results]
        trace['after_topic_filter'] = len(results)

    if not results:
        log_search("no_results", [])
        filter_msg = f" with topic '{topic}'" if topic else ""
        return format_message(
            f"No results found for query: '{query}'{filter_msg}.",
            cause="The words do not appear in the indexed chunks, or a filter removed every match.",
            fix="Try fewer or different words. Call 'list_topics' to check the topic filter. Drop the date, "
                "phrase, or regex filter to widen the search.",
        )

    format_started = time.perf_counter()

    filter_parts = []
    if topic:
        filter_parts.append(f"topic: '{topic}'")
    if phrase_search:
        filter_parts.append("phrase match")
    if date_from or date_to:
        filter_parts.append("date filter")
    if regex_pattern:
        filter_parts.append("regex filter")
    
    filter_info = f" ({', '.join(filter_parts)})" if filter_parts else ""
    response_parts = [f"Found {len(results)} relevant chunks for query: '{query}'{filter_info}\n"]

    for i, result in enumerate(results, 1):
        metadata = result['metadata']
        filename = metadata.get('filename', 'Unknown')
        page = metadata.get('page', 'Unknown')
        topics = metadata.get('topics', ['uncategorized'])
        filetype = metadata.get('filetype', '.pdf')

        if isinstance(topics, str):
            topics = [topics]

        topics_display = TOPIC_SEPARATOR.join(topics)

        response_parts.append(f"\n--- Result {i} ---")
        response_parts.append(f"Topics: {topics_display}")
        response_parts.append(f"Source: {filename} ({filetype}) [Page {page}]")

        # ChromaDB returns 1 - cosine similarity only in cosine space
        distance = result.get('distance')
        if distance is not None:
            if CHROMA_SPACE == 'cosine':
                relevance = max(0.0, min(100.0, (1.0 - distance) * 100))
                response_parts.append(f"Relevance: {relevance:.1f}%")
            else:
                response_parts.append(f"Distance ({CHROMA_SPACE}): {distance:.4f}")

        response_parts.append(f"\nContent:\n{result['text']}")

    response_parts.append(
        "\nTip: call 'get_document' with one of these file names to read that document in full, "
        "or 'get_document_file' to get the original file."
    )
    response = "\n".join(response_parts)
    trace['format_ms'] = round((time.perf_counter() - format_started) * 1000, 2)
    log_search("ok", results)
    return response


@friendly_errors
@logged_tool
def list_documents(topic: Optional[str] = None) -> str:
    """Get a list of all available documents with their hierarchical topics.

    Args:
        topic: Optional: Filter to show only documents that have this topic
    """
    vector_store = VectorStore()
    documents = vector_store.list_documents()

    if topic:
        filtered_docs = []
        for doc in documents:
            doc_topics = doc.get('topics', [])
            if isinstance(doc_topics, str):
                doc_topics = [doc_topics]
            if topic in doc_topics:
                filtered_docs.append(doc)
        documents = filtered_docs

    if not documents:
        filter_msg = f" with topic '{topic}'" if topic else ""
        return format_message(
            f"No documents found{filter_msg}.",
            cause="Nothing is indexed yet, or the topic filter matches no folder.",
            fix="Run the 'scan_all_my_documents' tool, or drop the topic filter. Call 'list_topics' to see "
                "the indexed topics.",
        )

    docs_by_first_topic = {}
    for doc in documents:
        topics = doc.get('topics', ['uncategorized'])
        if isinstance(topics, str):
            topics = [topics]
        first_topic = topics[0] if topics else 'uncategorized'

        if first_topic not in docs_by_first_topic:
            docs_by_first_topic[first_topic] = []
        docs_by_first_topic[first_topic].append(doc)

    response_parts = []
    filter_info = f" (filtered to topic: '{topic}')" if topic else ""
    response_parts.append(f"Available documents{filter_info}: {len(documents)} total\n")

    for first_topic in sorted(docs_by_first_topic.keys()):
        topic_docs = docs_by_first_topic[first_topic]
        response_parts.append(f"\n{first_topic} ({len(topic_docs)} documents)")
        for doc in topic_docs:
            topics = doc.get('topics', ['uncategorized'])
            if isinstance(topics, str):
                topics = [topics]
            topics_display = TOPIC_SEPARATOR.join(topics)
            filetype = doc.get('filetype', '.pdf')

            size_str = _format_file_size(doc.get('file_size', 0))
            mod_time = _format_timestamp(doc.get('last_modified', 0))

            response_parts.append(f"  • {doc['filename']} ({filetype}) - Size: {size_str}, Modified: {mod_time}")
            response_parts.append(f"    Topics: {topics_display}")

    return "\n".join(response_parts)


# Base64 inflates a file by a third and every MCP client caps a tool response, so
# the file tool starts well below the client limits and the caller can raise it.
DEFAULT_MAX_FILE_BYTES = 1_000_000


def _human_size(size_bytes: int) -> str:
    if size_bytes > 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes > 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} bytes"


def _iso_time(timestamp: float) -> str:
    if not timestamp:
        return "unknown"
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def _normalise(text: str) -> str:
    return str(text).replace('\\', '/').strip().lower()


def _match_document(document: str, documents: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Find one indexed document by path, filename, or a part of either.

    Returns ``(match, candidates)``. ``match`` is None when the request is
    ambiguous; ``candidates`` then holds the options to choose from.
    """
    needle = _normalise(document)
    if not needle:
        return None, []

    def names(doc: Dict[str, Any]) -> List[str]:
        filename = str(doc.get('filename', ''))
        path = _normalise(doc.get('filepath', ''))
        stem = filename.rsplit('.', 1)[0] if '.' in filename else filename
        return [_normalise(filename), _normalise(stem), path]

    # exact path, then exact filename, then filename without extension
    for level in range(3):
        hits = [doc for doc in documents if names(doc)[level] == needle]
        if len(hits) == 1:
            return hits[0], []
        if len(hits) > 1:
            return None, hits

    # path suffix ("legal docs/contract.docx"), then substring of filename or path
    suffix_hits = [doc for doc in documents if _normalise(doc.get('filepath', '')).endswith(needle)]
    if len(suffix_hits) == 1:
        return suffix_hits[0], []
    if len(suffix_hits) > 1:
        return None, suffix_hits

    partial = [doc for doc in documents
               if any(needle in name for name in (names(doc)[0], names(doc)[2]))]
    if len(partial) == 1:
        return partial[0], []
    return None, partial


def _document_chunks(vector_store, filepath: str) -> List[Dict[str, Any]]:
    """All indexed chunks of one document, ordered by page and chunk index."""
    try:
        result = vector_store.collection.get(
            where={"filepath": filepath}, include=["documents", "metadatas"]
        )
    except Exception:
        return []

    chunks = []
    for index, chunk_id in enumerate(result.get('ids') or []):
        metadata = (result.get('metadatas') or [])[index] or {}
        chunks.append({
            'id': chunk_id,
            'text': (result.get('documents') or [])[index] or '',
            'page': metadata.get('page', 1),
            'chunk_index': metadata.get('chunk_index', 0),
            'is_ocr': bool(metadata.get('is_ocr')),
            'metadata': metadata,
        })
    chunks.sort(key=lambda item: (item['page'], item['chunk_index']))
    return chunks


def _document_pages(vector_store, doc: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    """Full text of a document as pages, plus where the text came from."""
    filepath = doc.get('filepath', '')
    path = Path(filepath)

    # Why the text below does not come from the file on disk
    fallback_reason = 'source file missing'
    if filepath and path.is_file():
        from app.document_processor import DocumentProcessor
        try:
            pages = DocumentProcessor().extract_text_from_document(str(path), DOCS_DIR)
            if pages:
                return pages, 'source file'
            fallback_reason = "source file produced no text"
        except Exception as exc:
            # A broken or unsupported file must not hide the text that is indexed
            log_warn(f"Could not re-read {path.name} for get_document: {exc}", component="MCP")
            fallback_reason = f"source file could not be read ({type(exc).__name__})"

    # Source file gone or unreadable: rebuild the text from the stored chunks
    chunks = _document_chunks(vector_store, filepath)
    pages_map: Dict[int, List[str]] = {}
    for chunk in chunks:
        pages_map.setdefault(chunk['page'], []).append(chunk['text'])
    ocr_pages = {chunk['page'] for chunk in chunks if chunk['is_ocr']}
    pages = [
        {
            'page': page,
            'text': "\n".join(texts),
            'total_pages': len(pages_map),
            'ocr': page in ocr_pages,
        }
        for page, texts in sorted(pages_map.items())
    ]
    return pages, f"indexed chunks ({fallback_reason})"


def _document_overview(vector_store, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Metadata block shared by the document tools."""
    filepath = doc.get('filepath', '')
    path = Path(filepath)
    chunks = _document_chunks(vector_store, filepath)
    pages = sorted({chunk['page'] for chunk in chunks})
    on_disk = path.is_file()
    stat = path.stat() if on_disk else None
    size_now = stat.st_size if stat else None
    modified_now = stat.st_mtime if stat else None
    created_now = stat.st_ctime if stat else None
    indexed_size = doc.get('file_size')
    indexed_modified = doc.get('last_modified')

    if not on_disk:
        state = 'missing on disk'
    elif size_now == indexed_size and modified_now == indexed_modified:
        state = 'unchanged since the last scan'
    else:
        state = 'changed on disk since the last scan, re-scan to refresh the chunks'

    return {
        'filename': doc.get('filename'),
        'filepath': filepath,
        'topics': doc.get('topics', []),
        'filetype': doc.get('filetype'),
        'size_bytes': indexed_size,
        'size_human': _human_size(indexed_size or 0),
        'last_modified': _iso_time(indexed_modified or 0),
        'last_modified_epoch': indexed_modified,
        'current_size_bytes': size_now,
        'current_last_modified': _iso_time(modified_now or 0),
        'created': _iso_time(created_now or 0),
        # st_ctime is the creation time on Windows and the inode change time elsewhere
        'created_kind': 'created' if os.name == 'nt' else 'inode changed',
        'total_pages': next((chunk['metadata'].get('total_pages') for chunk in chunks
                             if chunk['metadata'].get('total_pages')), None),
        'on_disk': on_disk,
        'index_state': state,
        'chunk_count': len(chunks),
        'pages_with_chunks': pages,
        'ocr_pages': sorted({chunk['page'] for chunk in chunks if chunk['metadata'].get('is_ocr')}),
        'collection': CHROMA_COLLECTION_NAME,
    }


def _resolve_document(vector_store, document: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Find the one document the caller means, or the text that explains why not."""
    documents = vector_store.list_documents()
    if not documents:
        return None, format_message(
            "No documents are indexed yet.",
            cause="Nothing has been scanned into the vector store.",
            fix="Run the 'scan_all_my_documents' tool first.",
        )

    match, candidates = _match_document(document, documents)
    if match is not None:
        return match, None

    if candidates:
        lines = [f"More than one document matches '{document}'. "
                 "Call the tool again with the full name or path:"]
        for item in candidates[:20]:
            lines.append(f"- {item['filename']}  ({TOPIC_SEPARATOR.join(item.get('topics') or [])})")
            lines.append(f"  {item['filepath']}")
        return None, "\n".join(lines)

    return None, format_message(
        f"No indexed document matches '{document}'.",
        cause="The name is different, or the document was never scanned.",
        fix="Call 'list_documents' and copy a filename from there, then run this tool again.",
    )


def _page_list(pages: List[int]) -> str:
    """'1-61' or '1-3, 7, 9-12' for a sorted page list."""
    if not pages:
        return 'none'
    parts = []
    start = previous = pages[0]
    for page in pages[1:]:
        if page == previous + 1:
            previous = page
            continue
        parts.append(f"{start}-{previous}" if start != previous else f"{start}")
        start = previous = page
    parts.append(f"{start}-{previous}" if start != previous else f"{start}")
    return ", ".join(parts)


def _overview_text(overview: Dict[str, Any]) -> List[str]:
    lines = [f"Document: {overview['filename']}"]
    lines.append(f"Path: {overview['filepath']}")
    lines.append(f"Topics: {TOPIC_SEPARATOR.join(overview['topics']) if overview['topics'] else 'uncategorized'}")
    lines.append(f"Type: {overview['filetype']}")
    if overview['size_human'] == f"{overview['size_bytes']} bytes":
        lines.append(f"Size: {overview['size_bytes']} bytes")
    else:
        lines.append(f"Size: {overview['size_human']} ({overview['size_bytes']} bytes)")
    lines.append(f"Last modified: {overview['last_modified']} (epoch {overview['last_modified_epoch']})")
    if overview['total_pages'] and overview['total_pages'] > 0:
        lines.append(f"Pages in the document: {overview['total_pages']}")
    lines.append(f"Chunks in index: {overview['chunk_count']} on page(s) "
                 f"{_page_list(overview['pages_with_chunks'])}")
    if overview['ocr_pages']:
        lines.append(f"OCR pages: {_page_list(overview['ocr_pages'])} (text came from OCR)")
    lines.append(f"Source state: {overview['index_state']}")
    if overview['on_disk']:
        lines.append(f"File on disk now: {_human_size(overview['current_size_bytes'] or 0)}, "
                     f"modified {overview['current_last_modified']}, "
                     f"{overview['created_kind']} {overview['created']}")
    lines.append(f"Collection: {overview['collection']}")
    return lines


@friendly_errors
@logged_tool
def get_document_metadata(document: str) -> str:
    """Return the metadata of one indexed document: dates, size, topics, chunk count.

    Args:
        document: Filename, path, or part of either, as returned by list_documents
    """
    vector_store = VectorStore()
    match, problem = _resolve_document(vector_store, document)
    if problem:
        return problem

    return "\n".join(_overview_text(_document_overview(vector_store, match)))


@friendly_errors
@logged_tool
def get_document(document: str, page: Optional[int] = None, max_chars: int = 0) -> str:
    """Return one document in full, with its metadata.

    Args:
        document: Filename, path, or part of either, as returned by list_documents
        page: Optional: return only this page (1-based)
        max_chars: Optional: cut the text after this many characters (0 = no limit)
    """
    vector_store = VectorStore()
    match, problem = _resolve_document(vector_store, document)
    if problem:
        return problem

    overview = _document_overview(vector_store, match)
    pages, source = _document_pages(vector_store, match)

    if page is not None:
        pages = [item for item in pages if item['page'] == page]
        if not pages:
            return format_message(
                f"Page {page} does not exist in '{match['filename']}'.",
                cause="The page number is outside the document.",
                fix=f"Valid pages: {_page_list(overview['pages_with_chunks'])}. Call the tool again "
                    "without the page argument to get everything.",
            )

    body_parts = []
    for item in pages:
        # The extractor sets 'ocr'; pages read from the document cache carry it
        # on their metadata instead
        is_ocr = item.get('ocr') or (item.get('metadata') or {}).get('is_ocr')
        marker = " (OCR)" if is_ocr else ""
        body_parts.append(f"--- Page {item['page']}{marker} ---\n{item['text']}")
    body = "\n\n".join(body_parts)

    total_chars = len(body)
    if max_chars and total_chars > max_chars:
        body = body[:max_chars] + f"\n...[{total_chars - max_chars} chars cut, call again with max_chars=0 for all]"

    lines = _overview_text(overview)
    lines.append(f"Text source: {source}")
    lines.append(f"Characters returned: {len(body)} of {total_chars}")
    lines.append("")
    lines.append("--- Text ---")
    lines.append(body)
    return "\n".join(lines)


@friendly_errors
@logged_tool
def get_document_file(document: str, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> str:
    """Return the original document file as base64, with its metadata.

    Args:
        document: Filename, path, or part of either, as returned by list_documents
        max_bytes: Refuse files larger than this (default 1 MB, raise it to get a bigger file)
    """
    vector_store = VectorStore()
    match, problem = _resolve_document(vector_store, document)
    if problem:
        return problem

    path = Path(match.get('filepath', ''))
    if not path.is_file():
        return format_message(
            f"The file for '{match['filename']}' is not on disk any more.",
            cause="The document was moved or deleted after it was indexed.",
            fix="Restore the file next to the mounted documents folder and re-scan, or use 'get_document' "
                "to read the text that is still indexed.",
        )

    size = path.stat().st_size
    if size > max_bytes:
        return format_message(
            f"'{match['filename']}' is {_human_size(size)}, above the {_human_size(max_bytes)} limit.",
            cause="Large binary files are not returned in one tool response by default.",
            fix=f"Call the tool again with max_bytes={size} to get the whole file, or use 'get_document' "
                "to read the extracted text instead.",
        )

    data = path.read_bytes()
    mime, _ = mimetypes.guess_type(path.name)
    overview = _document_overview(vector_store, match)

    lines = _overview_text(overview)
    lines.append(f"MIME type: {mime or 'application/octet-stream'}")
    lines.append(f"Bytes: {size}")
    lines.append(f"SHA-256: {hashlib.sha256(data).hexdigest()}")
    lines.append(f"Encoding: base64 (about {int(size * 4 / 3)} characters)")
    lines.append("")
    lines.append("--- Base64 ---")
    lines.append(base64.b64encode(data).decode('ascii'))
    return "\n".join(lines)


@friendly_errors
@logged_tool
def list_topics() -> str:
    """Get a list of all topics/categories in the document collection."""
    vector_store = VectorStore()
    topics = vector_store.list_topics()

    if not topics:
        return format_message(
            "No topics found.",
            cause="Nothing is indexed yet, or USE_FOLDER_AS_TOPIC is off and every document uses the "
                  "default topic.",
            fix="Run the 'scan_all_my_documents' tool. Put documents in subfolders to get one topic per folder.",
        )

    stats = vector_store.get_stats()
    topic_counts = stats['documents_per_topic']

    response = f"Available topics ({len(topics)}):\n\n"
    response += "Topics are hierarchical - each folder in the path becomes a topic.\n"
    response += "Documents can have multiple topics based on their folder location.\n\n"

    for topic in topics:
        count = topic_counts.get(topic, 0)
        response += f"  {topic}: {count} document{'s' if count != 1 else ''}\n"

    return response


@friendly_errors
@logged_tool
def get_collection_stats() -> str:
    """Get statistics about the document collection."""
    vector_store = VectorStore()
    stats = vector_store.get_stats()

    response = "Document Collection Statistics:\n\n"
    response += f"Total chunks: {stats['total_chunks']}\n"
    response += f"Total documents: {stats['total_documents']}\n"
    response += f"Total topics: {stats['total_topics']}\n"
    response += f"Collection: {stats['collection_name']}\n"
    response += f"Embedding model: {stats.get('embedding_model', 'unknown')} "
    response += f"({stats.get('embedding_dimension', 'unknown')}-dim, {stats.get('distance_space', 'l2')})\n"
    retrieval = "hybrid (BM25 + dense, RRF)" if stats.get('hybrid_search') else "dense only"
    response += f"Retrieval: {retrieval}\n"
    if stats.get('reranker'):
        response += f"Re-ranker: {stats['reranker']}\n"
    response += "\n"

    if 'documents_per_filetype' in stats and stats['documents_per_filetype']:
        response += "Documents per file type:\n"
        for filetype in sorted(stats['documents_per_filetype'].keys()):
            count = stats['documents_per_filetype'][filetype]
            response += f"  {filetype}: {count} document{'s' if count != 1 else ''}\n"
        response += "\n"

    if stats['topics']:
        response += "Documents per topic (hierarchical):\n"
        for topic in sorted(stats['topics']):
            count = stats['documents_per_topic'].get(topic, 0)
            response += f"  {topic}: {count} document{'s' if count != 1 else ''}\n"

    if stats['documents']:
        response += "\nFile Size Information:\n"
        total_size = sum(doc.get('file_size', 0) for doc in stats['documents'])
        size_str = _format_file_size(total_size)
        response += f"  Total size of all documents: {size_str}\n"

        sorted_docs = sorted(stats['documents'], key=lambda x: x.get('file_size', 0), reverse=True)
        response += "\nLargest documents:\n"
        for doc in sorted_docs[:5]:
            size_str = _format_file_size(doc.get('file_size', 0))
            mod_time = _format_timestamp(doc.get('last_modified', 0))
            response += f"  {doc['filename']}: {size_str}, Modified: {mod_time}\n"

    return response


@friendly_errors
@logged_tool
def scan_all_my_documents() -> str:
    """Scan all documents in the docs directory and update the vector database."""
    # A second scan would reset the index while the first one is still writing
    if is_scan_in_progress():
        return format_message(
            "A scan is already running, so this request was not started.",
            cause="The startup scan or a previous request is still indexing documents.",
            fix="Wait for the running scan to finish (the container log shows progress), then ask again.",
        )

    try:
        result = scan_all(DOCS_DIR)

        if isinstance(result, list) and result:
            return "\n".join(item.text for item in result if hasattr(item, 'text'))
        return str(result)
    except Exception as e:
        return explain(e, context="scan_all_my_documents")


@friendly_errors
@logged_tool
def start_watching_folder() -> str:
    """Start watching the documents folder for changes and automatically trigger incremental updates."""
    try:
        def scan_callback(changes, incremental):
            try:
                if incremental and changes:
                    return process_incremental_changes(changes, DOCS_DIR)
                else:
                    return scan_all(DOCS_DIR)
            except Exception as e:
                log_error(f"Scan failed: {e}", component="MCP")
                return explain(e, context="folder watcher scan")

        result = start_folder_watcher(scan_callback, do_initial_scan=True)

        if result['status'] == 'started':
            response_parts = []
            response_parts.append("Folder watcher started successfully\n")
            response_parts.append(f"Watching: {result['watch_path']}")
            response_parts.append(f"Debounce: {result['debounce_seconds']} seconds")
            response_parts.append(f"Full scan interval: {result['full_scan_interval_days']} days")
            response_parts.append("Mode: Incremental updates enabled")

            if 'scan_result' in result and result['scan_result']:
                response_parts.append("\n" + "="*60)
                response_parts.append("INITIAL SCAN RESULTS:")
                response_parts.append("="*60)
                response_parts.append(result['scan_result'])

            return "\n".join(response_parts)
        elif result['status'] == 'already_watching':
            auto_start_msg = " (auto-started on boot)" if FOLDER_WATCHER_ACTIVE_ON_BOOT else ""
            return f"Folder watcher is already active{auto_start_msg}\n\nWatching: {result['watch_path']}"
        else:
            return format_message(
                f"The folder watcher could not start for '{DOCS_DIR}'.",
                cause=result.get('message', "The folder is missing, unreadable, or the watcher failed to start."),
                fix="Check DOCS_DIR. Create the folder and give the server read access. Then call "
                    "'start_watching_folder' again.",
            )
    except Exception as e:
        return explain(e, context="start_watching_folder")


@friendly_errors
@logged_tool
def stop_watching_folder() -> str:
    """Stop watching the folder for changes."""
    try:
        result = stop_folder_watcher()

        if result['status'] == 'stopped':
            return "Folder watcher stopped successfully"
        elif result['status'] == 'not_watching':
            return "Folder watcher is not currently active"
        else:
            return format_message(
                "The folder watcher could not be stopped.",
                cause=result.get('message', "The watcher was in an unexpected state."),
                fix="Restart the server. If the message repeats, report it with the text above.",
            )
    except Exception as e:
        return explain(e, context="stop_watching_folder")


@friendly_errors
@logged_tool
def get_time_of_last_folder_scan() -> str:
    """Get the timestamp of when the last folder scan was started and finished."""
    try:
        result = get_last_scan_time()

        if result["status"] == "success":
            response_parts = ["Last Folder Scan Information:\n"]
            response_parts.append(f"Started:  {result['scan_start_time_formatted']}")

            if 'scan_end_time_formatted' in result:
                response_parts.append(f"Finished: {result['scan_end_time_formatted']}")
                response_parts.append(f"Duration: {result['duration_seconds']} seconds")
            else:
                response_parts.append("Status: Scan in progress...")

            if 'last_full_scan_time_formatted' in result:
                response_parts.append(f"\nLast Full Scan: {result['last_full_scan_time_formatted']}")
                days_since = int(result['days_since_full_scan'])
                response_parts.append(f"Days since full scan: {days_since}")
                if result.get('next_full_scan_due'):
                    response_parts.append("Next full scan: DUE NOW")
                else:
                    days_remaining = 7 - days_since
                    response_parts.append(f"Next full scan in: {days_remaining} days")

            return "\n".join(response_parts)
        elif result["status"] == "not_watching":
            return "Folder watcher is not currently active"
        elif result["status"] == "no_scans_yet":
            return "Folder watcher is active but no scans have been triggered yet"
        else:
            return format_message(
                "The last scan status could not be read.",
                cause=result.get('message', "The watcher is in an unexpected state."),
                fix="Start the watcher with 'start_watching_folder', then ask again.",
            )
    except Exception as e:
        return explain(e, context="get_time_of_last_folder_scan")
