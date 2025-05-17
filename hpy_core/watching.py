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
    class Change: # type: ignore
        added = 1
        modified = 2
        deleted = 3

from .config import (
    LAYOUT_FILENAME, WATCHER_DEBOUNCE_INTERVAL,
    load_config, find_project_root, DEFAULT_STATIC_DIR_NAME
)
from .building import compile_hpy_file, copy_and_inject_py_script, compile_directory
from .parsing import parse_hpy_file

RELOAD_TRIGGER_FILENAME = ".hpy_reload"

def _touch_reload_trigger(output_dir: Path, verbose: bool = False):
    try:
        trigger_file = output_dir / RELOAD_TRIGGER_FILENAME
        trigger_file.touch(exist_ok=True)
        if verbose: print(f"DEBUG: Touched reload trigger: {trigger_file}")
    except Exception as e:
        if verbose: print(f"DEBUG: Could not touch reload trigger file: {e}", file=sys.stderr)

def _parse_layout_content(layout_file_path: Path, verbose: bool = False) -> Optional[Dict[str, Any]]:
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
    try:
        parsed_data = parse_hpy_file(str(hpy_file), is_layout=False, verbose=False)
        explicit_src = parsed_data.get('script_src')
        source_static_dir_abs = input_dir / static_dir_name if static_dir_name else None

        if explicit_src:
            potential_src_py = (hpy_file.parent / explicit_src).resolve()
            if not potential_src_py.is_file():
                if verbose: print(f"DEBUG: Watcher: Explicit script '{explicit_src}' in '{hpy_file.name}' not found. Ignoring.", file=sys.stderr)
                return None
            try: potential_src_py.relative_to(input_dir)
            except ValueError:
                 if verbose: print(f"DEBUG: Watcher: Explicit script '{explicit_src}' in '{hpy_file.name}' points outside input dir. Ignoring.", file=sys.stderr)
                 return None
            if source_static_dir_abs and source_static_dir_abs.exists() and potential_src_py.is_relative_to(source_static_dir_abs):
                 if verbose: print(f"DEBUG: Watcher: Explicit script '{explicit_src}' in '{hpy_file.name}' points inside static dir. Ignoring.", file=sys.stderr)
                 return None
            return potential_src_py
        else:
            conventional_py_file = hpy_file.with_suffix('.py')
            if conventional_py_file.is_file():
                resolved_conv_py = conventional_py_file.resolve()
                if source_static_dir_abs and source_static_dir_abs.exists() and resolved_conv_py.is_relative_to(source_static_dir_abs):
                    if verbose: print(f"DEBUG: Watcher: Conventional script '{resolved_conv_py.name}' for '{hpy_file.name}' is in static dir. Ignoring.")
                    return None
                return resolved_conv_py
    except Exception as e:
        if verbose: print(f"DEBUG: Watcher: Error determining script dependency for {hpy_file.name}: {e}", file=sys.stderr)
    return None

def _rebuild_single_hpy_file(
    hpy_file_to_rebuild: Path,
    input_dir: Path,
    output_dir: Path,
    layout_content: Optional[Dict[str, Any]],
    static_dir_name: Optional[str],
    verbose: bool = False,
    is_dev_watch_mode: bool = True # Watcher implies dev mode for rebuilds
):
    if not hpy_file_to_rebuild.is_file():
        if verbose: print(f"DEBUG: Watcher: HPY file '{hpy_file_to_rebuild.name}' not found for rebuild. Skipping.")
        return

    print(f"\nRebuilding page: {hpy_file_to_rebuild.name}...")
    rebuilt_successfully = False
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
            verbose,
            is_dev_watch_mode=is_dev_watch_mode # Pass the flag
        )
        print(f"Successfully rebuilt: {hpy_file_to_rebuild.name} -> {output_html_path.name}")
        rebuilt_successfully = True

    except Exception as e:
        print(f"Error rebuilding {hpy_file_to_rebuild.name}: {e}", file=sys.stderr)
        if verbose: traceback.print_exc()
    
    if rebuilt_successfully:
        _touch_reload_trigger(output_dir, verbose)

