import sys
import time
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class DebounceHandler(FileSystemEventHandler):
    def __init__(self, callback, debounce_seconds=180):
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.last_triggered = 0
        
    def on_any_event(self, event):
        # Ignore directory events and temporary files
        if event.is_directory:
            return
            
        # Check if enough time has passed since last trigger
        current_time = time.time()
        if current_time - self.last_triggered >= self.debounce_seconds:
            print(f"Change detected: {event.event_type} - {event.src_path}")
            self.last_triggered = current_time
            self.callback()
        else:
            time_remaining = int(self.debounce_seconds - (current_time - self.last_triggered))
            print(f"Change detected but debounced ({time_remaining}s remaining)")

def trigger_subprocess():
    """
    This function runs when a file change is detected.
    Replace the command below with your actual subprocess.
    """
    print("Triggering subprocess...")
    try:


        result = subprocess.run(
            ["python", "-m", "app.add_docs_to_database", "--doc-dir", "/app/docs"],
            capture_output=True,
            text=True,
            check=True,
            timeout=600
        )



        print(f"Subprocess output: {result.stdout}")
        if result.stderr:
            print(f"Subprocess errors: {result.stderr}")
    except subprocess.TimeoutExpired:
        print("Subprocess timed out")
    except Exception as e:
        print(f"Error running subprocess: {e}")

def watch_folder(folder_path):
    """
    Watch a folder for changes and trigger subprocess with debouncing.
    """
    path = Path(folder_path)
    if not path.exists():
        print(f"Error: Folder '{folder_path}' does not exist")
        sys.exit(1)
    
    print(f"Watching folder: {path.absolute()}")
    print("Press Ctrl+C to stop watching\n")
    
    # Create event handler with 3-minute (180 seconds) debounce
    event_handler = DebounceHandler(trigger_subprocess, debounce_seconds=180)
    
    # Create observer and schedule it
    observer = Observer()
    observer.schedule(event_handler, str(path), recursive=True)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping file watcher...")
        observer.stop()
    
    observer.join()
    print("File watcher stopped")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python file_watcher.py <folder_path>")
        sys.exit(1)
    
    folder_to_watch = sys.argv[1]
    watch_folder(folder_to_watch)