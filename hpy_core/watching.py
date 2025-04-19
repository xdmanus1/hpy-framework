# hpy_core/watching.py
"""File watching logic using watchdog."""

import os
import sys
import time
import shutil
import traceback
from pathlib import Path
from typing import Optional, Dict, Set, Tuple, Any

# (Watchdog imports remain the same)
try:
    from watchdog.observers import Observer
    from watchdog.events import ( FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent, DirModifiedEvent, DirCreatedEvent, DirDeletedEvent, FileSystemEvent, FileMovedEvent, DirMovedEvent )
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    class Observer: pass
    class FileSystemEventHandler: pass
    class FileModifiedEvent: pass
    class FileCreatedEvent: pass
    class FileDeletedEvent: pass
    class FileSystemEvent: pass
    class DirModifiedEvent: pass
    class DirCreatedEvent: pass
    class DirDeletedEvent: pass
    class FileMovedEvent: pass
    class DirMovedEvent: pass


# Import from other modules in the package
from .config import LAYOUT_FILENAME, WATCHER_DEBOUNCE_INTERVAL
from .config import load_config, find_project_root, DEFAULT_STATIC_DIR_NAME
from .building import compile_hpy_file, copy_and_inject_py_script # Import build helpers
# --- Updated parsing import ---
from .parsing import parse_hpy_file # Parser needed for dependencies

