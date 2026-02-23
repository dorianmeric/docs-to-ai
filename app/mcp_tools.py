"""
MCP Tools Module - Tool definitions for the MCP server.

This module contains all the tool function definitions that are exposed
via the MCP protocol.
"""

import time
import sys
from typing import Optional

from app.vector_store import VectorStore
from app.config import (
    DEFAULT_SEARCH_RESULTS,
    MAX_SEARCH_RESULTS,
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


DOCS_DIR = "/app/my-docs"


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
    vector_store = VectorStore()

    max_results = min(max(1, max_results), MAX_SEARCH_RESULTS)

    search_limit = max_results * 3 if topic or phrase_search or regex_pattern else max_results
    results = vector_store.search(
        query, 
        n_results=search_limit,
        phrase_search=phrase_search,
        date_from=date_from,
        date_to=date_to,
        regex_pattern=regex_pattern
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

    if not results:
        filter_msg = f" with topic '{topic}'" if topic else ""
        return f"No results found for query: '{query}'{filter_msg}"

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

        if result.get('distance') is not None:
            relevance = max(0, 100 - (result['distance'] * 100))
            response_parts.append(f"Relevance: {relevance:.1f}%")

        response_parts.append(f"\nContent:\n{result['text']}")

    return "\n".join(response_parts)


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
        return f"No documents found{filter_msg}. Use 'python -m app.scan_all_my_documents' to add documents."

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


def list_topics() -> str:
    """Get a list of all topics/categories in the document collection."""
    vector_store = VectorStore()
    topics = vector_store.list_topics()

    if not topics:
        return "No topics found. Use scan_all_my_documents.py to add documents."

    stats = vector_store.get_stats()
    topic_counts = stats['documents_per_topic']

    response = f"Available topics ({len(topics)}):\n\n"
    response += "Topics are hierarchical - each folder in the path becomes a topic.\n"
    response += "Documents can have multiple topics based on their folder location.\n\n"

    for topic in topics:
        count = topic_counts.get(topic, 0)
        response += f"  {topic}: {count} document{'s' if count != 1 else ''}\n"

    return response


def get_collection_stats() -> str:
    """Get statistics about the document collection."""
    vector_store = VectorStore()
    stats = vector_store.get_stats()

    response = "Document Collection Statistics:\n\n"
    response += f"Total chunks: {stats['total_chunks']}\n"
    response += f"Total documents: {stats['total_documents']}\n"
    response += f"Total topics: {stats['total_topics']}\n"
    response += f"Collection: {stats['collection_name']}\n\n"

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


def scan_all_my_documents() -> str:
    """Scan all documents in the docs directory and update the vector database."""
    try:
        result = scan_all(DOCS_DIR)

        if isinstance(result, list) and result:
            return "\n".join(item.text for item in result if hasattr(item, 'text'))
        return str(result)
    except Exception as e:
        return f"Error scanning documents: {str(e)}"


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
                print(f"[MCP] Error during scan: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc()
                return f"Error during scan: {str(e)}"

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
            return f"Failed to start folder watcher\n\nError: {result.get('message', 'Unknown error')}"
    except Exception as e:
        return f"Error starting folder watcher: {str(e)}"


def stop_watching_folder() -> str:
    """Stop watching the folder for changes."""
    try:
        result = stop_folder_watcher()

        if result['status'] == 'stopped':
            return "Folder watcher stopped successfully"
        elif result['status'] == 'not_watching':
            return "Folder watcher is not currently active"
        else:
            return f"Error stopping folder watcher: {result.get('message', 'Unknown error')}"
    except Exception as e:
        return f"Error stopping folder watcher: {str(e)}"


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
            return f"Error: {result.get('message', 'Unknown error')}"
    except Exception as e:
        return f"Error getting last scan time: {str(e)}"
