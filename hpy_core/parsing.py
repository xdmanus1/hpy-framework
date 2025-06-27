# hpy_core/parsing.py
"""Parsing logic for .hpy files."""

import re
import sys
import os
from pathlib import Path
from typing import Dict, Optional, Any, List

from .config import LAYOUT_FILENAME, LAYOUT_PLACEHOLDER, APP_SHELL_HEAD_PLACEHOLDER, APP_SHELL_BODY_PLACEHOLDER

PYTHON_SRC_REGEX = re.compile(
    r"""<python\s+ # Opening tag with at least one space
    [^>]*?         # Any characters except > (non-greedy)
    src\s*=\s*     # src attribute preamble
    (?:
        "([^"]+)" # Double-quoted value (Group 1)
      |
        '([^']+)' # Single-quoted value (Group 2)
    )
    [^>]*?         # Any remaining attributes/chars
    >              # Closing > of the tag
    """,
    re.DOTALL | re.IGNORECASE | re.VERBOSE
)

# --- NEW: Regex for <css href="..."> ---
CSS_HREF_REGEX = re.compile(
    r"""<css\s+       # Opening <css tag
    [^>]*?           # Any characters except > (non-greedy)
    href\s*=\s*      # href attribute preamble
    (?:
        "([^"]+)"   # Double-quoted value (Group 1)
      |
        '([^']+)'   # Single-quoted value (Group 2)
    )
    [^>]*?           # Any remaining attributes/chars
    /?>              # Optional self-closing slash and closing >
    """,

    re.IGNORECASE | re.VERBOSE
)
# --- END NEW ---

# Regex to find top-level <hpy-head>...</hpy-head>
HPY_HEAD_REGEX = re.compile(r"<hpy-head.*?>(.*?)</hpy-head>", re.DOTALL | re.IGNORECASE)
# Regex to find top-level <hpy-body>...</hpy-body>
HPY_BODY_REGEX = re.compile(r"<hpy-body.*?>(.*?)</hpy-body>", re.DOTALL | re.IGNORECASE)


