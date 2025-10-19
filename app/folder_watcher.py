"""
Folder Watcher Module - Real-time Document Monitoring with Incremental Updates

This module provides intelligent file system monitoring for document directories,
implementing a sophisticated debouncing and batching system for efficient document
processing.

OVERVIEW
========
The folder watcher monitors a directory for file changes (create, modify, delete,
move) and triggers document processing callbacks. It supports two modes:

1. **Incremental Updates** (default)
   - Monitors individual file changes
   - Batches multiple changes using debouncing (default: 10 seconds)
   - Only processes changed files, not entire directory
   - Fast and efficient for ongoing operations

2. **Full Scans** (periodic)
   - Re-processes ALL documents in the directory
   - Resets the document database
   - Runs on startup (optional) and weekly schedule
   - Ensures data consistency and catches missed changes

ARCHITECTURE
============
The system uses several key components:

- **watchdog.Observer**: Third-party library that monitors file system events
- **IncrementalChangeHandler**: Custom event handler that implements debouncing
  and change batching
- **Debounce Timer**: Delays processing until file changes stop for N seconds
- **Global State**: Tracks watcher status, scan times, and callback function

THREADING MODEL
===============
The folder watcher operates across multiple threads:

1. Main Thread: Calls start/stop functions, processes callbacks
2. Observer Thread: watchdog Observer monitoring file system
3. Timer Thread(s): Debounce timers waiting to trigger callbacks

Thread safety is ensured using:
- threading.Lock for accessing shared state (pending_changes, timer)
- Atomic operations for global variables
- Careful lock management (acquire, operate, release pattern)

WORKFLOW EXAMPLE
================
User saves "report.pdf":
  1. File system generates modify event
  2. Observer thread calls IncrementalChangeHandler.on_modified()
  3. Handler adds ('update', 'report.pdf') to pending_changes
  4. Handler starts 10-second debounce timer
  5. [9 seconds pass]
  6. User saves "notes.docx"
  7. Observer thread calls on_modified() again
  8. Handler adds ('update', 'notes.docx') to pending_changes
  9. Handler cancels old timer, starts new 10-second timer
  10. [10 seconds pass with no more changes]
  11. Timer expires, calls _execute_update()
  12. Both files are processed together in one batch
  13. Callback is invoked with [('update', 'report.pdf'), ('update', 'notes.docx')]

KEY FEATURES
============
- **Debouncing**: Batches rapid file changes to avoid excessive processing
- **Smart Deduplication**: Handles edge cases (file created then deleted, etc.)
- **File Filtering**: Ignores temporary files (.tmp, ~$, etc.) and unsupported extensions
- **Weekly Full Scans**: Maintains data consistency with periodic re-processing
- **Recursive Monitoring**: Watches subdirectories automatically
- **Error Resilience**: Exceptions in callbacks don't crash the watcher
- **Status Tracking**: Provides detailed timing and status information

PUBLIC API
==========
Main Functions:
  - start_watching_folder(): Initialize and start monitoring
  - stop_watching_folder(): Stop monitoring and cleanup
  - get_last_scan_time(): Get detailed scan timing information
  - trigger_full_scan_if_needed(): Check weekly schedule and scan if needed
  - force_full_scan(): Manually trigger full scan immediately
  - is_watching(): Check if watcher is currently active

CONFIGURATION
=============
Global Constants (modify at module level):
  - FULL_SCAN_INTERVAL_DAYS: Days between full scans (default: 7)
  - DEBOUNCE_SECONDS: Delay after last change before processing (default: 10)

Per-Instance Settings (passed to start_watching_folder):
  - folder_path: Directory to monitor
  - debounce_seconds: Override default debounce period
  - do_initial_scan: Whether to scan on startup

DEPENDENCIES
============
External:
  - watchdog: File system monitoring library
  - pathlib: Path handling (Python stdlib)
  - threading: Thread management (Python stdlib)

Internal:
  - app.config: Configuration (BASE_DIR, SUPPORTED_EXTENSIONS)

USAGE EXAMPLE
=============
```python
from app.folder_watcher import start_watching_folder, stop_watching_folder

def my_callback(changes, incremental):
    \"\"\"Process document changes.\"\"\"
    if incremental:
        for action, filepath in changes:
            if action == 'add':
                process_new_document(filepath)
            elif action == 'update':
                update_document(filepath)
            elif action == 'delete':
                remove_document(filepath)
    else:
        # Full scan - process everything
        process_all_documents()

    return [TextContent(type="text", text="Processing complete")]

# Start watching with initial full scan
result = start_watching_folder(
    my_callback,
    folder_path="/my-docs",
    debounce_seconds=10,
    do_initial_scan=True
)

if result['status'] == 'started':
    print(f"Monitoring: {result['watch_path']}")

# Later, stop watching
stop_watching_folder()
```

NOTES
=====
- Designed for MCP (Model Context Protocol) server integration
- Logs to stderr to avoid interfering with MCP JSON-RPC protocol
- Callback results are returned via MCP TextContent objects
- Can be run standalone for testing (see __main__ section)

See also: mcp_server.py for production integration example
"""
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from app.config import BASE_DIR, SUPPORTED_EXTENSIONS
from typing import Callable, Optional, Set
import os
import sys

