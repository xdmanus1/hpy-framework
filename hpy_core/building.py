# hpy_core/building.py
"""Core build logic: combining content, generating HTML, handling static assets."""

import sys
import textwrap
import traceback
import shutil # Import shutil for file operations
from pathlib import Path
from typing import Dict, Optional, List, Tuple

# Import from other modules in the package
from .config import BRYTHON_VERSION, LAYOUT_FILENAME, LAYOUT_PLACEHOLDER
from .config import load_config, find_project_root, DEFAULT_STATIC_DIR_NAME # Added config helpers
from .parsing import parse_hpy_file # Use the parsing function

# build_output_html function remains unchanged
def build_output_html(final_hpy_content: Dict[str, str], output_file_path_str: str) -> str:
    """
    Build the final HTML file from the *already combined* hpy_content.
    Injects helper functions (byid, qs, qsa) before the combined Python code.
    """
    output_file_path = Path(output_file_path_str)
    output_dir = output_file_path.parent
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e: raise OSError(f"Could not create output dir {output_dir}: {e}") from e

    # Dedent the final combined Python code first
    combined_python_code = textwrap.dedent(final_hpy_content['python'])

    # --- Add Helper Function Injection Back ---
    helper_code = textwrap.dedent("""
        # --- HPY Tool Helper Functions (Injected) ---
        from browser import document
        import sys as _hpy_sys # Alias to avoid user conflicts
        def byid(element_id):
            # Shortcut for document[element_id]. Returns None if ID not found.
            try: return document[element_id]
            except KeyError: return None
        def qs(selector):
            # Shortcut for document.select_one(selector). Returns None if not found.
            return document.select_one(selector)
        def qsa(selector):
            # Shortcut for document.select(selector). Returns a list (possibly empty).
            return document.select(selector)
        # --- End Helper Functions ---

    """) # End of textwrap.dedent for helpers

    # Inject helpers *before* all other python code
    full_python_code_with_helpers = helper_code + combined_python_code
    # --- End Helper Function Injection ---


    # --- HTML Template ---
    # Use the combined content and injected python code
    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HPY Application ({output_file_path.stem})</title>
    <script src="https://cdn.jsdelivr.net/npm/brython@{BRYTHON_VERSION}/brython.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/brython@{BRYTHON_VERSION}/brython_stdlib.js"></script>
    <style>
/* --- Start Combined CSS ({output_file_path.name}) --- */
{final_hpy_content['style']}
/* --- End Combined CSS --- */
    </style>
</head>
<body onload="brython({{'debug': 1}})">

{final_hpy_content['html']}

<script type="text/python">
# --- Start Combined Python ({output_file_path.name}) ---
{full_python_code_with_helpers}
# --- End Combined Python ---
</script>

