# hpy_core/watching.py
"""File watching logic using watchdog."""

import os
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Set, Tuple

# Try importing watchdog, handle gracefully if not available
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent, FileSystemEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    # Dummy classes (Corrected)
    class Observer: pass
    class FileSystemEventHandler: pass
    class FileModifiedEvent: pass
    class FileCreatedEvent: pass
    class FileDeletedEvent: pass
    class FileSystemEvent: pass

# Import from other modules in the package
from .config import LAYOUT_FILENAME, WATCHER_DEBOUNCE_INTERVAL
from .building import compile_hpy_file, compile_directory
from .parsing import parse_hpy_file

# --- Watchdog Event Handlers ---
# Guard watchdog-specific classes
if WATCHDOG_AVAILABLE:
    class HpySingleFileEventHandler(FileSystemEventHandler):
        # --- CORRECTED __init__ ---
        def __init__(self, input_file_abs: str, output_file_abs: str, verbose: bool = False):
             super().__init__() # Call superclass initializer
             self.input_file_abs = input_file_abs
             self.output_file_abs = output_file_abs
             self.verbose = verbose
             self._last_triggered = 0
             self._debounce_interval = WATCHER_DEBOUNCE_INTERVAL
        # --- END CORRECTION ---

        def on_modified(self, event: FileModifiedEvent):
             if not event.is_directory and event.src_path == self.input_file_abs:
                 current_time = time.time()
                 if current_time - self._last_triggered > self._debounce_interval:
                     base_filename = Path(self.input_file_abs).name; print(f"\nRebuilding {base_filename}...")
                     try:
                         compile_hpy_file(self.input_file_abs, self.output_file_abs, layout_content=None, verbose=self.verbose)
                         print(f"Rebuilt {base_filename} successfully.")
                     except Exception as e: print(f"Rebuild failed for {base_filename}: {e}", file=sys.stderr)
                     self._last_triggered = current_time

    class HpyDirectoryEventHandler(FileSystemEventHandler):
        # (Code remains the same as v0.6.2 except for dispatch correction)
        def __init__(self, input_dir_abs: str, output_dir_abs: str, verbose: bool = False):
            super().__init__()
            self.input_dir = Path(input_dir_abs)
            self.output_dir = Path(output_dir_abs)
            self.layout_file_abs = str(self.input_dir / LAYOUT_FILENAME)
            self.verbose = verbose
            self._last_triggered = {}
            self._debounce_interval = WATCHER_DEBOUNCE_INTERVAL
            self.layout_content = self._parse_layout()
            self.page_files = self._find_page_files()

        def _find_page_files(self) -> Set[Path]:
             return {p.resolve() for p in self.input_dir.glob('**/*.hpy') if p.name != LAYOUT_FILENAME}

        def _parse_layout(self) -> Optional[Dict[str, str]]:
            layout_path = Path(self.layout_file_abs)
            if layout_path.exists():
                try: return parse_hpy_file(str(layout_path), is_layout=True) # Use imported parse
                except Exception as e: print(f"\nWarning: Error parsing layout '{layout_path.name}': {e}. Builds proceed without layout.", file=sys.stderr); return None
            return None

        def _debounce(self, path_str: str) -> bool:
            current_time = time.time(); last_time = self._last_triggered.get(path_str, 0)
            if current_time - last_time > self._debounce_interval: self._last_triggered[path_str] = current_time; return True
            return False

        def _rebuild_all_pages(self):
             print(f"\nRebuilding all pages...")
             error_count = 0
             self.page_files = self._find_page_files() # Refresh file list
             for page_file in self.page_files:
                 try:
                     relative_path = page_file.relative_to(self.input_dir)
                     output_file = (self.output_dir / relative_path).with_suffix('.html')
                     compile_hpy_file(str(page_file), str(output_file), self.layout_content, self.verbose) # Use imported compile
                 except Exception: error_count += 1
             if error_count == 0 and self.verbose: print("Full rebuild successful.")
             elif error_count > 0: print(f"Full rebuild finished with {error_count} error(s).", file=sys.stderr)

        def _rebuild_single_page(self, input_file: Path):
             if input_file not in self.page_files:
                 if self.verbose: print(f"Ignoring change outside known source pages: {input_file}")
                 return
             print(f"\nRebuilding {input_file.name}...")
             try:
                 relative_path = input_file.relative_to(self.input_dir)
                 output_file = (self.output_dir / relative_path).with_suffix('.html')
                 compile_hpy_file(str(input_file), str(output_file), self.layout_content, self.verbose) # Use imported compile
                 if self.verbose: print(f"Finished rebuilding {input_file.name}.")
             except Exception: print(f"Rebuild failed for {input_file.name}.")

        def _handle_deletion(self, deleted_path_str: str):
             deleted_path = Path(deleted_path_str).resolve();
             if deleted_path.suffix.lower() != '.hpy': return
             if deleted_path == Path(self.layout_file_abs).resolve():
                 print(f"\nLayout file '{LAYOUT_FILENAME}' deleted. Rebuilding all without layout.", file=sys.stderr); self.layout_content = None; self._rebuild_all_pages(); return
             self.page_files.discard(deleted_path); print(f"\nSource file {deleted_path.name} deleted, removing output...")
             try:
                 relative_path = deleted_path.relative_to(self.input_dir); output_file_to_delete = (self.output_dir / relative_path).with_suffix('.html')
                 if output_file_to_delete.exists(): output_file_to_delete.unlink(); print(f"Removed {output_file_to_delete.name}")
                 elif self.verbose: print(f"Output file {output_file_to_delete.name} not found.")
             except Exception as e: print(f"Error removing output for {deleted_path.name}: {e}", file=sys.stderr)

        # Dispatch method (Corrected in previous step v0.6.2)
        def dispatch(self, event: FileSystemEvent):
            """Dispatch events to the appropriate handler method."""
            if event.is_directory: return # Ignore directory events

            path_str = event.src_path
            path_resolved = Path(path_str).resolve()

            # Ignore events outside input dir or inside output dir
            try:
                _ = path_resolved.relative_to(self.input_dir) # Check if it's within input_dir
                # Check if it's inside the output directory
                if self.output_dir in path_resolved.parents or self.output_dir == path_resolved:
                    if self.verbose:
                         print(f"Ignoring event inside output dir: {path_str}")
                    return # Exit dispatch if inside output dir
            except ValueError:
                 # Not relative to input_dir, so ignore
                 if self.verbose:
                      print(f"Ignoring event outside input dir: {path_str}")
                 return # Exit dispatch if outside input dir

            # Debounce the event path
            if not self._debounce(path_str):
                if self.verbose: print(f"Debounced event for: {Path(path_str).name}")
                return # Exit dispatch if debounced

            # Handle Deletion
            if isinstance(event, FileDeletedEvent):
                self._handle_deletion(path_str)
                return # Finished handling

            # Handle Creation/Modification
            if isinstance(event, (FileCreatedEvent, FileModifiedEvent)):
                # Refresh page file list on creation
                if isinstance(event, FileCreatedEvent) and path_resolved.suffix.lower() == '.hpy':
                    self.page_files.add(path_resolved)

                # If layout changed, re-parse it and rebuild all
                if path_resolved == Path(self.layout_file_abs).resolve():
                    print(f"\nChange detected in layout file '{LAYOUT_FILENAME}'.")
                    self.layout_content = self._parse_layout()
                    self._rebuild_all_pages()
                # If a known page file changed, rebuild just that page
                elif path_resolved in self.page_files:
                    self._rebuild_single_page(path_resolved)
                # If an unknown .hpy file changed (could be a component - REVERTED component logic)
                elif path_resolved.suffix.lower() == '.hpy':
                    # Assume component change requires full rebuild (simple approach)
                    print(f"\nChange detected in non-page/non-layout .hpy file '{path_resolved.name}', rebuilding all pages.")
                    self._rebuild_all_pages()
                else:
                    # Other file types changed (e.g. .py, static assets) - ignore for now
                     if self.verbose: print(f"Ignoring change in non-hpy/non-layout file: {path_resolved.name}")


