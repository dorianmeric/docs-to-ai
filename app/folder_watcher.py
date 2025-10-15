"""
Folder watcher module for monitoring document directory changes.
Provides functions to start/stop watching and track scan times.
Supports incremental updates (only processing changed files) and weekly full scans.
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

# Global state
_observer = None
_watcher_active = False
_last_scan_start_time = None
_last_scan_end_time = None
_last_full_scan_time = None
_callback_function = None
_watch_path = None

# Configuration
FULL_SCAN_INTERVAL_DAYS = 7  # Do a full scan once a week
DEBOUNCE_SECONDS = 10  # Reduced from 180 to make incremental updates more responsive


class IncrementalChangeHandler(FileSystemEventHandler):
    """Event handler that tracks individual file changes and triggers incremental updates."""
    
    def __init__(self, callback: Callable, watch_path: Path, debounce_seconds: int = DEBOUNCE_SECONDS):
        super().__init__()
        self.callback = callback
        self.watch_path = watch_path
        self.debounce_seconds = debounce_seconds
        self.pending_changes: Set[tuple] = set()  # (action, filepath)
        self.last_triggered = 0
        self.timer = None
        self.lock = threading.Lock()
        
    def _is_supported_file(self, path: str) -> bool:
        """Check if file has a supported extension."""
        return any(path.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)
    
    def _should_ignore(self, path: str) -> bool:
        """Check if file should be ignored."""
        filename = os.path.basename(path)
        # Ignore temporary files and system files
        ignore_patterns = ['.tmp', '~$', '.swp', '.DS_Store', 'Thumbs.db', '.crdownload', '.part']
        return any(pattern in filename for pattern in ignore_patterns)
    
    def _schedule_update(self):
        """Schedule an update after debounce period."""
        with self.lock:
            # Cancel existing timer
            if self.timer:
                self.timer.cancel()
            
            # Schedule new update
            self.timer = threading.Timer(self.debounce_seconds, self._execute_update)
            self.timer.daemon = True
            self.timer.start()
    
    def _execute_update(self):
        """Execute the incremental update for all pending changes."""
        global _last_scan_start_time, _last_scan_end_time
        
        with self.lock:
            if not self.pending_changes:
                return
            
            # Copy and clear pending changes
            changes_to_process = list(self.pending_changes)
            self.pending_changes.clear()
            self.timer = None
        
        try:
            _last_scan_start_time = time.time()
            print(f"\n[FolderWatcher] Starting incremental update at {datetime.fromtimestamp(_last_scan_start_time).isoformat()}")
            print(f"[FolderWatcher] Processing {len(changes_to_process)} file change(s)")
            
            # Group changes by action
            changes_by_action = {}
            for action, filepath in changes_to_process:
                if action not in changes_by_action:
                    changes_by_action[action] = []
                changes_by_action[action].append(filepath)
            
            # Log summary
            for action, files in changes_by_action.items():
                print(f"[FolderWatcher]   {action}: {len(files)} file(s)")
            
            # Execute callback with changes
            if self.callback:
                self.callback(changes_to_process, incremental=True)
            
            _last_scan_end_time = time.time()
            duration = _last_scan_end_time - _last_scan_start_time
            print(f"[FolderWatcher] Incremental update completed in {duration:.2f}s")
            
        except Exception as e:
            _last_scan_end_time = time.time()
            print(f"[FolderWatcher] Error during incremental update: {e}")
            import traceback
            traceback.print_exc()
    
    def on_created(self, event: FileSystemEvent):
        """Handle file creation."""
        if event.is_directory:
            return
        
        src_path = event.src_path
        if self._should_ignore(src_path) or not self._is_supported_file(src_path):
            return
        
        with self.lock:
            # Remove any previous delete actions for this file
            self.pending_changes.discard(('delete', src_path))
            self.pending_changes.add(('add', src_path))
        
        print(f"[FolderWatcher] File created: {src_path}")
        self._schedule_update()
    
    def on_modified(self, event: FileSystemEvent):
        """Handle file modification."""
        if event.is_directory:
            return
        
        src_path = event.src_path
        if self._should_ignore(src_path) or not self._is_supported_file(src_path):
            return
        
        with self.lock:
            # Treat modification as update
            self.pending_changes.add(('update', src_path))
        
        print(f"[FolderWatcher] File modified: {src_path}")
        self._schedule_update()
    
    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion."""
        if event.is_directory:
            return
        
        src_path = event.src_path
        if self._should_ignore(src_path) or not self._is_supported_file(src_path):
            return
        
        with self.lock:
            # Remove any pending add/update actions for this file
            self.pending_changes.discard(('add', src_path))
            self.pending_changes.discard(('update', src_path))
            self.pending_changes.add(('delete', src_path))
        
        print(f"[FolderWatcher] File deleted: {src_path}")
        self._schedule_update()
    
    def on_moved(self, event: FileSystemEvent):
        """Handle file move/rename."""
        if event.is_directory:
            return
        
        src_path = event.src_path
        dest_path = event.dest_path
        
        # Handle source file
        if self._is_supported_file(src_path) and not self._should_ignore(src_path):
            with self.lock:
                # Remove any pending actions for old path
                self.pending_changes.discard(('add', src_path))
                self.pending_changes.discard(('update', src_path))
                self.pending_changes.add(('delete', src_path))
            print(f"[FolderWatcher] File moved from: {src_path}")
        
        # Handle destination file
        if self._is_supported_file(dest_path) and not self._should_ignore(dest_path):
            with self.lock:
                # Add new file at destination
                self.pending_changes.discard(('delete', dest_path))
                self.pending_changes.add(('add', dest_path))
            print(f"[FolderWatcher] File moved to: {dest_path}")
        
        self._schedule_update()