</body>
</html>"""

    try:
        with open(output_file_path, 'w', encoding='utf-8') as f: f.write(html_template)
    except IOError as e: raise IOError(f"Could not write to output file {output_file_path}: {e}") from e
    return str(output_file_path)

# compile_hpy_file function remains unchanged
def compile_hpy_file(
    input_file_path_str: str, output_file_path_str: str, layout_content: Optional[Dict[str, str]], verbose: bool = False
) -> str:
    """
    Process a single .hpy file, apply layout if provided, generate HTML.
    """
    input_file_path = Path(input_file_path_str)
    if verbose: print(f"Processing {input_file_path.name} -> {Path(output_file_path_str).name}{' (using layout)' if layout_content else ''}...")
    try:
        # Use the imported parse_hpy_file
        page_content = parse_hpy_file(input_file_path_str, is_layout=False)

        if layout_content:
            combined_style = (f"/* Layout: {LAYOUT_FILENAME} */\n{layout_content['style']}\n\n"
                              f"/* Page: {input_file_path.name} */\n{page_content['style']}")
            combined_python = (f"# Layout: {LAYOUT_FILENAME}\n{layout_content['python']}\n\n"
                               f"# Page: {input_file_path.name}\n{page_content['python']}")
            page_html_fragment = page_content['html']
            layout_html_template = layout_content['html']
            if LAYOUT_PLACEHOLDER not in layout_html_template: raise ValueError(f"Layout missing '{LAYOUT_PLACEHOLDER}'.")
            final_html = layout_html_template.replace(LAYOUT_PLACEHOLDER, page_html_fragment)
            final_hpy_content = {'html': final_html, 'style': combined_style, 'python': combined_python}
        else:
            final_hpy_content = page_content
            final_hpy_content['style'] = f"/* Page: {input_file_path.name} */\n{page_content['style']}"
            final_hpy_content['python'] = f"# Page: {input_file_path.name}\n{page_content['python']}"

        if verbose: print(f"  Final sizes: HTML={len(final_hpy_content['html'])}, CSS={len(final_hpy_content['style'])}, Py={len(final_hpy_content['python'])}")

        # Call build_output_html which NOW includes helper injection
        built_path = build_output_html(final_hpy_content, output_file_path_str)
        return built_path

    except (FileNotFoundError, ValueError, IOError, OSError, RuntimeError) as e:
        print(f"Error processing file {input_file_path.name}: {e}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"Unexpected error compiling {input_file_path.name}: {e}", file=sys.stderr)
        if verbose: traceback.print_exc()
        raise RuntimeError(f"Failed to compile {input_file_path.name}") from e

def _copy_static_assets(input_dir: Path, output_dir: Path, config: Dict, verbose: bool = False):
    """Copies static assets from input static dir to output static dir."""
    static_dir_name = config.get("static_dir_name") # Get configured name

    if not static_dir_name:
        if verbose: print("Static asset handling disabled (no 'static_dir_name' in config).")
        return # Static handling is disabled if not set in config

    source_static_dir = (input_dir / static_dir_name).resolve()
    target_static_dir = (output_dir / static_dir_name).resolve()

    if source_static_dir.is_dir():
        try:
            if verbose: print(f"Copying static assets from '{source_static_dir.relative_to(input_dir.parent)}' to '{target_static_dir.relative_to(output_dir.parent)}'...")
            shutil.copytree(source_static_dir, target_static_dir, dirs_exist_ok=True)
            if verbose: print("Static assets copied successfully.")
        except OSError as e:
            print(f"Error copying static assets: {e}", file=sys.stderr)
            # Decide if this should be fatal? For now, just warn.
    else:
        if verbose: print(f"No static directory found at '{source_static_dir.relative_to(input_dir.parent)}', skipping asset copy.")


def compile_directory(input_dir_str: str, output_dir_str: str, verbose: bool = False) -> Tuple[List[str], int]:
    """Compiles .hpy files from input_dir to output_dir, using layout file if found, and copies static assets."""
    input_dir = Path(input_dir_str).resolve()
    output_dir = Path(output_dir_str).resolve()
    layout_file_path = input_dir / LAYOUT_FILENAME
    if not input_dir.is_dir(): raise FileNotFoundError(f"Input dir not found: {input_dir_str}")

    # --- Load Config to get static_dir_name ---
    # Project root is likely the parent of the input directory
    project_root = find_project_root(input_dir)
    config = load_config(project_root)
    # --- End Config Loading ---

    print(f"\nCompiling project '{input_dir.name}' -> '{output_dir.name}'...")

    # --- Ensure Output Directory Exists ---
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"FATAL ERROR: Could not create output directory '{output_dir}': {e}", file=sys.stderr)
        raise RuntimeError("Output directory creation failed.") from e

    # --- Copy Static Assets (Before compiling pages) ---
    _copy_static_assets(input_dir, output_dir, config, verbose) # Pass loaded config

    # --- Parse Layout ---
    layout_content: Optional[Dict[str, str]] = None
    if layout_file_path.exists():
        try:
            if verbose: print(f"Parsing layout file: {LAYOUT_FILENAME}")
            layout_content = parse_hpy_file(str(layout_file_path), is_layout=True) # Use imported parse
            print(f"Using layout file: {LAYOUT_FILENAME}")
        except Exception as e:
            print(f"FATAL ERROR parsing layout '{layout_file_path.name}': {e}", file=sys.stderr)
            raise RuntimeError("Layout file parsing failed.") from e
    else:
        if verbose: print(f"No layout file '{LAYOUT_FILENAME}' found.")

    # --- Compile HPY Pages ---
    compiled_files: List[str] = []
    failed_files: List[str] = []
    files_processed = 0
    hpy_files_found = [p for p in input_dir.glob('**/*.hpy') if p.name != LAYOUT_FILENAME]

    # Exclude files within the static directory from being treated as pages
    static_dir_name = config.get("static_dir_name")
    if static_dir_name:
        source_static_dir = (input_dir / static_dir_name).resolve()
        hpy_files_found = [
            p for p in hpy_files_found if not p.resolve().is_relative_to(source_static_dir)
        ]

    if not hpy_files_found:
        print(f"Warning: No page .hpy files found in '{input_dir_str}' (outside static dir).", file=sys.stderr)
        # If static assets were copied, build might still be considered partially successful
        # return [], 0

    print(f"Compiling {len(hpy_files_found)} page file(s)...")
    for hpy_file in hpy_files_found:
        files_processed += 1
        try:
            relative_path = hpy_file.relative_to(input_dir)
            output_html_path = output_dir / relative_path.with_suffix('.html')
            # Ensure parent directory exists for nested pages
            output_html_path.parent.mkdir(parents=True, exist_ok=True)
            compile_hpy_file(str(hpy_file), str(output_html_path), layout_content, verbose) # Use imported compile
            compiled_files.append(str(output_html_path))
        except Exception:
             failed_files.append(hpy_file.name) # Error already printed by compile_hpy_file

    # --- Build Summary ---
    print(f"\n--- Build Summary ---")
    print(f"Processed: {files_processed} page file(s).")
    if static_dir_name and (input_dir / static_dir_name).exists():
        print(f"Static assets handled from: '{static_dir_name}'")
    if not failed_files:
        print(f"Status: SUCCESS")
    else:
        print(f"Status: FAILURE ({len(failed_files)} error(s))", file=sys.stderr)
        print(f"Failed page files: {', '.join(failed_files)}", file=sys.stderr)
    print(f"-------------------")
    return compiled_files, len(failed_files)