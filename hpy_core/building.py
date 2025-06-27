# hpy_core/building.py
"""Core build logic for HPY Tool, with App Shell and Production Mode support."""

import sys
import textwrap
import traceback
import shutil
import os
import re
from pathlib import Path
from typing import Dict, Optional, List, Tuple, Any, Set

from .config import (
    BRYTHON_VERSION, LAYOUT_FILENAME, LAYOUT_PLACEHOLDER, __version__ as hpy_tool_version,
    find_project_root, load_config,
    APP_SHELL_FILENAME, APP_SHELL_HEAD_PLACEHOLDER, APP_SHELL_BODY_PLACEHOLDER
)
from .parsing import parse_hpy_file, CSS_HREF_REGEX

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
                    }}
                }})
                .catch(e => {{ /* Allow initial fetch to fail silently */ }})
                .finally(() => {{
                    initialFetchAttempted = true; 
                    setTimeout(pollForChanges, POLLING_INTERVAL); 
                }});
        }})();
    </script>
""")

verbose_build_output_html = False

def _extract_title_from_head_content(head_content: str) -> Optional[str]:
    title_match = re.search(r"<title.*?>(.*?)</title>", head_content, re.IGNORECASE | re.DOTALL)
    if title_match:
        return title_match.group(1).strip()
    return None

def _replace_title_in_app_shell(app_shell_html: str, new_title: Optional[str]) -> str:
    if not new_title:
        return app_shell_html
    new_app_shell, num_replacements = re.subn(
        r"(<head[^>]*>.*?<title)(?:[^>]*>)(?:.*?)(</title>)",
        rf"\1>{new_title}\2", app_shell_html, count=1, flags=re.IGNORECASE | re.DOTALL
    )
    if num_replacements > 0:
        return new_app_shell
    else:
        head_end_match = re.search(r"(</head>)", app_shell_html, re.IGNORECASE | re.DOTALL)
        if head_end_match:
            return app_shell_html.replace(head_end_match.group(1), f"    <title>{new_title}</title>\n{head_end_match.group(1)}", 1)
    return app_shell_html

def build_output_html(
    app_shell_template: Optional[str],
    page_head_fragment: str,
    page_body_fragment: str,
    combined_style_content: str,
    final_css_links_for_html: List[str],
    layout_python_script_tag: Optional[str],
    page_python_script_tag: Optional[str],
    output_file_path_str: str,
    is_dev_watch_mode: bool = False,
    is_production_build: bool = False
) -> str:
    output_file_path = Path(output_file_path_str)
    try: output_file_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e: raise OSError(f"Could not create output dir {output_file_path.parent}: {e}") from e

    live_reload_injection = LIVE_RELOAD_SCRIPT if is_dev_watch_mode and not is_production_build else ""
    brython_debug_level = 0 if is_production_build else 1
    final_html_output = ""

    final_page_title = _extract_title_from_head_content(page_head_fragment)
    default_app_shell_title = "HPY Application"

    css_link_tags = [f'<link rel="stylesheet" href="{href}">' for href in final_css_links_for_html]
    final_css_links_str = "\n    ".join(css_link_tags) if css_link_tags else ""

    if app_shell_template:
        if verbose_build_output_html: print(f"DEBUG_BUILDING: Using App Shell for '{output_file_path.name}'")
        
        current_app_shell_title = _extract_title_from_head_content(app_shell_template) or default_app_shell_title
        title_to_use = final_page_title or current_app_shell_title
        
        temp_html = _replace_title_in_app_shell(app_shell_template, title_to_use)
        if final_page_title: 
            page_head_fragment = re.sub(r"<title.*?</title>", "", page_head_fragment, count=1, flags=re.IGNORECASE | re.DOTALL)

        temp_html = re.sub(r"brython\s*\(\s*{[^}]*'debug'\s*:\s*\d+\s*[^}]*}\s*\)", f"brython({{'debug': {brython_debug_level}}})", temp_html, flags=re.IGNORECASE)
        
        head_injection_content = (final_css_links_str + "\n    " + page_head_fragment.strip()).strip()
        temp_html = temp_html.replace(APP_SHELL_HEAD_PLACEHOLDER, head_injection_content)
        temp_html = temp_html.replace(APP_SHELL_BODY_PLACEHOLDER, page_body_fragment)
        
        scripts_to_inject = f"\n{layout_python_script_tag or ''}\n{page_python_script_tag or ''}\n{live_reload_injection}\n"

        body_end_match = re.search(r"(</body>)", temp_html, re.IGNORECASE | re.DOTALL)
        if body_end_match:
            final_html_output = temp_html.replace(body_end_match.group(1), scripts_to_inject + body_end_match.group(1), 1)
        else: 
            final_html_output = temp_html + scripts_to_inject
    else: 
        if verbose_build_output_html: print(f"DEBUG_BUILDING: No App Shell. Generating full HTML for '{output_file_path.name}'")
        title_to_use = final_page_title or f"HPY Application ({output_file_path.stem})"
        final_html_output = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title_to_use}</title>
    <script src="https://cdn.jsdelivr.net/npm/brython@{BRYTHON_VERSION}/brython.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/brython@{BRYTHON_VERSION}/brython_stdlib.js"></script>
    {final_css_links_str}
    <style id='_hpy_combined_styles_fallback'>
{combined_style_content.strip()}
    </style>
    {page_head_fragment.strip()}
</head>
<body onload="brython({{'debug': {brython_debug_level}}})">
{page_body_fragment}
{layout_python_script_tag or ''}
{page_python_script_tag or ''}
{live_reload_injection}
</body>
</html>"""

    if verbose_build_output_html or (is_dev_watch_mode and not is_production_build):
        print(f"DEBUG_BUILDING: build_output_html for '{output_file_path.name}' - DevWatch: {is_dev_watch_mode}, Production: {is_production_build} -> Injecting reload: {bool(is_dev_watch_mode and not is_production_build)}")

    try:
        with open(output_file_path, 'w', encoding='utf-8') as f: f.write(final_html_output)
    except IOError as e: raise IOError(f"Could not write to output file {output_file_path}: {e}") from e
    return str(output_file_path)

