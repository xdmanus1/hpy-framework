# hpy_core/init.py
"""Project initialization logic."""

import sys
import time
from pathlib import Path

# Import constants from config within the same package
from .config import LAYOUT_FILENAME, BRYTHON_VERSION, LAYOUT_PLACEHOLDER

# --- Template Definitions ---


def _get_single_file_template() -> str:
    """Returns the template content for a single app.hpy file."""
    # Basic single-file example
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
        
        h1 {{
            color: #333;
        }}
        
        .card {{
            margin-top: 20px;
            padding: 15px;
            background-color: #f9f9f9;
            border-radius: 4px;
        }}
        
        input {{
            padding: 8px;
            margin-bottom: 10px;
            width: 100%;
            box-sizing: border-box;
        }}
        
        button {{
            background-color: #4CAF50;
            color: white;
            padding: 10px 15px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
        }}
        
        button:hover {{
            background-color: #45a049;
        }}
    </style>

<python>
# --- Start Python code HERE, with NO leading spaces/tabs on this line ---
from browser import document, html

# Counter functionality
count = 0 # This should be at the base indentation level (0)

def update_counter(event):
    # Code inside functions/classes is indented relative to the def/class line
    global count
    count += 1
    document["counter-btn"].text = f"Clicked: {{count}} times"

# This top-level call should also be at base indentation level (0)
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
    # Same layout as before
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
    </style>
</head>
<body onload="brython({{'debug': 1}})">
    <header><h1>My HPY Application</h1><nav><a href="/">Home</a> <a href="/about.html">About</a></nav></header>
    <main>{LAYOUT_PLACEHOLDER}</main>
    <footer><p>© {time.strftime('%Y')} My HPY Project.</p></footer>
    <script type="text/python">print("Global layout script loaded.")</script>
</body>
</html>
"""


def _get_layout_index_template() -> str:
    """Returns template content for index.hpy in layout mode."""
    return """<html>
<h2>Homepage</h2>
<p>Welcome! Content from <code>src/index.hpy</code>.</p>
<button id="home-btn">Click Me (Home)</button>
<div id="home-output"></div>
</html>
<style>#home-output { margin-top: 10px; padding: 8px; background-color: #e0e0e0; }</style>
<python>
home_btn = byid("home-btn"); home_output = byid("home-output"); home_count = 0
def home_button_click(event): global home_count; home_count += 1; home_output.text = f"Home button clicked {home_count} times."
if home_btn: home_btn.bind("click", home_button_click)
print("index.hpy page script executed.")
</python>
"""


def _get_layout_about_template() -> str:
    """Returns template content for about.hpy in layout mode."""
    return """<html>
<h2>About Us</h2>
<p>Content from <code>src/about.hpy</code>.</p>
<p id="about-message">Brython can update this.</p>
</html>
<style>#about-message { font-style: italic; color: #555; }</style>
<python>
from browser import timer
about_msg = byid("about-message")
def update_msg(): about_msg.text = "Updated by about.hpy!"
if about_msg: timer.set_timeout(update_msg, 500)
print("about.hpy page script executed.")
</python>
"""


# --- Helper Functions for Project Creation ---


def _create_single_file_project(project_path: Path):
    """Creates the files for a single-file project."""
    app_hpy_path = project_path / "app.hpy"
    try:
        project_path.mkdir(parents=True, exist_ok=True)
        with open(app_hpy_path, "w", encoding="utf-8") as f:
            f.write(_get_single_file_template())
    except OSError as e:
        print(f"Error creating project directory: {e}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(
            f"Error writing template file '{app_hpy_path.name}': {e}", file=sys.stderr
        )
        sys.exit(1)

    print(f"\n✓ Simple single-file HPY project initialized in '{project_path}'.")
    print(f"✓ Created: {app_hpy_path.name}")
    print("\nTo get started:")
    print(f"  cd {project_path.name}")
    print(f"  hpy app.hpy -w")  # Updated run command


def _create_layout_project(project_path: Path):
    """Creates the files for a directory-based project with layout."""
    src_path = project_path / "src"
    layout_hpy_path = src_path / LAYOUT_FILENAME
    index_hpy_path = src_path / "index.hpy"
    about_hpy_path = src_path / "about.hpy"
    try:
        src_path.mkdir(parents=True, exist_ok=True)
        with open(layout_hpy_path, "w", encoding="utf-8") as f:
            f.write(_get_layout_template())
        with open(index_hpy_path, "w", encoding="utf-8") as f:
            f.write(_get_layout_index_template())
        with open(about_hpy_path, "w", encoding="utf-8") as f:
            f.write(_get_layout_about_template())
    except OSError as e:
        print(f"Error creating project directories: {e}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error writing template files: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n✓ Directory-based HPY project initialized in '{project_path}'.")
    print(f"✓ Source files created in '{src_path}'.")
    print("\nTo get started:")
    print(f"  cd {project_path.name}")
    print(f"  hpy src -w")  # Use 'src' as target


# --- Main Initialization Function ---


def init_project(project_dir: str):
    """
    Initialize a new hpy project structure interactively.
    """
    project_path = Path(project_dir)

    # 1. Check if target directory/file already exists
    if project_path.exists() and any(project_path.iterdir()):
        print(
            f"Error: Directory '{project_dir}' already exists and is not empty.",
            file=sys.stderr,
        )
        sys.exit(1)
    elif project_path.is_file():
        print(f"Error: '{project_dir}' exists and is a file.", file=sys.stderr)
        sys.exit(1)

    # 2. Ask user for project type
    print("Choose a project template:")
    print("  1: Simple Single File (app.hpy)")
    print("  2: Directory with Layout (src/_layout.hpy, src/index.hpy, ...)")

    choice = ""
    while choice not in ["1", "2"]:
        choice = input("Enter choice (default: 2): ").strip()
        if not choice:  # Handle empty input as default
            choice = "2"
        if choice not in ["1", "2"]:
            print("Invalid choice. Please enter 1 or 2.")

    # 3. Create project based on choice
    if choice == "1":
        _create_single_file_project(project_path)
    else:  # Choice is "2"
        _create_layout_project(project_path)
