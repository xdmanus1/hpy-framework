# hpy_core/init.py
"""Project initialization logic."""

import sys
import time
from pathlib import Path
import os # Needed for path manipulation
import shutil # Needed for rmtree potentially on error cleanup (optional)
from typing import Optional # Added for type hinting

# Import constants from config within the same package
from .config import (
    LAYOUT_FILENAME, BRYTHON_VERSION, LAYOUT_PLACEHOLDER,
    CONFIG_FILENAME, DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR,
    DEFAULT_STATIC_DIR_NAME
)


# --- Template Definitions ---

def _get_single_file_template() -> str:
    """Returns the template content for a single app.hpy file."""
    # Reverted to standard formatting for Python block
    return f""" <html>
        <div id="app">
            <h1>Hello, HPY Framework!</h1>
            <button id="counter-btn">Clicked: 0 times</button>
            <div class="card">
                <input id="name-input" type="text" placeholder="Enter your name">
                <div id="greeting"></div>
            </div>
        </div>
    </html>

    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        #app {{
            max-width: 600px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }}
        h1 {{ color: #333; }}
        .card {{ margin-top: 20px; padding: 15px; background-color: #f9f9f9; border-radius: 4px; }}
        input {{ padding: 8px; margin-bottom: 10px; width: 100%; box-sizing: border-box; }}
        button {{ background-color: #4CAF50; color: white; padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }}
        button:hover {{ background-color: #45a049; }}
    </style>

<python>
# --- Start Python code HERE, with NO leading spaces/tabs on this line ---
from browser import document, html

# Counter functionality
count = 0

def update_counter(event):
    global count
    count += 1
    document["counter-btn"].text = f"Clicked: {{count}} times"

document["counter-btn"].bind("click", update_counter)

# Name input functionality
def update_greeting(event):
    name = document["name-input"].value
    if name:
        document["greeting"].html = f"<p>Hello, <strong>{{name}}</strong>! Welcome to HPY Framework.</p>"
    else:
        document["greeting"].html = ""

document["name-input"].bind("input", update_greeting)

# Add a dynamic element using Brython's html module
document["app"] <= html.P("This paragraph was dynamically added with Brython!")
# --- End Python code ---
</python>
"""

def _get_layout_template() -> str:
    """Returns the template content for the _layout.hpy file."""
    # Reverted Python block to standard formatting
    return f"""<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My HPY Site</title>
    <script src="https://cdn.jsdelivr.net/npm/brython@{BRYTHON_VERSION}/brython.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/brython@{BRYTHON_VERSION}/brython_stdlib.js"></script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; padding: 20px; max-width: 800px; margin: 20px auto; background-color: #f8f8f8; color: #333; }}
        h1, h2 {{ color: #333; }} nav {{ margin: 20px 0; padding: 10px 0; border-top: 1px solid #eee; border-bottom: 1px solid #eee; }} nav a {{ text-decoration: none; color: #007bff; margin-right: 15px; }} nav a:hover {{ text-decoration: underline; }}
        main {{ padding: 15px 0; }} footer {{ margin-top: 30px; padding-top: 10px; border-top: 1px solid #eee; font-size: 0.9em; color: #666; }} header h1 {{ margin-bottom: 0.5em; }}
        .logo {{ max-width: 50px; vertical-align: middle; margin-left: 10px; }}
    </style>
</head>
<body onload="brython({{'debug': 1}})">
    <header><h1>My HPY Application</h1><nav><a href="/">Home</a> <a href="/about.html">About</a> <img src="/static/logo.svg" alt="Logo" class="logo"></nav></header>
    <main>{LAYOUT_PLACEHOLDER}</main>
    <footer><p>© {time.strftime('%Y')} My HPY Project.</p></footer>
    <script type="text/python">
# Example Python in Layout - Helpers injected before this.
print("Global layout script loaded.")
# You could define globally available functions here
# def layout_function():
#     print("layout_function called")
    </script>
</body>
</html>
"""

def _get_layout_index_template() -> str:
    """Returns template content for index.hpy, minimal python as index.py exists."""
    # Reverted Python block to standard formatting
    return """<html>
<h2>Homepage</h2>
<p>Welcome! Content from <code>src/index.hpy</code>.</p>
<p>This page's logic is primarily in <code>src/index.py</code>.</p>
<button id="home-btn">Click Me (Home)</button>
<div id="home-output"></div>
</html>

<style>
#home-output { margin-top: 10px; padding: 8px; background-color: #e0e0e0; border: 1px solid #ccc; }
</style>

<python>
# Minimal inline python for index.hpy (mostly handled by index.py)
# print("Inline python from index.hpy executed (should be ignored if index.py exists).")
</python>
"""

