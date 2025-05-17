# hpy_core/building.py
"""Core build logic: combining content, generating HTML, handling static assets & external scripts."""

import sys
import textwrap
import traceback
import shutil
import os
from pathlib import Path
from typing import Dict, Optional, List, Tuple, Any

from .config import (
    BRYTHON_VERSION, LAYOUT_FILENAME, LAYOUT_PLACEHOLDER, __version__ as hpy_tool_version,
    find_project_root, load_config
)
from .parsing import parse_hpy_file

HELPER_FUNCTION_CODE = textwrap.dedent("""
    # --- HPY Tool Helper Functions (Injected) ---
    from browser import document
    import sys as _hpy_sys
    def byid(element_id):
        try: return document[element_id]
        except KeyError: return None
    def qs(selector): return document.select_one(selector)
    def qsa(selector): return document.select(selector)
    # --- End Helper Functions ---

""")

LIVE_RELOAD_SCRIPT = textwrap.dedent(f"""
    <script>
        // HPY Tool Live Reload v{hpy_tool_version}
        (function() {{
            const RELOAD_FILE = '/.hpy_reload'; 
            const POLLING_INTERVAL = 1500; 
            let currentLastModified = null; 
            let initialFetchAttempted = false;
            let consecutiveErrors = 0;
            const MAX_ERRORS_BEFORE_WARN_SILENCE = 3;

            async function pollForChanges() {{
                if (!document.hidden) {{ 
                    try {{
                        const response = await fetch(RELOAD_FILE, {{ method: 'HEAD', cache: 'no-store' }});
                        if (response.ok) {{
                            const serverLastModified = response.headers.get('Last-Modified');
                            consecutiveErrors = 0;

                            if (serverLastModified) {{ 
                                if (initialFetchAttempted && currentLastModified && serverLastModified !== currentLastModified) {{
                                    console.log('HPY Live Reload: Changes detected (timestamp changed), reloading page...');
                                    window.location.reload();
                                    return; 
                                }}
                                currentLastModified = serverLastModified; 
                            }}
                            if (!initialFetchAttempted) {{
                                initialFetchAttempted = true;
                            }}
                        }} else if (response.status === 404) {{
                            if (initialFetchAttempted && consecutiveErrors < MAX_ERRORS_BEFORE_WARN_SILENCE) {{
                                // console.warn('HPY Live Reload: Trigger file not found.');
                            }}
                        }} else {{
                            if (consecutiveErrors < MAX_ERRORS_BEFORE_WARN_SILENCE) {{
                                // console.warn(`HPY Live Reload: HEAD request status: ${{response.status}}`);
                            }}
                            consecutiveErrors++;
                        }}
                    }} catch (error) {{
                        if (consecutiveErrors < MAX_ERRORS_BEFORE_WARN_SILENCE) {{
                            // console.warn('HPY Live Reload: Error polling for reload trigger:', error);
                        }}
                        consecutiveErrors++;
                    }}
                }}
                setTimeout(pollForChanges, POLLING_INTERVAL);
            }}

            fetch(RELOAD_FILE, {{ method: 'HEAD', cache: 'no-store' }})
                .then(response => {{
                    if (response.ok) {{
                        currentLastModified = response.headers.get('Last-Modified');
                        // console.log('HPY Live Reload: Initial trigger timestamp:', currentLastModified);
                    }}
                }})
                .catch(e => {{
                    // console.warn('HPY Live Reload: Initial fetch for trigger file failed (normal on first load/no changes yet).');
                }})
                .finally(() => {{
                    initialFetchAttempted = true; 
                    setTimeout(pollForChanges, POLLING_INTERVAL); 
                }});
        }})();
    </script>
""")

