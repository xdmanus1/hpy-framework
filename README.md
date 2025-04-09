# HPY Tool ⚡

[![PyPI version](https://img.shields.io/pypi/v/hpy-tool.svg?style=flat-square)](https://pypi.org/project/hpy-tool/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

**A simple command-line tool to build interactive web applications from single `.hpy` files (HTML + CSS + Python) using the magic of [Brython](https://brython.info)!  ✨**

Write your entire web component – structure, style, and logic – in one `.hpy` file and let `hpy-tool` bundle it into a ready-to-run HTML application where your Python code executes directly in the browser.

Perfect for:

*   Rapid prototyping of web ideas.
*   Learning and experimenting with Brython.
*   Small projects where you want everything in one place.
*   Creating interactive examples or documentation snippets.

## Features

*   **Compile `.hpy`:** Parses `.hpy` files and generates a standalone `index.html`.
*   **Brython Integration:** Automatically includes the Brython runtime and embeds your Python code correctly.
*   **Development Server:** (`-s`) Serves your compiled app locally.
*   **Live Reload:** (`-w`) Watches your `.hpy` file for changes and automatically rebuilds. Just refresh your browser! (Requires `watchdog`).
*   **Configurable:** Specify output directory (`-o`) and server port (`-p`).
*   **Verbose Mode:** (`-v`) Get detailed output during the build and server requests.

## Installation

It's recommended to use a Python virtual environment.

```bash
# 1. Create and activate a virtual environment (if you haven't already)
python -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`

# 2. Install hpy-tool (from PyPI - placeholder for future)
# pip install hpy-tool

# OR: Install from local source for development (navigate to project dir first)
pip install -e .
```

This will also install necessary dependencies like `watchdog` if you plan to use the `-w` flag.

## Usage

```bash
# Display help message
hpy --help

# Compile a single file (outputs to ./dist/index.html by default)
hpy my_app.hpy

# Compile to a specific directory
hpy my_app.hpy -o build

# Compile and start a development server (default port 8000)
hpy my_app.hpy -s

# Compile, serve on port 8080, and watch for changes (recommended for dev)
hpy my_app.hpy -s -w -p 8080
# or simply:
hpy my_app.hpy -w -p 8080 # (-w implies -s)

# Use verbose mode for more detailed output
hpy my_app.hpy -w -v
```

## `.hpy` File Structure

An `.hpy` file combines HTML, CSS, and Python using dedicated tags:


<!-- my_app.hpy -->

<html>
    <!-- Your main HTML structure goes here -->
    <h1>Hello, <span id="name">World</span>!</h1>
    <input id="name-input" placeholder="Enter your name">
</html>

<style>
    /* Your CSS rules go here */
    body { font-family: sans-serif; }
    h1 { color: steelblue; }
    input { margin-top: 10px; padding: 5px; }
</style>

<python>
# Your Brython-powered Python code goes here
# Make sure code starts at indentation level 0 within this block!
from browser import document, bind

def update_name(event):
    name = document['name-input'].value
    document['name'].text = name if name else "World"

# Bind event listener
input_element = document['name-input']
input_element.bind('input', update_name)

# Initial greeting update (optional)
update_name(None)

print("HPY app loaded and Python executed!")
</python>


**Important:** Ensure your Python code inside the `<python>` block starts with no leading indentation. `hpy-tool` uses `textwrap.dedent` to handle block-level indentation, but your Python syntax's relative indentation must be correct.

## Behind the Scenes

`hpy-tool` leverages [Brython](https://brython.info), a fantastic project that implements a Python 3 interpreter directly in the browser using JavaScript. Your Python code within `<python>` tags is executed by Brython's engine.

## License

This project is licensed under the **MIT License**. See the `LICENSE` file for details (You should add a LICENSE file to your project).