def _remove_hpy_outputs(
    hpy_file_path: Path,
    input_dir: Path,
    output_dir: Path,
    verbose: bool = False
):
    print(f"\nProcessing deletion of page: {hpy_file_path.name}...")
    deleted_something_significant = False
    try:
        relative_hpy_path = hpy_file_path.relative_to(input_dir)
        output_html_path = (output_dir / relative_hpy_path).with_suffix('.html')
        output_py_path_conventional = (output_dir / relative_hpy_path).with_suffix('.py')

        if output_html_path.exists():
            output_html_path.unlink()
            if verbose: print(f"  Deleted output HTML: {output_html_path.name}")
            deleted_something_significant = True
        if output_py_path_conventional.exists():
            output_py_path_conventional.unlink()
            if verbose: print(f"  Deleted conventional output Python: {output_py_path_conventional.name}")
        
        current_parent = output_html_path.parent
        while current_parent != output_dir and current_parent.exists() and not any(current_parent.iterdir()):
            if verbose: print(f"  Deleting empty output directory: {current_parent.name}")
            current_parent.rmdir()
            current_parent = current_parent.parent

    except ValueError:
        if verbose: print(f"  Error: Could not determine relative path for deleted HPY '{hpy_file_path.name}'.")
    except Exception as e:
        print(f"  Error removing outputs for {hpy_file_path.name}: {e}", file=sys.stderr)

    if deleted_something_significant:
        _touch_reload_trigger(output_dir, verbose)

def _handle_static_file_change(
    change_type: Change,
    changed_path_abs: Path,
    source_static_root_abs: Path,
    target_static_root_abs: Path,
    output_dir_for_reload_trigger: Path,
    verbose: bool = False
):
    try:
        relative_path_to_static_root = changed_path_abs.relative_to(source_static_root_abs)
    except ValueError:
        if verbose: print(f"DEBUG: Static file '{changed_path_abs.name}' not relative to static root '{source_static_root_abs}'. Skipping.")
        return

    target_path_abs = target_static_root_abs / relative_path_to_static_root
    action_str_map = {Change.added: "Copying", Change.modified: "Updating", Change.deleted: "Deleting"}
    action_str = action_str_map.get(change_type, "Handling")
    
    asset_type = "file" # Default
    if change_type == Change.deleted:
        # For deletions, source path might not exist. Check target if it helps guess type.
        if target_path_abs.is_dir(): asset_type = "directory"
    elif changed_path_abs.is_dir():
        asset_type = "directory"

    print(f"\n{action_str} static {asset_type}: {relative_path_to_static_root}")
    processed_successfully = False

    if change_type == Change.deleted:
        if target_path_abs.exists():
            try:
                if target_path_abs.is_dir():
                    shutil.rmtree(target_path_abs)
                else:
                    target_path_abs.unlink()
                if verbose: print(f"  Deleted from output: {target_path_abs}")
                processed_successfully = True
            except Exception as e:
                print(f"  Error deleting static asset from output '{target_path_abs}': {e}", file=sys.stderr)
        elif verbose:
            print(f"  Target static asset '{target_path_abs}' already deleted.")
            processed_successfully = True
    else: 
        try:
            target_path_abs.parent.mkdir(parents=True, exist_ok=True)
            if changed_path_abs.is_dir():
                shutil.copytree(changed_path_abs, target_path_abs, dirs_exist_ok=True)
            else:
                shutil.copy2(changed_path_abs, target_path_abs)
            if verbose: print(f"  Processed to output: {target_path_abs}")
            processed_successfully = True
        except Exception as e:
            print(f"  Error copying static asset to output '{target_path_abs}': {e}", file=sys.stderr)
    
    if processed_successfully and changed_path_abs.suffix.lower() in ['.css', '.js']: # Reload for CSS/JS
        _touch_reload_trigger(output_dir_for_reload_trigger, verbose)