def build_output_html(
    html_content: str,
    style_content: str,
    layout_python: Optional[str],
    page_python: Optional[str],
    external_script_src: Optional[str],
    output_file_path_str: str,
    is_dev_watch_mode: bool = False
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
# No layout or page python found. Brython helpers injected.
</script>"""

    final_page_python_script = ""
    if external_script_src:
        script_src_html = external_script_src.replace(os.sep, '/')
        final_page_python_script = f'<script type="text/python" src="{script_src_html}"></script>'
    elif page_python:
        dedented_page_python = textwrap.dedent(page_python)
        python_to_embed = dedented_page_python
        if not layout_has_python:
             python_to_embed = HELPER_FUNCTION_CODE + dedented_page_python
        final_page_python_script = f"""<script type="text/python">
# --- Start Page Python ({output_file_path.stem}.hpy) ---
{python_to_embed}
# --- End Page Python ---
</script>"""

    # In watch mode, print the debug message. Suppress if not verbose or not watch mode to reduce noise.
    # For this iteration, we'll keep the unconditional print to ensure we see it.
    print(f"DEBUG_BUILDING: build_output_html - is_dev_watch_mode = {is_dev_watch_mode} -> Injecting reload script: {bool(is_dev_watch_mode)}")

    live_reload_injection = LIVE_RELOAD_SCRIPT if is_dev_watch_mode else ""

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

{live_reload_injection}
</body>
</html>"""

    try:
        with open(output_file_path, 'w', encoding='utf-8') as f: f.write(html_template)
    except IOError as e: raise IOError(f"Could not write to output file {output_file_path}: {e}") from e
    return str(output_file_path)


def compile_hpy_file(
    input_file_path_str: str,
    output_file_path_str: str,
    layout_content: Optional[Dict[str, Any]],
    external_script_src: Optional[str],
    verbose: bool = False,
    is_dev_watch_mode: bool = False
) -> str:
    input_file_path = Path(input_file_path_str)
    use_external_script = external_script_src is not None
    page_type = f"(using external script '{external_script_src}')" if use_external_script else "(using inline python)"
    layout_info = " (using layout)" if layout_content else ""

    if verbose: print(f"Processing {input_file_path.name} -> {Path(output_file_path_str).name} {page_type}{layout_info}...")

    try:
        page_parsed_data = parse_hpy_file(str(input_file_path), is_layout=False, verbose=verbose)
        page_html_fragment = page_parsed_data['html']
        page_style = page_parsed_data['style']
        page_python_inline = page_parsed_data['python'] if not use_external_script else None

        layout_html_template = layout_content['html'] if layout_content else None
        layout_style = layout_content['style'] if layout_content else ""
        layout_python = layout_content.get('python') if layout_content else None

        final_style = ""
        if layout_style: final_style += f"/* Layout: {LAYOUT_FILENAME} */\n{layout_style}\n\n"
        final_style += f"/* Page: {input_file_path.name} */\n{page_style}"

        final_html = ""
        if layout_html_template:
            if LAYOUT_PLACEHOLDER not in layout_html_template: raise ValueError(f"Layout missing '{LAYOUT_PLACEHOLDER}'.")
            final_html = layout_html_template.replace(LAYOUT_PLACEHOLDER, page_html_fragment)
        else:
            final_html = page_html_fragment

        built_path = build_output_html(
            html_content=final_html,
            style_content=final_style,
            layout_python=layout_python,
            page_python=page_python_inline,
            external_script_src=external_script_src,
            output_file_path_str=output_file_path_str,
            is_dev_watch_mode=is_dev_watch_mode
        )
        return built_path

    except (FileNotFoundError, ValueError, IOError, OSError, RuntimeError) as e:
        print(f"Error processing file {input_file_path.name}: {e}", file=sys.stderr)
        raise 
    except Exception as e:
        print(f"Unexpected error compiling {input_file_path.name}: {e}", file=sys.stderr)
        if verbose: traceback.print_exc()
        raise RuntimeError(f"Failed to compile {input_file_path.name}") from e

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
        except OSError as e:
            print(f"Error copying static assets: {e}", file=sys.stderr)
    else:
        try: src_rel = source_static_dir.relative_to(Path.cwd())
        except ValueError: src_rel = source_static_dir
        if verbose: print(f"No static directory found at '{src_rel}', skipping asset copy.")

def copy_and_inject_py_script(py_file: Path, output_py_path: Path, verbose: bool = False):
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

def compile_directory(input_dir_str: str, output_dir_str: str, verbose: bool = False, is_dev_watch_mode: bool = False) -> Tuple[List[str], int]:
    input_dir = Path(input_dir_str).resolve()
    output_dir = Path(output_dir_str).resolve()
    layout_file_path = input_dir / LAYOUT_FILENAME
    if not input_dir.is_dir(): raise FileNotFoundError(f"Input dir not found: {input_dir_str}")

    project_root = find_project_root(input_dir)
    config = load_config(project_root)

    if verbose: print(f"DEBUG_BUILDING: compile_directory - is_dev_watch_mode = {is_dev_watch_mode}")

    print(f"\nCompiling project '{input_dir.name}' -> '{output_dir.name}'...")

    try: output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e: raise RuntimeError(f"Output directory creation failed: {e}") from e

    _copy_static_assets(input_dir, output_dir, config, verbose)

    layout_content: Optional[Dict[str, Any]] = None
    if layout_file_path.exists():
        try:
            if verbose: print(f"Parsing layout file: {LAYOUT_FILENAME}")
            layout_content = parse_hpy_file(str(layout_file_path), is_layout=True, verbose=verbose)
            print(f"Using layout file: {LAYOUT_FILENAME}")
        except Exception as e: raise RuntimeError(f"Layout file parsing failed: {e}") from e
    else:
        if verbose: print(f"No layout file '{LAYOUT_FILENAME}' found.")

    compiled_files: List[str] = []
    failed_files: List[str] = []
    files_processed = 0
    processed_py_scripts: Set[Path] = set() 

    hpy_files_found = [p for p in input_dir.glob('**/*.hpy') if p.name != LAYOUT_FILENAME]
    static_dir_name = config.get("static_dir_name")
    source_static_dir: Optional[Path] = None
    if static_dir_name:
        source_static_dir = (input_dir / static_dir_name).resolve()
        if source_static_dir.exists():
            hpy_files_found = [p for p in hpy_files_found if not p.resolve().is_relative_to(source_static_dir)]

    if not hpy_files_found and verbose: print(f"Warning: No page .hpy files found in '{input_dir}'.", file=sys.stderr)

    if verbose: print(f"Compiling {len(hpy_files_found)} page file(s)...")
    py_files_processed_count = 0
    for hpy_file in hpy_files_found:
        files_processed += 1
        external_script_src_for_html: Optional[str] = None
        source_py_to_copy: Optional[Path] = None
        output_py_path: Optional[Path] = None

        try:
            parsed_data = parse_hpy_file(str(hpy_file), is_layout=False, verbose=verbose)
            explicit_src = parsed_data.get('script_src')
            relative_hpy_path = hpy_file.relative_to(input_dir)
            output_html_path = output_dir / relative_hpy_path.with_suffix('.html')

            if explicit_src:
                potential_src_py = (hpy_file.parent / explicit_src).resolve()
                if not potential_src_py.is_file():
                    raise FileNotFoundError(f"Explicit script '{explicit_src}' referenced in '{hpy_file.name}' not found at '{potential_src_py}'")
                try: potential_src_py.relative_to(input_dir)
                except ValueError: raise ValueError(f"Explicit script '{explicit_src}' in '{hpy_file.name}' points outside input directory '{input_dir}'.")
                if source_static_dir and source_static_dir.exists() and potential_src_py.is_relative_to(source_static_dir):
                    raise ValueError(f"Explicit script '{explicit_src}' in '{hpy_file.name}' points inside static directory '{source_static_dir}'.")
                source_py_to_copy = potential_src_py
                relative_py_path_from_input = source_py_to_copy.relative_to(input_dir)
                output_py_path = (output_dir / relative_py_path_from_input).resolve()
                html_dir = output_html_path.parent
                external_script_src_for_html = os.path.relpath(output_py_path, start=html_dir)
            else:
                conventional_py_file = hpy_file.with_suffix('.py')
                if conventional_py_file.exists():
                     resolved_conv_py = conventional_py_file.resolve()
                     if not (source_static_dir and source_static_dir.exists() and resolved_conv_py.is_relative_to(source_static_dir)):
                          source_py_to_copy = resolved_conv_py
                          output_py_path = (output_dir / relative_hpy_path).with_suffix('.py').resolve()
                          external_script_src_for_html = output_py_path.name 
                     elif verbose:
                          print(f"  Ignoring conventional script {conventional_py_file.name} as it's inside static dir.")

            if source_py_to_copy and output_py_path:
                if source_py_to_copy not in processed_py_scripts:
                    copy_and_inject_py_script(source_py_to_copy, output_py_path, verbose)
                    processed_py_scripts.add(source_py_to_copy)
                    py_files_processed_count += 1
                elif verbose:
                    print(f"  Skipping copy/inject for already processed script: {source_py_to_copy.name}")

            output_html_path.parent.mkdir(parents=True, exist_ok=True)
            compile_hpy_file(
                str(hpy_file),
                str(output_html_path),
                layout_content,
                external_script_src_for_html,
                verbose,
                is_dev_watch_mode=is_dev_watch_mode
            )
            compiled_files.append(str(output_html_path))

        except Exception as e:
            print(f"Failed processing {hpy_file.name}: {e}", file=sys.stderr)
            failed_files.append(f"{hpy_file.name} ({type(e).__name__})")
            if verbose: traceback.print_exc()

    if verbose or files_processed > 0 or py_files_processed_count > 0 or (static_dir_name and source_static_dir and source_static_dir.exists()):
        print(f"\n--- Build Summary ---")
        print(f"Processed: {files_processed} page file(s).")
        if processed_py_scripts:
            print(f"External Python scripts processed (helpers injected): {py_files_processed_count}")
        if static_dir_name and source_static_dir and source_static_dir.exists():
            print(f"Static assets handled from: '{static_dir_name}'")
        elif static_dir_name:
            print(f"Static asset directory '{static_dir_name}' configured but not found in source '{input_dir / static_dir_name}'.")

        if not failed_files:
            print(f"Status: SUCCESS")
        else:
            print(f"Status: FAILURE ({len(failed_files)} error(s))", file=sys.stderr)
            print(f"Failed items: {', '.join(failed_files)}", file=sys.stderr)
        print(f"-------------------")
    elif not hpy_files_found:
         print(f"Warning: No page .hpy files found to compile in '{input_dir_str}'.", file=sys.stderr)

    return compiled_files, len(failed_files)