def _check_full_scan_needed() -> bool:
    """Check if a full scan is needed based on time since last full scan."""
    global _last_full_scan_time
    
    if _last_full_scan_time is None:
        return True
    
    time_since_last_scan = datetime.now() - datetime.fromtimestamp(_last_full_scan_time)
    return time_since_last_scan.days >= FULL_SCAN_INTERVAL_DAYS


def _trigger_full_scan(callback: Callable):
    """Trigger a full scan of all documents."""
    global _last_scan_start_time, _last_scan_end_time, _last_full_scan_time
    
    try:
        _last_scan_start_time = time.time()
        _last_full_scan_time = _last_scan_start_time
        
        print(f"\n[FolderWatcher] Starting FULL SCAN at {datetime.fromtimestamp(_last_scan_start_time).isoformat()}")
        
        # Execute callback with full scan flag
        if callback:
            callback([], incremental=False)
        
        _last_scan_end_time = time.time()
        duration = _last_scan_end_time - _last_scan_start_time
        print(f"[FolderWatcher] Full scan completed in {duration:.2f}s")
        
    except Exception as e:
        _last_scan_end_time = time.time()
        print(f"[FolderWatcher] Error during full scan: {e}")
        import traceback
        traceback.print_exc()


def start_watching_folder(scan_callback: Callable, folder_path: Optional[str] = None, 
                         debounce_seconds: int = DEBOUNCE_SECONDS, 
                         do_initial_scan: bool = True):
    """
    Start watching a folder for changes with incremental update support.
    
    Args:
        scan_callback: Function to call when changes are detected. 
                      Signature: callback(changes: List[Tuple[str, str]], incremental: bool)
                      - changes: List of (action, filepath) tuples
                      - incremental: True for incremental update, False for full scan
        folder_path: Path to watch (defaults to app/my-docs)
        debounce_seconds: Minimum seconds between triggers (default: 10)
        do_initial_scan: Whether to perform initial full scan on startup
    
    Returns:
        dict: Status information
    """
    global _observer, _watcher_active, _callback_function, _watch_path, _last_full_scan_time
    
    # Check if already watching
    if _watcher_active:
        return {
            "status": "already_watching",
            "message": "Folder watcher is already active",
            "watch_path": str(_get_watch_path(folder_path))
        }
    
    # Determine watch path
    watch_path = _get_watch_path(folder_path)
    
    if not watch_path.exists():
        return {
            "status": "error",
            "message": f"Folder does not exist: {watch_path}",
            "watch_path": str(watch_path)
        }
    
    try:
        # Store callback and path
        _callback_function = scan_callback
        _watch_path = watch_path
        
        # Create event handler
        event_handler = IncrementalChangeHandler(
            scan_callback, 
            watch_path, 
            debounce_seconds=debounce_seconds
        )
        
        # Create and start observer
        _observer = Observer()
        _observer.schedule(event_handler, str(watch_path), recursive=True)
        _observer.start()
        _watcher_active = True
        
        print(f"[FolderWatcher] Started watching: {watch_path.absolute()}")
        print(f"[FolderWatcher] Incremental updates enabled with {debounce_seconds}s debounce")
        print(f"[FolderWatcher] Full scan interval: {FULL_SCAN_INTERVAL_DAYS} days")
        
        # Do initial full scan if requested
        if do_initial_scan:
            print(f"[FolderWatcher] Performing initial full scan...")
            _trigger_full_scan(scan_callback)
        
        return {
            "status": "started",
            "message": "Folder watcher started successfully",
            "watch_path": str(watch_path.absolute()),
            "debounce_seconds": debounce_seconds,
            "full_scan_interval_days": FULL_SCAN_INTERVAL_DAYS
        }
    except Exception as e:
        _watcher_active = False
        return {
            "status": "error",
            "message": f"Failed to start folder watcher: {str(e)}",
            "watch_path": str(watch_path)
        }


