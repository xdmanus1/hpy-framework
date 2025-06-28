# hpy_core/building.py
"""Core build logic for HPY Tool, with App Shell, Components, and Production Mode support."""

import sys
import textwrap
import traceback
import shutil
import os
import re
import uuid
from pathlib import Path
from typing import Dict, Optional, List, Tuple, Any, Set

from .config import (
    BRYTHON_VERSION, LAYOUT_FILENAME, LAYOUT_PLACEHOLDER, __version__ as hpy_tool_version,
    find_project_root, load_config,
    APP_SHELL_FILENAME, APP_SHELL_HEAD_PLACEHOLDER, APP_SHELL_BODY_PLACEHOLDER,
    DEFAULT_COMPONENTS_DIR
)
from .parsing import (
    parse_hpy_file, CSS_HREF_REGEX,
    COMPONENT_PLACEHOLDER_PREFIX, COMPONENT_PLACEHOLDER_SUFFIX
)
from .components import ComponentRegistry, PROPS_REGEX

COMPONENT_PLACEHOLDER_REGEX = re.compile(re.escape(COMPONENT_PLACEHOLDER_PREFIX) + r"([0-9a-f\-]+)" + re.escape(COMPONENT_PLACEHOLDER_SUFFIX))

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
                            // Silence this warning
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
                .then(response => {{ if (response.ok) {{ currentLastModified = response.headers.get('Last-Modified'); }} }})
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
    if title_match: return title_match.group(1).strip()
    return None

def _replace_title_in_app_shell(app_shell_html: str, new_title: Optional[str]) -> str:
    if not new_title: return app_shell_html
    new_app_shell, num_replacements = re.subn(r"(<head[^>]*>.*?<title)(?:[^>]*>)(?:.*?)(</title>)", rf"\1>{new_title}\2", app_shell_html, count=1, flags=re.IGNORECASE | re.DOTALL)
    if num_replacements > 0: return new_app_shell
    else:
        head_end_match = re.search(r"(</head>)", app_shell_html, re.IGNORECASE | re.DOTALL)
        if head_end_match: return app_shell_html.replace(head_end_match.group(1), f"    <title>{new_title}</title>\n{head_end_match.group(1)}", 1)
    return app_shell_html

def _render_content_recursively(
    content_to_render: str,
    component_data_map: Dict[str, Any],
    component_registry: ComponentRegistry,
    scoped_styles_collection: List[str],
    props: Optional[Dict[str, str]] = None,
    verbose: bool = False,
    max_depth: int = 10
) -> str:
    if max_depth <= 0:
        if verbose: print("Warning: Max component recursion depth reached.", file=sys.stderr)
        return "<!-- MAX RECURSION DEPTH -->"

    rendered_content = content_to_render
    if props:
        def replace_prop(match):
            prop_key = match.group(1)
            return str(props.get(prop_key, ''))
        rendered_content = PROPS_REGEX.sub(replace_prop, rendered_content)

    def render_match(match):
        placeholder_id = match.group(1)
        component_instance = component_data_map.get(placeholder_id)
        if not component_instance: return ""

        comp_name, comp_props = component_instance["name"], component_instance["props"]
        comp_path = component_registry.get_path(comp_name)
        if not comp_path: return f"<!-- Component <{comp_name}> not found -->"
        
        try:
            comp_parsed_data = parse_hpy_file(str(comp_path), is_layout=False, verbose=verbose)
            comp_html_fragment = comp_parsed_data['html']
            
            all_comp_styles = []
            if comp_parsed_data.get('style'):
                all_comp_styles.append(comp_parsed_data['style'])
            
            for href in comp_parsed_data.get('css_links', []):
                source_css_file = (comp_path.parent / href).resolve()
                if not source_css_file.is_file():
                    raise FileNotFoundError(f"In component '{comp_name}', CSS file '{href}' not found at '{source_css_file}'")
                all_comp_styles.append(source_css_file.read_text(encoding='utf-8'))

            unique_id = f"hpy-c-{uuid.uuid4().hex[:8]}"
            scoped_html = comp_html_fragment
            
            if all_comp_styles:
                comp_style_content = "\n\n".join(all_comp_styles)
                def scope_selector(m):
                    selector = m.group(1).strip()
                    scoped_selectors = [f"{s.strip()}[data-hpy-id='{unique_id}']" for s in selector.split(',')]
                    return ", ".join(scoped_selectors) + m.group(2)
                
                scoped_css = re.sub(r'([^{,]+)(\s*\{)', scope_selector, comp_style_content)
                scoped_styles_collection.append(f"/* Scoped styles for <{comp_name}> ({unique_id}) */\n{scoped_css}")
                
                # --- THE FIX ---
                # Tag ALL elements in the fragment, not just the first one.
                # Remove count=1 to apply to all occurrences.
                scoped_html = re.sub(r'<([a-zA-Z0-9]+)', rf'<\1 data-hpy-id="{unique_id}"', scoped_html)
                # --- END FIX ---

            return _render_content_recursively(
                scoped_html, comp_parsed_data.get('components', {}),
                component_registry, scoped_styles_collection, props=comp_props,
                verbose=verbose, max_depth=max_depth - 1
            )
        except Exception as e:
            if verbose: traceback.print_exc()
            return f"<!-- Error rendering component <{comp_name}>: {e} -->"

    while COMPONENT_PLACEHOLDER_REGEX.search(rendered_content):
        rendered_content = COMPONENT_PLACEHOLDER_REGEX.sub(render_match, rendered_content)
        
    return rendered_content

