# hpy_core/watching.py
"""File watching logic using watchfiles."""

import os
import sys
import time
import shutil
import traceback
from pathlib import Path
from typing import Optional, Dict, Set, Any

try:
    from watchfiles import watch, Change
    WATCHFILES_AVAILABLE = True
except ImportError:
    WATCHFILES_AVAILABLE = False
    # Define Change enum for type hinting if watchfiles is not installed
    class Change: # type: ignore
        added = 1
        modified = 2
        deleted = 3

# Import from other modules in the package
from .config import (
    LAYOUT_FILENAME, WATCHER_DEBOUNCE_INTERVAL,
    load_config, find_project_root, DEFAULT_STATIC_DIR_NAME
)
from .building import compile_hpy_file, copy_and_inject_py_script, _copy_static_assets, compile_directory
from .parsing import parse_hpy_file

# --- Helper Functions for Watcher ---

def _parse_layout_content(layout_file_path: Path, verbose: bool = False) -> Optional[Dict[str, Any]]:
    """Parses the layout file if it exists."""
    if layout_file_path.is_file():
        if verbose: print(f"DEBUG: Parsing layout file: {layout_file_path.name}")
        try:
            return parse_hpy_file(str(layout_file_path), is_layout=True, verbose=verbose)
        except Exception as e:
            print(f"Warning: Error parsing layout '{layout_file_path.name}': {e}", file=sys.stderr)
            return None
    if verbose: print(f"DEBUG: Layout file '{layout_file_path.name}' not found.")
    return None

def _get_source_py_dependency_for_hpy(hpy_file: Path, input_dir: Path, static_dir_name: Optional[str], verbose: bool = False) -> Optional[Path]:
    """
    Parses an HPY file to determine its source Python script dependency (explicit or conventional).
    Returns the absolute path to the source .py file if valid, otherwise None.
    """
    try:
        parsed_data = parse_hpy_file(str(hpy_file), is_layout=False, verbose=False) # Verbose off for scanning
        explicit_src = parsed_data.get('script_src')
        source_static_dir_abs = input_dir / static_dir_name if static_dir_name else None

        if explicit_src:
            # Resolve explicit src relative to the hpy file
            potential_src_py = (hpy_file.parent / explicit_src).resolve()
            if not potential_src_py.is_file():
                if verbose: print(f"DEBUG: Watcher: Explicit script '{explicit_src}' in '{hpy_file.name}' not found. Ignoring.", file=sys.stderr)
                return None
            # Check if script is within input_dir (for security/simplicity)
            try: potential_src_py.relative_to(input_dir)
            except ValueError:
                 if verbose: print(f"DEBUG: Watcher: Explicit script '{explicit_src}' in '{hpy_file.name}' points outside input dir. Ignoring.", file=sys.stderr)
                 return None
            if source_static_dir_abs and potential_src_py.is_relative_to(source_static_dir_abs):
                 if verbose: print(f"DEBUG: Watcher: Explicit script '{explicit_src}' in '{hpy_file.name}' points inside static dir. Ignoring.", file=sys.stderr)
                 return None
            return potential_src_py
        else:
            # No explicit src, check for conventional .py file
            conventional_py_file = hpy_file.with_suffix('.py')
            if conventional_py_file.is_file():
                resolved_conv_py = conventional_py_file.resolve()
                if source_static_dir_abs and resolved_conv_py.is_relative_to(source_static_dir_abs):
                    if verbose: print(f"DEBUG: Watcher: Conventional script '{resolved_conv_py.name}' for '{hpy_file.name}' is in static dir. Ignoring.")
                    return None
                return resolved_conv_py
    except Exception as e:
        if verbose: print(f"DEBUG: Watcher: Error determining script dependency for {hpy_file.name}: {e}", file=sys.stderr)
    return None