def stop_watching_folder():
    """
    Stop the folder watcher if it's running.
    
    Returns:
        dict: Status information
    """
    global _observer, _watcher_active, _callback_function, _watch_path
    
    if not _watcher_active:
        return {
            "status": "not_watching",
            "message": "Folder watcher is not currently active"
        }
    
    try:
        if _observer:
            _observer.stop()
            _observer.join(timeout=5)
            _observer = None
        
        _watcher_active = False
        _callback_function = None
        _watch_path = None
        
        print("[FolderWatcher] Stopped watching folder")
        
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
    Get the timestamp of the last scan.
    
    Returns:
        dict: Scan timing information
    """
    global _last_scan_start_time, _last_scan_end_time, _last_full_scan_time
    
    if not _watcher_active:
        return {
            "status": "not_watching",
            "message": "Folder watcher is not currently active"
        }
    
    if _last_scan_start_time is None:
        return {
            "status": "no_scans_yet",
            "message": "No scans have been triggered yet"
        }
    
    start_dt = datetime.fromtimestamp(_last_scan_start_time)
    result = {
        "status": "success",
        "scan_start_timestamp": _last_scan_start_time,
        "scan_start_time": start_dt.isoformat(),
        "scan_start_time_formatted": start_dt.strftime("%Y-%m-%d %H:%M:%S")
    }
    
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
        result["scan_status"] = "in_progress"
    
    # Add last full scan info
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
    This should be called periodically (e.g., on startup or from a timer).
    
    Returns:
        dict: Status information
    """
    global _callback_function
    
    if not _watcher_active:
        return {
            "status": "not_watching",
            "message": "Folder watcher is not currently active"
        }
    
    if _check_full_scan_needed():
        _trigger_full_scan(_callback_function)
        return {
            "status": "full_scan_triggered",
            "message": "Full scan was needed and has been triggered"
        }
    else:
        days_since = (datetime.now() - datetime.fromtimestamp(_last_full_scan_time)).days
        days_until = FULL_SCAN_INTERVAL_DAYS - days_since
        return {
            "status": "full_scan_not_needed",
            "message": f"Full scan not needed yet. Next scan in {days_until} day(s)"
        }


def force_full_scan():
    """
    Force a full scan immediately regardless of schedule.
    
    Returns:
        dict: Status information
    """
    global _callback_function
    
    if not _watcher_active:
        return {
            "status": "not_watching",
            "message": "Folder watcher is not currently active"
        }
    
    _trigger_full_scan(_callback_function)
    return {
        "status": "full_scan_triggered",
        "message": "Full scan has been triggered"
    }


def is_watching():
    """
    Check if the folder watcher is currently active.
    
    Returns:
        bool: True if watching, False otherwise
    """
    return _watcher_active


def _get_watch_path(folder_path: Optional[str] = None) -> Path:
    """
    Get the path to watch.
    
    Args:
        folder_path: Optional custom path
    
    Returns:
        Path: Path object to watch
    """
    if folder_path:
        return Path(folder_path)
    
    # Default to app/my-docs relative to BASE_DIR
    return BASE_DIR / "app" / "my-docs"


# Standalone script support (for backward compatibility)
if __name__ == "__main__":
    import sys
    import subprocess
    
    def simple_callback(changes, incremental):
        """Simple callback for standalone mode."""
        if incremental:
            print(f"[FolderWatcher] Processing {len(changes)} incremental changes")
            for action, filepath in changes:
                print(f"[FolderWatcher]   {action}: {filepath}")
        else:
            print("[FolderWatcher] Performing full scan")
        
        # Trigger full scan script (for backward compatibility)
        try:
            result = subprocess.run(
                ["python", "-m", "app.add_docs_to_database", "--doc-dir", "/app/docs"],
                capture_output=True,
                text=True,
                check=True,
                timeout=600
            )
            print(f"[FolderWatcher] Scan output: {result.stdout}")
            if result.stderr:
                print(f"[FolderWatcher] Scan errors: {result.stderr}")
        except subprocess.TimeoutExpired:
            print("[FolderWatcher] Scan timed out")
        except Exception as e:
            print(f"[FolderWatcher] Error running scan: {e}")
    
    if len(sys.argv) < 2:
        print("Usage: python folder_watcher.py <folder_path>")
        sys.exit(1)
    
    folder_to_watch = sys.argv[1]
    result = start_watching_folder(simple_callback, folder_path=folder_to_watch)
    
    if result["status"] != "started":
        print(f"Error: {result['message']}")
        sys.exit(1)
    
    print(f"Watching folder: {result['watch_path']}")
    print("Press Ctrl+C to stop watching\n")
    
    try:
        while True:
            time.sleep(60)
            # Check if full scan is needed every minute
            trigger_full_scan_if_needed()
    except KeyboardInterrupt:
        print("\n[FolderWatcher] Stopping...")
        stop_watching_folder()
        print("[FolderWatcher] Stopped")