def parse_hpy_file(file_path: str, is_layout: bool = False, verbose: bool = False) -> Dict[str, Any]:
    """
    Parse a .hpy file.
    - For layouts (is_layout=True):
        - Looks for <hpy-head> and <hpy-body> tags.
        - Returns 'head_content', 'html' (from <hpy-body>), 'style', 'python', 'script_src', and 'css_links'.
        - If <hpy-head>/<hpy-body> not found, falls back to looking for full <html> structure (legacy layout).
    - For regular pages (is_layout=False):
        - Expects an <html>...</html> fragment (which will be the body content).
        - May optionally contain <hpy-head> for direct injection if no layout is used but _app.html is.
        - Returns 'html', 'style', 'python', 'script_src', 'css_links', and potentially 'head_content'.
    """
    path = Path(file_path).resolve()
    if not path.is_file(): raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() != '.hpy': raise ValueError(f"Not a valid .hpy file: {file_path}")

    try:
        with open(path, 'r', encoding='utf-8') as f: content = f.read()
    except Exception as e: raise IOError(f"Could not read file {path}: {e}") from e

    result: Dict[str, Any] = {
        'html': '',
        'style': '',
        'python': None,
        'script_src': None,
        'head_content': None,
        'css_links': []  # New key for external CSS links
    }

    # --- NEW: CSS Link Extraction ---
    css_matches = CSS_HREF_REGEX.finditer(content)
    for match in css_matches:
        href = match.group(1) or match.group(2)
        if href:
            result['css_links'].append(href.strip())
    if result['css_links'] and verbose:
        print(f"  Found {len(result['css_links'])} external CSS link(s) in {path.name}: {result['css_links']}")
    # --- END NEW ---

    # --- Script Source Extraction (applies to both layouts and pages) ---
    python_src_match = PYTHON_SRC_REGEX.search(content)
    if python_src_match:
        explicit_script_src = python_src_match.group(1) or python_src_match.group(2)
        if explicit_script_src:
            result['script_src'] = os.path.normpath(explicit_script_src.strip())
            if verbose: print(f"  Found explicit script source in {path.name}: '{result['script_src']}'")
            if len(PYTHON_SRC_REGEX.findall(content)) > 1 and verbose:
                print(f"Warning: Multiple <python src=...> tags found in '{path.name}'. Using the first one.", file=sys.stderr)
        else:
            if verbose: print(f"Warning: Found <python src=...> tag with empty value in '{path.name}'. Ignoring.", file=sys.stderr)

    # --- Inline Python Extraction (if no script_src) ---
    if not result['script_src']:
        python_content_matches = re.findall(r'<python.*?>(.*?)</python>', content, re.DOTALL | re.IGNORECASE)
        if python_content_matches:
            result['python'] = "\n\n".join(p.strip() for p in python_content_matches).strip() or None
            if result['python'] and verbose: print(f"  Using inline Python from {path.name}")
    elif verbose and any(p.strip() for p in re.findall(r'<python.*?>(.*?)</python>', content, re.DOTALL | re.IGNORECASE)):
        print(f"Warning: Inline <python> content ignored in '{path.name}' because <python src='{result['script_src']}'> is used.", file=sys.stderr)


    # --- Style Extraction (applies to both, typically from root or <hpy-head>) ---
    style_matches = re.findall(r'<style.*?>(.*?)</style>', content, re.DOTALL | re.IGNORECASE)
    result['style'] = "\n\n".join(s.strip() for s in style_matches).strip() or ""

    # --- Specific Parsing for Layouts vs. Pages ---
    if is_layout:
        hpy_head_match = HPY_HEAD_REGEX.search(content)
        hpy_body_match = HPY_BODY_REGEX.search(content)

        if hpy_head_match and hpy_body_match:
            if verbose: print(f"  Parsing layout '{path.name}' using <hpy-head>/<hpy-body> structure.")
            head_fragment = hpy_head_match.group(1).strip()
            result['html'] = hpy_body_match.group(1).strip()
            result['head_content'] = head_fragment
            
            if LAYOUT_PLACEHOLDER not in result['html']:
                raise ValueError(f"Error: Layout file '{path.name}' (using <hpy-body>) must contain placeholder '{LAYOUT_PLACEHOLDER}'.")
            if result['script_src'] and verbose:
                 print(f"Warning: <python src='{result['script_src']}'> found in layout file '{path.name}'. Layouts typically use inline python.", file=sys.stderr)
        
        else: # Fallback for legacy layout
            if verbose: print(f"  Layout '{path.name}' does not use <hpy-head>/<hpy-body>. Looking for full <html> structure (legacy).")
            html_match = re.search(r'<html.*?>(.*?)</html>', content, re.DOTALL | re.IGNORECASE)
            if not html_match:
                raise ValueError(f"Error: Layout file '{path.name}' must either use <hpy-head>/<hpy-body> tags or contain a full <html>...</html> section.")
            result['html'] = html_match.group(1).strip()
            if LAYOUT_PLACEHOLDER not in result['html']:
                raise ValueError(f"Error: Layout file '{path.name}' (using <html>) must contain placeholder '{LAYOUT_PLACEHOLDER}'.")

    else: # Parsing a regular page
        hpy_head_match = HPY_HEAD_REGEX.search(content)
        if hpy_head_match:
            if verbose: print(f"  Page '{path.name}' contains <hpy-head> section.")
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
            # --- NEW: Also remove <css> tags from the remnant ---
            temp_content = CSS_HREF_REGEX.sub('', temp_content)
            # --- END NEW ---
            if hpy_head_match:
                temp_content = HPY_HEAD_REGEX.sub('', temp_content, count=1)
            
            result['html'] = temp_content.strip()
            if not result['html'] and verbose:
                print(f"Warning: No <html>...</html> fragment or direct content found in page '{path.name}'. HTML body will be empty.", file=sys.stderr)
            elif verbose and ("<" in result['html'] or ">" in result['html']):
                 print(f"Warning: Page '{path.name}' content is used directly as HTML body, but not wrapped in <html> tags.", file=sys.stderr)
        else:
            result['html'] = html_match.group(1).strip()

    if verbose:
        print(f"  Parsed {path.name}:")
        print(f"    head_content: {'Yes' if result['head_content'] else 'No'}")
        print(f"    style: {'Yes' if result['style'] else 'No'}")
        print(f"    css_links: {result['css_links'] if result['css_links'] else 'No'}")
        print(f"    python: {'Inline' if result['python'] else ('Src: ' + result['script_src'] if result['script_src'] else 'No')}")

    return result