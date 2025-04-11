# hpy_core/parsing.py
"""Parsing logic for .hpy files."""

import re
import sys
from pathlib import Path
from typing import Dict, Optional

# Import constants from config
from .config import LAYOUT_FILENAME, LAYOUT_PLACEHOLDER

def parse_hpy_file(file_path: str, is_layout: bool = False) -> Dict[str, str]:
    """
    Parse a .hpy file. Layout files have slightly different requirements checks.
    NOTE: Component include logic is removed for this version.
    """
    path = Path(file_path).resolve()
    if not path.is_file(): raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() != '.hpy': raise ValueError(f"Not a valid .hpy file: {file_path}")

    try:
        with open(path, 'r', encoding='utf-8') as f: content = f.read()
    except Exception as e: raise IOError(f"Could not read file {path}: {e}") from e

    # Extract top-level sections for *this specific file*
    html_match = re.search(r'<html.*?>(.*?)</html>', content, re.DOTALL | re.IGNORECASE)
    style_matches = re.findall(r'<style.*?>(.*?)</style>', content, re.DOTALL | re.IGNORECASE)
    python_matches = re.findall(r'<python.*?>(.*?)</python>', content, re.DOTALL | re.IGNORECASE)

    # Combine this file's own style/python
    this_file_style = "\n\n".join(s.strip() for s in style_matches)
    this_file_python = "\n\n".join(p.strip() for p in python_matches)

    # --- Stricter Checks ---
    if not html_match:
        raise ValueError(f"Error: Required <html>...</html> section not found in '{path.name}'.")

    html_content_raw = html_match.group(1).strip()

    # Layout specific checks
    if is_layout:
        if LAYOUT_PLACEHOLDER not in html_content_raw:
             raise ValueError(f"Error: Layout file '{path.name}' must contain placeholder '{LAYOUT_PLACEHOLDER}'.")
        if not python_matches: print(f"Warning: No <python> section found in layout '{path.name}'.", file=sys.stderr)
        if not style_matches: print(f"Warning: No <style> section found in layout '{path.name}'.", file=sys.stderr)

    # Return extracted content (no include processing)
    return {
        'html': html_content_raw,
        'style': this_file_style,
        'python': this_file_python
    }