def compile_hpy_file(
    input_file_path_str: str,
    output_file_path_str: str,
    app_shell_template: Optional[str],
    layout_parsed_data: Optional[Dict[str, Any]],
    page_parsed_data: Dict[str, Any],
    external_script_src: Optional[str],
    final_css_links_for_html: List[str],
    verbose: bool = False,
    is_dev_watch_mode: bool = False,
    is_production_build: bool = False
) -> str:
    input_file_path = Path(input_file_path_str)
    if verbose: print(f"Processing {input_file_path.name} -> {Path(output_file_path_str).name}...")
    try:
        page_html_body_fragment = page_parsed_data['html']
        page_head_direct_content = page_parsed_data.get('head_content', "") or ""
        page_style_content = page_parsed_data['style'] or ""
        page_python_inline = page_parsed_data['python'] if not external_script_src else None

        final_head_content_for_injection = ""
        final_body_content_for_injection = ""
        final_combined_styles = ""

        layout_head_content = layout_parsed_data.get('head_content', "") if layout_parsed_data else ""
        layout_body_template = layout_parsed_data.get('html', "") if layout_parsed_data else ""
        layout_style_content = layout_parsed_data.get('style', "") if layout_parsed_data else ""
        layout_python_inline = layout_parsed_data.get('python') if layout_parsed_data else None

        if layout_style_content:
            final_combined_styles += f"/* Layout Styles: {LAYOUT_FILENAME} */\n{layout_style_content.strip()}\n\n"
        if page_style_content:
            final_combined_styles += f"/* Page Styles: {input_file_path.name} */\n{page_style_content.strip()}\n"
        final_combined_styles = final_combined_styles.strip()

        final_layout_python_script_tag = ""
        needs_global_helpers = True 
        if layout_python_inline:
            code_to_embed = HELPER_FUNCTION_CODE + textwrap.dedent(layout_python_inline)
            final_layout_python_script_tag = f'<script type="text/python" id="_hpy_layout_script">\n# --- Layout Python ---\n{code_to_embed}\n# --- End Layout Python ---\n</script>'
            needs_global_helpers = False

        final_page_python_script_tag = ""
        if external_script_src:
            script_src_html = external_script_src.replace(os.sep, '/')
            final_page_python_script_tag = f'<script type="text/python" src="{script_src_html}" id="_hpy_page_script_external"></script>'
            needs_global_helpers = False 
        elif page_python_inline:
            code_to_embed = textwrap.dedent(page_python_inline)
            if needs_global_helpers: 
                code_to_embed = HELPER_FUNCTION_CODE + code_to_embed
                needs_global_helpers = False
            final_page_python_script_tag = f'<script type="text/python" id="_hpy_page_script_inline">\n# --- Page Python ---\n{code_to_embed}\n# --- End Page Python ---\n</script>'
        
        if layout_head_content:
            layout_head_content = CSS_HREF_REGEX.sub('', layout_head_content)
        if page_head_direct_content:
            page_head_direct_content = CSS_HREF_REGEX.sub('', page_head_direct_content)

        if layout_parsed_data: 
            if LAYOUT_PLACEHOLDER not in layout_body_template:
                raise ValueError(f"Layout file '{LAYOUT_FILENAME}' is missing placeholder '{LAYOUT_PLACEHOLDER}'.")
            processed_layout_body = layout_body_template.replace(LAYOUT_PLACEHOLDER, page_html_body_fragment)
            final_body_content_for_injection = processed_layout_body
            final_head_content_for_injection = (layout_head_content or "").strip() + "\n" + (page_head_direct_content or "").strip()
        else: 
            final_body_content_for_injection = page_html_body_fragment
            final_head_content_for_injection = (page_head_direct_content or "").strip()
        
        if app_shell_template and final_combined_styles:
             final_head_content_for_injection += f"\n<style id='_hpy_combined_styles_page_injected'>\n{final_combined_styles}\n</style>"
        elif not app_shell_template and not final_head_content_for_injection and final_combined_styles:
            final_head_content_for_injection = f"<style id='_hpy_combined_styles_fallback'>\n{final_combined_styles}\n</style>"

        built_path = build_output_html(
            app_shell_template=app_shell_template,
            page_head_fragment=final_head_content_for_injection.strip(),
            page_body_fragment=final_body_content_for_injection.strip(),
            combined_style_content=final_combined_styles,
            final_css_links_for_html=final_css_links_for_html,
            layout_python_script_tag=final_layout_python_script_tag,
            page_python_script_tag=final_page_python_script_tag,
            output_file_path_str=output_file_path_str,
            is_dev_watch_mode=is_dev_watch_mode,
            is_production_build=is_production_build
        )
        return built_path
    except Exception as e:
        if verbose: traceback.print_exc()
        if isinstance(e, (FileNotFoundError, ValueError, IOError, OSError, RuntimeError)): raise
        raise RuntimeError(f"Failed to compile {input_file_path.name}: {e}") from e