# ============================================================================
# Global State Variables
# ============================================================================
# These global variables maintain the state of the folder watcher across
# function calls and allow coordination between the watcher thread and
# the main application thread.

# The watchdog Observer instance that monitors file system events
_observer = None

# Boolean flag indicating whether the watcher is currently active
_watcher_active = False

# Unix timestamp (float) of when the last scan started
# Used to track scan duration and provide status information
_last_scan_start_time = None

# Unix timestamp (float) of when the last scan completed
# Used to calculate scan duration
_last_scan_end_time = None

# Unix timestamp (float) of when the last FULL scan was performed
# Used to determine if a weekly full scan is due
_last_full_scan_time = None

# The callback function provided by the caller to process document changes
# Signature: callback(changes: List[Tuple[str, str]], incremental: bool) -> list[TextContent]
_callback_function = None

# Path object representing the directory being watched
_watch_path = None

# ============================================================================
# Configuration Constants
# ============================================================================
# Full scan interval - ensures the entire document set is re-processed weekly
# This catches any documents that might have been missed by incremental updates
FULL_SCAN_INTERVAL_DAYS = 7  # Do a full scan once a week

# Debounce period in seconds - prevents excessive processing during rapid file changes
# When multiple files change in quick succession, changes are batched together
# Reduced from 180 to 10 seconds to make incremental updates more responsive
DEBOUNCE_SECONDS = 10


