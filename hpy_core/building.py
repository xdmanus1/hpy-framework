# hpy_core/building.py
"""Core build logic: combining content, generating HTML, handling static assets & external scripts."""

import sys
import textwrap
import traceback
import shutil
import os # Import os for path operations
from pathlib import Path
from typing import Dict, Optional, List, Tuple, Any

# Import from other modules in the package
from .config import BRYTHON_VERSION, LAYOUT_FILENAME, LAYOUT_PLACEHOLDER
from .config import load_config, find_project_root, DEFAULT_STATIC_DIR_NAME
# --- Updated parsing import ---
from .parsing import parse_hpy_file # Parser now returns script_src

# --- Helper Code Definition (Centralized) ---
HELPER_FUNCTION_CODE = textwrap.dedent("""
    # --- HPY Tool Helper Functions (Injected) ---
    from browser import document
    import sys as _hpy_sys # Alias to avoid user conflicts
    def byid(element_id):
        try: return document[element_id]
        except KeyError: return None
    def qs(selector): return document.select_one(selector)
    def qsa(selector): return document.select(selector)
    # --- End Helper Functions ---

""")

# build_output_html remains the same as the previous version (accepts external_script_src)
def build_output_html(
    html_content: str,
    style_content: str,
    layout_python: Optional[str],
    page_python: Optional[str],
    external_script_src: Optional[str], # Relative path FROM HTML TO script
    output_file_path_str: str
) -> str:
    output_file_path = Path(output_file_path_str)
    output_dir = output_file_path.parent
    try: output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e: raise OSError(f"Could not create output dir {output_dir}: {e}") from e

    final_layout_python_script = ""
    layout_has_python = bool(layout_python)
    if layout_python:
        combined_layout_code = HELPER_FUNCTION_CODE + textwrap.dedent(layout_python)
        final_layout_python_script = f"""<script type="text/python">
# --- Start Layout Python ({LAYOUT_FILENAME}) ---
{combined_layout_code}
# --- End Layout Python ---
</script>"""
    elif not external_script_src and not page_python:
         final_layout_python_script = f"""<script type="text/python">
{HELPER_FUNCTION_CODE}
# No layout or page python found.
</script>"""

    final_page_python_script = ""
    if external_script_src:
        script_src_html = external_script_src.replace(os.sep, '/') # Ensure forward slashes
        final_page_python_script = f'<script type="text/python" src="{script_src_html}"></script>'
    elif page_python:
        dedented_page_python = textwrap.dedent(page_python)
        python_to_embed = dedented_page_python
        if not layout_has_python: # Inject helpers here if layout didn't
             python_to_embed = HELPER_FUNCTION_CODE + dedented_page_python
        final_page_python_script = f"""<script type="text/python">
# --- Start Page Python ({output_file_path.stem}.hpy) ---
{python_to_embed}
# --- End Page Python ---
</script>"""

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
{style_content}
/* --- End Combined CSS --- */
    </style>
</head>
<body onload="brython({{'debug': 1}})">

{html_content}

{final_layout_python_script}

{final_page_python_script}