def _trigger_full_rebuild(
    input_dir: Path,
    output_dir: Path,
    project_root:Optional[Path],
    verbose: bool = False,
    is_dev_watch_mode: bool = True # Watcher implies dev mode for rebuilds
):
    print("\nTriggering full project rebuild...")
    rebuilt_successfully = False
    try:
        compile_directory(str(input_dir), str(output_dir), verbose, is_dev_watch_mode=is_dev_watch_mode)
        print("Full project rebuild completed.")
        rebuilt_successfully = True
    except Exception as e:
        print(f"Error during full project rebuild: {e}", file=sys.stderr)
        if verbose: traceback.print_exc()
    
    if rebuilt_successfully:
        _touch_reload_trigger(output_dir, verbose)


def start_watching(
    watch_target_str: str,
    is_directory_mode: bool,
    input_dir_abs_str: str,
    output_dir_abs_str: str,
    verbose: bool = False # This verbose is for watcher's own messages
):
    if not WATCHFILES_AVAILABLE:
        print("Error: File watching requires 'watchfiles' library. `pip install watchfiles`", file=sys.stderr)
        sys.exit(1)

    input_dir_path = Path(input_dir_abs_str).resolve()
    output_dir_path = Path(output_dir_abs_str).resolve()
    
    project_root = find_project_root(input_dir_path)
    config = load_config(project_root)
    static_dir_name = config.get("static_dir_name")
    source_static_dir_abs = input_dir_path / static_dir_name if static_dir_name else None
    
    layout_file_abs = input_dir_path / LAYOUT_FILENAME
    current_layout_content = _parse_layout_content(layout_file_abs, verbose)

    # is_dev_watch_mode for compilation functions is True because start_watching itself implies it.
    # The verbose flag here is for the watcher's debug messages.
    compile_is_dev_watch_mode = True

    paths_to_watch = [Path(watch_target_str).resolve()]
    if is_directory_mode:
        print(f"Watching directory '{paths_to_watch[0]}' for changes with watchfiles...")
        _touch_reload_trigger(output_dir_path, verbose)
    else:
        print(f"Watching single file '{paths_to_watch[0].name}' for changes with watchfiles...")
        current_layout_content = None
        source_static_dir_abs = None 
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
            
            layout_changed_this_batch = False
            if is_directory_mode:
                for change_type, path_str in changes:
                    if Path(path_str).resolve() == layout_file_abs:
                        if verbose: print(f"DEBUG: Layout file '{LAYOUT_FILENAME}' changed (Event: {change_type.name}). Re-parsing...")
                        current_layout_content = _parse_layout_content(layout_file_abs, verbose)
                        layout_changed_this_batch = True
                        break 
                
                if layout_changed_this_batch:
                    _trigger_full_rebuild(input_dir_path, output_dir_path, project_root, verbose, is_dev_watch_mode=compile_is_dev_watch_mode)
                    continue

            for change_type, path_str in changes:
                changed_path_abs = Path(path_str).resolve()
                
                if not is_directory_mode and changed_path_abs != paths_to_watch[0]:
                    if verbose: print(f"DEBUG: Single file mode: Ignoring change to '{changed_path_abs.name}' as it's not '{paths_to_watch[0].name}'.")
                    continue

                if is_directory_mode and source_static_dir_abs and source_static_dir_abs.exists() and changed_path_abs.is_relative_to(source_static_dir_abs):
                    target_static_root_abs = output_dir_path / static_dir_name if static_dir_name else output_dir_path
                    _handle_static_file_change(change_type, changed_path_abs, source_static_dir_abs, target_static_root_abs, output_dir_path, verbose)
                    continue
                
                if is_directory_mode and changed_path_abs == layout_file_abs:
                    if verbose: print(f"DEBUG: Layout file '{LAYOUT_FILENAME}' change processed individually (should be rare). Triggering full rebuild.")
                    current_layout_content = _parse_layout_content(layout_file_abs, verbose)
                    _trigger_full_rebuild(input_dir_path, output_dir_path, project_root, verbose, is_dev_watch_mode=compile_is_dev_watch_mode)
                    break 

                if changed_path_abs.suffix.lower() == '.hpy':
                    if change_type == Change.deleted:
                        _remove_hpy_outputs(changed_path_abs, input_dir_path, output_dir_path, verbose)
                    else: 
                        _rebuild_single_hpy_file(changed_path_abs, input_dir_path, output_dir_path, current_layout_content, static_dir_name if is_directory_mode else None, verbose, is_dev_watch_mode=compile_is_dev_watch_mode)
                    continue
                
                if changed_path_abs.suffix.lower() == '.py':
                    if verbose: print(f"DEBUG: Python script '{changed_path_abs.name}' changed (Event: {change_type.name}).")
                    
                    py_script_affected_pages = False
                    if change_type == Change.deleted:
                        try:
                            relative_py_path = changed_path_abs.relative_to(input_dir_path)
                            output_py_to_delete = (output_dir_path / relative_py_path)
                            if output_py_to_delete.exists():
                                output_py_to_delete.unlink()
                                if verbose: print(f"  Deleted corresponding output Python: {output_py_to_delete.name}")
                        except ValueError: pass 
                        except Exception as e_rm_py:
                            if verbose: print(f"  Error deleting output for script '{changed_path_abs.name}': {e_rm_py}")
                    
                    hpy_files_to_check = []
                    if is_directory_mode:
                        for item in input_dir_path.rglob('*.hpy'):
                            if item.is_file() and item != layout_file_abs:
                                if source_static_dir_abs and source_static_dir_abs.exists() and item.is_relative_to(source_static_dir_abs):
                                    continue
                                hpy_files_to_check.append(item)
                    else: 
                        if paths_to_watch[0].suffix.lower() == '.hpy':
                             hpy_files_to_check.append(paths_to_watch[0])
                    
                    affected_hpy_pages: Set[Path] = set()
                    for hpy_page_path in hpy_files_to_check:
                        dep_py_abs = _get_source_py_dependency_for_hpy(hpy_page_path, input_dir_path, static_dir_name if is_directory_mode else None, verbose)
                        if dep_py_abs and dep_py_abs == changed_path_abs:
                            affected_hpy_pages.add(hpy_page_path)
                    
                    if affected_hpy_pages:
                        py_script_affected_pages = True
                        if verbose: print(f"  Script '{changed_path_abs.name}' affects HPY pages: {[p.name for p in affected_hpy_pages]}. Rebuilding them...")
                        for hpy_page_to_rebuild in affected_hpy_pages:
                            _rebuild_single_hpy_file(hpy_page_to_rebuild, input_dir_path, output_dir_path, current_layout_content, static_dir_name if is_directory_mode else None, verbose, is_dev_watch_mode=compile_is_dev_watch_mode)
                    elif verbose:
                        print(f"  Script '{changed_path_abs.name}' does not appear to be a direct dependency for any tracked HPY pages.")
                    
                    if not py_script_affected_pages and change_type != Change.deleted:
                         _touch_reload_trigger(output_dir_path, verbose) # If .py changed but no hpy rebuilt, still signal potential reload
                    elif change_type == Change.deleted and not affected_hpy_pages: # A .py was deleted that didn't affect pages
                         _touch_reload_trigger(output_dir_path, verbose) # Still, might be worth a reload check client-side
                    continue

                if changed_path_abs.is_dir() and change_type == Change.deleted:
                     if not (is_directory_mode and source_static_dir_abs and source_static_dir_abs.exists() and changed_path_abs.is_relative_to(source_static_dir_abs)):
                        if verbose: print(f"DEBUG: Directory '{changed_path_abs.name}' deleted. Individual file deletions should handle content.")
                        try:
                            relative_dir_path = changed_path_abs.relative_to(input_dir_path)
                            output_dir_to_remove = output_dir_path / relative_dir_path
                            if output_dir_to_remove.is_dir() and not any(output_dir_to_remove.iterdir()):
                                output_dir_to_remove.rmdir()
                                if verbose: print(f"  Removed empty output directory: {output_dir_to_remove.name}")
                        except ValueError: pass
                        except OSError: pass
                        _touch_reload_trigger(output_dir_path, verbose)
                     continue
                
                if verbose: print(f"DEBUG: Unhandled change type or file: {changed_path_abs.name} (Event: {change_type.name})")

    except KeyboardInterrupt:
        print("\nStopping watcher (watchfiles)...")
    except Exception as e:
        print(f"\nWatcher (watchfiles) encountered an error: {e}", file=sys.stderr)
        if verbose: traceback.print_exc()
    finally:
        print("Watcher stopped.")