class IncrementalChangeHandler(FileSystemEventHandler):
    """
    Event handler that tracks individual file changes and triggers incremental updates.

    This class extends watchdog's FileSystemEventHandler to monitor file system events
    (create, modify, delete, move) and batch them for efficient processing. It uses
    a debouncing mechanism to avoid triggering updates too frequently when many files
    change in rapid succession.

    Design Pattern:
    - Debouncing: File changes are collected and processed after a quiet period
    - Thread-safe: Uses locks to coordinate between the file watcher thread and timer thread
    - Smart deduplication: Conflicting actions (e.g., add then delete) are resolved intelligently

    Example:
        If 10 files are modified within 5 seconds, instead of triggering 10 separate
        updates, they are batched into a single update that processes all 10 files together.
    """

    def __init__(self, callback: Callable, watch_path: Path, debounce_seconds: int = DEBOUNCE_SECONDS):
        """
        Initialize the incremental change handler.

        Args:
            callback: Function to call when processing batched changes
                     Signature: callback(changes: List[Tuple[str, str]], incremental: bool)
            watch_path: Path object for the directory being monitored
            debounce_seconds: Seconds to wait after last change before triggering callback
        """
        super().__init__()
        self.callback = callback
        self.watch_path = watch_path
        self.debounce_seconds = debounce_seconds

        # Set of pending changes: {(action, filepath), ...}
        # Actions: 'add', 'update', 'delete'
        # Using a set ensures no duplicate entries for the same (action, filepath) pair
        self.pending_changes: Set[tuple] = set()

        # Timestamp of the last time the callback was triggered (currently unused)
        self.last_triggered = 0

        # Timer object for implementing the debounce delay
        # Cancelled and recreated each time a new file change is detected
        self.timer = None

        # Thread lock to ensure thread-safe access to pending_changes and timer
        # Necessary because file events and timer callbacks run on different threads
        self.lock = threading.Lock()
        
    def _is_supported_file(self, path: str) -> bool:
        """
        Check if file has a supported extension.

        This filters out files that aren't document types we want to process.
        Supported extensions are defined in app.config.SUPPORTED_EXTENSIONS.

        Args:
            path: Full file path to check

        Returns:
            bool: True if file extension is supported, False otherwise

        Examples:
            _is_supported_file("/docs/report.pdf") -> True (if .pdf is supported)
            _is_supported_file("/docs/image.jpg") -> False (if .jpg not supported)
        """
        return any(path.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)

    def _should_ignore(self, path: str) -> bool:
        """
        Check if file should be ignored based on filename patterns.

        This filters out temporary files, backup files, and system files that
        shouldn't trigger document processing. Common patterns include:
        - Editor temporary files (.tmp, .swp, ~$)
        - System metadata files (.DS_Store, Thumbs.db)
        - Partial downloads (.crdownload, .part)

        Args:
            path: Full file path to check

        Returns:
            bool: True if file should be ignored, False if it should be processed

        Note:
            This uses substring matching, not regex, for simplicity and speed.
            For example, "~$report.docx" will be ignored because it contains "~$".
        """
        filename = os.path.basename(path)
        # Ignore temporary files and system files
        ignore_patterns = ['.tmp', '~$', '.swp', '.DS_Store', 'Thumbs.db', '.crdownload', '.part']
        return any(pattern in filename for pattern in ignore_patterns)
    
    def _schedule_update(self):
        """
        Schedule an update after debounce period.

        This implements the debouncing mechanism. Every time a file change is detected,
        this method is called. If a timer is already running, it's cancelled and a new
        one is started. This means the callback will only execute after there have been
        no file changes for `debounce_seconds`.

        Thread Safety:
            Uses self.lock to prevent race conditions between:
            - Multiple file events happening simultaneously
            - File events and timer expiration

        Debouncing Example:
            Time 0s: File A modified -> timer starts (10s countdown)
            Time 2s: File B modified -> timer cancelled, new timer starts (10s countdown)
            Time 5s: File C modified -> timer cancelled, new timer starts (10s countdown)
            Time 15s: No more changes -> timer expires, _execute_update called with all 3 files
        """
        with self.lock:
            # Cancel existing timer if one is running
            # This effectively "resets" the debounce countdown
            if self.timer:
                self.timer.cancel()

            # Schedule new update to execute after debounce_seconds
            self.timer = threading.Timer(self.debounce_seconds, self._execute_update)
            # Mark as daemon so it won't prevent program exit
            self.timer.daemon = True
            self.timer.start()
    
    def _execute_update(self):
        """
        Execute the incremental update for all pending changes.

        This method is called by the timer after the debounce period expires.
        It processes all accumulated file changes as a batch, improving efficiency
        compared to processing each change individually.

        Process Flow:
            1. Atomically extract and clear pending changes (thread-safe)
            2. Group changes by action type for logging
            3. Call the user-provided callback with all changes
            4. Update global scan timing variables

        Global Side Effects:
            - Updates _last_scan_start_time
            - Updates _last_scan_end_time

        Thread Safety:
            Uses self.lock only briefly to copy/clear pending_changes, then
            releases it before the potentially long-running callback execution.
            This allows new file events to be queued while processing is ongoing.

        Error Handling:
            Exceptions are caught and logged but don't crash the watcher.
            This ensures the folder watcher remains active even if document
            processing fails.
        """
        global _last_scan_start_time, _last_scan_end_time

        # Atomically extract pending changes and reset state
        with self.lock:
            if not self.pending_changes:
                return

            # Copy the changes and clear the set
            # This allows new changes to accumulate while we process these
            changes_to_process = list(self.pending_changes)
            self.pending_changes.clear()
            self.timer = None

        try:
            _last_scan_start_time = time.time()
            # Note: These print statements are for server-side logging only
            # The actual results are returned via the callback's JSON-RPC response
            print(f"\n[FolderWatcher] Starting incremental update at {datetime.fromtimestamp(_last_scan_start_time).isoformat()}", file=sys.stderr)
            print(f"[FolderWatcher] Processing {len(changes_to_process)} file change(s)", file=sys.stderr)

            # Group changes by action type for diagnostic logging
            changes_by_action = {}
            for action, filepath in changes_to_process:
                if action not in changes_by_action:
                    changes_by_action[action] = []
                changes_by_action[action].append(filepath)

            # Log summary of what we're processing
            for action, files in changes_by_action.items():
                print(f"[FolderWatcher]   {action}: {len(files)} file(s)", file=sys.stderr)

            # Execute callback with changes - callback returns JSON-RPC response
            if self.callback:
                result = self.callback(changes_to_process, incremental=True)
                # Result is now a list[TextContent] that will be sent via MCP
                print(f"[FolderWatcher] Update callback completed, result returned via MCP", file=sys.stderr)

            _last_scan_end_time = time.time()
            duration = _last_scan_end_time - _last_scan_start_time
            print(f"[FolderWatcher] Incremental update completed in {duration:.2f}s", file=sys.stderr)

        except Exception as e:
            _last_scan_end_time = time.time()
            print(f"[FolderWatcher] Error during incremental update: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
    
    def on_created(self, event: FileSystemEvent):
        """
        Handle file creation events.

        Called by watchdog when a new file is created in the watched directory.

        Smart Deduplication:
            If a file was previously marked for deletion (e.g., during a move operation),
            that delete action is removed before adding the 'add' action. This prevents
            unnecessary delete+add operations for renamed files.

        Args:
            event: FileSystemEvent object containing the file path

        Actions Taken:
            - Ignores directories (only files are processed)
            - Filters out temporary/system files and unsupported extensions
            - Adds ('add', filepath) to pending_changes
            - Schedules debounced update
        """
        if event.is_directory:
            return

        src_path = str(event.src_path)
        if self._should_ignore(src_path) or not self._is_supported_file(src_path):
            return

        with self.lock:
            # Remove any previous delete actions for this file
            # This handles the case where a file is moved/renamed within the watched directory
            self.pending_changes.discard(('delete', src_path))
            self.pending_changes.add(('add', src_path))

        print(f"[FolderWatcher] File created: {src_path}", file=sys.stderr)
        self._schedule_update()
    
    def on_modified(self, event: FileSystemEvent):
        """
        Handle file modification events.

        Called by watchdog when an existing file is modified (content changed).

        Note on Duplicate Events:
            File systems may generate multiple modification events for a single
            save operation. The debouncing mechanism handles this by batching
            all modifications within the debounce period.

        Args:
            event: FileSystemEvent object containing the file path

        Actions Taken:
            - Ignores directories (only files are processed)
            - Filters out temporary/system files and unsupported extensions
            - Adds ('update', filepath) to pending_changes
            - Schedules debounced update
        """
        if event.is_directory:
            return

        src_path = str(event.src_path)
        if self._should_ignore(src_path) or not self._is_supported_file(src_path):
            return

        with self.lock:
            # Treat modification as update
            # If the same file is modified multiple times, the set will deduplicate
            self.pending_changes.add(('update', src_path))

        print(f"[FolderWatcher] File modified: {src_path}", file=sys.stderr)
        self._schedule_update()
    
    def on_deleted(self, event: FileSystemEvent):
        """
        Handle file deletion events.

        Called by watchdog when a file is deleted from the watched directory.

        Smart Deduplication:
            If a file was previously marked for 'add' or 'update', those actions
            are removed. This handles scenarios like:
            - File created then immediately deleted -> no action needed
            - File modified then deleted -> only delete action needed

        Args:
            event: FileSystemEvent object containing the file path

        Actions Taken:
            - Ignores directories (only files are processed)
            - Filters out temporary/system files and unsupported extensions
            - Removes any pending 'add' or 'update' actions for this file
            - Adds ('delete', filepath) to pending_changes
            - Schedules debounced update
        """
        if event.is_directory:
            return

        src_path = str(event.src_path)
        if self._should_ignore(src_path) or not self._is_supported_file(src_path):
            return

        with self.lock:
            # Remove any pending add/update actions for this file
            # This ensures we don't try to add/update a file that no longer exists
            self.pending_changes.discard(('add', src_path))
            self.pending_changes.discard(('update', src_path))
            self.pending_changes.add(('delete', src_path))

        print(f"[FolderWatcher] File deleted: {src_path}", file=sys.stderr)
        self._schedule_update()
    
    def on_moved(self, event: FileSystemEvent):
        """
        Handle file move/rename events.

        Called by watchdog when a file is moved or renamed. This is treated as
        a combination of delete (old path) and add (new path).

        Complex Scenarios Handled:
            1. Move within watched directory: Delete old path, add new path
            2. Move from watched to unwatched directory: Delete only
            3. Move from unwatched to watched directory: Add only
            4. Rename (special case of move): Delete old name, add new name

        File Extension Changes:
            If a file is renamed from .pdf to .txt (for example), and only .pdf
            is supported, this will correctly delete the old file and ignore the
            new unsupported extension.

        Args:
            event: FileSystemEvent object containing src_path and dest_path

        Actions Taken:
            - Ignores directories (only files are processed)
            - Processes source path: Removes pending actions, adds delete
            - Processes dest path: Removes delete action, adds add
            - Schedules debounced update
        """
        if event.is_directory:
            return

        src_path = str(event.src_path)
        dest_path = str(event.dest_path)

        # Handle source file (old location)
        if self._is_supported_file(src_path) and not self._should_ignore(src_path):
            with self.lock:
                # Remove any pending actions for old path
                self.pending_changes.discard(('add', src_path))
                self.pending_changes.discard(('update', src_path))
                # Mark old path for deletion
                self.pending_changes.add(('delete', src_path))
            print(f"[FolderWatcher] File moved from: {src_path}", file=sys.stderr)

        # Handle destination file (new location)
        if self._is_supported_file(dest_path) and not self._should_ignore(dest_path):
            with self.lock:
                # Remove any delete action for destination (in case of overwrite)
                self.pending_changes.discard(('delete', dest_path))
                # Mark new path for addition
                self.pending_changes.add(('add', dest_path))
            print(f"[FolderWatcher] File moved to: {dest_path}", file=sys.stderr)

        self._schedule_update()


def _check_full_scan_needed() -> bool:
    """
    Check if a full scan is needed based on time since last full scan.

    Full scans are performed periodically (default: every 7 days) to ensure
    data consistency. This catches any documents that might have been missed
    by incremental updates due to edge cases or system issues.

    Returns:
        bool: True if full scan is needed, False otherwise

    Logic:
        - Returns True if no full scan has ever been performed
        - Returns True if FULL_SCAN_INTERVAL_DAYS or more have passed
        - Returns False otherwise
    """
    global _last_full_scan_time

    # If we've never done a full scan, we need one
    if _last_full_scan_time is None:
        return True

    # Calculate days since last full scan
    time_since_last_scan = datetime.now() - datetime.fromtimestamp(_last_full_scan_time)
    return time_since_last_scan.days >= FULL_SCAN_INTERVAL_DAYS


def _trigger_full_scan(callback: Callable):
    """
    Trigger a full scan of all documents with database reset.

    Unlike incremental updates, a full scan:
    - Resets the database (clears existing document embeddings)
    - Re-processes ALL documents in the watched directory
    - Updates _last_full_scan_time to track the weekly schedule

    This is used for:
    - Initial setup (first-time scan)
    - Weekly maintenance scans
    - Manual forced scans (when user suspects data issues)

    Args:
        callback: Callback function that processes documents
                 Signature: callback(changes: List, incremental: bool) -> list[TextContent]
                 For full scans, changes is an empty list and incremental=False

    Returns:
        list[TextContent]: Result from callback containing scan summary
        None: If an error occurred during scanning

    Global Side Effects:
        - Updates _last_scan_start_time
        - Updates _last_scan_end_time
        - Updates _last_full_scan_time (used for weekly scheduling)

    Error Handling:
        Exceptions are caught, logged, and None is returned. This prevents
        the watcher from crashing due to document processing errors.
    """
    global _last_scan_start_time, _last_scan_end_time, _last_full_scan_time

    try:
        _last_scan_start_time = time.time()
        _last_full_scan_time = _last_scan_start_time

        # Note: These print statements are for server-side logging only
        # The actual results are returned via the callback's JSON-RPC response
        print(f"\n[FolderWatcher] Starting FULL SCAN (with database reset) at {datetime.fromtimestamp(_last_scan_start_time).isoformat()}", file=sys.stderr)

        # Execute callback with full scan flag - callback returns JSON-RPC response
        result = None
        if callback:
            # Empty changes list + incremental=False signals a full scan
            result = callback([], incremental=False)
            # Result is now a list[TextContent] that will be sent via MCP
            print(f"[FolderWatcher] Full scan callback completed, result returned via MCP", file=sys.stderr)

        _last_scan_end_time = time.time()
        duration = _last_scan_end_time - _last_scan_start_time
        print(f"[FolderWatcher] Full scan completed in {duration:.2f}s", file=sys.stderr)

        return result

    except Exception as e:
        _last_scan_end_time = time.time()
        print(f"[FolderWatcher] Error during full scan: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None


def start_watching_folder(scan_callback: Callable, folder_path: Optional[str] = None,
                         debounce_seconds: int = DEBOUNCE_SECONDS,
                         do_initial_scan: bool = False):
    """
    Start watching a folder for changes with incremental update support.

    This is the main entry point for the folder watcher. It initializes the
    watchdog Observer, sets up event handlers, and optionally performs an
    initial full scan of all documents.

    Lifecycle:
        1. Validate inputs and check if already watching
        2. Create IncrementalChangeHandler with user's callback
        3. Start watchdog Observer to monitor file system events
        4. Optionally perform initial full scan
        5. Return status dict to caller

    Args:
        scan_callback: Function to call when changes are detected.
                      Signature: callback(changes: List[Tuple[str, str]], incremental: bool) -> list[TextContent]
                      - changes: List of (action, filepath) tuples for incremental updates
                                Empty list for full scans
                      - incremental: True for incremental update, False for full scan
                      - Returns: list[TextContent] with scan results (sent via MCP)
        folder_path: Path to watch (defaults to BASE_DIR/my-docs, typically /my-docs)
        debounce_seconds: Minimum seconds between triggers (default: 10)
                         Higher values = less frequent but more batched updates
        do_initial_scan: Whether to perform initial full scan on startup
                        Recommended: True for first-time setup

    Returns:
        dict: Status information containing:
            - status: 'started', 'already_watching', or 'error'
            - message: Human-readable status message
            - watch_path: Absolute path being monitored
            - debounce_seconds: Configured debounce period
            - full_scan_interval_days: Days between full scans
            - scan_result: (optional) list[TextContent] from initial scan

    Examples:
        # Start watching with initial scan
        result = start_watching_folder(my_callback, do_initial_scan=True)
        if result['status'] == 'started':
            print(f"Watching {result['watch_path']}")

        # Start watching custom path with longer debounce
        result = start_watching_folder(my_callback,
                                      folder_path="/custom/docs",
                                      debounce_seconds=30)
    """
    global _observer, _watcher_active, _callback_function, _watch_path, _last_full_scan_time

    # ========================================================================
    # Validation: Check if already watching
    # ========================================================================
    if _watcher_active:
        return {
            "status": "already_watching",
            "message": "Folder watcher is already active",
            "watch_path": str(_get_watch_path(folder_path))
        }

    # ========================================================================
    # Validation: Determine and verify watch path
    # ========================================================================
    watch_path = _get_watch_path(folder_path)

    if not watch_path.exists():
        return {
            "status": "error",
            "message": f"Folder does not exist: {watch_path}",
            "watch_path": str(watch_path)
        }

    try:
        # ====================================================================
        # Initialization: Store callback and path in global state
        # ====================================================================
        _callback_function = scan_callback
        _watch_path = watch_path

        # ====================================================================
        # Setup: Create event handler with debouncing
        # ====================================================================
        # This handler will receive all file system events and batch them
        event_handler = IncrementalChangeHandler(
            scan_callback,
            watch_path,
            debounce_seconds=debounce_seconds
        )

        # ====================================================================
        # Setup: Create and start watchdog Observer
        # ====================================================================
        # The Observer runs in a separate thread and monitors file system events
        _observer = Observer()
        # recursive=True means subdirectories are also monitored
        _observer.schedule(event_handler, str(watch_path), recursive=True)
        _observer.start()
        _watcher_active = True

        # Log successful startup
        print(f"[FolderWatcher] Started watching: {watch_path.absolute()}", file=sys.stderr)
        print(f"[FolderWatcher] Incremental updates enabled with {debounce_seconds}s debounce", file=sys.stderr)
        print(f"[FolderWatcher] Full scan interval: {FULL_SCAN_INTERVAL_DAYS} days", file=sys.stderr)

        # ====================================================================
        # Prepare return value
        # ====================================================================
        result = {
            "status": "started",
            "message": "Folder watcher started successfully",
            "watch_path": str(watch_path.absolute()),
            "debounce_seconds": debounce_seconds,
            "full_scan_interval_days": FULL_SCAN_INTERVAL_DAYS
        }

        # ====================================================================
        # Optional: Perform initial full scan
        # ====================================================================
        # This ensures the database is populated on first startup
        if do_initial_scan:
            print(f"[FolderWatcher] Performing initial full scan...", file=sys.stderr)
            scan_result = _trigger_full_scan(scan_callback)
            # Include scan results in return value for MCP response
            if scan_result:
                result['scan_result'] = scan_result

        return result

    except Exception as e:
        # ====================================================================
        # Error Handling: Reset state and return error
        # ====================================================================
        _watcher_active = False
        return {
            "status": "error",
            "message": f"Failed to start folder watcher: {str(e)}",
            "watch_path": str(watch_path)
        }


def stop_watching_folder():
    """
    Stop the folder watcher if it's running.

    This cleanly shuts down the watchdog Observer and resets all global state.
    Any pending debounced updates will be lost (not executed).

    Thread Safety:
        Calls observer.stop() to signal the observer thread to stop, then
        observer.join() to wait for it to fully terminate (max 5 seconds).

    Returns:
        dict: Status information containing:
            - status: 'stopped', 'not_watching', or 'error'
            - message: Human-readable status message

    Side Effects:
        - Stops the watchdog Observer thread
        - Resets all global state variables
        - Cancels any pending debounced updates

    Usage:
        result = stop_watching_folder()
        if result['status'] == 'stopped':
            print("Watcher stopped successfully")
    """
    global _observer, _watcher_active, _callback_function, _watch_path

    if not _watcher_active:
        return {
            "status": "not_watching",
            "message": "Folder watcher is not currently active"
        }

    try:
        # Stop the observer thread
        if _observer:
            _observer.stop()
            # Wait up to 5 seconds for the thread to terminate
            _observer.join(timeout=5)
            _observer = None

        # Reset all global state
        _watcher_active = False
        _callback_function = None
        _watch_path = None

        print("[FolderWatcher] Stopped watching folder", file=sys.stderr)

        return {
            "status": "stopped",
            "message": "Folder watcher stopped successfully"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error stopping folder watcher: {str(e)}"
        }


def get_last_scan_time():
    """
    Get the timestamp and metadata of the last scan.

    Provides detailed information about:
    - When the last scan (incremental or full) started and ended
    - How long it took to complete
    - When the last full scan occurred
    - Whether a full scan is currently due

    This is useful for:
    - Monitoring system health
    - Debugging scan issues
    - Displaying status in UIs
    - Determining if weekly full scan is needed

    Returns:
        dict: Scan timing information containing:
            When watcher inactive:
                - status: 'not_watching'
                - message: Error message

            When no scans have run:
                - status: 'no_scans_yet'
                - message: Info message

            When scans have run:
                - status: 'success'
                - scan_start_timestamp: Unix timestamp (float)
                - scan_start_time: ISO 8601 format
                - scan_start_time_formatted: Human-readable format
                - scan_end_timestamp: Unix timestamp (if completed)
                - scan_end_time: ISO 8601 format (if completed)
                - scan_end_time_formatted: Human-readable (if completed)
                - duration_seconds: Time taken (if completed)
                - scan_status: 'in_progress' (if not completed)
                - last_full_scan_timestamp: When last full scan ran
                - last_full_scan_time: ISO 8601 format
                - last_full_scan_time_formatted: Human-readable
                - days_since_full_scan: Days elapsed
                - next_full_scan_due: Boolean, true if >= 7 days

    Usage:
        info = get_last_scan_time()
        if info.get('next_full_scan_due'):
            print("Weekly full scan is due!")
    """
    global _last_scan_start_time, _last_scan_end_time, _last_full_scan_time

    # Check if watcher is active
    if not _watcher_active:
        return {
            "status": "not_watching",
            "message": "Folder watcher is not currently active"
        }

    # Check if any scans have been triggered
    if _last_scan_start_time is None:
        return {
            "status": "no_scans_yet",
            "message": "No scans have been triggered yet"
        }

    # Build response with scan start time
    start_dt = datetime.fromtimestamp(_last_scan_start_time)
    result = {
        "status": "success",
        "scan_start_timestamp": _last_scan_start_time,
        "scan_start_time": start_dt.isoformat(),
        "scan_start_time_formatted": start_dt.strftime("%Y-%m-%d %H:%M:%S")
    }

    # Add scan end time and duration if scan completed
    if _last_scan_end_time is not None:
        end_dt = datetime.fromtimestamp(_last_scan_end_time)
        duration = _last_scan_end_time - _last_scan_start_time
        result.update({
            "scan_end_timestamp": _last_scan_end_time,
            "scan_end_time": end_dt.isoformat(),
            "scan_end_time_formatted": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": round(duration, 2)
        })
    else:
        # Scan is still running
        result["scan_status"] = "in_progress"

    # Add information about last full scan and weekly schedule
    if _last_full_scan_time is not None:
        full_scan_dt = datetime.fromtimestamp(_last_full_scan_time)
        result.update({
            "last_full_scan_timestamp": _last_full_scan_time,
            "last_full_scan_time": full_scan_dt.isoformat(),
            "last_full_scan_time_formatted": full_scan_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "days_since_full_scan": (datetime.now() - full_scan_dt).days,
            "next_full_scan_due": _check_full_scan_needed()
        })

    return result


def trigger_full_scan_if_needed():
    """
    Check if a full scan is needed and trigger it if so.

    This should be called periodically to maintain the weekly full scan schedule.
    Good times to call this:
    - On application startup
    - From a periodic timer (e.g., daily cron job)
    - After the system has been offline for a while

    The function checks if FULL_SCAN_INTERVAL_DAYS (default: 7) have passed
    since the last full scan, and triggers one if needed.

    Returns:
        dict: Status information containing:
            - status: 'not_watching', 'full_scan_triggered', or 'full_scan_not_needed'
            - message: Human-readable status message
            - days_until: (when not needed) Days until next full scan

    Usage:
        # Call this daily to maintain weekly full scan schedule
        result = trigger_full_scan_if_needed()
        if result['status'] == 'full_scan_triggered':
            print("Weekly full scan started")
    """
    global _callback_function

    if not _watcher_active:
        return {
            "status": "not_watching",
            "message": "Folder watcher is not currently active"
        }

    # Check if it's time for a full scan
    if _check_full_scan_needed():
        if _callback_function is None:
            return {
                "status": "error",
                "message": "No callback function is set"
            }
        _trigger_full_scan(_callback_function)
        return {
            "status": "full_scan_triggered",
            "message": "Full scan was needed and has been triggered"
        }
    else:
        # Calculate how many days until next scan
        if _last_full_scan_time is None:
            # This should not happen due to _check_full_scan_needed() logic, but handle defensively
            return {
                "status": "error",
                "message": "Last full scan time is not set"
            }
        days_since = (datetime.now() - datetime.fromtimestamp(_last_full_scan_time)).days
        days_until = FULL_SCAN_INTERVAL_DAYS - days_since
        return {
            "status": "full_scan_not_needed",
            "message": f"Full scan not needed yet. Next scan in {days_until} day(s)"
        }


def force_full_scan():
    """
    Force a full scan immediately regardless of schedule.

    Unlike trigger_full_scan_if_needed(), this function always triggers a
    full scan, bypassing the weekly schedule check. This is useful when:
    - User manually requests a rescan (e.g., after fixing corrupted data)
    - System recovery after database issues
    - Testing or debugging document processing
    - Ensuring database is in sync with file system

    The scan will:
    - Reset the document database (clear existing embeddings)
    - Re-process all documents in the watched directory
    - Update the _last_full_scan_time timestamp

    Returns:
        dict: Status information containing:
            - status: 'not_watching' or 'full_scan_triggered'
            - message: Human-readable status message

    Usage:
        # Manually trigger a full rescan
        result = force_full_scan()
        if result['status'] == 'full_scan_triggered':
            print("Full scan started, this may take several minutes...")
    """
    global _callback_function

    if not _watcher_active:
        return {
            "status": "not_watching",
            "message": "Folder watcher is not currently active"
        }

    if _callback_function is None:
        return {
            "status": "error",
            "message": "No callback function is set"
        }

    # Trigger full scan regardless of schedule
    _trigger_full_scan(_callback_function)
    return {
        "status": "full_scan_triggered",
        "message": "Full scan has been triggered"
    }


def is_watching():
    """
    Check if the folder watcher is currently active.

    This is a simple boolean check useful for:
    - Conditional logic (don't start watcher if already running)
    - Status displays in UIs
    - Health checks and monitoring

    Returns:
        bool: True if watching, False otherwise

    Usage:
        if not is_watching():
            start_watching_folder(callback)
    """
    return _watcher_active


def _get_watch_path(folder_path: Optional[str] = None) -> Path:
    """
    Get the path to watch, with default fallback.

    This is an internal helper function that determines which directory to
    monitor. If no custom path is provided, it defaults to BASE_DIR/my-docs.

    Args:
        folder_path: Optional custom path (string or Path-like)
                    If None, uses default location

    Returns:
        Path: Path object representing the directory to watch

    Default Behavior:
        In Docker: /app/my-docs
        In development: <project_root>/my-docs

    Usage:
        # Use default path
        path = _get_watch_path()  # Returns BASE_DIR/my-docs

        # Use custom path
        path = _get_watch_path("/custom/docs")  # Returns /custom/docs
    """
    if folder_path:
        return Path(folder_path)

    # Default to my-docs directory relative to BASE_DIR
    # BASE_DIR is typically /app in Docker or project root in development
    return BASE_DIR / "my-docs"


# ============================================================================
# Standalone Script Support (Backward Compatibility)
# ============================================================================
# This section allows the module to be run as a standalone script for testing
# or backward compatibility with older deployment methods.
#
# Usage: python folder_watcher.py <folder_path>
#
# In production, this module is typically imported and used via the MCP server,
# not run directly as a script.
if __name__ == "__main__":
    import sys
    import subprocess

    def simple_callback(changes, incremental):
        """
        Simple callback for standalone mode.

        This is a basic implementation that logs changes and calls the
        legacy scan_all_my_documents script. In production, the MCP server
        provides a more sophisticated callback.

        Args:
            changes: List of (action, filepath) tuples
            incremental: True for incremental, False for full scan
        """
        if incremental:
            print(f"[FolderWatcher] Processing {len(changes)} incremental changes", file=sys.stderr)
            for action, filepath in changes:
                print(f"[FolderWatcher]   {action}: {filepath}", file=sys.stderr)
                pass
        else:
            print("[FolderWatcher] Performing full scan", file=sys.stderr)
            pass

        # Trigger full scan script (for backward compatibility)
        # In production, document processing happens in the callback provided by MCP server
        try:
            result = subprocess.run(
                ["python", "-m", "app.scan_all_my_documents", "--doc-dir", "/app/my-docs"],
                capture_output=True,
                text=True,
                check=True,
                timeout=600  # 10 minute timeout
            )
            print(f"[FolderWatcher] Scan output: {result.stdout}", file=sys.stderr)
            if result.stderr:
                print(f"[FolderWatcher] Scan errors: {result.stderr}", file=sys.stderr)
                pass
        except subprocess.TimeoutExpired:
            print("[FolderWatcher] Scan timed out", file=sys.stderr)
            pass
        except Exception as e:
            print(f"[FolderWatcher] Error running scan: {e}", file=sys.stderr)
            pass

    # ========================================================================
    # Parse command line arguments
    # ========================================================================
    if len(sys.argv) < 2:
        print("Usage: python folder_watcher.py <folder_path>", file=sys.stderr)
        sys.exit(1)

    folder_to_watch = sys.argv[1]

    # ========================================================================
    # Start watching the specified folder
    # ========================================================================
    result = start_watching_folder(simple_callback, folder_path=folder_to_watch)

    if result["status"] != "started":
        print(f"Error: {result['message']}", file=sys.stderr)
        sys.exit(1)

    print(f"Watching folder: {result['watch_path']}", file=sys.stderr)
    print("Press Ctrl+C to stop watching\n", file=sys.stderr)

    # ========================================================================
    # Main loop: Check for scheduled full scans every minute
    # ========================================================================
    try:
        while True:
            time.sleep(60)
            # Check if weekly full scan is needed
            trigger_full_scan_if_needed()
    except KeyboardInterrupt:
        # ====================================================================
        # Graceful shutdown on Ctrl+C
        # ====================================================================
        print("\n[FolderWatcher] Stopping...", file=sys.stderr)
        stop_watching_folder()
        print("[FolderWatcher] Stopped", file=sys.stderr)