# HpySingleFileEventHandler remains unchanged
if WATCHDOG_AVAILABLE:
    class HpySingleFileEventHandler(FileSystemEventHandler):
        # (No changes needed here)
        def __init__(self, input_file_abs: str, output_file_abs: str, verbose: bool = False):
             super().__init__(); self.input_file_abs = input_file_abs; self.output_file_abs = output_file_abs; self.verbose = verbose; self._last_triggered = 0; self._debounce_interval = WATCHER_DEBOUNCE_INTERVAL
        def on_modified(self, event: FileModifiedEvent):
             if not event.is_directory and Path(event.src_path).resolve() == Path(self.input_file_abs).resolve():
                 current_time = time.time()
                 if current_time - self._last_triggered > self._debounce_interval:
                     base_filename = Path(self.input_file_abs).name; print(f"\nChange detected in {base_filename}, rebuilding...")
                     try:
                         Path(self.output_file_abs).parent.mkdir(parents=True, exist_ok=True)
                         compile_hpy_file(self.input_file_abs, self.output_file_abs, layout_content=None, external_script_src=None, verbose=self.verbose)
                         print(f"Rebuilt {base_filename} successfully.")
                     except Exception as e: print(f"Rebuild failed for {base_filename}: {e}", file=sys.stderr)
                     self._last_triggered = current_time

    # --- HpyDirectoryEventHandler ---
    class HpyDirectoryEventHandler(FileSystemEventHandler):
        def __init__(self, input_dir_abs: str, output_dir_abs: str, verbose: bool = False):
            super().__init__()
            self.input_dir = Path(input_dir_abs).resolve()
            self.output_dir = Path(output_dir_abs).resolve()
            self.verbose = verbose
            self._last_triggered: Dict[str, float] = {}
            self._debounce_interval = WATCHER_DEBOUNCE_INTERVAL

            # --- Load Config & Determine Paths ---
            self.project_root = find_project_root(self.input_dir)
            self.config = load_config(self.project_root)
            self.static_dir_name = self.config.get("static_dir_name")
            self.source_static_dir: Optional[Path] = None
            self.target_static_dir: Optional[Path] = None
            self.static_handling_enabled = False
            if self.static_dir_name:
                if os.sep in self.static_dir_name or ('/' in self.static_dir_name): print(f"Warning: Invalid 'static_dir_name'. Disabling static handling.", file=sys.stderr)
                else:
                    self.source_static_dir = (self.input_dir / self.static_dir_name).resolve()
                    self.target_static_dir = (self.output_dir / self.static_dir_name).resolve()
                    self.static_handling_enabled = True
                    if verbose: print(f"Static handling enabled for: '{self.static_dir_name}'")

            self.layout_file_path = self.input_dir / LAYOUT_FILENAME
            self.layout_content = self._parse_layout()

            # --- Dependency Tracking ---
            self.page_files: Set[Path] = set() # Populated by map build
            # Stores the *source* path of the python script used by an hpy file
            self.hpy_dependency: Dict[Path, Optional[Path]] = {} # hpy_path -> py_path | None
            # Stores the reverse: py_path -> set of hpy_paths that depend on it
            self.script_dependents: Dict[Path, Set[Path]] = {} # py_path -> {hpy_paths}

            self._build_dependency_map() # Initial build
            # --- End Dependency Tracking ---


        def _is_path_valid(self, path: Path) -> bool:
            """Check if path is within input_dir and not in output_dir."""
            try:
                 # Resolve safely, handling potential FileNotFoundError during checks
                 resolved_path = path.resolve()
                 if self.output_dir in resolved_path.parents or self.output_dir == resolved_path: return False
                 if not resolved_path.is_relative_to(self.input_dir): return False
            except ValueError: return False # Not relative to input_dir
            except FileNotFoundError: return True # Allow check for non-existent paths (e.g., deletions)
            except Exception: return False # Other errors
            return True

        def _get_source_py_dependency(self, hpy_file: Path) -> Optional[Path]:
            """Parse hpy file, find explicit or conventional py dependency, validate it."""
            try:
                # Pass verbose to parser? Maybe not needed here, map build is enough.
                parsed_data = parse_hpy_file(str(hpy_file), is_layout=False, verbose=False)
                explicit_src = parsed_data.get('script_src')

                if explicit_src:
                    # Resolve explicit src relative to the hpy file
                    potential_src_py = (hpy_file.parent / explicit_src).resolve()
                    # --- Validation ---
                    if not potential_src_py.is_file():
                        print(f"Warning: Explicit script '{explicit_src}' in '{hpy_file.name}' not found. Ignoring.", file=sys.stderr)
                        return None
                    potential_src_py.relative_to(self.input_dir) # Check within input dir
                    if self.source_static_dir and potential_src_py.is_relative_to(self.source_static_dir):
                         print(f"Warning: Explicit script '{explicit_src}' in '{hpy_file.name}' points inside static dir. Ignoring.", file=sys.stderr)
                         return None
                    # --- End Validation ---
                    return potential_src_py
                else:
                    # No explicit src, check conventional
                    conventional_py_file = hpy_file.with_suffix('.py')
                    if conventional_py_file.exists():
                        resolved_conv_py = conventional_py_file.resolve()
                        if not (self.source_static_dir and resolved_conv_py.is_relative_to(self.source_static_dir)):
                            return resolved_conv_py
            except (ValueError, FileNotFoundError) as e: # Catch validation errors
                 print(f"Warning: Invalid script reference in {hpy_file.name}: {e}", file=sys.stderr)
                 return None
            except Exception as e: # Catch parsing errors
                 print(f"Warning: Could not parse {hpy_file.name} to find dependency: {e}", file=sys.stderr)
                 return None
            return None # No valid dependency found

        def _build_dependency_map(self):
            """Scan all .hpy files, parse them, and build the dependency maps."""
            if self.verbose: print("Building initial dependency map...")
            self.page_files.clear()
            self.hpy_dependency.clear()
            self.script_dependents.clear()

            hpy_files_found = [p for p in self.input_dir.glob('**/*.hpy') if p.name != LAYOUT_FILENAME]
            if self.source_static_dir:
                 hpy_files_found = [p for p in hpy_files_found if not p.resolve().is_relative_to(self.source_static_dir)]

            for hpy_path in hpy_files_found:
                 resolved_hpy = hpy_path.resolve()
                 self.page_files.add(resolved_hpy)
                 py_dependency = self._get_source_py_dependency(resolved_hpy)
                 self.hpy_dependency[resolved_hpy] = py_dependency
                 if py_dependency:
                     self.script_dependents.setdefault(py_dependency, set()).add(resolved_hpy)

            if self.verbose: print(f"Dependency map built. Found {len(self.page_files)} pages.")
            # Optional: Print map for debugging
            # if self.verbose:
            #      print("Dependencies (HPY -> PY):", self.hpy_dependency)
            #      print("Dependents (PY -> {HPY}):", self.script_dependents)


        def _update_dependencies(self, hpy_file: Path):
            """Update dependency maps for a single modified/created hpy file."""
            resolved_hpy = hpy_file.resolve()
            if not self._is_path_valid(resolved_hpy): return # Ignore invalid paths

            # 1. Remove old dependency links
            old_dependency = self.hpy_dependency.get(resolved_hpy)
            if old_dependency and old_dependency in self.script_dependents:
                self.script_dependents[old_dependency].discard(resolved_hpy)
                if not self.script_dependents[old_dependency]: # Remove empty set
                    del self.script_dependents[old_dependency]

            # 2. Add to page files (if not already present)
            self.page_files.add(resolved_hpy)

            # 3. Find and add new dependency links
            new_dependency = self._get_source_py_dependency(resolved_hpy)
            self.hpy_dependency[resolved_hpy] = new_dependency
            if new_dependency:
                self.script_dependents.setdefault(new_dependency, set()).add(resolved_hpy)
            if self.verbose: print(f"  Updated dependencies for {hpy_file.name}. Script: {new_dependency.name if new_dependency else 'None'}")


        def _remove_dependencies(self, hpy_file: Path):
            """Remove a deleted hpy file and its dependencies from maps."""
            resolved_hpy = hpy_file.resolve()
            self.page_files.discard(resolved_hpy)
            old_dependency = self.hpy_dependency.pop(resolved_hpy, None) # Remove from hpy->py map
            if old_dependency and old_dependency in self.script_dependents:
                self.script_dependents[old_dependency].discard(resolved_hpy)
                if not self.script_dependents[old_dependency]:
                    del self.script_dependents[old_dependency]
            if self.verbose: print(f"  Removed dependencies for deleted {hpy_file.name}")


        def _parse_layout(self) -> Optional[Dict[str, Any]]: # Updated Type hint
            if self.layout_file_path.exists():
                try: return parse_hpy_file(str(self.layout_file_path), is_layout=True, verbose=self.verbose) # Pass verbose
                except Exception as e: print(f"\nWarning: Error parsing layout '{self.layout_file_path.name}': {e}.", file=sys.stderr); return None
            return None

        def _debounce(self, event_path: str) -> bool:
            try: resolved_path_str = str(Path(event_path).resolve())
            except FileNotFoundError: resolved_path_str = event_path
            current_time = time.time(); last_time = self._last_triggered.get(resolved_path_str, 0)
            if current_time - last_time > self._debounce_interval: self._last_triggered[resolved_path_str] = current_time; return True
            # if self.verbose: print(f"Debounced event for: {Path(event_path).name}") # Can be noisy
            return False

        def _is_path_within_static_dir(self, path_to_check: Path) -> bool:
            if not self.static_handling_enabled or not self.source_static_dir: return False
            try: path_to_check.resolve().relative_to(self.source_static_dir); return True
            except (ValueError, FileNotFoundError): return False

        def _get_target_static_path(self, source_path: Path) -> Optional[Path]:
            if not self.static_handling_enabled or not self.source_static_dir or not self.target_static_dir: return None
            try: relative_path = source_path.resolve().relative_to(self.source_static_dir); return self.target_static_dir / relative_path
            except (ValueError, FileNotFoundError): return None

        def _rebuild_all_pages(self, reason: str = "change"):
            print(f"\nRebuilding all pages due to {reason}...")
            error_count = 0
            # Rebuild dependency map in case files were added/removed externally
            self._build_dependency_map()
            if not self.page_files and self.verbose: print("No page files found to rebuild.")
            for page_file in list(self.page_files): # Iterate over copy
                 try: self._rebuild_single_page(page_file)
                 except Exception: error_count += 1
            status = "successful" if error_count == 0 else f"finished with {error_count} error(s)"
            print(f"Full rebuild {status}.")


        def _rebuild_single_page(self, hpy_input_file: Path):
            """Rebuilds a single page file, processing its python dependency."""
            resolved_hpy = hpy_input_file.resolve()
            if not self._is_path_valid(resolved_hpy):
                 if self.verbose: print(f"Skipping rebuild for invalid/outside path: {hpy_input_file.name}")
                 return
            if resolved_hpy not in self.page_files:
                 # This might happen if called just after deletion during move?
                 if self.verbose: print(f"Ignoring rebuild request for non-tracked page: {hpy_input_file.name}")
                 return

            try:
                print(f"\nRebuilding {hpy_input_file.name}...")
                external_script_src_for_html: Optional[str] = None
                source_py_dependency = self.hpy_dependency.get(resolved_hpy) # Get from map
                relative_hpy_path = resolved_hpy.relative_to(self.input_dir)
                output_html_path = (self.output_dir / relative_hpy_path).with_suffix('.html')

                # Process python dependency if it exists
                if source_py_dependency:
                     # Ensure dependency still exists before trying to copy
                     if source_py_dependency.is_file():
                          # Calculate output path based on dependency's relative path from input dir
                          relative_py_path = source_py_dependency.relative_to(self.input_dir)
                          output_py_path = (self.output_dir / relative_py_path).resolve()
                          # Use helper function to copy and inject
                          copy_and_inject_py_script(source_py_dependency, output_py_path, self.verbose)
                          # Calculate src for HTML tag (relative from HTML file's dir to output py file)
                          external_script_src_for_html = os.path.relpath(output_py_path, start=output_html_path.parent)
                     else:
                          # Dependency listed but not found - remove it and warn
                          print(f"Warning: Dependency script '{source_py_dependency.name}' for '{resolved_hpy.name}' not found during rebuild. Removing dependency.", file=sys.stderr)
                          self._remove_dependencies(resolved_hpy) # Update maps fully
                          source_py_dependency = None # Ensure we don't try to use it

                # If no dependency existed OR it was just removed, ensure output py is gone
                if not source_py_dependency:
                     output_py_path = (self.output_dir / relative_hpy_path).with_suffix('.py') # Conventional output path
                     if output_py_path.exists():
                          try: output_py_path.unlink(); print(f"  Removed potentially orphaned output script: {output_py_path.name}")
                          except Exception as e: print(f"Warning: Could not remove orphaned script {output_py_path.name}: {e}", file=sys.stderr)

                # Compile the .hpy file
                output_html_path.parent.mkdir(parents=True, exist_ok=True)
                compile_hpy_file(
                    str(resolved_hpy),
                    str(output_html_path),
                    self.layout_content,
                    external_script_src_for_html,
                    self.verbose
                )
                if self.verbose: print(f"Finished rebuilding {hpy_input_file.name}.")

            except Exception as e:
                 print(f"Rebuild failed for {hpy_input_file.name}: {e}", file=sys.stderr)
                 if self.verbose: traceback.print_exc()
                 raise


        # --- Static handlers remain the same ---
        def _handle_static_creation_or_modification(self, source_path_str: str, is_dir: bool):
            source_path = Path(source_path_str); target_path = self._get_target_static_path(source_path)
            if not target_path: return
            action = "Updating" if isinstance(self, FileModifiedEvent) else "Copying"
            asset_type = "directory" if is_dir else "file"
            try:
                print(f"\n{action} static {asset_type}: {source_path.relative_to(self.input_dir)} -> {target_path.relative_to(self.output_dir)}")
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if is_dir: shutil.copytree(source_path, target_path, dirs_exist_ok=True)
                else: shutil.copy2(source_path, target_path)
            except Exception as e: print(f"Error copying static asset {source_path.name}: {e}", file=sys.stderr)

        def _handle_static_deletion(self, source_path_str: str, is_dir: bool):
            target_path = None
            if self.static_handling_enabled and self.source_static_dir and self.target_static_dir:
                 try: relative_path = Path(source_path_str).relative_to(self.input_dir); potential_target = (self.output_dir / relative_path).resolve(); potential_target.relative_to(self.target_static_dir); target_path = potential_target
                 except (ValueError, FileNotFoundError): pass
            if not target_path:
                 if self.verbose: print(f"Could not determine target path for deleted static asset: {source_path_str}")
                 return
            asset_type = "directory" if is_dir else "file"; print(f"\nDeleting static {asset_type}: {target_path.relative_to(self.output_dir)}")
            if target_path.exists():
                try:
                    if is_dir:
                        if self.target_static_dir in target_path.parents or target_path == self.target_static_dir: shutil.rmtree(target_path)
                        else: print(f"Warning: Skipped rmtree on potentially incorrect target: {target_path}")
                    else: target_path.unlink()
                except Exception as e: print(f"Error deleting static asset {target_path.name}: {e}", file=sys.stderr)
            elif self.verbose: print(f"Target static asset {target_path.name} already deleted.")

        def _handle_static_move(self, src_path_str: str, dest_path_str: str, is_dir: bool):
            print(f"\nHandling move of static asset...")
            self._handle_static_deletion(src_path_str, is_dir)
            self._handle_static_creation_or_modification(dest_path_str, is_dir)


        # --- Event Dispatcher (Simplified Routing) ---
        def dispatch(self, event: FileSystemEvent):
            if isinstance(event, DirModifiedEvent): return # Ignore noisy dir modify events
            event_path_str = getattr(event, 'src_path', None)
            if not event_path_str: return
            if not self._debounce(event_path_str): return

            # Resolve paths safely
            src_path = Path(event_path_str)
            try: src_resolved = src_path.resolve()
            except FileNotFoundError: src_resolved = src_path

            is_move = isinstance(event, (FileMovedEvent, DirMovedEvent))
            dest_path_str = getattr(event, 'dest_path', None)
            dest_path = Path(dest_path_str) if dest_path_str else None
            dest_resolved = None
            if dest_path:
                 try: dest_resolved = dest_path.resolve()
                 except FileNotFoundError: dest_resolved = dest_path

            # --- Basic Path Validation (only check source for now, moves handled later) ---
            if not self._is_path_valid(src_resolved):
                 # Allow deletion events for paths that might now be invalid
                 if not isinstance(event, (FileDeletedEvent, DirDeletedEvent)):
                      if self.verbose: print(f"Ignoring event for invalid/outside path: {src_resolved.name}")
                      return

            # --- Routing Logic ---
            is_directory = event.is_directory
            is_src_static = self._is_path_within_static_dir(src_resolved)

            # 1. Handle Static Files/Dirs
            if is_src_static:
                if is_move and dest_path_str:
                    self._handle_static_move(event_path_str, dest_path_str, is_directory)
                elif isinstance(event, (FileDeletedEvent, DirDeletedEvent)):
                    self._handle_static_deletion(event_path_str, is_directory)
                elif isinstance(event, (FileCreatedEvent, DirCreatedEvent, FileModifiedEvent)):
                    self._handle_static_creation_or_modification(event_path_str, is_directory)
                return # Handled static

            # 2. Handle Layout File
            if src_resolved == self.layout_file_path.resolve():
                if isinstance(event, FileDeletedEvent):
                     print(f"\nLayout file '{LAYOUT_FILENAME}' deleted. Rebuilding all without layout.", file=sys.stderr)
                     self.layout_content = None
                     self._rebuild_all_pages(reason="layout deletion")
                elif isinstance(event, (FileCreatedEvent, FileModifiedEvent)):
                     print(f"\nChange detected in layout file '{LAYOUT_FILENAME}'.")
                     self.layout_content = self._parse_layout() # Re-parse
                     self._rebuild_all_pages(reason=f"layout change")
                # Ignore moves of layout for now? Or treat as delete+create?
                return # Handled layout

            # 3. Handle HPY Page Files (Create/Modify/Delete/Move)
            if src_resolved.suffix.lower() == '.hpy':
                 if is_move and dest_resolved:
                      self._handle_hpy_move(src_resolved, dest_resolved)
                 elif isinstance(event, FileDeletedEvent):
                      self._handle_hpy_deletion(src_resolved)
                 elif isinstance(event, (FileCreatedEvent, FileModifiedEvent)):
                      self._handle_hpy_creation_or_modification(src_resolved)
                 return # Handled HPY

            # 4. Handle PY Script Files (Create/Modify/Delete/Move)
            if src_resolved.suffix.lower() == '.py':
                 if is_move and dest_resolved:
                      self._handle_py_move(src_resolved, dest_resolved)
                 elif isinstance(event, FileDeletedEvent):
                      self._handle_py_deletion(src_resolved)
                 elif isinstance(event, (FileCreatedEvent, FileModifiedEvent)):
                      self._handle_py_creation_or_modification(src_resolved)
                 return # Handled PY

            # 5. Ignore other files
            if self.verbose:
                 print(f"Ignoring event for unhandled file type: {src_resolved.name}")


        # --- Specific Handlers for HPY and PY files ---
        def _handle_hpy_creation_or_modification(self, hpy_path: Path):
             """Handles create/modify for an HPY file."""
             if not self._is_path_valid(hpy_path): return
             print(f"\nChange detected in page file: {hpy_path.name}")
             self._update_dependencies(hpy_path) # Update maps
             try: self._rebuild_single_page(hpy_path) # Rebuild this page
             except Exception: pass # Error logged in rebuild

        def _handle_hpy_deletion(self, hpy_path: Path):
            """Handles deletion of an HPY file."""
            # Path might not be valid anymore, but use resolved if possible
            resolved_hpy = hpy_path.resolve() if hpy_path.exists() else hpy_path
            if resolved_hpy in self.page_files: # Check if we were tracking it
                 print(f"\nPage file deleted: {resolved_hpy.name}")
                 self._remove_dependencies(resolved_hpy) # Update maps
                 # Remove corresponding output HTML and maybe PY
                 try:
                      relative_path = resolved_hpy.relative_to(self.input_dir)
                      output_html = (self.output_dir / relative_path).with_suffix('.html')
                      output_py = (self.output_dir / relative_path).with_suffix('.py')
                      if output_html.exists(): output_html.unlink(); print(f"  Removed output: {output_html.name}")
                      if output_py.exists(): output_py.unlink(); print(f"  Removed output: {output_py.name}")
                 except ValueError: pass # Cannot get relative path if input_dir deleted?
                 except Exception as e: print(f"  Error removing output files for {resolved_hpy.name}: {e}", file=sys.stderr)

        def _handle_hpy_move(self, src_path: Path, dest_path: Path):
             """Handles move/rename of an HPY file."""
             print(f"\nPage file moved: {src_path.name} -> {dest_path.name}")
             self._handle_hpy_deletion(src_path)
             # Only handle creation if destination is valid
             if self._is_path_valid(dest_path) and dest_path.suffix.lower() == '.hpy':
                 self._handle_hpy_creation_or_modification(dest_path)

        def _handle_py_creation_or_modification(self, py_path: Path):
            """Handles create/modify for a PY file."""
            if not self._is_path_valid(py_path): return
            resolved_py = py_path.resolve()
            # Check if this script is a dependency for any tracked page
            dependents = list(self.script_dependents.get(resolved_py, set())) # Iterate copy
            if dependents:
                 print(f"\nChange detected in script: {py_path.name} (used by {[p.name for p in dependents]})")
                 for hpy_dep in dependents:
                      try: self._rebuild_single_page(hpy_dep) # Rebuild pages that depend on it
                      except Exception: pass # Error logged in rebuild
            # Also check if it's a *new* conventional match for a page without explicit src
            else:
                 conventional_hpy = py_path.with_suffix('.hpy')
                 if conventional_hpy in self.page_files and self.hpy_dependency.get(conventional_hpy) is None:
                       print(f"\nConventional script created/modified for page: {py_path.name}")
                       self._update_dependencies(conventional_hpy) # Update map for this hpy
                       try: self._rebuild_single_page(conventional_hpy)
                       except Exception: pass
                 elif self.verbose:
                       print(f"Ignoring change in unused script: {py_path.name}")


        def _handle_py_deletion(self, py_path: Path):
            """Handles deletion of a PY file."""
            resolved_py = py_path.resolve() if py_path.exists() else py_path
            dependents = list(self.script_dependents.get(resolved_py, set()))
            if dependents:
                 print(f"\nDependency script deleted: {resolved_py.name} (used by {[p.name for p in dependents]})")
                 # Update maps and rebuild dependents
                 dependents_to_rebuild = set()
                 if resolved_py in self.script_dependents:
                     associated_hpys = self.script_dependents.pop(resolved_py)
                     for hpy_file in associated_hpys:
                         if self.hpy_dependency.get(hpy_file) == resolved_py:
                             self.hpy_dependency[hpy_file] = None # Remove link
                             dependents_to_rebuild.add(hpy_file)

                 # Remove corresponding output py file (use first dependent to find path)
                 if dependents_to_rebuild:
                      first_hpy = next(iter(dependents_to_rebuild))
                      try:
                           relative_py_path = resolved_py.relative_to(self.input_dir)
                           output_py = (self.output_dir / relative_py_path).resolve()
                           if output_py.exists(): output_py.unlink(); print(f"  Removed output script: {output_py.name}")
                      except ValueError: pass
                      except Exception as e: print(f"  Error removing output script for {resolved_py.name}: {e}", file=sys.stderr)

                 # Trigger rebuilds
                 for hpy_file in dependents_to_rebuild:
                     try: self._rebuild_single_page(hpy_file) # Will now use inline python
                     except Exception: pass
            elif self.verbose:
                 print(f"Ignoring deletion of unused script: {py_path.name}")


        def _handle_py_move(self, src_path: Path, dest_path: Path):
             """Handles move/rename of a PY file."""
             print(f"\nScript file moved: {src_path.name} -> {dest_path.name}")
             self._handle_py_deletion(src_path)
             # Only handle creation if destination is valid
             if self._is_path_valid(dest_path) and dest_path.suffix.lower() == '.py':
                 self._handle_py_creation_or_modification(dest_path)