def _get_layout_index_py_template() -> str:
    """Returns template content for index.py (external script)."""
    # Corrected Python formatting with newlines and indentation
    return """
# External Python script for index.hpy (loaded via src attribute)
# Brython helpers (byid, qs, qsa) are available (injected by hpy-tool).

print("index.py external script executed.")

# Access elements defined in index.hpy's <html> section
home_btn = byid("home-btn")
home_output = byid("home-output")
home_count = 0

def home_button_click(event):
    global home_count
    home_count += 1
    if home_output: # Check if element exists
        home_output.text = f"Home button (external script) clicked {home_count} times."

# Bind event if button exists
if home_btn:
    home_btn.bind("click", home_button_click)
    print("Bound click event to home-btn from index.py")
else:
    print("Could not find #home-btn in index.py")

# Example: Using a helper defined in layout's python (if any)
# try:
#     layout_function() # Call function defined in _layout.hpy's <python>
# except NameError:
#     print("layout_function not found (expected if layout has no python).")

"""

def _get_layout_about_template() -> str:
    """Returns template content for about.hpy, using <python src="...">."""
    # Reverted Python block (which is ignored anyway) to standard formatting
    return """<html>
<h2>About Us</h2>
<p>Content from <code>src/about.hpy</code>.</p>
<p>This page uses an external script specified via <code><python src></code>.</p>
<p id="about-message">Brython can update this.</p>
<button id="about-button">Update Message</button>
</html>

<style>
#about-message { font-style: italic; color: #555; }
#about-button { margin-top: 10px; }
</style>

<!-- Explicitly link the Python logic -->
<python src="scripts/about_logic.py">
# Inline python here is ignored because src is specified above.
</python>
"""

def _get_layout_about_py_template() -> str:
    """Returns template content for scripts/about_logic.py."""
    # Corrected Python formatting
    return """
# External Python script for about.hpy (loaded via explicit src attribute)
# Brython helpers (byid, qs, qsa) are available (injected by hpy-tool).

print("about_logic.py external script executed.")

# Access elements defined in about.hpy's <html> section
about_msg = byid("about-message")
about_btn = byid("about-button")

message_counter = 0

def update_about_message(event=None):
    global message_counter
    message_counter += 1
    if about_msg:
        about_msg.text = f"Updated by about_logic.py! (Count: {message_counter})"
    else:
        print("Could not find #about-message")

# Bind event if button exists
if about_btn:
    about_btn.bind("click", update_about_message)
    print("Bound click event to about-button from about_logic.py")
else:
    print("Could not find #about-button")

# Initial update
update_about_message()
"""

def _get_hpy_toml_template() -> str:
    """Returns the default content for the hpy.toml file."""
    # Standard multi-line formatting
    return f"""# HPY Tool Project Configuration ({CONFIG_FILENAME})
# For documentation, see [URL to docs when available]

[tool.hpy]

# Source directory containing your .hpy files and static assets.
input_dir = "{DEFAULT_INPUT_DIR}"

# Directory where compiled HTML and static assets will be placed.
output_dir = "{DEFAULT_OUTPUT_DIR}"

# Name of the directory within 'input_dir' for static assets (e.g., "static", "public", "assets").
# Files in this directory will be copied directly to 'output_dir'.
# The name here is also used as the base path in the output dir (e.g., output_dir/static_dir_name/).
static_dir_name = "{DEFAULT_STATIC_DIR_NAME}" # Uncomment and change if needed (must be uncommented to enable feature)
"""

def _get_logo_svg_template() -> str:
    """ Returns simple SVG logo content. """
    # Standard multi-line formatting
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="50" height="50">
  <circle cx="50" cy="50" r="45" fill="#4CAF50"/>
  <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="Arial" font-size="40" fill="white">HPY</text>
