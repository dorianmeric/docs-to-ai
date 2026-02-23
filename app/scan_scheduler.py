"""
Scan Scheduler Module - Handles periodic full scans and scan timing logic.

This module provides functions for scheduling and triggering full document scans
to ensure data consistency.
"""

import json
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from .config import (
    FULL_SCAN_INTERVAL_DAYS,
    BASE_DIR,
    CHROMADB_DIR
)

_last_scan_time: Optional[float] = None
_last_scan_duration: Optional[float] = None
_last_full_scan_time: Optional[float] = None
_scan_in_progress = False
_scan_in_progress_lock = threading.Lock()

_scan_state_file = CHROMADB_DIR / "scan_state.json"


def _load_scan_state():
    """Load scan timing state from disk."""
    global _last_scan_time, _last_full_scan_time
    
    try:
        if _scan_state_file.exists():
            with open(_scan_state_file, 'r') as f:
                state = json.load(f)
                _last_scan_time = state.get('last_scan_time')
                _last_full_scan_time = state.get('last_full_scan_time')
    except Exception as e:
        print(f"[ScanScheduler] Error loading scan state: {e}", flush=True)


def _save_scan_state():
    """Save scan timing state to disk."""
    global _last_scan_time, _last_full_scan_time
    
    try:
        CHROMADB_DIR.mkdir(parents=True, exist_ok=True)
        state = {
            'last_scan_time': _last_scan_time,
            'last_full_scan_time': _last_full_scan_time
        }
        with open(_scan_state_file, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"[ScanScheduler] Error saving scan state: {e}", flush=True)


def _check_full_scan_needed() -> bool:
    """Check if a full scan is needed based on time since last full scan.
    
    Returns:
        True if a full scan should be performed
    """
    global _last_full_scan_time
    
    if _last_full_scan_time is None:
        return True
    
    current_time = time.time()
    days_since = (current_time - _last_full_scan_time) / (24 * 3600)
    
    return days_since >= FULL_SCAN_INTERVAL_DAYS


def _trigger_full_scan(callback: Callable):
    """Trigger a full scan using the provided callback.
    
    Args:
        callback: Function to call for full scan (receives empty changes list)
    """
    global _last_full_scan_time, _scan_in_progress
    
    with _scan_in_progress_lock:
        if _scan_in_progress:
            return
        _scan_in_progress = True
    
    _last_full_scan_time = time.time()
    _save_scan_state()
    
    try:
        callback([], incremental=False)
    except Exception as e:
        print(f"[ScanScheduler] Error during full scan: {e}", flush=True)
    finally:
        with _scan_in_progress_lock:
            _scan_in_progress = False


def update_scan_time(duration_seconds: float = 0):
    """Update the last scan time.
    
    Args:
        duration_seconds: Duration of the scan in seconds
    """
    global _last_scan_time, _last_scan_duration
    
    _last_scan_time = time.time()
    _last_scan_duration = duration_seconds
    _save_scan_state()


def get_scan_timing_info() -> Dict:
    """Get detailed timing information about scans.
    
    Returns:
        Dictionary with scan timing information
    """
    global _last_scan_time, _last_scan_duration, _last_full_scan_time, _scan_in_progress
    
    info = {
        'scan_in_progress': _scan_in_progress,
        'last_scan_time': _last_scan_time,
        'last_full_scan_time': _last_full_scan_time,
    }
    
    if _last_scan_time:
        info['last_scan_time_formatted'] = time.ctime(_last_scan_time)
    
    if _last_full_scan_time:
        info['last_full_scan_time_formatted'] = time.ctime(_last_full_scan_time)
        days_since = (time.time() - _last_full_scan_time) / (24 * 3600)
        info['days_since_full_scan'] = int(days_since)
        info['next_full_scan_due'] = days_since >= FULL_SCAN_INTERVAL_DAYS
    
    return info