def start_watching(watch_target_str: str, is_directory: bool, input_dir_abs: str, output_dir_abs: str, verbose: bool):
    """Starts the watchdog observer."""
    if not WATCHDOG_AVAILABLE:
        print("Error: File watching requires the 'watchdog' library.", file=sys.stderr)
        print("Please install it: pip install watchdog", file=sys.stderr)
        sys.exit(1)

    observer = Observer()
    target_path = Path(watch_target_str).resolve()
    print("-" * 50)
    if is_directory:
        print(f"Watching directory '{watch_target_str}' recursively...")
        event_handler = HpyDirectoryEventHandler(input_dir_abs, output_dir_abs, verbose)
        observer.schedule(event_handler, str(target_path), recursive=True)
    else: # Single file watching
        watch_dir = str(target_path.parent)
        try: # Calculate output path relative to input dir context
             input_dir_path = Path(input_dir_abs); relative_path = target_path.relative_to(input_dir_path); output_file_path = Path(output_dir_abs) / relative_path.with_suffix('.html')
        except ValueError: # Fallback if input isn't inside the context dir (shouldn't happen with resolve)
            output_file_path = Path(output_dir_abs) / target_path.with_suffix('.html').name
        print(f"Watching single file '{target_path.name}'...")
        event_handler = HpySingleFileEventHandler(str(target_path), str(output_file_path), verbose) # Use corrected handler
        observer.schedule(event_handler, watch_dir, recursive=False)
    print("Press Ctrl+C to stop watcher."); print("-" * 50)
    observer.start()
    try:
        while observer.is_alive(): observer.join(timeout=1)
    except FileNotFoundError: print(f"\nError: Watched path not found.", file=sys.stderr)
    except KeyboardInterrupt: print("\nStopping watcher...")
    finally:
        if observer.is_alive(): observer.stop()
        observer.join()
    print("Watcher stopped.")