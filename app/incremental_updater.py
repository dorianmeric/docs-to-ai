"""
Incremental updater for processing individual file changes.
Handles add, update, and delete operations on specific files.
"""
from pathlib import Path
from typing import List, Tuple
from app.document_processor import DocumentProcessor
from app.vector_store import VectorStore
from app.config import TOPIC_SEPARATOR
from mcp.types import TextContent
import time
import sys


class IncrementalUpdater:
    """Handles incremental updates to the vector store.

    Note:
        Uses the singleton VectorStore instance, ensuring all incremental updates
        operate on the same vector database as full scans and searches.
    """

    def __init__(self):
        self.processor = DocumentProcessor()
        # Get the singleton VectorStore instance
        self.store = VectorStore()
        self.debug_messages = []
    
    def process_changes(self, changes: List[Tuple[str, str]], base_dir: str) -> dict:
        """
        Process a list of file changes incrementally.
        
        Args:
            changes: List of (action, filepath) tuples
                    action can be 'add', 'update', or 'delete'
            base_dir: Base directory for documents
        
        Returns:
            dict: Statistics about the update
        """
        base_path = Path(base_dir)
        
        stats = {
            'added': 0,
            'updated': 0,
            'deleted': 0,
            'failed': 0,
            'total_chunks_added': 0,
            'total_chunks_deleted': 0,
            'files_processed': []
        }
        
        for action, filepath in changes:
            file_path = Path(filepath)
            
            try:
                if action == 'delete':
                    # Delete from vector store
                    result = self._delete_file(file_path)
                    if result['success']:
                        stats['deleted'] += 1
                        stats['total_chunks_deleted'] += result['chunks_deleted']
                        stats['files_processed'].append({
                            'action': 'deleted',
                            'file': str(file_path),
                            'chunks': result['chunks_deleted']
                        })
                    else:
                        stats['failed'] += 1
                        
                elif action in ['add', 'update']:
                    # For updates, delete old version first
                    if action == 'update':
                        delete_result = self._delete_file(file_path)
                        stats['total_chunks_deleted'] += delete_result['chunks_deleted']
                    
                    # Add new/updated version
                    result = self._add_or_update_file(file_path, base_path)
                    if result['success']:
                        if action == 'add':
                            stats['added'] += 1
                        else:
                            stats['updated'] += 1
                        stats['total_chunks_added'] += result['chunks_added']
                        stats['files_processed'].append({
                            'action': action,
                            'file': str(file_path),
                            'chunks': result['chunks_added'],
                            'topics': result.get('topics', [])
                        })
                    else:
                        stats['failed'] += 1

            except Exception as e:
                self.debug_messages.append(f"  ✗ Error processing {action} for {file_path}: {e}")
                stats['failed'] += 1
                stats['files_processed'].append({
                    'action': f'{action}_failed',
                    'file': str(file_path),
                    'error': str(e)
                })
        
        return stats
    
    def _add_or_update_file(self, file_path: Path, base_path: Path) -> dict:
        """
        Add or update a single file in the vector store.
        
        Args:
            file_path: Path to the file
            base_path: Base directory for extracting topics
        
        Returns:
            dict: Result information
        """
        result = {
            'success': False,
            'chunks_added': 0,
            'topics': []
        }
        
        try:
            # Check if file exists
            if not file_path.exists():
                self.debug_messages.append(f"  ⚠ File no longer exists: {file_path}")
                return result

            # Extract topics for display
            topics = self.processor.extract_topics_from_path(file_path, base_path)
            topics_display = TOPIC_SEPARATOR.join(topics)
            ext = file_path.suffix.lower()

            self.debug_messages.append(f"  Processing: {file_path.name}")
            self.debug_messages.append(f"    Type: {ext}")
            self.debug_messages.append(f"    Topics: {topics_display}")

            # Process document
            chunks = self.processor.process_document(str(file_path), str(base_path))

            if chunks:
                # Add to vector store
                num_added = self.store.add_documents(chunks)
                result['chunks_added'] = num_added
                result['success'] = True
                result['topics'] = topics
                self.debug_messages.append(f"    ✓ Added {num_added} chunks")
            else:
                self.debug_messages.append(f"    ⚠ No text extracted from {file_path.name}")

        except Exception as e:
            self.debug_messages.append(f"    ✗ Error: {e}")
            import traceback
            import io
            error_io = io.StringIO()
            traceback.print_exc(file=error_io)
            self.debug_messages.append(error_io.getvalue())
        
        return result
    
    def _delete_file(self, file_path: Path) -> dict:
        """
        Delete a file from the vector store.
        
        Args:
            file_path: Path to the file to delete
        
        Returns:
            dict: Result information
        """
        result = {
            'success': False,
            'chunks_deleted': 0
        }
        
        try:
            # Delete from vector store by filepath
            chunks_deleted = self.store.delete_document(str(file_path))
            result['chunks_deleted'] = chunks_deleted
            result['success'] = True

            if chunks_deleted > 0:
                self.debug_messages.append(f"  ✓ Deleted {chunks_deleted} chunks from {file_path.name}")
            else:
                self.debug_messages.append(f"  ℹ No chunks found for {file_path.name} (may have already been deleted)")

        except Exception as e:
            self.debug_messages.append(f"  ✗ Error deleting {file_path}: {e}")
        
        return result
    
    def get_summary(self, stats: dict) -> list:
        """
        Get a summary of the incremental update as a list of message lines.

        Args:
            stats: Statistics dictionary from process_changes

        Returns:
            list: List of summary message lines
        """
        summary = []
        summary.append("\n" + "="*60)
        summary.append("INCREMENTAL UPDATE SUMMARY")
        summary.append("="*60)
        summary.append(f"Files added:   {stats['added']}")
        summary.append(f"Files updated: {stats['updated']}")
        summary.append(f"Files deleted: {stats['deleted']}")
        summary.append(f"Files failed:  {stats['failed']}")
        summary.append(f"Chunks added:   {stats['total_chunks_added']}")
        summary.append(f"Chunks deleted: {stats['total_chunks_deleted']}")
        summary.append(f"Net change:     {stats['total_chunks_added'] - stats['total_chunks_deleted']:+d} chunks")

        # Get current store stats
        store_stats = self.store.get_stats()
        summary.append(f"\nCurrent vector store:")
        summary.append(f"  Total chunks:    {store_stats['total_chunks']}")
        summary.append(f"  Total documents: {store_stats['total_documents']}")
        summary.append(f"  Total topics:    {store_stats['total_topics']}")

        return summary


