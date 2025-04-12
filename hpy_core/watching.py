# hpy_core/watching.py
"""File watching logic using watchdog."""

import os
import sys
import time
import shutil  # Import shutil
from pathlib import Path
from typing import Optional, Dict, Set, Tuple, Any  # Added Any for config type hint

# Try importing watchdog, handle gracefully if not available
try:
    from watchdog.observers import Observer
    from watchdog.events import (
        FileSystemEventHandler,
        FileModifiedEvent,
        FileCreatedEvent,
        FileDeletedEvent,
        DirModifiedEvent,
        DirCreatedEvent,
        DirDeletedEvent,  # Import directory events
        FileSystemEvent,
        FileMovedEvent,
        DirMovedEvent,  # Import move events
    )

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

    # Dummy classes
    class Observer:
        pass

    class FileSystemEventHandler:
        pass

    class FileModifiedEvent:
        pass

    class FileCreatedEvent:
        pass

    class FileDeletedEvent:
        pass

    class FileSystemEvent:
        pass

    class DirModifiedEvent:
        pass  # Dummy

    class DirCreatedEvent:
        pass  # Dummy

    class DirDeletedEvent:
        pass  # Dummy

    class FileMovedEvent:
        pass  # Dummy

    class DirMovedEvent:
        pass  # Dummy


# Import from other modules in the package
from .config import LAYOUT_FILENAME, WATCHER_DEBOUNCE_INTERVAL
from .config import (
    load_config,
    find_project_root,
    DEFAULT_STATIC_DIR_NAME,
)  # Added config imports
from .building import compile_hpy_file  # Don't need compile_directory here
from .parsing import parse_hpy_file