</body>
</html>"""

    try:
        with open(output_file_path, 'w', encoding='utf-8') as f: f.write(html_template)
    except IOError as e: raise IOError(f"Could not write to output file {output_file_path}: {e}") from e
    return str(output_file_path)


# compile_hpy_file remains the same as previous version (accepts external_script_src)
def compile_hpy_file(
    input_file_path_str: str,
    output_file_path_str: str,
    layout_content: Optional[Dict[str, Any]], # Changed Dict type hint
    external_script_src: Optional[str], # Relative path FROM HTML TO script
    verbose: bool = False
) -> str:
    input_file_path = Path(input_file_path_str)
    use_external_script = external_script_src is not None
    page_type = f"(using external script '{external_script_src}')" if use_external_script else "(using inline python)"
    layout_info = " (using layout)" if layout_content else ""

    if verbose: print(f"Processing {input_file_path.name} -> {Path(output_file_path_str).name} {page_type}{layout_info}...")

    try:
        # Parse the page file - we only need html and style here now
        page_parsed_data = parse_hpy_file(input_file_path_str, is_layout=False, verbose=verbose)
        page_html_fragment = page_parsed_data['html']
        page_style = page_parsed_data['style']
        # Get potential inline python ONLY if no external script is being used
        page_python_inline = page_parsed_data['python'] if not use_external_script else None

        # Extract layout components if available
        layout_html_template = layout_content['html'] if layout_content else None
        layout_style = layout_content['style'] if layout_content else ""
        layout_python = layout_content.get('python') if layout_content else None # Layout uses inline

        # Combine Styles
        final_style = ""
        if layout_style: final_style += f"/* Layout: {LAYOUT_FILENAME} */\n{layout_style}\n\n"
        final_style += f"/* Page: {input_file_path.name} */\n{page_style}"

        # Combine HTML
        final_html = ""
        if layout_html_template:
            if LAYOUT_PLACEHOLDER not in layout_html_template: raise ValueError(f"Layout missing '{LAYOUT_PLACEHOLDER}'.")
            final_html = layout_html_template.replace(LAYOUT_PLACEHOLDER, page_html_fragment)
        else:
            final_html = page_html_fragment

        # Build final output HTML
        built_path = build_output_html(
            html_content=final_html,
            style_content=final_style,
            layout_python=layout_python,
            page_python=page_python_inline, # Pass inline only if no external src
            external_script_src=external_script_src, # Pass the already calculated relative path
            output_file_path_str=output_file_path_str
        )
        return built_path

    except (FileNotFoundError, ValueError, IOError, OSError, RuntimeError) as e:
        print(f"Error processing file {input_file_path.name}: {e}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"Unexpected error compiling {input_file_path.name}: {e}", file=sys.stderr)
        if verbose: traceback.print_exc()
        raise RuntimeError(f"Failed to compile {input_file_path.name}") from e


# _copy_static_assets remains the same
def _copy_static_assets(input_dir: Path, output_dir: Path, config: Dict, verbose: bool = False):
    static_dir_name = config.get("static_dir_name")
    if not static_dir_name:
        if verbose: print("Static asset handling disabled (no 'static_dir_name' in config).")
        return
    source_static_dir = (input_dir / static_dir_name).resolve()
    target_static_dir = (output_dir / static_dir_name).resolve()
    if source_static_dir.is_dir():
        try:
            try: src_rel = source_static_dir.relative_to(Path.cwd())
            except ValueError: src_rel = source_static_dir
            try: tgt_rel = target_static_dir.relative_to(Path.cwd())
            except ValueError: tgt_rel = target_static_dir
            if verbose: print(f"Copying static assets from '{src_rel}' to '{tgt_rel}'...")
            shutil.copytree(source_static_dir, target_static_dir, dirs_exist_ok=True)
            if verbose: print("Static assets copied successfully.")
        except OSError as e: print(f"Error copying static assets: {e}", file=sys.stderr)
    else:
         try: src_rel = source_static_dir.relative_to(Path.cwd())
         except ValueError: src_rel = source_static_dir
         if verbose: print(f"No static directory found at '{src_rel}', skipping asset copy.")


# copy_and_inject_py_script remains the same
def copy_and_inject_py_script(py_file: Path, output_py_path: Path, verbose: bool = False):
    """Reads py_file, prepends helpers, writes to output_py_path."""
    try:
        if verbose: print(f"  Processing external script: {py_file.name}")
        original_content = py_file.read_text(encoding='utf-8')
        final_content = HELPER_FUNCTION_CODE + "\n# --- Original User Code Below ---\n" + original_content
        output_py_path.parent.mkdir(parents=True, exist_ok=True)
        output_py_path.write_text(final_content, encoding='utf-8')
        if verbose: print(f"  Injected helpers and copied script: {py_file.name} -> {output_py_path.name}")
    except IOError as e:
        print(f"Error reading/writing script '{py_file.name}' -> '{output_py_path.name}': {e}", file=sys.stderr)
        raise
    except Exception as e:
         print(f"Unexpected error processing script {py_file.name}: {e}", file=sys.stderr)
         raise


# --- Heavily Modified compile_directory ---
def compile_directory(input_dir_str: str, output_dir_str: str, verbose: bool = False) -> Tuple[List[str], int]:
    """Compiles .hpy files, handles explicit/conventional external .py scripts, copies static assets."""
    input_dir = Path(input_dir_str).resolve()
    output_dir = Path(output_dir_str).resolve()
    layout_file_path = input_dir / LAYOUT_FILENAME
    if not input_dir.is_dir(): raise FileNotFoundError(f"Input dir not found: {input_dir_str}")

    project_root = find_project_root(input_dir)
    config = load_config(project_root)

    print(f"\nCompiling project '{input_dir.name}' -> '{output_dir.name}'...")

    try: output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e: raise RuntimeError(f"Output directory creation failed: {e}") from e

    _copy_static_assets(input_dir, output_dir, config, verbose)

    # Parse Layout (now returns script_src, though we ignore it for layout)
    layout_content: Optional[Dict[str, Any]] = None
    if layout_file_path.exists():
        try:
            if verbose: print(f"Parsing layout file: {LAYOUT_FILENAME}")
            # Pass verbose to parser
            layout_content = parse_hpy_file(str(layout_file_path), is_layout=True, verbose=verbose)
            print(f"Using layout file: {LAYOUT_FILENAME}")
        except Exception as e: raise RuntimeError(f"Layout file parsing failed: {e}") from e
    else:
        if verbose: print(f"No layout file '{LAYOUT_FILENAME}' found.")

    compiled_files: List[str] = []
    failed_files: List[str] = []
    files_processed = 0
    processed_py_scripts: Set[Path] = set() # Track copied scripts to avoid duplicates

    # Find page files (excluding static dir and layout)
    hpy_files_found = [p for p in input_dir.glob('**/*.hpy') if p.name != LAYOUT_FILENAME]
    static_dir_name = config.get("static_dir_name")
    source_static_dir: Optional[Path] = None
    if static_dir_name:
        source_static_dir = (input_dir / static_dir_name).resolve()
        hpy_files_found = [p for p in hpy_files_found if not p.resolve().is_relative_to(source_static_dir)]

    if not hpy_files_found: print(f"Warning: No page .hpy files found.", file=sys.stderr)

    print(f"Compiling {len(hpy_files_found)} page file(s)...")
    py_files_processed_count = 0
    for hpy_file in hpy_files_found:
        files_processed += 1
        external_script_src_for_html: Optional[str] = None
        source_py_to_copy: Optional[Path] = None
        output_py_path: Optional[Path] = None

        try:
            # 1. Parse the HPY file
            # Pass verbose to parser
            parsed_data = parse_hpy_file(str(hpy_file), is_layout=False, verbose=verbose)
            explicit_src = parsed_data.get('script_src')
            relative_hpy_path = hpy_file.relative_to(input_dir)
            output_html_path = output_dir / relative_hpy_path.with_suffix('.html')

            # 2. Determine the source Python script (explicit or conventional)
            if explicit_src:
                # Resolve explicit src relative to the *hpy file*
                potential_src_py = (hpy_file.parent / explicit_src).resolve()
                # --- Validation ---
                if not potential_src_py.is_file():
                    raise FileNotFoundError(f"Explicit script '{explicit_src}' referenced in '{hpy_file.name}' not found at '{potential_src_py}'")
                # Check if script is within input_dir (for security/simplicity)
                try:
                    potential_src_py.relative_to(input_dir)
                except ValueError:
                    raise ValueError(f"Explicit script '{explicit_src}' in '{hpy_file.name}' points outside the input directory '{input_dir}'. This is not allowed.")
                # Check not in static dir
                if source_static_dir and potential_src_py.is_relative_to(source_static_dir):
                    raise ValueError(f"Explicit script '{explicit_src}' in '{hpy_file.name}' points inside the static directory '{source_static_dir}'. This is not allowed.")
                # --- End Validation ---
                source_py_to_copy = potential_src_py
                # Calculate output path, maintaining structure relative to input_dir
                relative_py_path_from_input = source_py_to_copy.relative_to(input_dir)
                output_py_path = (output_dir / relative_py_path_from_input).resolve()
                # Calculate src for HTML tag (relative from HTML file's dir to output py file)
                html_dir = output_html_path.parent
                external_script_src_for_html = os.path.relpath(output_py_path, start=html_dir)

            else:
                # No explicit src, check for conventional .py file
                conventional_py_file = hpy_file.with_suffix('.py')
                if conventional_py_file.exists():
                     resolved_conv_py = conventional_py_file.resolve()
                     # Check not in static dir
                     if not (source_static_dir and resolved_conv_py.is_relative_to(source_static_dir)):
                          source_py_to_copy = resolved_conv_py
                          # Output path mirrors hpy file structure
                          output_py_path = (output_dir / relative_hpy_path).with_suffix('.py').resolve()
                          # Src for HTML tag is just the filename relative to HTML
                          external_script_src_for_html = output_py_path.name
                     elif verbose:
                          print(f"  Ignoring conventional script {conventional_py_file.name} as it's inside static dir.")


            # 3. Copy and Inject the Python script (if one was determined)
            if source_py_to_copy and output_py_path:
                # Only process+count if not already done (e.g., shared script)
                if source_py_to_copy not in processed_py_scripts:
                    copy_and_inject_py_script(source_py_to_copy, output_py_path, verbose)
                    processed_py_scripts.add(source_py_to_copy)
                    py_files_processed_count += 1
                elif verbose:
                    print(f"  Skipping copy/inject for already processed script: {source_py_to_copy.name}")

            # 4. Compile the HPY file, passing the calculated HTML src attribute
            output_html_path.parent.mkdir(parents=True, exist_ok=True)
            compile_hpy_file(
                str(hpy_file),
                str(output_html_path),
                layout_content,
                external_script_src_for_html, # Pass calculated src for HTML
                verbose
            )
            compiled_files.append(str(output_html_path))

        except Exception as e:
            # Catch errors from parsing, validation, script processing, or compiling
            print(f"Failed processing {hpy_file.name}: {e}", file=sys.stderr)
            failed_files.append(f"{hpy_file.name} ({type(e).__name__})") # Add error type
            if verbose: traceback.print_exc()


    # --- Build Summary ---
    print(f"\n--- Build Summary ---")
    print(f"Processed: {files_processed} page file(s).")
    if processed_py_scripts: # Check if set is not empty
        print(f"External Python scripts processed (helpers injected): {py_files_processed_count}")
    if static_dir_name and source_static_dir and source_static_dir.exists():
        print(f"Static assets handled from: '{static_dir_name}'")
    if not failed_files:
        print(f"Status: SUCCESS")
    else:
        print(f"Status: FAILURE ({len(failed_files)} error(s))", file=sys.stderr)
        print(f"Failed items: {', '.join(failed_files)}", file=sys.stderr)
    print(f"-------------------")
    return compiled_files, len(failed_files)