def _rebuild_single_hpy_file(
    hpy_file_to_rebuild: Path,
    input_dir: Path, # Absolute path to the project's input directory (e.g., src/)
    output_dir: Path, # Absolute path to the project's output directory (e.g., dist/)
    layout_content: Optional[Dict[str, Any]],
    static_dir_name: Optional[str], # Name of the static directory (e.g., "static")
    verbose: bool = False
):
    """Rebuilds a single HPY file and its associated Python script if any."""
    if not hpy_file_to_rebuild.is_file():
        if verbose: print(f"DEBUG: Watcher: HPY file '{hpy_file_to_rebuild.name}' not found for rebuild. Skipping.")
        return

    print(f"\nRebuilding page: {hpy_file_to_rebuild.name}...")
    try:
        relative_hpy_path = hpy_file_to_rebuild.relative_to(input_dir)
        output_html_path = (output_dir / relative_hpy_path).with_suffix('.html')
        output_html_path.parent.mkdir(parents=True, exist_ok=True)

        external_script_src_for_html: Optional[str] = None
        source_py_script_abs = _get_source_py_dependency_for_hpy(hpy_file_to_rebuild, input_dir, static_dir_name, verbose)

        if source_py_script_abs and source_py_script_abs.is_file():
            relative_py_path_from_input = source_py_script_abs.relative_to(input_dir)
            output_py_path_abs = (output_dir / relative_py_path_from_input).resolve()
            
            copy_and_inject_py_script(source_py_script_abs, output_py_path_abs, verbose)
            external_script_src_for_html = os.path.relpath(output_py_path_abs, start=output_html_path.parent)
            if verbose: print(f"  Processed Python script '{source_py_script_abs.name}' -> '{output_py_path_abs.name}'")
        else:
            # If no source script, or it's invalid, ensure no corresponding .py file in output based on hpy name
            # (covers case where a .py was deleted, or hpy changed from script to inline)
            conventional_output_py = (output_dir / relative_hpy_path).with_suffix('.py')
            if conventional_output_py.exists():
                try:
                    conventional_output_py.unlink()
                    if verbose: print(f"  Removed orphaned output script: {conventional_output_py.name}")
                except OSError as e_rm:
                    if verbose: print(f"  Warning: Could not remove orphaned script '{conventional_output_py.name}': {e_rm}", file=sys.stderr)


        compile_hpy_file(
            str(hpy_file_to_rebuild),
            str(output_html_path),
            layout_content,
            external_script_src_for_html,
            verbose
        )
        print(f"Successfully rebuilt: {hpy_file_to_rebuild.name} -> {output_html_path.name}")

    except Exception as e:
        print(f"Error rebuilding {hpy_file_to_rebuild.name}: {e}", file=sys.stderr)
        if verbose: traceback.print_exc()

def _remove_hpy_outputs(
    hpy_file_path: Path, # Path to the deleted .hpy file in source
    input_dir: Path,
    output_dir: Path,
    verbose: bool = False
):
    """Removes corresponding .html and potentially .py outputs for a deleted .hpy file."""
    print(f"\nProcessing deletion of page: {hpy_file_path.name}...")
    try:
        relative_hpy_path = hpy_file_path.relative_to(input_dir)
        output_html_path = (output_dir / relative_hpy_path).with_suffix('.html')
        # Also try to remove a conventionally named output .py file
        output_py_path_conventional = (output_dir / relative_hpy_path).with_suffix('.py')
        # And output .py file that might have been based on an explicit src attribute
        # This is harder to predict without parsing the file before deletion. For now, just conventional.

        if output_html_path.exists():
            output_html_path.unlink()
            if verbose: print(f"  Deleted output HTML: {output_html_path.name}")
        if output_py_path_conventional.exists():
            output_py_path_conventional.unlink()
            if verbose: print(f"  Deleted conventional output Python: {output_py_path_conventional.name}")
        
        # Attempt to clean up empty parent directories in output
        current_parent = output_html_path.parent
        while current_parent != output_dir and current_parent.exists() and not any(current_parent.iterdir()):
            if verbose: print(f"  Deleting empty output directory: {current_parent.name}")
            current_parent.rmdir()
            current_parent = current_parent.parent


    except ValueError: # If hpy_file_path is not relative to input_dir (should not happen if logic is correct)
        if verbose: print(f"  Error: Could not determine relative path for deleted HPY '{hpy_file_path.name}'.")
    except Exception as e:
        print(f"  Error removing outputs for {hpy_file_path.name}: {e}", file=sys.stderr)

