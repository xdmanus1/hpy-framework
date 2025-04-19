# hpy_core/parsing.py
"""Parsing logic for .hpy files, now supporting <python src="...">."""

import re
import sys
import os # For path normalization
from pathlib import Path
from typing import Dict, Optional, Any # Added Any

# Import constants from config
from .config import LAYOUT_FILENAME, LAYOUT_PLACEHOLDER

# Regex to find <python ... src="value" ...> or src='value'
# Captures the attribute value (group 1 or 2)
PYTHON_SRC_REGEX = re.compile(
    r"""<python        # Opening tag
    [^>]*?             # Any characters except > (non-greedy)
    src\s*=\s*         # src attribute preamble
    (?:
        "([^"]+)"     # Double-quoted value (Group 1)
      |
        '([^']+)'     # Single-quoted value (Group 2)
    )
    [^>]*?             # Any remaining attributes/chars
    >                  # Closing > of the tag
    """,
    re.DOTALL | re.IGNORECASE | re.VERBOSE
)

def parse_hpy_file(file_path: str, is_layout: bool = False, verbose: bool = False) -> Dict[str, Any]:
    """
    Parse a .hpy file. Extracts html, style, and either inline python
    or an explicit script source reference from <python src="...">.

    Returns dict with keys: 'html', 'style', 'python' (inline, str|None), 'script_src' (explicit, str|None).
    """
    path = Path(file_path).resolve()
    if not path.is_file(): raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() != '.hpy': raise ValueError(f"Not a valid .hpy file: {file_path}")

    try:
        with open(path, 'r', encoding='utf-8') as f: content = f.read()
    except Exception as e: raise IOError(f"Could not read file {path}: {e}") from e

    # Extract top-level sections
    html_match = re.search(r'<html.*?>(.*?)</html>', content, re.DOTALL | re.IGNORECASE)
    style_matches = re.findall(r'<style.*?>(.*?)</style>', content, re.DOTALL | re.IGNORECASE)
    # Find all python blocks first for potential inline content
    python_content_matches = re.findall(r'<python.*?>(.*?)</python>', content, re.DOTALL | re.IGNORECASE)
    # Find explicit src attribute
    python_src_match = PYTHON_SRC_REGEX.search(content)

    # --- Stricter Checks ---
    if not html_match:
        raise ValueError(f"Error: Required <html>...</html> section not found in '{path.name}'.")

    html_content_raw = html_match.group(1).strip()

    # Combine styles
    this_file_style = "\n\n".join(s.strip() for s in style_matches)

    # Determine script source and inline python
    explicit_script_src: Optional[str] = None
    inline_python: Optional[str] = None

    if python_src_match:
        # Found explicit src attribute. Use the first non-empty capture group.
        explicit_script_src = python_src_match.group(1) or python_src_match.group(2)
        if not explicit_script_src:
            # This should technically not happen with the regex if src= exists
            print(f"Warning: Found <python src=...> tag with empty value in '{path.name}'. Ignoring.", file=sys.stderr)
            explicit_script_src = None # Treat as if not found
        else:
             # Normalize path separators for internal consistency
             explicit_script_src = os.path.normpath(explicit_script_src.strip())
             if verbose: print(f"  Found explicit script source in {path.name}: '{explicit_script_src}'")
             # Check for multiple src tags (optional warning)
             if len(PYTHON_SRC_REGEX.findall(content)) > 1 and verbose:
                  print(f"Warning: Multiple <python src=...> tags found in '{path.name}'. Using the first one: '{explicit_script_src}'.", file=sys.stderr)

    # If no *valid* explicit src was found, collect inline python
    if not explicit_script_src:
        inline_python = "\n\n".join(p.strip() for p in python_content_matches) or None
        if inline_python and verbose: print(f"  Using inline Python from {path.name}")
    elif python_content_matches and any(p.strip() for p in python_content_matches) and verbose:
         # Warn if src is used AND there's non-empty inline python
         print(f"Warning: Inline <python> content ignored in '{path.name}' because <python src='{explicit_script_src}'> is used.", file=sys.stderr)


    # Layout specific checks
    if is_layout:
        if explicit_script_src:
             print(f"Warning: <python src='{explicit_script_src}'> found in layout file '{path.name}'. Layouts should use inline python. Ignoring src attribute.", file=sys.stderr)
             explicit_script_src = None # Ignore src in layout, force inline
             inline_python = "\n\n".join(p.strip() for p in python_content_matches) or None # Re-evaluate inline
        if LAYOUT_PLACEHOLDER not in html_content_raw:
             raise ValueError(f"Error: Layout file '{path.name}' must contain placeholder '{LAYOUT_PLACEHOLDER}'.")
        # Warnings for missing style/python remain useful
        if not inline_python: print(f"Warning: No <python> section found in layout '{path.name}'.", file=sys.stderr)
        if not style_matches: print(f"Warning: No <style> section found in layout '{path.name}'.", file=sys.stderr)

    # Return extracted content
    return {
        'html': html_content_raw,
        'style': this_file_style,
        'python': inline_python, # Content of inline python tags (None if src used or none found)
        'script_src': explicit_script_src # Path from src attribute (None if not found/used)
    }