def _copy_static_assets(input_dir: Path, output_dir: Path, config: Dict, verbose: bool = False):
    static_dir_name = config.get("static_dir_name")
    if not static_dir_name:
        if verbose: print("Static asset handling disabled (no 'static_dir_name' in config).")
        return
    source_static_dir = (input_dir / static_dir_name).resolve()
    target_static_dir = (output_dir / static_dir_name).resolve()
    if source_static_dir.is_dir():
        try:
            src_rel = source_static_dir.relative_to(Path.cwd()) if Path.cwd() in source_static_dir.parents or Path.cwd() == source_static_dir else source_static_dir
            tgt_rel = target_static_dir.relative_to(Path.cwd()) if Path.cwd() in target_static_dir.parents or Path.cwd() == target_static_dir else target_static_dir
            if verbose: print(f"Copying static assets from '{src_rel}' to '{tgt_rel}'...")
            shutil.copytree(source_static_dir, target_static_dir, dirs_exist_ok=True)
            if verbose: print("Static assets copied successfully.")
        except OSError as e: print(f"Error copying static assets: {e}", file=sys.stderr)
    else:
        src_rel = source_static_dir.relative_to(Path.cwd()) if Path.cwd() in source_static_dir.parents or Path.cwd() == source_static_dir else source_static_dir
        if verbose: print(f"No static directory found at '{src_rel}', skipping asset copy.")

