# hpy_core/init.py
"""Project initialization logic."""

import sys
import time
from pathlib import Path

# Import constants from config within the same package
from .config import LAYOUT_FILENAME, BRYTHON_VERSION, LAYOUT_PLACEHOLDER

def init_project(project_dir: str):
    """
    Initialize a new hpy project structure with layout and example pages.
    """
    project_path = Path(project_dir)
    src_path = project_path / "src"

    if project_path.exists() and any(project_path.iterdir()):
         print(f"Error: Directory '{project_dir}' exists and is not empty.", file=sys.stderr)
         sys.exit(1)
    elif project_path.is_file():
         print(f"Error: '{project_dir}' exists and is a file.", file=sys.stderr)
         sys.exit(1)

    try:
        src_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Error creating project dirs: {e}", file=sys.stderr); sys.exit(1)

    # --- Template Content (Simplified for brevity) ---
    layout_hpy_content = f"""<html><head><title>My HPY Site</title><script src="https://cdn.jsdelivr.net/npm/brython@{BRYTHON_VERSION}/brython.min.js"></script><script src="https://cdn.jsdelivr.net/npm/brython@{BRYTHON_VERSION}/brython_stdlib.js"></script><style>body {{font-family: sans-serif; padding: 20px;}} nav a {{ margin-right: 10px; }}</style></head><body onload="brython({{'debug': 1}})"><header><h1>My HPY App</h1><nav><a href="/">Home</a><a href="/about.html">About</a></nav></header><main>{LAYOUT_PLACEHOLDER}</main><footer><p>© {time.strftime('%Y')}</p></footer><script type="text/python">print("Layout script")</script></body></html>"""
    index_hpy_content = f"""<html><h2>Homepage</h2><p>Content from index.hpy.</p></html><style>/* index style */</style><python>print("Index script")</python>"""
    about_hpy_content = f"""<html><h2>About</h2><p>Content from about.hpy.</p></html><style>/* about style */</style><python>print("About script")</python>"""
    # --- End Template Content ---

    layout_hpy_path = src_path / LAYOUT_FILENAME
    index_hpy_path = src_path / "index.hpy"
    about_hpy_path = src_path / "about.hpy"

    try:
        with open(layout_hpy_path, "w", encoding="utf-8") as f: f.write(layout_hpy_content)
        with open(index_hpy_path, "w", encoding="utf-8") as f: f.write(index_hpy_content)
        with open(about_hpy_path, "w", encoding="utf-8") as f: f.write(about_hpy_content)
    except IOError as e: print(f"Error writing template files: {e}", file=sys.stderr); sys.exit(1)

    print(f"✓ HPY project initialized in '{project_dir}'.")
    print(f"✓ Source files created in '{src_path}'.")
    print("\nTo get started:")
    print(f"  cd {project_dir}")
    print(f"  hpy src -w")