def _handle_static_file_change(
    change_type: Change,
    changed_path_abs: Path, # Absolute path to the changed file/dir in source
    source_static_root_abs: Path, # Absolute path to the root of source static dir
    target_static_root_abs: Path, # Absolute path to the root of target static dir
    verbose: bool = False
):
    """Handles changes to static files or directories."""
    try:
        relative_path_to_static_root = changed_path_abs.relative_to(source_static_root_abs)
    except ValueError:
        if verbose: print(f"DEBUG: Static file '{changed_path_abs.name}' not relative to static root '{source_static_root_abs}'. Skipping.")
        return

    target_path_abs = target_static_root_abs / relative_path_to_static_root
    action_str_map = {Change.added: "Copying", Change.modified: "Updating", Change.deleted: "Deleting"}
    action_str = action_str_map.get(change_type, "Handling")
    asset_type = "directory" if changed_path_abs.is_dir() else "file" # Check original source for type on delete

    print(f"\n{action_str} static {asset_type}: {relative_path_to_static_root}")

    if change_type == Change.deleted:
        if target_path_abs.exists():
            try:
                if target_path_abs.is_dir(): # Check target, not source which is gone
                    shutil.rmtree(target_path_abs)
                else:
                    target_path_abs.unlink()
                if verbose: print(f"  Deleted from output: {target_path_abs}")
            except Exception as e:
                print(f"  Error deleting static asset from output '{target_path_abs}': {e}", file=sys.stderr)
        elif verbose:
            print(f"  Target static asset '{target_path_abs}' already deleted.")
    else: # Added or Modified
        try:
            target_path_abs.parent.mkdir(parents=True, exist_ok=True)
            if changed_path_abs.is_dir():
                shutil.copytree(changed_path_abs, target_path_abs, dirs_exist_ok=True)
            else:
                shutil.copy2(changed_path_abs, target_path_abs)
            if verbose: print(f"  Processed to output: {target_path_abs}")
        except Exception as e:
            print(f"  Error copying static asset to output '{target_path_abs}': {e}", file=sys.stderr)

def _trigger_full_rebuild(input_dir: Path, output_dir: Path, project_root:Optional[Path], verbose: bool = False):
    """Invokes the main compile_directory which handles full project build."""
    print("\nTriggering full project rebuild...")
    try:
        # compile_directory takes strings
        compile_directory(str(input_dir), str(output_dir), verbose)
        print("Full project rebuild completed.")
    except Exception as e:
        print(f"Error during full project rebuild: {e}", file=sys.stderr)
        if verbose: traceback.print_exc()