def copy_and_inject_py_script(py_file: Path, output_py_path: Path, verbose: bool = False):
    try:
        if verbose: print(f"  Processing external script: {py_file.name}")
        original_content = py_file.read_text(encoding='utf-8')
        if HELPER_FUNCTION_CODE.strip() not in original_content:
            final_content = HELPER_FUNCTION_CODE + "\n# --- Original User Code Below ---\n" + original_content
        else:
            final_content = original_content
        output_py_path.parent.mkdir(parents=True, exist_ok=True)
        output_py_path.write_text(final_content, encoding='utf-8')
        if verbose: print(f"  Processed external script: {py_file.name} -> {output_py_path.name}")
    except IOError as e: print(f"Error reading/writing script '{py_file.name}' -> '{output_py_path.name}': {e}", file=sys.stderr); raise 
    except Exception as e: print(f"Unexpected error processing script {py_file.name}: {e}", file=sys.stderr); raise

def compile_directory(
    input_dir_str: str, output_dir_str: str, verbose: bool = False, 
    is_dev_watch_mode: bool = False, is_production_build: bool = False
) -> Tuple[List[str], int]:
    input_dir = Path(input_dir_str).resolve()
    output_dir = Path(output_dir_str).resolve()
    project_root = find_project_root(input_dir)
    config = load_config(project_root)

    app_shell_file_path = input_dir / APP_SHELL_FILENAME
    app_shell_template_content: Optional[str] = None
    if app_shell_file_path.is_file():
        try:
            app_shell_template_content = app_shell_file_path.read_text(encoding='utf-8')
            if verbose: print(f"Using App Shell: {APP_SHELL_FILENAME}")
            if APP_SHELL_HEAD_PLACEHOLDER not in app_shell_template_content: print(f"Warning: App Shell '{APP_SHELL_FILENAME}' missing '{APP_SHELL_HEAD_PLACEHOLDER}'.", file=sys.stderr)
            if APP_SHELL_BODY_PLACEHOLDER not in app_shell_template_content: print(f"Warning: App Shell '{APP_SHELL_FILENAME}' missing '{APP_SHELL_BODY_PLACEHOLDER}'.", file=sys.stderr)
        except IOError as e: print(f"Warning: Could not read App Shell '{APP_SHELL_FILENAME}': {e}. Proceeding without.", file=sys.stderr)
    elif verbose: print(f"No App Shell ('{APP_SHELL_FILENAME}') found in '{input_dir}'.")

    layout_file_path = input_dir / LAYOUT_FILENAME
    if not input_dir.is_dir(): raise FileNotFoundError(f"Input dir not found: {input_dir_str}")

    if verbose: print(f"DEBUG_BUILDING: compile_directory for '{input_dir.name}' - DevWatch: {is_dev_watch_mode}, Production: {is_production_build}")
    print(f"\nCompiling project '{input_dir.name}' -> '{output_dir.name}' ({'Production' if is_production_build else 'Development'} mode)...")

    try: output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e: raise RuntimeError(f"Output directory creation failed: {e}") from e

    _copy_static_assets(input_dir, output_dir, config, verbose)

    layout_parsed_data: Optional[Dict[str, Any]] = None
    if layout_file_path.exists():
        try:
            if verbose: print(f"Parsing layout file: {LAYOUT_FILENAME}")
            layout_parsed_data = parse_hpy_file(str(layout_file_path), is_layout=True, verbose=verbose)
            print(f"Using layout file: {LAYOUT_FILENAME}")
        except Exception as e:
            print(f"Error parsing layout file {LAYOUT_FILENAME}: {e}", file=sys.stderr)
            if verbose: traceback.print_exc()
            raise RuntimeError(f"Layout file parsing failed: {e}") from e
    elif verbose: print(f"No layout file '{LAYOUT_FILENAME}' found.")

    compiled_files: List[str] = []
    failed_files: List[str] = []
    files_processed = 0
    processed_py_scripts: Set[Path] = set() 
    processed_css_files: Set[Path] = set()
    hpy_files_found = [p for p in input_dir.glob('**/*.hpy') if p.name != LAYOUT_FILENAME and p.name != APP_SHELL_FILENAME]
    static_dir_name = config.get("static_dir_name")
    source_static_dir: Optional[Path] = None
    if static_dir_name:
        source_static_dir = (input_dir / static_dir_name).resolve()
        if source_static_dir.exists(): hpy_files_found = [p for p in hpy_files_found if not p.resolve().is_relative_to(source_static_dir)]

    if not hpy_files_found and verbose: print(f"Warning: No page .hpy files found in '{input_dir}'.")
    if verbose and hpy_files_found: print(f"Compiling {len(hpy_files_found)} page file(s)...")
    
    py_files_processed_count = 0
    css_files_processed_count = 0
    for hpy_file in hpy_files_found:
        files_processed += 1
        try:
            page_parsed_data = parse_hpy_file(str(hpy_file), is_layout=False, verbose=verbose)
            relative_hpy_path = hpy_file.relative_to(input_dir)
            output_html_path = output_dir / relative_hpy_path.with_suffix('.html')

            # --- Process and copy linked Python script for this page ---
            external_script_src_for_html: Optional[str] = None
            explicit_src_from_page = page_parsed_data.get('script_src')
            if explicit_src_from_page:
                potential_src_py = (hpy_file.parent / explicit_src_from_page).resolve()
                if not potential_src_py.is_file(): raise FileNotFoundError(f"Script '{explicit_src_from_page}' in '{hpy_file.name}' not found at '{potential_src_py}'")
                try: potential_src_py.relative_to(input_dir)
                except ValueError: raise ValueError(f"Script '{explicit_src_from_page}' in '{hpy_file.name}' outside input dir '{input_dir}'.")
                if source_static_dir and source_static_dir.exists() and potential_src_py.is_relative_to(source_static_dir): raise ValueError(f"Script '{explicit_src_from_page}' in '{hpy_file.name}' is in static dir '{source_static_dir}'.")
                
                if potential_src_py not in processed_py_scripts:
                    relative_py_path_from_input = potential_src_py.relative_to(input_dir)
                    output_py_path = (output_dir / relative_py_path_from_input).resolve()
                    copy_and_inject_py_script(potential_src_py, output_py_path, verbose)
                    processed_py_scripts.add(potential_src_py)
                    py_files_processed_count += 1
                
                relative_py_path_from_input = potential_src_py.relative_to(input_dir)
                output_py_path = (output_dir / relative_py_path_from_input).resolve()
                external_script_src_for_html = os.path.relpath(output_py_path, start=output_html_path.parent)
            else:
                conventional_py_file = hpy_file.with_suffix('.py')
                if conventional_py_file.exists():
                     resolved_conv_py = conventional_py_file.resolve()
                     if not (source_static_dir and source_static_dir.exists() and resolved_conv_py.is_relative_to(source_static_dir)):
                          if resolved_conv_py not in processed_py_scripts:
                              output_py_path = (output_dir / relative_hpy_path).with_suffix('.py').resolve()
                              copy_and_inject_py_script(resolved_conv_py, output_py_path, verbose)
                              processed_py_scripts.add(resolved_conv_py)
                              py_files_processed_count += 1
                          external_script_src_for_html = Path(relative_hpy_path.name).with_suffix('.py').name
            
            # --- Process and copy linked CSS files for this page ---
            page_css_hrefs = page_parsed_data.get('css_links', [])
            layout_css_hrefs = layout_parsed_data.get('css_links', []) if layout_parsed_data else []
            all_css_sources_for_page = []
            if layout_css_hrefs: all_css_sources_for_page.extend([(href, layout_file_path.parent) for href in layout_css_hrefs])
            if page_css_hrefs: all_css_sources_for_page.extend([(href, hpy_file.parent) for href in page_css_hrefs])
            
            final_css_links_for_html: List[str] = []
            unique_css_sources_on_page: Set[Path] = set()

            for href, base_path in all_css_sources_for_page:
                source_css_file = (base_path / href).resolve()
                if source_css_file in unique_css_sources_on_page: continue
                unique_css_sources_on_page.add(source_css_file)

                if not source_css_file.is_file(): raise FileNotFoundError(f"CSS file '{href}' linked in '{base_path.name}' not found at '{source_css_file}'")
                try: source_css_file.relative_to(input_dir)
                except ValueError: raise ValueError(f"CSS file '{href}' in '{base_path.name}' is outside input dir '{input_dir}'.")
                if source_static_dir and source_static_dir.exists() and source_css_file.is_relative_to(source_static_dir): raise ValueError(f"CSS file '{href}' in '{base_path.name}' is in static dir '{source_static_dir}'.")

                relative_css_path = source_css_file.relative_to(input_dir)
                output_css_path = (output_dir / relative_css_path).resolve()

                if source_css_file not in processed_css_files:
                    output_css_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_css_file, output_css_path)
                    if verbose: print(f"  Copied linked asset: {source_css_file.name} -> {output_css_path.relative_to(output_dir)}")
                    processed_css_files.add(source_css_file)
                    css_files_processed_count += 1
                
                html_href = os.path.relpath(output_css_path, start=output_html_path.parent).replace(os.sep, '/')
                final_css_links_for_html.append(html_href)

            # --- Compile the final HTML ---
            compile_hpy_file(
                str(hpy_file), str(output_html_path), app_shell_template_content, layout_parsed_data,
                page_parsed_data, external_script_src_for_html, final_css_links_for_html,
                verbose, is_dev_watch_mode, is_production_build
            )
            compiled_files.append(str(output_html_path))
        except Exception as e:
            print(f"Failed processing {hpy_file.name}: {e}", file=sys.stderr)
            if verbose: traceback.print_exc()
            failed_files.append(f"{hpy_file.name} ({type(e).__name__})")

    if verbose or files_processed > 0 or py_files_processed_count > 0 or css_files_processed_count > 0 or (static_dir_name and source_static_dir and source_static_dir.exists()):
        print(f"\n--- Build Summary ---")
        print(f"Mode: {'Production' if is_production_build else 'Development'}")
        print(f"Processed: {files_processed} page file(s).")
        if processed_py_scripts: print(f"External Python scripts processed: {py_files_processed_count}")
        if processed_css_files: print(f"Linked CSS assets processed: {css_files_processed_count}")
        if static_dir_name and source_static_dir and source_static_dir.exists(): print(f"Static assets handled from: '{static_dir_name}'")
        elif static_dir_name: print(f"Static asset directory '{static_dir_name}' configured but not found in source '{input_dir / static_dir_name}'.")
        if not failed_files: print(f"Status: SUCCESS")
        else: print(f"Status: FAILURE ({len(failed_files)} error(s))", file=sys.stderr); print(f"Failed items: {', '.join(failed_files)}", file=sys.stderr)
        print(f"-------------------")
    elif not hpy_files_found and not verbose: print(f"Warning: No page .hpy files found to compile in '{input_dir_str}'.", file=sys.stderr)

    return compiled_files, len(failed_files)