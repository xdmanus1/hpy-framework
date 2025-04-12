# HPY Tool ⚡ v0.7.0

[![License: BSD 3-Clause](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg?style=flat-square)](https://opensource.org/licenses/BSD-3-Clause)
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg?style=flat-square)](https://www.python.org/downloads/)
<!-- Optional: Add PyPI badge if published -->
<!-- [![PyPI version](https://img.shields.io/pypi/v/hpy-tool.svg?style=flat-square)](https://pypi.org/project/hpy-tool/) -->

**Initialize, configure, build, serve, and live-reload web applications from structured `.hpy` projects (HTML + CSS + Python + Static Assets) using the magic of [Brython](https://brython.info)! ✨**

`hpy-tool` streamlines creating interactive web applications by processing `.hpy` files, static assets, and directories. Define shared layouts and individual pages, keeping structure (`<html>`), styling (`<style>`), and client-side logic (`<python>`) organized. Use a simple `hpy.toml` file for project configuration. `hpy-tool` bundles everything into standard HTML files where your Python code runs directly in the browser, powered by Brython, and copies your static assets to the output directory.

Inspired by the simplicity of tools like SvelteKit, this tool aims to provide a straightforward development experience for Brython-based projects.

## Project Status & Disclaimer

⚠️ **Please Note:** This project is currently maintained primarily as a learning exercise. While it aims to be functional and useful for the described use cases, it's still under development. There might be bugs, rough edges, or areas for improvement. Treat it as **experimental**. Feedback, bug reports, and contributions are highly encouraged!

## Core Features (v0.7.0)

*   🚀 **Project Initialization:** (`--init`) Quickly scaffold a new project with a default layout, example pages, `hpy.toml` configuration, and a static assets directory.
*   ⚙️ **Project Configuration:** (`hpy.toml`) Define common settings like input source directory, output directory, and static asset directory name in a simple TOML file at the project root. CLI flags override `hpy.toml` settings.
*   📁 **Directory-Based Workflow:** Process an entire source directory (`src/` by default, configurable via `hpy.toml`) containing your layout, page files, and static assets.
*   📄 **Layout Support:** Define a global `_layout.hpy` for shared HTML structure, CSS, and Python logic. Page content is injected automatically.
*   🧩 **Single-File Pages:** Write individual page content and logic in separate `.hpy` files within your source directory.
*   🖼️ **Static Asset Handling:** Automatically copies files from a designated static directory (e.g., `src/static/`) to the output directory (e.g., `dist/static/`) during builds and keeps them synced in watch mode.
*   🐍 **Brython Integration:** Automatically includes the Brython runtime and correctly embeds combined layout and page Python code.
*   ⚙️ **Smart Compilation:** Builds HTML files corresponding to your source `.hpy` pages, applying the layout.
*   🚀 **Development Server:** (`-s`, `-p`) Instantly serves your compiled application locally from the output directory with no-cache headers.
*   🔄 **Live Rebuilding & Syncing:** (`-w`) Automatically recompiles `.hpy` files and syncs static assets when source files change (requires `watchdog`). Uses a simple, robust strategy (layout change rebuilds all, page change rebuilds page, static changes are synced).
*   🗣️ **Verbose Mode:** (`-v`) Provides detailed logs for build steps, static file operations, and server activity.
*   💡 **DOM Helpers:** Automatically injects `byid()`, `qs()`, `qsa()` helpers for cleaner Python DOM manipulation.
*   🏗️ **Refactored Codebase:** Internal code organized into the `hpy_core` package for better maintainability.

## Ideal For

*   ⚡ Building small to medium-sized web applications or dashboards with Python in the browser, including static assets like images and CSS.
*   🎓 Learning and experimenting with Brython in a structured project setup with configuration.
*   📦 Creating interactive documentation examples or simple UI components.
*   ⚡ Rapid prototyping where code organization and configuration are helpful.

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

# Note: This installs 'watchdog' (needed for -w) and 'tomli' (for hpy.toml on Python < 3.11) automatically.
```

## Getting Started: New Project

1.  **Initialize a Project:**

    ```bash
    hpy --init my-new-app
    cd my-new-app
    ```
    This creates a directory-based project (default):
    ```
    my-new-app/
    ├── hpy.toml        # Project configuration file
    └── src/            # Default source directory
        ├── _layout.hpy   # Shared layout file
        ├── about.hpy     # Example page
        ├── index.hpy     # Example homepage
        └── static/       # Static asset directory
            └── logo.svg  # Example static file
    ```
    *(Review `hpy.toml` - you may need to uncomment `static_dir_name`)*

2.  **Run the Dev Server with Watch:**

    ```bash
    # Make sure you are inside 'my-new-app' directory
    hpy -w
    ```
    *(No source directory argument needed! `hpy` reads `input_dir` from `hpy.toml` or uses the default "src". `-w` enables watching, building, static sync, and serving)*

3.  **Open your browser:** Navigate to `http://localhost:8000` (or the specified port). You should see the homepage with the SVG logo from the static directory.
4.  **Develop!** Edit files in the `src/` directory, including `.hpy` files and files within `src/static/`.
5.  **Save:** Save your changes. The tool will automatically rebuild `.hpy` files or sync static assets. Refresh your browser!

## Project Structure Explained

*   **`hpy.toml` (Project Root):** Configuration file for `hpy-tool`. Defines input/output directories, static asset folder name, etc.
*   **`src/` (or your configured `input_dir`):** Contains all your source `.hpy` files and the static asset directory.
*   **`src/static/` (or your configured `static_dir_name`):** Holds static assets (CSS, JS, images, fonts). Contents are copied directly to the output directory under the same name (e.g., `dist/static/`).
*   **`src/_layout.hpy` (Optional but Recommended):**
    *   Defines the main HTML structure (`<head>`, `<body>`, shared elements).
    *   Must contain `<!-- HPY_PAGE_CONTENT -->` where page content is injected.
    *   Can contain global `<style>` and `<python>` blocks. Can reference assets like `<img src="/static/logo.svg">`.
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
*   Static asset handling requires `static_dir_name` to be set (uncommented) in `hpy.toml`.

### Simplified DOM Access

These helpers are automatically available in your `<python>` blocks:

*   `byid(id)`: Returns element or `None`.
*   `qs(selector)`: Returns first matching element or `None`.
*   `qsa(selector)`: Returns a list of matching elements.

## Command-Line Usage

```
usage: hpy [-h] [--init PROJECT_DIR] [-o DIR] [-v] [-s] [-p PORT] [-w] [--version] [SOURCE]

HPY Tool: Compile/serve .hpy projects. Configurable via hpy.toml.

positional arguments:
  SOURCE                Path to source .hpy file or directory.
                        (default: 'src' from hpy.toml or built-in)

options:
  -h, --help            show this help message and exit
  --init PROJECT_DIR    Initialize a new HPY project structure (creates hpy.toml). Ignores SOURCE.
  -o DIR, --output-dir DIR
                        Directory for compiled output.
                        (overrides hpy.toml, default: 'dist' from hpy.toml or built-in)
  -v, --verbose         Enable detailed output.
  -s, --serve           Start a dev server serving the output directory.
  -p PORT, --port PORT  Port for the development server.
                        (default: 8000)
  -w, --watch           Watch source for changes and rebuild/sync. Requires 'watchdog'.
                        Using -w implies -s and uses the effective input/output dirs.
  --version             show program's version number and exit

Examples:
  hpy --init my_app          # Initialize project 'my_app' (creates hpy.toml, src/, src/static/)
  hpy                        # Compile project (uses settings from hpy.toml or defaults 'src' -> 'dist')
  hpy -o build               # Compile project, overriding output dir to 'build'
  hpy app_source -o public   # Compile specific input dir, overriding output dir
  hpy page.hpy -o build      # Compile single file (no layout/static handling) to build/page.html
  hpy -w                     # Watch (src -> dist via hpy.toml/defaults), build, sync static, and serve
  hpy -w -p 8080             # Watch and serve on port 8080
  hpy src/app.hpy -w         # Watch single file (layout/static NOT automatically used)

Configuration (hpy.toml in project root):
  [tool.hpy]
  input_dir = "src"      # Default: "src"
  output_dir = "dist"    # Default: "dist"
  static_dir_name = "static" # Default: "static" (Must be set to enable static handling)

Precedence: CLI Arguments > hpy.toml Settings > Built-in Defaults
```

## How it Works

When processing a directory, `hpy-tool` first checks `hpy.toml` for configuration. It then copies static assets (if configured and the directory exists). It parses the layout (if present) and then each page file (excluding those in the static directory). It combines the CSS and Python, injects the page HTML into the layout placeholder, and generates the final output HTML file. The watcher monitors the source directory (including the static subdirectory) and triggers rebuilds or static file synchronization based on changes.

## Contributing & Development Notes

This project uses standard Python tooling (`setuptools`, `venv`).

*   **Commits:** Please follow conventional commit message standards if possible (e.g., `feat: Add feature X`, `fix: Correct bug Y`).
*   **Reporting Issues:** If you find a bug or have a suggestion, please open an issue on the project repository (if available). Provide clear steps to reproduce the problem.
*   **Pull Requests:** Contributions are welcome! Please discuss larger changes in an issue first. Ensure code is formatted reasonably and includes necessary explanations.

Remember the project status disclaimer - your contributions can help improve it significantly!

## License

This project is licensed under the **BSD 3-Clause "New" or "Revised" License**. See the `LICENSE` file for details.