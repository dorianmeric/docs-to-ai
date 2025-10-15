"""
Incremental updater for processing individual file changes.
Handles add, update, and delete operations on specific files.
"""
from pathlib import Path
from typing import List, Tuple
from app.document_processor import DocumentProcessor
from app.vector_store import VectorStore
from app.config import TOPIC_SEPARATOR
import time


class IncrementalUpdater:
    """Handles incremental updates to the vector store."""
    
    def __init__(self):
        self.processor = DocumentProcessor()
        self.store = VectorStore()
    
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
                print(f"  ✗ Error processing {action} for {file_path}: {e}")
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
                print(f"  ⚠ File no longer exists: {file_path}")
                return result
            
            # Extract topics for display
            topics = self.processor.extract_topics_from_path(file_path, base_path)
            topics_display = TOPIC_SEPARATOR.join(topics)
            ext = file_path.suffix.lower()
            
            print(f"  Processing: {file_path.name}")
            print(f"    Type: {ext}")
            print(f"    Topics: {topics_display}")
            
            # Process document
            chunks = self.processor.process_document(str(file_path), str(base_path))
            
            if chunks:
                # Add to vector store
                num_added = self.store.add_documents(chunks)
                result['chunks_added'] = num_added
                result['success'] = True
                result['topics'] = topics
                print(f"    ✓ Added {num_added} chunks")
            else:
                print(f"    ⚠ No text extracted from {file_path.name}")
                
        except Exception as e:
            print(f"    ✗ Error: {e}")
            import traceback
            traceback.print_exc()
        
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
                print(f"  ✓ Deleted {chunks_deleted} chunks from {file_path.name}")
            else:
                print(f"  ℹ No chunks found for {file_path.name} (may have already been deleted)")
                
        except Exception as e:
            print(f"  ✗ Error deleting {file_path}: {e}")
        
        return result
    
    def print_summary(self, stats: dict):
        """
        Print a summary of the incremental update.
        
        Args:
            stats: Statistics dictionary from process_changes
        """
        print("\n" + "="*60)
        print("INCREMENTAL UPDATE SUMMARY")
        print("="*60)
        print(f"Files added:   {stats['added']}")
        print(f"Files updated: {stats['updated']}")
        print(f"Files deleted: {stats['deleted']}")
        print(f"Files failed:  {stats['failed']}")
        print(f"Chunks added:   {stats['total_chunks_added']}")
        print(f"Chunks deleted: {stats['total_chunks_deleted']}")
        print(f"Net change:     {stats['total_chunks_added'] - stats['total_chunks_deleted']:+d} chunks")
        
        # Get current store stats
        store_stats = self.store.get_stats()
        print(f"\nCurrent vector store:")
        print(f"  Total chunks:    {store_stats['total_chunks']}")
        print(f"  Total documents: {store_stats['total_documents']}")
        print(f"  Total topics:    {store_stats['total_topics']}")


def process_incremental_changes(changes: List[Tuple[str, str]], doc_dir: str):
    """
    Process incremental file changes.
    
    Args:
        changes: List of (action, filepath) tuples
        doc_dir: Base directory for documents
    """
    start_time = time.time()
    
    print("\n" + "="*60)
    print("INCREMENTAL UPDATE")
    print("="*60)
    print(f"Processing {len(changes)} file change(s)...")
    
    # Count changes by type
    change_counts = {}
    for action, _ in changes:
        change_counts[action] = change_counts.get(action, 0) + 1
    
    for action, count in sorted(change_counts.items()):
        print(f"  {action}: {count} file(s)")
    
    # Process changes
    updater = IncrementalUpdater()
    stats = updater.process_changes(changes, doc_dir)
    
    # Print summary
    updater.print_summary(stats)
    
    duration = time.time() - start_time
    print(f"\nUpdate completed in {duration:.2f} seconds")
    print("="*60)


if __name__ == "__main__":
    # Test the incremental updater
    print("This module is designed to be used by folder_watcher.py")
    print("It processes incremental file changes (add, update, delete)")