def process_incremental_changes(changes: List[Tuple[str, str]], doc_dir: str):
    """
    Process incremental file changes and return results via JSON-RPC.

    Args:
        changes: List of (action, filepath) tuples
        doc_dir: Base directory for documents

    Returns:
        list[TextContent]: MCP response with debug info
    """
    start_time = time.time()

    response_parts = []
    response_parts.append("\n" + "="*60)
    response_parts.append("INCREMENTAL UPDATE")
    response_parts.append("="*60)
    response_parts.append(f"Processing {len(changes)} file change(s)...")

    # Count changes by type
    change_counts = {}
    for action, _ in changes:
        change_counts[action] = change_counts.get(action, 0) + 1

    for action, count in sorted(change_counts.items()):
        response_parts.append(f"  {action}: {count} file(s)")

    # Process changes
    updater = IncrementalUpdater()
    stats = updater.process_changes(changes, doc_dir)

    # Collect debug messages
    response_parts.extend(updater.debug_messages)

    # Get summary
    summary = updater.get_summary(stats)
    response_parts.extend(summary)

    duration = time.time() - start_time
    response_parts.append(f"\nUpdate completed in {duration:.2f} seconds")
    response_parts.append("="*60)

    return [TextContent(
        type="text",
        text="\n".join(response_parts)
    )]


if __name__ == "__main__":
    pass
    # Test the incremental updater
    print("This module is designed to be used by folder_watcher.py", file=sys.stderr)
    print("It processes incremental file changes (add, update, delete)", file=sys.stderr)