</svg>
"""


# --- Helper Functions for Project Creation ---

def _create_hpy_toml(project_path: Path):
    """Creates the default hpy.toml file."""
    hpy_toml_path = project_path / CONFIG_FILENAME
    try:
        with open(hpy_toml_path, "w", encoding="utf-8") as f:
            f.write(_get_hpy_toml_template())
        return hpy_toml_path
    except IOError as e:
        print(f"Error writing config file '{hpy_toml_path.name}': {e}", file=sys.stderr)
        raise

def _create_single_file_project(project_path: Path):
    """Creates the files for a single-file project."""
    app_hpy_path = project_path / "app.hpy"
    hpy_toml_path: Optional[Path] = None
    try:
        project_path.mkdir(parents=True, exist_ok=True)
        hpy_toml_path = _create_hpy_toml(project_path)
        with open(app_hpy_path, "w", encoding="utf-8") as f:
            f.write(_get_single_file_template())
    except OSError as e:
        print(f"Error creating project directory or files: {e}", file=sys.stderr)
        sys.exit(1)
    except IOError:
        print(f"Project initialization failed.", file=sys.stderr)
        sys.exit(1)
    print(f"\n✓ Simple single-file HPY project initialized in '{project_path}'.")
    if hpy_toml_path: print(f"✓ Created: {hpy_toml_path.name}")
    print(f"✓ Created: {app_hpy_path.name}")
    print("\nTo get started:")
    print(f"  cd {project_path.name}")
    print(f"  hpy app.hpy -w")


def _create_layout_project(project_path: Path):
    """Creates files for a directory-based project with layout, static dir, conventional and explicit external scripts."""
    hpy_toml_path: Optional[Path] = None
    static_dir_path: Optional[Path] = None
    scripts_dir_path: Optional[Path] = None # Track scripts dir

    try:
        project_path.mkdir(parents=True, exist_ok=True)
        hpy_toml_path = _create_hpy_toml(project_path)

        src_dir_name = DEFAULT_INPUT_DIR
        src_path = project_path / src_dir_name
        src_path.mkdir(exist_ok=True)

        # Create Layout
        layout_hpy_path = src_path / LAYOUT_FILENAME
        with open(layout_hpy_path, "w", encoding="utf-8") as f: f.write(_get_layout_template())

        # Create index page (uses conventional index.py)
        index_hpy_path = src_path / "index.hpy"
        index_py_path = src_path / "index.py"
        with open(index_hpy_path, "w", encoding="utf-8") as f: f.write(_get_layout_index_template())
        with open(index_py_path, "w", encoding="utf-8") as f: f.write(_get_layout_index_py_template())

        # Create about page (uses explicit src in sub-directory)
        about_hpy_path = src_path / "about.hpy"
        scripts_dir_path = src_path / "scripts"
        scripts_dir_path.mkdir(exist_ok=True)
        about_py_path = scripts_dir_path / "about_logic.py"
        with open(about_hpy_path, "w", encoding="utf-8") as f: f.write(_get_layout_about_template())
        with open(about_py_path, "w", encoding="utf-8") as f: f.write(_get_layout_about_py_template())

        # Create Static Directory and Asset
        static_dir_name = DEFAULT_STATIC_DIR_NAME
        static_dir_path = src_path / static_dir_name
        static_dir_path.mkdir(exist_ok=True)
        logo_path = static_dir_path / "logo.svg"
        with open(logo_path, "w", encoding="utf-8") as f: f.write(_get_logo_svg_template())

    except (OSError, IOError) as e:
        print(f"Error creating project files/directories: {e}", file=sys.stderr)
        sys.exit(1)

    # Update success messages
    print(f"\n✓ Directory-based HPY project initialized in '{project_path}'.")
    if hpy_toml_path: print(f"✓ Created: {hpy_toml_path.name}")
    print(f"✓ Source files created in '{src_path.relative_to(project_path)}'.")
    if scripts_dir_path: print(f"✓ Scripts directory created at '{scripts_dir_path.relative_to(project_path)}'.")
    if static_dir_path: print(f"✓ Static asset directory created at '{static_dir_path.relative_to(project_path)}'.")
    print(f"✓ Example pages created:")
    print(f"  - {src_path.relative_to(project_path)}/index.hpy (uses conventional src/index.py)")
    print(f"  - {src_path.relative_to(project_path)}/about.hpy (uses explicit <python src='scripts/about_logic.py'>)")

    print("\nTo get started:")
    print(f"  cd {project_path.name}")
    print(f"  (Edit {CONFIG_FILENAME} and uncomment 'static_dir_name' if needed)")
    print(f"  hpy -w")


# --- Main Initialization Function ---
def init_project(project_dir_str: str):
    """
    Initialize a new hpy project structure interactively.
    Creates the project directory and generates hpy.toml.
    """
    project_path = Path(project_dir_str).resolve()
    if project_path.exists() and project_path.is_dir() and any(project_path.iterdir()):
         print(f"Error: Directory '{project_dir_str}' already exists and is not empty.", file=sys.stderr); sys.exit(1)
    elif project_path.exists() and not project_path.is_dir():
         print(f"Error: '{project_dir_str}' exists and is not a directory.", file=sys.stderr); sys.exit(1)
    print("Choose a project template:")
    print("  1: Simple Single File (app.hpy + hpy.toml)")
    print(f"  2: Directory with Layout ({DEFAULT_INPUT_DIR}/_layout.hpy, scripts/, .py, {DEFAULT_STATIC_DIR_NAME}/, etc. + hpy.toml)")
    choice = "";
    while choice not in ["1", "2"]:
        choice = input("Enter choice (default: 2): ").strip();
        if not choice: choice = "2"
        if choice not in ["1", "2"]: print("Invalid choice. Please enter 1 or 2.")
    if choice == "1": _create_single_file_project(project_path)
    else: _create_layout_project(project_path)