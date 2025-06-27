# hpy_core/parsing.py
"""Parsing logic for .hpy files."""

import re
import sys
import os
import uuid
from pathlib import Path
from typing import Dict, Optional, Any, List, Tuple

from .config import LAYOUT_FILENAME, LAYOUT_PLACEHOLDER, APP_SHELL_HEAD_PLACEHOLDER, APP_SHELL_BODY_PLACEHOLDER

# --- Component and Prop Parsing Regex ---
# Matches <Component.Name ... > or <Component ... />
# 1: Component Name (e.g., Card or Forms.Button)
# 2: Attributes string (e.g., title="hello" class="world")
COMPONENT_REGEX = re.compile(
    r"""<([A-Z][a-zA-Z0-9\.]*)\s*     # 1: Tag name starting with uppercase, allowing dots
    ([^>]*?)                         # 2: Attributes (non-greedy)
    (/?)>                            # 3: Optional self-closing slash
    """,
    re.VERBOSE
)
# Matches key="value", key='value', or key (boolean)
PROPS_REGEX = re.compile(
    r"""([a-zA-Z0-9_-]+)             # 1: Prop name
    (?:
      \s*=\s*                        # Equals sign
      (?:
        "([^"]*)"                    # 2: Double-quoted value
        |
        '([^']*)'                    # 3: Single-quoted value
      )
    )?                               # The value part is optional (for boolean props)
    """,
    re.VERBOSE
)
COMPONENT_PLACEHOLDER_PREFIX = "<!--HPY-COMPONENT-PLACEHOLDER:"
COMPONENT_PLACEHOLDER_SUFFIX = "-->"
# --- End Component Regex ---

PYTHON_SRC_REGEX = re.compile(
    r"""<python\s+
    [^>]*?
    src\s*=\s*
    (?:
        "([^"]+)"
      |
        '([^']+)'
    )
    [^>]*?
    >
    """,
    re.DOTALL | re.IGNORECASE | re.VERBOSE
)

CSS_HREF_REGEX = re.compile(
    r"""<css\s+
    href\s*=\s*
    (?:
        "([^"]+)"
      |
        '([^']+)'
    )
    [^>]*?
    /?>
    """,
    re.IGNORECASE | re.VERBOSE
)

HPY_HEAD_REGEX = re.compile(r"<hpy-head.*?>(.*?)</hpy-head>", re.DOTALL | re.IGNORECASE)
HPY_BODY_REGEX = re.compile(r"<hpy-body.*?>(.*?)</hpy-body>", re.DOTALL | re.IGNORECASE)


def _parse_and_replace_components(content: str, verbose: bool = False) -> Tuple[str, Dict[str, Any]]:
    """Finds component tags, replaces them with placeholders, and returns structured data."""
    components_found: Dict[str, Any] = {}

    def component_replacer(match):
        component_name = match.group(1)
        attributes_str = match.group(2)
        is_self_closing = match.group(3) == '/'

        # Generate a unique ID for this specific component instance
        instance_id = str(uuid.uuid4())
        
        props = {}
        for prop_match in PROPS_REGEX.finditer(attributes_str):
            key = prop_match.group(1)
            # Value is from group 2 (double-quoted) or 3 (single-quoted)
            # If both are None, it's a boolean prop, so we set it to True
            value = prop_match.group(2) if prop_match.group(2) is not None else prop_match.group(3)
            props[key] = value if value is not None else True

        components_found[instance_id] = {
            "name": component_name,
            "props": props,
            "is_self_closing": is_self_closing,
        }
        
        if verbose:
            print(f"  Found component <{component_name}> with props: {props}")

        return f"{COMPONENT_PLACEHOLDER_PREFIX}{instance_id}{COMPONENT_PLACEHOLDER_SUFFIX}"

    # Use a non-capturing group to handle the full tag including content and closing tag
    # This is a simplified regex and might not handle complex nesting perfectly, but is a good start.
    full_component_regex = re.compile(
        r"""<([A-Z][a-zA-Z0-9\.]*)\s*   # 1: Tag name
        ([^>]*?)                       # 2: Attributes
        (/?)>                          # 3: Optional self-closing slash
        (?:
            (?!</\1>)                  # Negative lookahead to ensure we don't match empty content greedily
            (.*?)                      # 4: Content (non-greedy)
            </\1>                      # Closing tag
        )?                             # Content and closing tag are optional
        """, re.DOTALL | re.VERBOSE
    )

    # We do a simple replacement for now. The regex above is for future slot implementation.
    # The current simpler COMPONENT_REGEX is sufficient for self-closing or empty-body tags.
    content_with_placeholders = COMPONENT_REGEX.sub(component_replacer, content)
    
    return content_with_placeholders, components_found