# --- Main Watch Function (remains the same) ---
def start_watching(watch_target_str: str, is_directory: bool, input_dir_abs: str, output_dir_abs: str, verbose: bool):
    """Starts the watchdog observer."""
    if not WATCHDOG_AVAILABLE: print("Error: File watching requires 'watchdog'.", file=sys.stderr); sys.exit(1)

    observer = Observer()
    target_path = Path(watch_target_str).resolve()
    print("-" * 50)

    if is_directory:
        print(f"Watching directory '{watch_target_str}' recursively...")
        try:
            event_handler = HpyDirectoryEventHandler(input_dir_abs, output_dir_abs, verbose)
            if event_handler.static_handling_enabled and event_handler.target_static_dir:
                 try: event_handler.target_static_dir.mkdir(parents=True, exist_ok=True)
                 except OSError as e: print(f"Warning: Could not create target static directory '{event_handler.target_static_dir}': {e}", file=sys.stderr)
            observer.schedule(event_handler, str(target_path), recursive=True)
        except Exception as e: # Catch potential errors during handler init (e.g., map build)
             print(f"\nError initializing directory watcher: {e}", file=sys.stderr)
             if verbose: traceback.print_exc()
             sys.exit(1)
    else: # Single file watching
        watch_dir = str(target_path.parent)
        try:
             input_dir_path = Path(input_dir_abs); relative_path = target_path.relative_to(input_dir_path); output_file_path = Path(output_dir_abs) / relative_path.with_suffix('.html')
        except ValueError: output_file_path = Path(output_dir_abs) / target_path.with_suffix('.html').name
        try: Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)
        except OSError as e: print(f"Error: Cannot create output directory: {e}", file=sys.stderr); sys.exit(1)
        print(f"Watching single file '{target_path.name}'...")
        event_handler = HpySingleFileEventHandler(str(target_path), str(output_file_path), verbose)
        observer.schedule(event_handler, watch_dir, recursive=False)

    print("Press Ctrl+C to stop watcher."); print("-" * 50)
    observer.start()
    try:
        while observer.is_alive(): observer.join(timeout=1)
    except FileNotFoundError: print(f"\nError: Watched path '{watch_target_str}' not found or deleted.", file=sys.stderr)
    except KeyboardInterrupt: print("\nStopping watcher...")
    except Exception as e:
        print(f"\nWatcher encountered an error: {e}", file=sys.stderr)
        if verbose:
            traceback.print_exc()
    finally:
        if observer.is_alive(): observer.stop()
        observer.join()
    print("Watcher stopped.")