# --- Main Watch Function ---
def start_watching(
    watch_target_str: str, # For directory mode, this is input_dir. For file mode, the file itself.
    is_directory_mode: bool,
    input_dir_abs_str: str, # The resolved input directory (e.g. "src")
    output_dir_abs_str: str,
    verbose: bool = False
):
    """Starts the file watcher using watchfiles."""
    if not WATCHFILES_AVAILABLE:
        print("Error: File watching requires 'watchfiles' library. `pip install watchfiles`", file=sys.stderr)
        sys.exit(1)

    input_dir_path = Path(input_dir_abs_str).resolve()
    output_dir_path = Path(output_dir_abs_str).resolve()
    
    project_root = find_project_root(input_dir_path) # Find hpy.toml root
    config = load_config(project_root)
    static_dir_name = config.get("static_dir_name") # May be None
    source_static_dir_abs = input_dir_path / static_dir_name if static_dir_name else None
    
    layout_file_abs = input_dir_path / LAYOUT_FILENAME
    
    # Initial parse of layout, remains in memory
    current_layout_content = _parse_layout_content(layout_file_abs, verbose)

    # Determine what to watch
    paths_to_watch = [Path(watch_target_str).resolve()]
    if is_directory_mode:
        print(f"Watching directory '{paths_to_watch[0]}' for changes with watchfiles...")
    else: # Single file mode
        # For single file, watch_target_str is the file, input_dir_abs_str is its parent (context)
        print(f"Watching single file '{paths_to_watch[0].name}' for changes with watchfiles...")
        # In single file mode, layout and static dirs are typically not automatically used from context,
        # unless specified. For simplicity, single file watch will not auto-use layout or static.
        # This matches behavior of direct `hpy file.hpy` compilation.
        current_layout_content = None # No layout for single file watch by default
        source_static_dir_abs = None # No static handling for single file watch by default


    print("-" * 50)
    print("Press Ctrl+C to stop watcher.")
    print("-" * 50)
    
    try:
        for changes in watch(
            *paths_to_watch,
            watch_filter=None, # Could add a filter later if needed
            debounce=int(WATCHER_DEBOUNCE_INTERVAL * 1000), # ms
            yield_on_timeout=False,
            # stop_event can be used for programmatic stopping if needed later
        ):
            print(f"\nDEBUG: watchfiles detected changes: {changes}")
            
            # --- Prioritize Layout Changes for Full Rebuild (only in directory mode) ---
            if is_directory_mode:
                layout_changed_this_batch = False
                for change_type, path_str in changes:
                    if Path(path_str).resolve() == layout_file_abs:
                        print(f"DEBUG: Layout file '{LAYOUT_FILENAME}' changed (Event: {change_type.name}). Re-parsing...")
                        current_layout_content = _parse_layout_content(layout_file_abs, verbose)
                        layout_changed_this_batch = True
                        break # One layout change is enough to trigger full rebuild
                
                if layout_changed_this_batch:
                    _trigger_full_rebuild(input_dir_path, output_dir_path, project_root, verbose)
                    continue # Skip individual file processing for this batch

            # --- Process Individual File Changes ---
            for change_type, path_str in changes:
                changed_path_abs = Path(path_str).resolve()
                
                # If not directory mode, and changed path is not the initially watched file, skip
                if not is_directory_mode and changed_path_abs != paths_to_watch[0]:
                    if verbose: print(f"DEBUG: Single file mode: Ignoring change to '{changed_path_abs.name}' as it's not '{paths_to_watch[0].name}'.")
                    continue

                # A. Static File Handling (only in directory mode)
                if is_directory_mode and source_static_dir_abs and changed_path_abs.is_relative_to(source_static_dir_abs):
                    target_static_root_abs = output_dir_path / static_dir_name if static_dir_name else output_dir_path # Should have static_dir_name
                    _handle_static_file_change(change_type, changed_path_abs, source_static_dir_abs, target_static_root_abs, verbose)
                    continue

                # B. Layout File (already handled if it triggered full rebuild, but direct changes here too)
                # This secondary check handles if layout was the *only* thing changed and didn't trigger above.
                if is_directory_mode and changed_path_abs == layout_file_abs:
                    # Already handled by the priority full rebuild logic above this loop if it was part of a batch
                    # If it's the only change, it would have been caught there.
                    # This can be a no-op or a redundant re-parse/rebuild if logic above is robust.
                    # For safety, if it reaches here (e.g. single change was layout) ensure rebuild.
                    if verbose: print(f"DEBUG: Layout file '{LAYOUT_FILENAME}' change processed individually. Triggering full rebuild.")
                    current_layout_content = _parse_layout_content(layout_file_abs, verbose) # Re-parse
                    _trigger_full_rebuild(input_dir_path, output_dir_path, project_root, verbose)
                    break # Break from this inner loop for changes, outer loop will catch next batch

                # C. HPY Page File Handling
                if changed_path_abs.suffix.lower() == '.hpy': # And not layout
                    if change_type == Change.deleted:
                        _remove_hpy_outputs(changed_path_abs, input_dir_path, output_dir_path, verbose)
                    else: # Added or Modified
                        _rebuild_single_hpy_file(changed_path_abs, input_dir_path, output_dir_path, current_layout_content, static_dir_name if is_directory_mode else None, verbose)
                    continue
                
                # D. Python Script Handling
                if changed_path_abs.suffix.lower() == '.py':
                    print(f"DEBUG: Python script '{changed_path_abs.name}' changed (Event: {change_type.name}).")
                    
                    # If script is deleted, remove its direct output if it was copied verbatim
                    if change_type == Change.deleted:
                        try:
                            relative_py_path = changed_path_abs.relative_to(input_dir_path)
                            output_py_to_delete = (output_dir_path / relative_py_path)
                            if output_py_to_delete.exists():
                                output_py_to_delete.unlink()
                                if verbose: print(f"  Deleted corresponding output Python: {output_py_to_delete.name}")
                        except ValueError: # Not in input_dir, could be an external script not managed this way
                            pass 
                        except Exception as e_rm_py:
                            if verbose: print(f"  Error deleting output for script '{changed_path_abs.name}': {e_rm_py}")
                    
                    # Find and rebuild all HPY files that depend on this Python script
                    # In directory mode, scan all .hpy files in input_dir.
                    # In single file mode, only check the watched .hpy file.
                    hpy_files_to_check = []
                    if is_directory_mode:
                        for item in input_dir_path.rglob('*.hpy'):
                            if item.is_file() and item != layout_file_abs:
                                if source_static_dir_abs and item.is_relative_to(source_static_dir_abs):
                                    continue # Skip .hpy files inside static dir
                                hpy_files_to_check.append(item)
                    else: # Single file mode, only check the primary watched file
                        if paths_to_watch[0].suffix.lower() == '.hpy':
                             hpy_files_to_check.append(paths_to_watch[0])
                    
                    affected_hpy_pages: Set[Path] = set()
                    for hpy_page_path in hpy_files_to_check:
                        dep_py_abs = _get_source_py_dependency_for_hpy(hpy_page_path, input_dir_path, static_dir_name if is_directory_mode else None, verbose)
                        if dep_py_abs and dep_py_abs == changed_path_abs:
                            affected_hpy_pages.add(hpy_page_path)
                    
                    if affected_hpy_pages:
                        print(f"  Script '{changed_path_abs.name}' affects HPY pages: {[p.name for p in affected_hpy_pages]}. Rebuilding them...")
                        for hpy_page_to_rebuild in affected_hpy_pages:
                            _rebuild_single_hpy_file(hpy_page_to_rebuild, input_dir_path, output_dir_path, current_layout_content, static_dir_name if is_directory_mode else None, verbose)
                    elif verbose:
                        print(f"  Script '{changed_path_abs.name}' does not appear to be a direct dependency for any tracked HPY pages.")
                    continue

                # E. Directory Deletion (if watchfiles reports it distinctly and it's not static)
                # watchfiles usually reports deletions of files within a directory.
                # This is a fallback if a directory event itself is reported.
                if changed_path_abs.is_dir() and change_type == Change.deleted:
                     if not (is_directory_mode and source_static_dir_abs and changed_path_abs.is_relative_to(source_static_dir_abs)):
                        print(f"DEBUG: Directory '{changed_path_abs.name}' deleted. Individual file deletions should handle content.")
                        # Attempt to remove the corresponding empty directory from output
                        try:
                            relative_dir_path = changed_path_abs.relative_to(input_dir_path)
                            output_dir_to_remove = output_dir_path / relative_dir_path
                            if output_dir_to_remove.is_dir() and not any(output_dir_to_remove.iterdir()):
                                output_dir_to_remove.rmdir()
                                if verbose: print(f"  Removed empty output directory: {output_dir_to_remove.name}")
                        except ValueError: pass # Not relative
                        except OSError: pass # Not empty or other issue
                     continue
                
                if verbose: print(f"DEBUG: Unhandled change type or file: {changed_path_abs.name} (Event: {change_type.name})")

    except KeyboardInterrupt:
        print("\nStopping watcher (watchfiles)...")
    except Exception as e:
        print(f"\nWatcher (watchfiles) encountered an error: {e}", file=sys.stderr)
        if verbose: traceback.print_exc()
    finally:
        print("Watcher stopped.")