def parse_hpy_file(file_path: str, is_layout: bool = False, verbose: bool = False) -> Dict[str, Any]:
    """
    Parse a .hpy file, now with component detection.
    """
    path = Path(file_path).resolve()
    if not path.is_file(): raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() != '.hpy': raise ValueError(f"Not a valid .hpy file: {file_path}")

    try:
        with open(path, 'r', encoding='utf-8') as f: content = f.read()
    except Exception as e: raise IOError(f"Could not read file {path}: {e}") from e

    # --- NEW: Component Pre-parsing ---
    # This must run first to replace component tags with placeholders
    # before other regexes (like the one for <html>) get confused.
    content, components_found = _parse_and_replace_components(content, verbose)

    result: Dict[str, Any] = {
        'html': '',
        'style': '',
        'python': None,
        'script_src': None,
        'head_content': None,
        'css_links': [],
        'components': components_found # New key for found components
    }

    # The rest of the parsing logic remains largely the same
    css_matches = CSS_HREF_REGEX.finditer(content)
    for match in css_matches:
        href = match.group(1) or match.group(2)
        if href:
            result['css_links'].append(href.strip())
    if result['css_links'] and verbose:
        print(f"  Found {len(result['css_links'])} external CSS link(s) in {path.name}: {result['css_links']}")

    python_src_match = PYTHON_SRC_REGEX.search(content)
    if python_src_match:
        explicit_script_src = python_src_match.group(1) or python_src_match.group(2)
        if explicit_script_src:
            result['script_src'] = os.path.normpath(explicit_script_src.strip())

    if not result['script_src']:
        python_content_matches = re.findall(r'<python.*?>(.*?)</python>', content, re.DOTALL | re.IGNORECASE)
        if python_content_matches:
            result['python'] = "\n\n".join(p.strip() for p in python_content_matches).strip() or None

    style_matches = re.findall(r'<style.*?>(.*?)</style>', content, re.DOTALL | re.IGNORECASE)
    result['style'] = "\n\n".join(s.strip() for s in style_matches).strip() or ""

    if is_layout:
        hpy_head_match = HPY_HEAD_REGEX.search(content)
        hpy_body_match = HPY_BODY_REGEX.search(content)

        if hpy_head_match and hpy_body_match:
            result['head_content'] = hpy_head_match.group(1).strip()
            result['html'] = hpy_body_match.group(1).strip()
            if LAYOUT_PLACEHOLDER not in result['html']:
                raise ValueError(f"Error: Layout file '{path.name}' (using <hpy-body>) must contain placeholder '{LAYOUT_PLACEHOLDER}'.")
        else:
            html_match = re.search(r'<html.*?>(.*?)</html>', content, re.DOTALL | re.IGNORECASE)
            if not html_match:
                raise ValueError(f"Error: Layout file '{path.name}' must either use <hpy-head>/<hpy-body> tags or contain a full <html>...</html> section.")
            result['html'] = html_match.group(1).strip()
            if LAYOUT_PLACEHOLDER not in result['html']:
                raise ValueError(f"Error: Layout file '{path.name}' (using <html>) must contain placeholder '{LAYOUT_PLACEHOLDER}'.")
    else:
        hpy_head_match = HPY_HEAD_REGEX.search(content)
        if hpy_head_match:
            result['head_content'] = hpy_head_match.group(1).strip()
            content_for_html_extraction = HPY_HEAD_REGEX.sub('', content, count=1)
        else:
            content_for_html_extraction = content
        
        html_match = re.search(r'<html.*?>(.*?)</html>', content_for_html_extraction, re.DOTALL | re.IGNORECASE)
        if not html_match:
            temp_content = content
            if result['script_src']:
                temp_content = PYTHON_SRC_REGEX.sub('', temp_content, count=1)
            temp_content = re.sub(r'<python.*?</python>', '', temp_content, flags=re.DOTALL | re.IGNORECASE)
            temp_content = re.sub(r'<style.*?</style>', '', temp_content, flags=re.DOTALL | re.IGNORECASE)
            temp_content = CSS_HREF_REGEX.sub('', temp_content)
            if hpy_head_match:
                temp_content = HPY_HEAD_REGEX.sub('', temp_content, count=1)
            result['html'] = temp_content.strip()
        else:
            result['html'] = html_match.group(1).strip()

    if verbose:
        print(f"  Parsed {path.name}:")
        if result['components']: print(f"    components: {len(result['components'])} found")
        if result['css_links']: print(f"    css_links: {result['css_links']}")
        if result['style']: print(f"    style: Yes")
        if result['python'] or result['script_src']: print(f"    python: {'Inline' if result['python'] else 'Src: ' + result['script_src']}")

    return result