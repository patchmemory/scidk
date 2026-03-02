"""
Script file watcher - monitors scripts/ directory for changes and hot-reloads.
"""
import time
from pathlib import Path
from typing import Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent


class ScriptFileHandler(FileSystemEventHandler):
    """Handles file system events for script files."""

    def __init__(
        self,
        on_created: Optional[Callable[[Path], None]] = None,
        on_modified: Optional[Callable[[Path], None]] = None,
        on_deleted: Optional[Callable[[Path], None]] = None
    ):
        """
        Initialize handler with callbacks.

        Args:
            on_created: Callback for file creation
            on_modified: Callback for file modification
            on_deleted: Callback for file deletion
        """
        self.on_created_cb = on_created
        self.on_modified_cb = on_modified
        self.on_deleted_cb = on_deleted
        self._debounce_cache = {}  # path -> last_event_time
        self._debounce_delay = 0.5  # seconds

    def _should_process(self, file_path: Path) -> bool:
        """
        Check if file should be processed (debouncing + filtering).

        Args:
            file_path: Path to check

        Returns:
            True if should process, False otherwise
        """
        # Ignore non-script files
        if file_path.suffix not in ('.py', '.cypher'):
            return False

        # Ignore __init__.py and __pycache__
        if file_path.name == '__init__.py' or '__pycache__' in file_path.parts:
            return False

        # Ignore README files
        if file_path.name.lower().startswith('readme'):
            return False

        # Debounce rapid changes
        now = time.time()
        last_time = self._debounce_cache.get(str(file_path), 0)
        if now - last_time < self._debounce_delay:
            return False

        self._debounce_cache[str(file_path)] = now
        return True

    def on_created(self, event: FileSystemEvent):
        """Handle file creation."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if self._should_process(file_path) and self.on_created_cb:
            self.on_created_cb(file_path)

    def on_modified(self, event: FileSystemEvent):
        """Handle file modification."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if self._should_process(file_path) and self.on_modified_cb:
            self.on_modified_cb(file_path)

    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        # Don't debounce deletions
        if file_path.suffix in ('.py', '.cypher') and self.on_deleted_cb:
            self.on_deleted_cb(file_path)


class ScriptWatcher:
    """Watches scripts directory for changes and triggers hot-reload."""

    def __init__(self, scripts_dir: Path):
        """
        Initialize watcher.

        Args:
            scripts_dir: Path to scripts/ directory to watch
        """
        self.scripts_dir = scripts_dir
        self.observer = Observer()
        self.handler = None
        self._running = False

    def start(
        self,
        on_created: Optional[Callable[[Path], None]] = None,
        on_modified: Optional[Callable[[Path], None]] = None,
        on_deleted: Optional[Callable[[Path], None]] = None
    ):
        """
        Start watching for file changes.

        Args:
            on_created: Callback for file creation
            on_modified: Callback for file modification
            on_deleted: Callback for file deletion
        """
        if self._running:
            return

        self.handler = ScriptFileHandler(
            on_created=on_created,
            on_modified=on_modified,
            on_deleted=on_deleted
        )

        self.observer.schedule(self.handler, str(self.scripts_dir), recursive=True)
        self.observer.start()
        self._running = True

    def stop(self):
        """Stop watching for file changes."""
        if not self._running:
            return

        self.observer.stop()
        self.observer.join()
        self._running = False

    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._running

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
