# hpy_core/parsing.py
"""Parsing logic for .hpy files."""

import re
import sys
import os
from pathlib import Path
from typing import Dict, Optional, Any

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

# Regex to find top-level <hpy-head>...</hpy-head>
HPY_HEAD_REGEX = re.compile(r"<hpy-head.*?>(.*?)</hpy-head>", re.DOTALL | re.IGNORECASE)
# Regex to find top-level <hpy-body>...</hpy-body>
HPY_BODY_REGEX = re.compile(r"<hpy-body.*?>(.*?)</hpy-body>", re.DOTALL | re.IGNORECASE)


def parse_hpy_file(file_path: str, is_layout: bool = False, verbose: bool = False) -> Dict[str, Any]:
    """
    Parse a .hpy file.
    - For layouts (is_layout=True):
        - Looks for <hpy-head> and <hpy-body> tags.
        - Returns 'head_content', 'html' (from <hpy-body>), 'style', 'python', 'script_src'.
        - If <hpy-head>/<hpy-body> not found, falls back to looking for full <html> structure (legacy layout).
    - For regular pages (is_layout=False):
        - Expects an <html>...</html> fragment (which will be the body content).
        - May optionally contain <hpy-head> for direct injection if no layout is used but _app.html is.
        - Returns 'html', 'style', 'python', 'script_src', and potentially 'head_content'.
    """
    path = Path(file_path).resolve()
    if not path.is_file(): raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() != '.hpy': raise ValueError(f"Not a valid .hpy file: {file_path}")

    try:
        with open(path, 'r', encoding='utf-8') as f: content = f.read()
    except Exception as e: raise IOError(f"Could not read file {path}: {e}") from e

    # Initialize results
    # 'html' will store the main body content fragment
    # 'head_content' will store content for the <head> of the app shell
    # 'style' will store combined <style> tags
    # 'python' will store inline python
    # 'script_src' will store external python script source
    result: Dict[str, Any] = {
        'html': '',
        'style': '',
        'python': None,
        'script_src': None,
        'head_content': None # New key for content to be injected into app shell's head
    }

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
    # We extract all style tags first. If <hpy-head> is used, styles from there are preferred for head_content.
    # For now, let's combine all styles found into result['style'].
    # The building logic can later decide if some styles go into head_content vs. inline in body if needed.
    style_matches = re.findall(r'<style.*?>(.*?)</style>', content, re.DOTALL | re.IGNORECASE)
    result['style'] = "\n\n".join(s.strip() for s in style_matches).strip() or ""


    # --- Specific Parsing for Layouts vs. Pages ---
    if is_layout:
        hpy_head_match = HPY_HEAD_REGEX.search(content)
        hpy_body_match = HPY_BODY_REGEX.search(content)

        if hpy_head_match and hpy_body_match:
            if verbose: print(f"  Parsing layout '{path.name}' using <hpy-head>/<hpy-body> structure.")
            head_fragment = hpy_head_match.group(1).strip()
            result['html'] = hpy_body_match.group(1).strip() # Main content for layout is from <hpy-body>

            # Extract styles and other tags from head_fragment to populate 'head_content'
            # For now, let's assume all of head_fragment (excluding its own style tags already caught)
            # can go into head_content. This logic can be refined.
            # Let's make head_content the raw content of <hpy-head> for now.
            # Building logic will integrate this.
            result['head_content'] = head_fragment
            
            # Styles within <hpy-head> are already part of result['style'] by global extraction.
            # Python within <hpy-head> or <hpy-body> is handled by the global Python extraction.

            if LAYOUT_PLACEHOLDER not in result['html']:
                raise ValueError(f"Error: Layout file '{path.name}' (using <hpy-body>) must contain placeholder '{LAYOUT_PLACEHOLDER}'.")
            if result['script_src'] and verbose: # script_src in layout is unusual but possible
                 print(f"Warning: <python src='{result['script_src']}'> found in layout file '{path.name}'. Layouts typically use inline python.", file=sys.stderr)
        
        else: # Fallback for legacy layout or layout not using <hpy-head>/<hpy-body>
            if verbose: print(f"  Layout '{path.name}' does not use <hpy-head>/<hpy-body>. Looking for full <html> structure (legacy).")
            html_match = re.search(r'<html.*?>(.*?)</html>', content, re.DOTALL | re.IGNORECASE)
            if not html_match:
                raise ValueError(f"Error: Layout file '{path.name}' must either use <hpy-head>/<hpy-body> tags or contain a full <html>...</html> section.")
            result['html'] = html_match.group(1).strip() # Entire content of <html> tag
            if LAYOUT_PLACEHOLDER not in result['html']:
                raise ValueError(f"Error: Layout file '{path.name}' (using <html>) must contain placeholder '{LAYOUT_PLACEHOLDER}'.")
            # In this legacy mode, 'head_content' remains None. Styles/Python extracted globally.

    else: # Parsing a regular page
        # A page might provide its own <hpy-head> content if no layout is used but _app.html is.
        hpy_head_match = HPY_HEAD_REGEX.search(content)
        if hpy_head_match:
            if verbose: print(f"  Page '{path.name}' contains <hpy-head> section.")
            result['head_content'] = hpy_head_match.group(1).strip()
            # Remove <hpy-head>...</hpy-head> from main content to avoid duplication if parsing <html> next
            content_for_html_extraction = HPY_HEAD_REGEX.sub('', content, count=1)
        else:
            content_for_html_extraction = content
        
        # Regular pages are expected to provide the content for the body (often an <html> fragment)
        html_match = re.search(r'<html.*?>(.*?)</html>', content_for_html_extraction, re.DOTALL | re.IGNORECASE)
        if not html_match:
            # If no <html> tag, consider the whole file content (minus scripts/styles/hpy-head) as the HTML fragment.
            # This is a simplification. For now, let's be stricter and expect <html> for pages.
            # This can be relaxed if needed, but might lead to less predictable parsing.
            # For now, let's allow it but warn if it's not just simple text.
            # A better approach would be to strip all known tags (<style>, <python>, <hpy-head>)
            # and use the remainder.

            # For now, if no <html> found in a page, take the content stripped of special blocks.
            # This is a rough approximation.
            temp_content = content
            if result['script_src']: # Remove the <python src> tag itself
                temp_content = PYTHON_SRC_REGEX.sub('', temp_content, count=1)
            
            # Remove all <python>...</python> blocks
            temp_content = re.sub(r'<python.*?</python>', '', temp_content, flags=re.DOTALL | re.IGNORECASE)
            # Remove all <style>...</style> blocks
            temp_content = re.sub(r'<style.*?</style>', '', temp_content, flags=re.DOTALL | re.IGNORECASE)
            # Remove <hpy-head> if present
            if hpy_head_match:
                temp_content = HPY_HEAD_REGEX.sub('', temp_content, count=1)
            
            result['html'] = temp_content.strip()
            if not result['html'] and verbose:
                print(f"Warning: No <html>...</html> fragment or direct content found in page '{path.name}'. HTML body will be empty.", file=sys.stderr)
            elif verbose and ("<" in result['html'] or ">" in result['html']): # If it looks like HTML but isn't wrapped
                 print(f"Warning: Page '{path.name}' content is used directly as HTML body, but not wrapped in <html> tags.", file=sys.stderr)

        else: # <html> tag found
            result['html'] = html_match.group(1).strip()


    if verbose:
        print(f"  Parsed {path.name}:")
        print(f"    head_content: {'Yes' if result['head_content'] else 'No'}")
        # print(f"    html: {result['html'][:50].replace(os.linesep, ' ') + '...' if result['html'] else 'None'}") # Can be too verbose
        print(f"    style: {'Yes' if result['style'] else 'No'}")
        print(f"    python: {'Inline' if result['python'] else ('Src: ' + result['script_src'] if result['script_src'] else 'No')}")

    return result