# --- Watchdog Event Handlers ---
# Guard watchdog-specific classes
if WATCHDOG_AVAILABLE:

    class HpySingleFileEventHandler(FileSystemEventHandler):
        # (Remains unchanged from previous version)
        def __init__(
            self, input_file_abs: str, output_file_abs: str, verbose: bool = False
        ):
            super().__init__()
            self.input_file_abs = input_file_abs
            self.output_file_abs = output_file_abs
            self.verbose = verbose
            self._last_triggered = 0
            self._debounce_interval = WATCHER_DEBOUNCE_INTERVAL

        def on_modified(self, event: FileModifiedEvent):
            # Only trigger if the specific file we are watching is modified
            if (
                not event.is_directory
                and Path(event.src_path).resolve()
                == Path(self.input_file_abs).resolve()
            ):
                current_time = time.time()
                if current_time - self._last_triggered > self._debounce_interval:
                    base_filename = Path(self.input_file_abs).name
                    print(f"\nChange detected in {base_filename}, rebuilding...")
                    try:
                        # Ensure output directory exists for single file watch too
                        Path(self.output_file_abs).parent.mkdir(
                            parents=True, exist_ok=True
                        )
                        compile_hpy_file(
                            self.input_file_abs,
                            self.output_file_abs,
                            layout_content=None,
                            verbose=self.verbose,
                        )
                        print(f"Rebuilt {base_filename} successfully.")
                    except Exception as e:
                        print(
                            f"Rebuild failed for {base_filename}: {e}", file=sys.stderr
                        )
                    self._last_triggered = current_time

    class HpyDirectoryEventHandler(FileSystemEventHandler):
        def __init__(
            self, input_dir_abs: str, output_dir_abs: str, verbose: bool = False
        ):
            super().__init__()
            self.input_dir = Path(input_dir_abs).resolve()
            self.output_dir = Path(output_dir_abs).resolve()
            self.verbose = verbose
            self._last_triggered: Dict[str, float] = (
                {}
            )  # Store last trigger time per path
            self._debounce_interval = WATCHER_DEBOUNCE_INTERVAL

            # --- Load Config & Determine Paths ---
            self.project_root = find_project_root(self.input_dir)
            self.config = load_config(self.project_root)
            self.static_dir_name = self.config.get("static_dir_name")  # Can be None
            self.source_static_dir: Optional[Path] = None
            self.target_static_dir: Optional[Path] = None
            self.static_handling_enabled = False
            if self.static_dir_name:
                # Ensure static dir name doesn't contain separators
                if os.sep in self.static_dir_name or ("/" in self.static_dir_name):
                    print(
                        f"Warning: Invalid 'static_dir_name' ('{self.static_dir_name}') contains path separators. Disabling static handling.",
                        file=sys.stderr,
                    )
                else:
                    self.source_static_dir = (
                        self.input_dir / self.static_dir_name
                    ).resolve()
                    self.target_static_dir = (
                        self.output_dir / self.static_dir_name
                    ).resolve()
                    self.static_handling_enabled = True
                    if verbose:
                        print(f"Static handling enabled for: '{self.static_dir_name}'")

            self.layout_file_path = self.input_dir / LAYOUT_FILENAME
            self.layout_content = self._parse_layout()
            self.page_files = self._find_page_files()
            # --- End Path Determination ---

        def _find_page_files(self) -> Set[Path]:
            """Finds all .hpy files excluding layout and those inside the static dir."""
            pages = set()
            for p in self.input_dir.glob("**/*.hpy"):
                resolved_p = p.resolve()
                # Exclude layout file
                if resolved_p == self.layout_file_path.resolve():
                    continue
                # Exclude files inside static dir if enabled
                if (
                    self.static_handling_enabled
                    and self.source_static_dir
                    and resolved_p.is_relative_to(self.source_static_dir)
                ):
                    continue
                pages.add(resolved_p)
            return pages

        def _parse_layout(self) -> Optional[Dict[str, str]]:
            if self.layout_file_path.exists():
                try:
                    return parse_hpy_file(str(self.layout_file_path), is_layout=True)
                except Exception as e:
                    print(
                        f"\nWarning: Error parsing layout '{self.layout_file_path.name}': {e}. Page builds proceed without layout.",
                        file=sys.stderr,
                    )
                    return None
            return None

        def _debounce(self, event_path: str) -> bool:
            """Checks if an event for a given path should be debounced."""
            # Use resolved path for debouncing to handle symlinks consistently
            try:
                resolved_path_str = str(Path(event_path).resolve())
            except FileNotFoundError:
                resolved_path_str = (
                    event_path  # Use original if resolve fails (e.g., during deletion)
                )

            current_time = time.time()
            last_time = self._last_triggered.get(resolved_path_str, 0)
            if current_time - last_time > self._debounce_interval:
                self._last_triggered[resolved_path_str] = current_time
                return True  # Event should proceed
            # If debounced, clear the trigger time to allow the *next* event after interval
            # self._last_triggered.pop(resolved_path_str, None) # Option: Reset debounce on block
            if self.verbose:
                print(f"Debounced event for: {Path(event_path).name}")
            return False  # Event should be ignored

        def _is_path_within_static_dir(self, path_to_check: Path) -> bool:
            """Checks if a given path is within the source static directory."""
            if not self.static_handling_enabled or not self.source_static_dir:
                return False
            try:
                # Check if path_to_check is relative to the source static directory
                path_to_check.resolve().relative_to(self.source_static_dir)
                return True
            except ValueError:
                return False  # Not relative, so not inside
            except FileNotFoundError:
                return False  # Path doesn't exist anymore

        def _get_target_static_path(self, source_path: Path) -> Optional[Path]:
            """Calculates the corresponding path in the target static directory."""
            if (
                not self.static_handling_enabled
                or not self.source_static_dir
                or not self.target_static_dir
            ):
                return None
            try:
                relative_path = source_path.resolve().relative_to(
                    self.source_static_dir
                )
                return self.target_static_dir / relative_path
            except (ValueError, FileNotFoundError):
                return None  # Not in source static or error resolving

        def _rebuild_all_pages(self, reason: str = "change"):
            """Rebuilds all known page files."""
            print(f"\nRebuilding all pages due to {reason}...")
            error_count = 0
            self.page_files = self._find_page_files()  # Refresh file list
            if not self.page_files and self.verbose:
                print("No page files found to rebuild.")

            for page_file in self.page_files:
                try:
                    relative_path = page_file.relative_to(self.input_dir)
                    output_file = (self.output_dir / relative_path).with_suffix(".html")
                    output_file.parent.mkdir(
                        parents=True, exist_ok=True
                    )  # Ensure dir exists
                    compile_hpy_file(
                        str(page_file),
                        str(output_file),
                        self.layout_content,
                        self.verbose,
                    )
                except Exception:
                    # Error should be printed by compile_hpy_file
                    error_count += 1
            status = (
                "successful"
                if error_count == 0
                else f"finished with {error_count} error(s)"
            )
            print(f"Full rebuild {status}.")

        def _rebuild_single_page(self, input_file: Path):
            """Rebuilds a single page file."""
            resolved_input = input_file.resolve()
            if resolved_input not in self.page_files:
                if self.verbose:
                    print(
                        f"Ignoring change outside known source pages: {input_file.name}"
                    )
                return

            print(f"\nRebuilding {input_file.name}...")
            try:
                relative_path = resolved_input.relative_to(self.input_dir)
                output_file = (self.output_dir / relative_path).with_suffix(".html")
                output_file.parent.mkdir(
                    parents=True, exist_ok=True
                )  # Ensure dir exists
                compile_hpy_file(
                    str(resolved_input),
                    str(output_file),
                    self.layout_content,
                    self.verbose,
                )
                if self.verbose:
                    print(f"Finished rebuilding {input_file.name}.")
            except Exception:
                # Error should be printed by compile_hpy_file
                print(
                    f"Rebuild failed for {input_file.name}."
                )  # Add specific message here too

        # --- Static Asset Handlers ---
        def _handle_static_creation_or_modification(
            self, source_path_str: str, is_dir: bool
        ):
            """Handles creation/modification of a static asset."""
            source_path = Path(source_path_str)
            target_path = self._get_target_static_path(source_path)
            if not target_path:
                return  # Should not happen if called correctly

            action = "Updating" if isinstance(self, FileModifiedEvent) else "Copying"
            asset_type = "directory" if is_dir else "file"
            print(
                f"\n{action} static {asset_type}: {source_path.relative_to(self.input_dir)} -> {target_path.relative_to(self.output_dir)}"
            )

            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if is_dir:
                    # copytree handles creation and update implicitly with dirs_exist_ok
                    shutil.copytree(source_path, target_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(source_path, target_path)  # copy2 preserves metadata
            except Exception as e:
                print(
                    f"Error copying static asset {source_path.name}: {e}",
                    file=sys.stderr,
                )

        def _handle_static_deletion(self, source_path_str: str, is_dir: bool):
            """Handles deletion of a static asset."""
            # Resolve source path *before* trying to get target, as source may not exist
            source_path = Path(
                source_path_str
            ).resolve()  # May fail if already deleted, need target calc differently
            # Calculate target based on string manipulation if source is gone
            target_path = None
            if (
                self.static_handling_enabled
                and self.source_static_dir
                and self.target_static_dir
            ):
                try:
                    # Try resolving relative path from original string if possible
                    relative_path = Path(source_path_str).relative_to(self.input_dir)
                    potential_target = (self.output_dir / relative_path).resolve()
                    # Check if this potential target is within the *intended* target static dir
                    potential_target.relative_to(self.target_static_dir)
                    target_path = potential_target
                except (ValueError, FileNotFoundError):
                    pass  # Could not determine target reliably

            if not target_path:
                if self.verbose:
                    print(
                        f"Could not determine target path for deleted static asset: {source_path_str}"
                    )
                return

            asset_type = "directory" if is_dir else "file"
            print(
                f"\nDeleting static {asset_type}: {target_path.relative_to(self.output_dir)}"
            )

            if target_path.exists():
                try:
                    if is_dir:
                        shutil.rmtree(target_path)
                    else:
                        target_path.unlink()
                except Exception as e:
                    print(
                        f"Error deleting static asset {target_path.name}: {e}",
                        file=sys.stderr,
                    )
            elif self.verbose:
                print(f"Target static asset {target_path.name} already deleted.")

        def _handle_static_move(
            self, src_path_str: str, dest_path_str: str, is_dir: bool
        ):
            """Handles moving/renaming of a static asset."""
            # Treat move as deletion of old + creation/modification of new
            print(f"\nHandling move of static asset...")
            self._handle_static_deletion(src_path_str, is_dir)
            self._handle_static_creation_or_modification(dest_path_str, is_dir)

        # --- Event Dispatcher ---
        def dispatch(self, event: FileSystemEvent):
            """Dispatch events to the appropriate handler method."""
            # Ignore directory modification events which fire often
            if isinstance(event, DirModifiedEvent):
                return

            event_path_str = getattr(event, "src_path", None)
            if not event_path_str:
                return  # Should not happen with standard events

            # --- Debounce ---
            if not self._debounce(event_path_str):
                return

            # Resolve path once
            try:
                src_path = Path(event_path_str).resolve()
            except FileNotFoundError:
                # Handle cases where the file is already gone (like deletion)
                src_path = Path(event_path_str)  # Use the original path string

            # --- Ignore events outside input dir or inside output dir ---
            # This check needs refinement for moves where dest_path might be outside
            is_move = isinstance(event, (FileMovedEvent, DirMovedEvent))
            dest_path_str = getattr(event, "dest_path", None)
            dest_path = Path(dest_path_str).resolve() if dest_path_str else None

            paths_to_check = [src_path]
            if is_move and dest_path:
                paths_to_check.append(dest_path)

            for path_to_check in paths_to_check:
                try:
                    # Check if path is inside the output directory
                    if (
                        self.output_dir in path_to_check.resolve().parents
                        or self.output_dir == path_to_check.resolve()
                    ):
                        if self.verbose:
                            print(
                                f"Ignoring event inside output dir: {path_to_check.name}"
                            )
                        return
                    # Check if path is outside the input directory (unless it's dest of move)
                    if not path_to_check.resolve().is_relative_to(self.input_dir):
                        # Allow moves *out* of input dir (results in deletion)
                        if not (is_move and path_to_check == dest_path):
                            if self.verbose:
                                print(
                                    f"Ignoring event outside input dir: {path_to_check.name}"
                                )
                            return
                except ValueError:  # Not relative to input_dir
                    if not (is_move and path_to_check == dest_path):  # Allow moves out
                        if self.verbose:
                            print(
                                f"Ignoring event outside input dir: {path_to_check.name}"
                            )
                        return
                except (
                    FileNotFoundError
                ):  # If path doesn't exist (e.g., after deletion or during move)
                    pass  # Allow processing deletions/moves
                except Exception as e:  # Catch other errors during path checks
                    if self.verbose:
                        print(f"Path check error for {path_to_check.name}: {e}")
                    return

            # --- Determine Event Type and Path ---
            is_directory = event.is_directory
            is_static = self._is_path_within_static_dir(src_path)

            # --- Handle Moved Events (FileMovedEvent, DirMovedEvent) ---
            if is_move and dest_path:
                is_dest_static = self._is_path_within_static_dir(dest_path)
                if is_static or is_dest_static:
                    # Handle move involving static dir (either source or dest)
                    self._handle_static_move(
                        event_path_str, dest_path_str, is_directory
                    )
                else:
                    # Handle move of non-static file (e.g., rename .hpy file)
                    # Treat as delete + create for simplicity -> triggers rebuilds
                    print(
                        f"\nHandling move of non-static file: {src_path.name} -> {dest_path.name}"
                    )
                    self._handle_deletion(
                        event_path_str
                    )  # Handle potential output deletion
                    self._handle_creation_or_modification(
                        dest_path_str
                    )  # Handle new file
                return  # Finished handling move

            # --- Handle Deletion Events (FileDeletedEvent, DirDeletedEvent) ---
            if isinstance(event, (FileDeletedEvent, DirDeletedEvent)):
                if is_static:
                    self._handle_static_deletion(event_path_str, is_directory)
                else:
                    # Pass original string path for deletion handling
                    self._handle_deletion(event_path_str)
                return  # Finished handling delete

            # --- Handle Creation/Modification Events (FileCreatedEvent, DirCreatedEvent, FileModifiedEvent) ---
            if isinstance(
                event, (FileCreatedEvent, DirCreatedEvent, FileModifiedEvent)
            ):
                # Check if path is inside static dir *now* (it might have been created)
                is_static = self._is_path_within_static_dir(src_path)
                if is_static:
                    self._handle_static_creation_or_modification(
                        event_path_str, is_directory
                    )
                else:
                    # Handle standard hpy/layout/other changes
                    self._handle_creation_or_modification(event_path_str)
                return  # Finished handling create/modify

        def _handle_creation_or_modification(self, path_str: str):
            """Handles Created/Modified events for non-static files."""
            path_resolved = Path(path_str).resolve()

            # If layout changed, re-parse it and rebuild all
            if path_resolved == self.layout_file_path.resolve():
                print(f"\nChange detected in layout file '{LAYOUT_FILENAME}'.")
                self.layout_content = self._parse_layout()
                self._rebuild_all_pages(reason=f"layout change")
            # If a page file changed (or was created)
            elif path_resolved.suffix.lower() == ".hpy":
                # Add to known pages if new, then rebuild
                is_new = path_resolved not in self.page_files
                self.page_files.add(path_resolved)
                if is_new:
                    print(f"\nNew page file detected: {path_resolved.name}")
                self._rebuild_single_page(path_resolved)
            # If an unknown non-hpy file changed (e.g. random .txt) - Ignore? Or trigger full rebuild?
            # For now, let's ignore non-hpy files outside static dir to avoid excessive rebuilds
            else:
                if self.verbose:
                    print(
                        f"Ignoring change in non-hpy/non-layout file: {path_resolved.name}"
                    )

        def _handle_deletion(self, deleted_path_str: str):
            """Handles Deletion events for non-static files."""
            deleted_path_resolved = Path(
                deleted_path_str
            ).resolve()  # Try resolving first

            # If layout deleted
            if deleted_path_resolved == self.layout_file_path.resolve():
                print(
                    f"\nLayout file '{LAYOUT_FILENAME}' deleted. Rebuilding all without layout.",
                    file=sys.stderr,
                )
                self.layout_content = None
                self._rebuild_all_pages(reason="layout deletion")
                return

            # If a page file deleted
            if deleted_path_resolved in self.page_files:
                print(f"\nSource page file {deleted_path_resolved.name} deleted.")
                self.page_files.discard(deleted_path_resolved)
                # Remove corresponding output file
                try:
                    relative_path = deleted_path_resolved.relative_to(self.input_dir)
                    output_file_to_delete = (
                        self.output_dir / relative_path
                    ).with_suffix(".html")
                    if output_file_to_delete.exists():
                        output_file_to_delete.unlink()
                        print(f"Removed output file: {output_file_to_delete.name}")
                    elif self.verbose:
                        print(f"Output file {output_file_to_delete.name} not found.")
                except Exception as e:
                    print(
                        f"Error removing output for {deleted_path_resolved.name}: {e}",
                        file=sys.stderr,
                    )
            # Ignore deletion of other file types


# --- Main Watch Function ---
# (start_watching function remains largely the same, just needs to instantiate the correct handler)
def start_watching(
    watch_target_str: str,
    is_directory: bool,
    input_dir_abs: str,
    output_dir_abs: str,
    verbose: bool,
):
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
        # HpyDirectoryEventHandler now handles config loading internally
        event_handler = HpyDirectoryEventHandler(input_dir_abs, output_dir_abs, verbose)
        observer.schedule(event_handler, str(target_path), recursive=True)
    else:  # Single file watching (static assets not handled in this mode)
        watch_dir = str(target_path.parent)  # Watch the directory containing the file
        # Calculate output path relative to input dir context (remains same logic)
        try:
            input_dir_path = Path(input_dir_abs)
            relative_path = target_path.relative_to(input_dir_path)
            output_file_path = Path(output_dir_abs) / relative_path.with_suffix(".html")
        except ValueError:  # Fallback if input isn't inside the context dir
            output_file_path = (
                Path(output_dir_abs) / target_path.with_suffix(".html").name
            )

        # Ensure output directory exists before starting watch
        try:
            Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(
                f"Error: Cannot create output directory for watched file: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"Watching single file '{target_path.name}'...")
        event_handler = HpySingleFileEventHandler(
            str(target_path), str(output_file_path), verbose
        )
        observer.schedule(
            event_handler, watch_dir, recursive=False
        )  # Only watch the immediate dir

    print("Press Ctrl+C to stop watcher.")
    print("-" * 50)
    observer.start()
    try:
        while observer.is_alive():
            observer.join(timeout=1)
    except FileNotFoundError:  # May happen if watched dir is deleted externally
        print(
            f"\nError: Watched path '{watch_target_str}' not found or deleted.",
            file=sys.stderr,
        )
    except KeyboardInterrupt:
        print("\nStopping watcher...")
    except Exception as e:  # Catch other potential observer errors
        print(f"\nWatcher encountered an error: {e}", file=sys.stderr)
        if verbose:
            traceback.print_exc()
    finally:
        if observer.is_alive():
            observer.stop()
        observer.join()  # Wait for observer thread to finish
    print("Watcher stopped.")
