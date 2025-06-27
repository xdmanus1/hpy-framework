# hpy_core/watching.py
"""File watching logic using watchfiles."""

import os
import sys
import time
import shutil
import traceback
from pathlib import Path
from typing import Set

try:
    from watchfiles import watch, Change
    WATCHFILES_AVAILABLE = True
except ImportError:
    WATCHFILES_AVAILABLE = False
    class Change: # type: ignore
        added = 1
        modified = 2
        deleted = 3

from .config import (
    WATCHER_DEBOUNCE_INTERVAL, load_config, find_project_root, 
    DEFAULT_COMPONENTS_DIR, DEFAULT_STATIC_DIR_NAME
)
from .building import compile_directory

RELOAD_TRIGGER_FILENAME = ".hpy_reload"

def _touch_reload_trigger(output_dir: Path, verbose: bool = False):
    """Touches the reload trigger file in the output directory to signal a browser refresh."""
    try:
        trigger_file = output_dir / RELOAD_TRIGGER_FILENAME
        trigger_file.touch(exist_ok=True)
        if verbose: print(f"DEBUG: Touched reload trigger: {trigger_file}")
    except Exception as e:
        if verbose: print(f"DEBUG: Could not touch reload trigger file: {e}", file=sys.stderr)

def _trigger_full_rebuild(input_dir: Path, output_dir: Path, verbose: bool = False):
    """Centralized function to perform a full project rebuild."""
    print("\nChange detected, triggering full project rebuild...")
    rebuilt_successfully = False
    try:
        _, error_count = compile_directory(
            str(input_dir), str(output_dir), verbose=verbose,
            is_dev_watch_mode=True, is_production_build=False
        )
        if error_count == 0:
            print("Full project rebuild completed successfully.")
            rebuilt_successfully = True
        else:
            print(f"Full project rebuild finished with {error_count} errors.", file=sys.stderr)
    except Exception as e:
        print(f"Error during full project rebuild: {e}", file=sys.stderr)
        if verbose: traceback.print_exc()
    
    if rebuilt_successfully:
        _touch_reload_trigger(output_dir, verbose)

def _handle_static_file_change(
    change_type: Change,
    changed_path_abs: Path,
    source_static_root_abs: Path,
    target_static_root_abs: Path,
    output_dir_for_reload_trigger: Path,
    verbose: bool = False
):
    """Handles copying, updating, or deleting a single static asset."""
    try:
        relative_path = changed_path_abs.relative_to(source_static_root_abs)
    except ValueError:
        if verbose: print(f"DEBUG: Static file '{changed_path_abs.name}' not relative to static root. Skipping.")
        return

    target_path_abs = target_static_root_abs / relative_path
    action_str_map = {Change.added: "Copying", Change.modified: "Updating", Change.deleted: "Deleting"}
    action_str = action_str_map.get(change_type, "Handling")
    
    print(f"\n{action_str} static asset: {relative_path}")
    processed_successfully = False

    try:
        if change_type == Change.deleted:
            if target_path_abs.is_dir():
                shutil.rmtree(target_path_abs, ignore_errors=True)
            elif target_path_abs.is_file():
                target_path_abs.unlink(missing_ok=True)
        else:
            target_path_abs.parent.mkdir(parents=True, exist_ok=True)
            if changed_path_abs.is_dir():
                shutil.copytree(changed_path_abs, target_path_abs, dirs_exist_ok=True)
            else:
                shutil.copy2(changed_path_abs, target_path_abs)
        processed_successfully = True
        if verbose: print(f"  Processed static asset change for: {target_path_abs}")
    except Exception as e:
        print(f"  Error handling static asset '{target_path_abs}': {e}", file=sys.stderr)
    
    if processed_successfully:
        _touch_reload_trigger(output_dir_for_reload_trigger, verbose)

def start_watching(
    watch_target_str: str,
    is_directory_mode: bool,
    input_dir_abs_str: str,
    output_dir_abs_str: str,
    verbose: bool = False
):
    if not WATCHFILES_AVAILABLE:
        print("Error: Watch requires 'watchfiles'. `pip install watchfiles`", file=sys.stderr)
        sys.exit(1)

    input_dir_path = Path(input_dir_abs_str).resolve()
    output_dir_path = Path(output_dir_abs_str).resolve()
    
    config = load_config(find_project_root(input_dir_path))
    static_dir_name = config.get("static_dir_name", DEFAULT_STATIC_DIR_NAME)
    components_dir_name = config.get("components_dir", DEFAULT_COMPONENTS_DIR)
    
    source_static_dir_abs = (input_dir_path / static_dir_name) if static_dir_name else None
    
    # --- NEW: Explicitly define all paths to watch ---
    paths_to_watch: Set[Path] = set()
    if is_directory_mode:
        paths_to_watch.add(input_dir_path)
    else:
        # For single file mode, we just watch the single file.
        paths_to_watch.add(Path(watch_target_str).resolve())

    # The user might have a components dir outside of the main input dir,
    # so we resolve its path and add it if it exists and is a directory.
    components_base_dir_abs = input_dir_path / components_dir_name
    if components_base_dir_abs.is_dir():
        paths_to_watch.add(components_base_dir_abs)
    # --- END NEW ---

    print("Watching for changes...")
    if verbose:
        for p in paths_to_watch:
            print(f"  -> Watching path: '{p}'")

    _touch_reload_trigger(output_dir_path, verbose)
    print("-" * 50)
    print("Press Ctrl+C to stop watcher.")
    print("-" * 50)
    
    try:
        for changes in watch(
            *paths_to_watch,
            watch_filter=None,
            debounce=int(WATCHER_DEBOUNCE_INTERVAL * 1000),
            yield_on_timeout=False,
        ):
            if verbose: print(f"\nDEBUG: watchfiles detected changes: {changes}")
            
            has_non_static_changes = False
            
            for change_type, path_str in changes:
                changed_path = Path(path_str).resolve()
                
                # Check if the change is within the static directory
                if source_static_dir_abs and source_static_dir_abs.exists() and changed_path.is_relative_to(source_static_dir_abs):
                    _handle_static_file_change(
                        change_type, changed_path, source_static_dir_abs, 
                        output_dir_path / static_dir_name, output_dir_path, verbose
                    )
                else:
                    # If it's any other file (.hpy, .py, component, etc.), mark for full rebuild
                    has_non_static_changes = True

            # If there was at least one non-static change, trigger a single full rebuild for the entire batch.
            if has_non_static_changes:
                if not is_directory_mode:
                    print("Warning: Live reload for single-file mode is limited. For full features, use directory mode.", file=sys.stderr)
                    _touch_reload_trigger(output_dir_path, verbose)
                else:
                    _trigger_full_rebuild(input_dir_path, output_dir_path, verbose)

    except KeyboardInterrupt:
        print("\nStopping watcher (watchfiles)...")
    except Exception as e:
        print(f"\nWatcher (watchfiles) encountered an error: {e}", file=sys.stderr)
        if verbose: traceback.print_exc()
    finally:
        print("Watcher stopped.")