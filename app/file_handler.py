"""
File Handler Module - Handles file system events for document monitoring.

This module provides the IncrementalChangeHandler class that processes
file system events with debouncing and batching.
"""

import time
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from .config import (
    DEBOUNCE_SECONDS,
    SUPPORTED_EXTENSIONS,
    BASE_DIR
)

_observer = None
_observer_lock = threading.Lock()

_pending_changes: Dict[str, Tuple[str, str]] = {}
_pending_changes_lock = threading.Lock()

_debounce_timer: Optional[threading.Timer] = None
_debounce_timer_lock = threading.Lock()


def _is_supported_file(filepath: str) -> bool:
    """Check if the file has a supported extension."""
    path = Path(filepath)
    if path.suffix.lower() in SUPPORTED_EXTENSIONS:
        return True
    return False


def _is_temp_file(filepath: str) -> bool:
    """Check if the file is a temporary file that should be ignored."""
    path = Path(filepath)
    name = path.name
    
    if name.startswith('~'):
        return True
    if name.endswith('.tmp'):
        return True
    if name.endswith('.swp'):
        return True
    if name.startswith('.'):
        return True
    if path.suffix.lower() in ['.pyc', '.pyo', '.pyd']:
        return True
    
    return False


class IncrementalChangeHandler(FileSystemEventHandler):
    """Handles file system events with debouncing for incremental updates.
    
    This handler monitors a directory for file changes (create, modify, delete)
    and batches these changes using a debounce timer to avoid excessive processing.
    
    Attributes:
        callback: Function to call when debounce timer expires with batched changes
        folder_path: Path being watched
    """
    
    def __init__(self, callback: Callable, folder_path: str):
        """Initialize the handler with a callback function.
        
        Args:
            callback: Function to call with (changes_list, incremental=True)
            folder_path: Path being watched
        """
        super().__init__()
        self.callback = callback
        self.folder_path = folder_path
    
    def on_created(self, event: FileSystemEvent):
        """Handle file creation events."""
        if event.is_directory:
            return
        
        filepath = event.src_path
        
        if _is_temp_file(filepath):
            return
        
        if not _is_supported_file(filepath):
            return
        
        self._add_change('add', filepath)
    
    def on_modified(self, event: FileSystemEvent):
        """Handle file modification events."""
        if event.is_directory:
            return
        
        filepath = event.src_path
        
        if _is_temp_file(filepath):
            return
        
        if not _is_supported_file(filepath):
            return
        
        self._add_change('update', filepath)
    
    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion events."""
        if event.is_directory:
            return
        
        filepath = event.src_path
        
        if _is_temp_file(filepath):
            return
        
        if not _is_supported_file(filepath):
            return
        
        self._add_change('delete', filepath)
    
    def on_moved(self, event: FileSystemEvent):
        """Handle file move events."""
        if event.is_directory:
            return
        
        src_path = event.src_path
        dest_path = event.dest_path
        
        if _is_temp_file(src_path) and _is_temp_file(dest_path):
            return
        
        if _is_supported_file(src_path):
            self._add_change('delete', src_path)
        
        if _is_supported_file(dest_path):
            self._add_change('add', dest_path)
    
    def _add_change(self, action: str, filepath: str):
        """Add a file change to the pending changes and reset debounce timer.
        
        Args:
            action: One of 'add', 'update', 'delete'
            filepath: Path to the file
        """
        global _debounce_timer
        
        with _pending_changes_lock:
            _pending_changes[filepath] = (action, filepath)
        
        with _debounce_timer_lock:
            if _debounce_timer is not None:
                _debounce_timer.cancel()
            
            _debounce_timer = threading.Timer(
                DEBOUNCE_SECONDS,
                self._execute_update
            )
            _debounce_timer.daemon = True
            _debounce_timer.start()
    
    def _execute_update(self):
        """Execute the callback with all pending changes."""
        global _pending_changes, _debounce_timer
        
        changes = []
        with _pending_changes_lock:
            changes = list(_pending_changes.values())
            _pending_changes.clear()
        
        with _debounce_timer_lock:
            _debounce_timer = None
        
        if not changes:
            return
        
        deduplicated_changes = []
        seen = set()
        
        for action, filepath in changes:
            if action == 'delete':
                if filepath in seen:
                    continue
                seen.add(filepath)
                deduplicated_changes.append((action, filepath))
            else:
                seen.add(filepath)
                deduplicated_changes.append((action, filepath))
        
        if not deduplicated_changes:
            return
        
        try:
            self.callback(deduplicated_changes, incremental=True)
        except Exception as e:
            print(f"[FileHandler] Error in callback: {e}", flush=True)