def build_output_html(
    app_shell_template: Optional[str],
    page_head_fragment: str,
    page_body_fragment: str,
    combined_style_content: str,
    scoped_styles_content: str,
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
    final_page_title = _extract_title_from_head_content(page_head_fragment)
    default_app_shell_title = "HPY Application"
    css_link_tags = [f'<link rel="stylesheet" href="{href}">' for href in final_css_links_for_html]
    final_css_links_str = "\n    ".join(css_link_tags) if css_link_tags else ""
    
    scoped_styles_injection = ""
    if scoped_styles_content:
        scoped_styles_injection = f"<style id='_hpy_scoped_styles'>\n{scoped_styles_content}\n</style>"

    if app_shell_template:
        current_app_shell_title = _extract_title_from_head_content(app_shell_template) or default_app_shell_title
        title_to_use = final_page_title or current_app_shell_title
        temp_html = _replace_title_in_app_shell(app_shell_template, title_to_use)
        if final_page_title: page_head_fragment = re.sub(r"<title.*?</title>", "", page_head_fragment, count=1, flags=re.IGNORECASE | re.DOTALL)
        temp_html = re.sub(r"brython\s*\(\s*{[^}]*'debug'\s*:\s*\d+\s*[^}]*}\s*\)", f"brython({{'debug': {brython_debug_level}}})", temp_html, flags=re.IGNORECASE)
        
        head_injection_content = (final_css_links_str + "\n    " + page_head_fragment.strip() + "\n    " + scoped_styles_injection).strip()
        temp_html = temp_html.replace(APP_SHELL_HEAD_PLACEHOLDER, head_injection_content)
        temp_html = temp_html.replace(APP_SHELL_BODY_PLACEHOLDER, page_body_fragment)
        
        scripts_to_inject = f"\n{layout_python_script_tag or ''}\n{page_python_script_tag or ''}\n{live_reload_injection}\n"
        body_end_match = re.search(r"(</body>)", temp_html, re.IGNORECASE | re.DOTALL)
        if body_end_match: final_html_output = temp_html.replace(body_end_match.group(1), scripts_to_inject + body_end_match.group(1), 1)
        else: final_html_output = temp_html + scripts_to_inject
    else:
        title_to_use = final_page_title or f"HPY Application ({output_file_path.stem})"
        final_html_output = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{title_to_use}</title><script src="https://cdn.jsdelivr.net/npm/brython@{BRYTHON_VERSION}/brython.min.js"></script><script src="https://cdn.jsdelivr.net/npm/brython@{BRYTHON_VERSION}/brython_stdlib.js"></script>{final_css_links_str}<style id='_hpy_combined_styles_fallback'>{combined_style_content.strip()}</style>{scoped_styles_injection}{page_head_fragment.strip()}</head><body onload="brython({{'debug': {brython_debug_level}}})">{page_body_fragment}{layout_python_script_tag or ''}{page_python_script_tag or ''}{live_reload_injection}</body></html>"""
    
    try:
        with open(output_file_path, 'w', encoding='utf-8') as f: f.write(final_html_output)
    except IOError as e: raise IOError(f"Could not write to output file {output_file_path}: {e}") from e
    return str(output_file_path)

def compile_hpy_file(
    input_file_path_str: str,
    output_file_path_str: str,
    component_registry: ComponentRegistry,
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
    if verbose: print(f"Compiling page {input_file_path.name}...")
    
    try:
        scoped_styles_collection: List[str] = []
        page_html_fragment = page_parsed_data['html']
        page_components = page_parsed_data.get('components', {})
        page_html_rendered = _render_content_recursively(
            page_html_fragment, page_components, component_registry, 
            scoped_styles_collection, verbose=verbose
        )

        page_head_direct_content = page_parsed_data.get('head_content', "") or ""
        page_style_content = page_parsed_data['style'] or ""
        page_python_inline = page_parsed_data['python'] if not external_script_src else None

        layout_head_content = layout_parsed_data.get('head_content', "") if layout_parsed_data else ""
        layout_body_template = layout_parsed_data.get('html', "") if layout_parsed_data else ""
        layout_style_content = layout_parsed_data.get('style', "") if layout_parsed_data else ""
        layout_python_inline = layout_parsed_data.get('python') if layout_parsed_data else None
        layout_components = layout_parsed_data.get('components', {}) if layout_parsed_data else {}
        
        final_global_styles = ""
        if layout_style_content: final_global_styles += f"/* Layout Styles */\n{layout_style_content.strip()}\n\n"
        if page_style_content: final_global_styles += f"/* Page Styles */\n{page_style_content.strip()}\n"
        
        needs_global_helpers = True
        final_layout_python_script_tag = ""
        if layout_python_inline:
            final_layout_python_script_tag = f'<script type="text/python" id="_hpy_layout_script">{HELPER_FUNCTION_CODE}{textwrap.dedent(layout_python_inline)}</script>'
            needs_global_helpers = False

        final_page_python_script_tag = ""
        if external_script_src:
            final_page_python_script_tag = f'<script type="text/python" src="{external_script_src.replace(os.sep, "/")}" id="_hpy_page_script_external"></script>'
        elif page_python_inline:
            code_to_embed = textwrap.dedent(page_python_inline)
            if needs_global_helpers: code_to_embed = HELPER_FUNCTION_CODE + code_to_embed
            final_page_python_script_tag = f'<script type="text/python" id="_hpy_page_script_inline">{code_to_embed}</script>'

        if layout_head_content: layout_head_content = CSS_HREF_REGEX.sub('', layout_head_content)
        if page_head_direct_content: page_head_direct_content = CSS_HREF_REGEX.sub('', page_head_direct_content)

        final_body_content = ""
        if layout_parsed_data:
            if LAYOUT_PLACEHOLDER not in layout_body_template:
                raise ValueError(f"Layout file '{LAYOUT_FILENAME}' is missing '{LAYOUT_PLACEHOLDER}'.")
            
            layout_body_rendered = _render_content_recursively(
                layout_body_template, layout_components, component_registry, 
                scoped_styles_collection, verbose=verbose
            )

            final_body_content = layout_body_rendered.replace(LAYOUT_PLACEHOLDER, page_html_rendered)
            final_head_content = (layout_head_content or "").strip() + "\n" + (page_head_direct_content or "").strip()
        else:
            final_body_content = page_html_rendered
            final_head_content = (page_head_direct_content or "").strip()

        if app_shell_template and final_global_styles.strip():
            final_head_content += f"\n<style id='_hpy_global_styles_injected'>{final_global_styles.strip()}</style>"

        built_path = build_output_html(
            app_shell_template, final_head_content.strip(), final_body_content.strip(),
            final_global_styles.strip(), "\n\n".join(scoped_styles_collection), final_css_links_for_html,
            final_layout_python_script_tag, final_page_python_script_tag,
            output_file_path_str, is_dev_watch_mode, is_production_build
        )
        return built_path
    except Exception as e:
        if verbose: traceback.print_exc()
        raise RuntimeError(f"Failed to compile {input_file_path.name}: {e}") from e

def _copy_static_assets(input_dir: Path, output_dir: Path, config: Dict, verbose: bool = False):
    static_dir_name = config.get("static_dir_name")
    if not static_dir_name: return
    source_static_dir = (input_dir / static_dir_name).resolve()
    target_static_dir = (output_dir / static_dir_name).resolve()
    if source_static_dir.is_dir():
        if verbose: print(f"Copying static assets from '{source_static_dir.relative_to(Path.cwd())}'...")
        shutil.copytree(source_static_dir, target_static_dir, dirs_exist_ok=True)
    elif verbose: print(f"No static directory found at '{source_static_dir}', skipping asset copy.")

def copy_and_inject_py_script(py_file: Path, output_py_path: Path, verbose: bool = False):
    try:
        if verbose: print(f"  Processing script: {py_file.name}")
        original_content = py_file.read_text(encoding='utf-8')
        if HELPER_FUNCTION_CODE.strip() not in original_content:
            final_content = HELPER_FUNCTION_CODE + "\n# --- Original User Code Below ---\n" + original_content
        else: final_content = original_content
        output_py_path.parent.mkdir(parents=True, exist_ok=True)
        output_py_path.write_text(final_content, encoding='utf-8')
    except IOError as e: print(f"Error reading/writing script '{py_file.name}': {e}", file=sys.stderr); raise 

def compile_directory(
    input_dir_str: str, output_dir_str: str, verbose: bool = False, 
    is_dev_watch_mode: bool = False, is_production_build: bool = False
) -> Tuple[List[str], int]:
    input_dir = Path(input_dir_str).resolve()
    output_dir = Path(output_dir_str).resolve()
    project_root = find_project_root(input_dir)
    config = load_config(project_root)

    components_dir_name = config.get("components_dir", DEFAULT_COMPONENTS_DIR)
    components_base_dir = input_dir / components_dir_name
    component_registry = ComponentRegistry(components_base_dir, input_dir, verbose)

    app_shell_file_path = input_dir / APP_SHELL_FILENAME
    app_shell_template_content: Optional[str] = None
    if app_shell_file_path.is_file():
        app_shell_template_content = app_shell_file_path.read_text(encoding='utf-8')
        if verbose: print(f"Using App Shell: {APP_SHELL_FILENAME}")

    layout_file_path = input_dir / LAYOUT_FILENAME
    if not input_dir.is_dir(): raise FileNotFoundError(f"Input dir not found: {input_dir_str}")

    print(f"\nCompiling project '{input_dir.name}' -> '{output_dir.name}' ({'Production' if is_production_build else 'Development'} mode)...")
    output_dir.mkdir(parents=True, exist_ok=True)
    _copy_static_assets(input_dir, output_dir, config, verbose)

    layout_parsed_data: Optional[Dict[str, Any]] = None
    if layout_file_path.exists():
        layout_parsed_data = parse_hpy_file(str(layout_file_path), is_layout=True, verbose=verbose)
        print(f"Using layout file: {LAYOUT_FILENAME}")

    compiled_files, failed_files = [], []
    processed_assets: Dict[str, Set[Path]] = {"py": set(), "css": set()}
    
    hpy_files_to_process = [p for p in input_dir.rglob('*.hpy') if p.is_file() and p.name != LAYOUT_FILENAME and not p.resolve().is_relative_to(components_base_dir)]
    static_dir_name = config.get("static_dir_name")
    if static_dir_name and (input_dir / static_dir_name).exists():
        static_dir_path = input_dir / static_dir_name
        hpy_files_to_process = [p for p in hpy_files_to_process if not p.resolve().is_relative_to(static_dir_path)]

    for hpy_file in hpy_files_to_process:
        try:
            page_parsed_data = parse_hpy_file(str(hpy_file), is_layout=False, verbose=verbose)
            relative_hpy_path = hpy_file.relative_to(input_dir)
            output_html_path = output_dir / relative_hpy_path.with_suffix('.html')
            
            external_script_src, source_py_to_copy, output_py_path = None, None, None
            explicit_src = page_parsed_data.get('script_src')
            if explicit_src:
                source_py_to_copy = (hpy_file.parent / explicit_src).resolve()
                rel_py_path = source_py_to_copy.relative_to(input_dir)
                output_py_path = (output_dir / rel_py_path).resolve()
                external_script_src = os.path.relpath(output_py_path, start=output_html_path.parent)
            else:
                conv_py = hpy_file.with_suffix('.py')
                if conv_py.exists():
                    source_py_to_copy = conv_py.resolve()
                    output_py_path = (output_dir / relative_hpy_path).with_suffix('.py').resolve()
                    external_script_src = output_py_path.name
            
            if source_py_to_copy and source_py_to_copy not in processed_assets["py"]:
                copy_and_inject_py_script(source_py_to_copy, output_py_path, verbose)
                processed_assets["py"].add(source_py_to_copy)

            page_css_hrefs = page_parsed_data.get('css_links', [])
            layout_css_hrefs = layout_parsed_data.get('css_links', []) if layout_parsed_data else []
            page_level_css_sources = set()
            for href in page_css_hrefs: page_level_css_sources.add((hpy_file.parent / href).resolve())
            if layout_parsed_data:
                for href in layout_css_hrefs: page_level_css_sources.add((layout_file_path.parent / href).resolve())
            
            final_css_links_for_html = []
            for source_css_file in sorted(list(page_level_css_sources)):
                if not source_css_file.is_file(): raise FileNotFoundError(f"CSS file '{source_css_file}' not found.")
                rel_css_path = source_css_file.relative_to(input_dir)
                output_css_path = (output_dir / rel_css_path).resolve()

                if source_css_file not in processed_assets["css"]:
                    output_css_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_css_file, output_css_path)
                    processed_assets["css"].add(source_css_file)
                
                final_css_links_for_html.append(os.path.relpath(output_css_path, start=output_html_path.parent).replace(os.sep, '/'))
            
            compile_hpy_file(
                str(hpy_file), str(output_html_path), component_registry, app_shell_template_content, layout_parsed_data,
                page_parsed_data, external_script_src, final_css_links_for_html,
                verbose, is_dev_watch_mode, is_production_build
            )
            compiled_files.append(str(output_html_path))
        except Exception as e:
            print(f"Failed processing {hpy_file.name}: {e}", file=sys.stderr)
            if verbose: traceback.print_exc()
            failed_files.append(f"{hpy_file.name} ({type(e).__name__})")

    if verbose or compiled_files:
        print(f"\n--- Build Summary ---")
        print(f"Mode: {'Production' if is_production_build else 'Development'}")
        print(f"Processed: {len(hpy_files_to_process)} page file(s).")
        if processed_assets['py']: print(f"Python scripts processed: {len(processed_assets['py'])}")
        if processed_assets['css']: print(f"Global CSS assets copied: {len(processed_assets['css'])}")
        if static_dir_name and (input_dir / static_dir_name).exists(): print(f"Static assets handled from: '{static_dir_name}'")
        if not failed_files: print(f"Status: SUCCESS")
        else: print(f"Status: FAILURE ({len(failed_files)} error(s))", file=sys.stderr); print(f"Failed items: {', '.join(failed_files)}", file=sys.stderr)
        print(f"-------------------")

    return compiled_files, len(failed_files)