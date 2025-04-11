# HPY Tool ⚡ v0.6.3

[![License: BSD 3-Clause](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg?style=flat-square)](https://opensource.org/licenses/BSD-3-Clause) <!-- Updated License Badge -->
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg?style=flat-square)](https://www.python.org/downloads/)
<!-- Optional: Add PyPI badge if published -->
<!-- [![PyPI version](https://img.shields.io/pypi/v/hpy-tool.svg?style=flat-square)](https://pypi.org/project/hpy-tool/) -->

**Initialize, build, serve, and live-reload web applications from structured `.hpy` projects (HTML + CSS + Python) using the magic of [Brython](https://brython.info)! ✨**

`hpy-tool` streamlines creating interactive web applications by processing `.hpy` files and directories. Define shared layouts and individual pages, keeping structure (`<html>`), styling (`<style>`), and client-side logic (`<python>`) organized. `hpy-tool` bundles everything into standard HTML files where your Python code runs directly in the browser, powered by Brython.

Inspired by the simplicity of tools like SvelteKit, this tool aims to provide a straightforward development experience for Brython-based projects.

## Project Status & Disclaimer

⚠️ **Please Note:** This project is currently maintained primarily as a learning exercise. While it aims to be functional and useful for the described use cases, it's still under development. There might be bugs, rough edges, or areas for improvement. Treat it as **experimental**. Feedback, bug reports, and contributions are highly encouraged!

## Core Features (v0.6.x)

*   🚀 **Project Initialization:** (`--init`) Quickly scaffold a new project with a default layout and example pages.
*   📁 **Directory-Based Workflow:** Process an entire source directory (`src/` by default) containing your layout and page files.
*   📄 **Layout Support:** Define a global `_layout.hpy` for shared HTML structure, CSS, and Python logic. Page content is injected automatically.
*   🧩 **Single-File Pages:** Write individual page content and logic in separate `.hpy` files within your source directory.
*   🐍 **Brython Integration:** Automatically includes the Brython runtime and correctly embeds combined layout and page Python code.
*   ⚙️ **Smart Compilation:** Builds HTML files corresponding to your source `.hpy` pages, applying the layout.
*   🚀 **Development Server:** (`-s`, `-p`) Instantly serves your compiled application locally from the output directory with no-cache headers.
*   🔄 **Live Rebuilding:** (`-w`) Automatically recompiles when source files change (requires `watchdog`). Uses a simple, robust strategy (layout/component change rebuilds all, page change rebuilds page).
*   🗣️ **Verbose Mode:** (`-v`) Provides detailed logs for build steps and server activity.
*   🔧 **Configurable:** Control the output directory (`-o`) and server port (`-p`).
*   💡 **DOM Helpers:** Automatically injects `byid()`, `qs()`, `qsa()` helpers for cleaner Python DOM manipulation.
*   🏗️ **Refactored Codebase:** Internal code organized into the `hpy_core` package for better maintainability.

## Ideal For

*   ⚡ Building small to medium-sized web applications or dashboards with Python in the browser.
*   🎓 Learning and experimenting with Brython in a structured project setup.
*   📦 Creating interactive documentation examples or simple UI components.
*   ⚡ Rapid prototyping where code organization is helpful.

## Installation

A Python virtual environment is strongly recommended.

```bash
# 1. Create and activate a virtual environment (if you haven't)
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows (CMD):
# .venv\Scripts\activate.bat
# Windows (PowerShell):
# .venv\Scripts\Activate.ps1

# 2. Install hpy-tool
# Option A: From PyPI (once published)
# pip install hpy-tool

# Option B: From local source code (for development)
# Navigate to the directory containing pyproject.toml
pip install -e .

# Note: This installs 'watchdog' automatically as a dependency, needed for -w.
```

## Getting Started: New Project

1.  **Initialize a Project:**

    ```bash
    hpy --init my-new-app
    cd my-new-app
    ```
    This creates:
    ```
    my-new-app/
    └── src/
        ├── _layout.hpy   # Shared layout file
        ├── about.hpy     # Example page
        └── index.hpy     # Example homepage
    ```

2.  **Run the Dev Server with Watch:**

    ```bash
    # Make sure you are inside 'my-new-app' directory
    hpy src -w
    ```
    *(The `src` argument tells `hpy` to process the `src` directory. `-w` enables watching and serving)*

3.  **Open your browser:** Navigate to `http://localhost:8000` (or the specified port).
4.  **Develop!** Edit files in the `src/` directory.
5.  **Save & Refresh:** Save your changes. The tool will automatically rebuild. Refresh your browser!

## Project Structure Explained

*   **`src/` (or your specified source directory):** Contains all your source `.hpy` files.
*   **`src/_layout.hpy` (Optional but Recommended):**
    *   Defines the main HTML structure (`<head>`, `<body>`, shared elements).
    *   Must contain `<!-- HPY_PAGE_CONTENT -->` where page content is injected.
    *   Can contain global `<style>` and `<python>` blocks.
*   **`src/*.hpy` (Page Files):**
    *   Contain specific page content (`<html>` section replaces the layout placeholder).
    *   Can contain page-specific `<style>` and `<python>` blocks.

## `.hpy` File Structure Guide

*   **`<html>...</html>`:** Contains the HTML fragment. (Required).
*   **`<style>...</style>`:** Contains CSS rules. Multiple tags are concatenated. (Optional).
*   **`<python>...</python>`:** Contains Brython (Python 3) code. Multiple tags are concatenated. (Optional).

**Important Notes:**
*   Ensure Python code inside `<python>` starts with no leading indentation.
*   The layout file must contain `<!-- HPY_PAGE_CONTENT -->`.
*   CSS and Python from layout/pages are combined globally – beware of name conflicts!

### Simplified DOM Access

These helpers are automatically available in your `<python>` blocks:

*   `byid(id)`: Returns element or `None`.
*   `qs(selector)`: Returns first matching element or `None`.
*   `qsa(selector)`: Returns a list of matching elements.

## Command-Line Usage

```
usage: hpy [-h] [--init PROJECT_DIR] [-o DIR] [-v] [-s] [-p PORT] [-w] [--version] [SOURCE]

HPY Tool: Compile/serve .hpy projects (with layout support). Initialize new projects.

positional arguments:
  SOURCE                Path to source .hpy file or directory.
                        (default: src)

options:
  -h, --help            show this help message and exit
  --init PROJECT_DIR    Initialize a new HPY project structure. Ignores SOURCE.
  -o DIR, --output-dir DIR
                        Directory for compiled output.
                        (default: dist)
  -v, --verbose         Enable detailed output.
  -s, --serve           Start a dev server serving the output directory.
  -p PORT, --port PORT  Port for the development server.
                        (default: 8000)
  -w, --watch           Watch source for changes and rebuild. Requires 'watchdog'.
                        Using -w implies -s.
  --version             show program's version number and exit

Examples:
  hpy --init my_app          # Initialize project 'my_app'
  hpy src -o build           # Compile src/ to build/ (using _layout.hpy)
  hpy src -s -p 8080         # Compile src/ and serve from dist/ on port 8080
  hpy src/app.hpy -w         # Watch single file (layout NOT automatically used)
  hpy src -w                 # Watch src/ recursively, rebuild on changes
```
*(Note: Single file mode (`hpy page.hpy`) compiles the file directly and does **not** automatically use a `_layout.hpy` file.)*

## How it Works

When processing a directory, `hpy-tool` parses the layout (if present) and then each page file. It combines the CSS and Python, injects the page HTML into the layout placeholder, and generates the final output file. The watcher monitors the source directory and triggers rebuilds based on file changes.

## Contributing & Development Notes

This project uses standard Python tooling (`setuptools`, `venv`).

*   **Commits:** Please follow conventional commit message standards if possible (e.g., `feat: Add static file copying`, `fix: Correct watcher logic`).
*   **Reporting Issues:** If you find a bug or have a suggestion, please open an issue on the project repository (if available). Provide clear steps to reproduce the problem.
*   **Pull Requests:** Contributions are welcome! Please discuss larger changes in an issue first. Ensure code is formatted reasonably and includes necessary explanations.

Remember the project status disclaimer - your contributions can help improve it significantly!

## License

This project is licensed under the **BSD 3-Clause "New" or "Revised" License**. See the `LICENSE` file for details.
