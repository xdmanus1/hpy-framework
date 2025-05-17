# HPY Tool ⚡ v0.7.7

[![License: BSD 3-Clause](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg?style=flat-square)](https://opensource.org/licenses/BSD-3-Clause)
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg?style=flat-square)](https://www.python.org/downloads/)
<!-- [![PyPI version](https://img.shields.io/pypi/v/hpy-tool.svg?style=flat-square)](https://pypi.org/project/hpy-tool/) -->

**Initialize, configure, build, serve, and live-reload web applications from structured `.hpy` projects (HTML + CSS + Python + Static Assets) using the magic of [Brython](https://brython.info)! ✨**

`hpy-tool` streamlines creating interactive web applications by processing a root HTML application shell (`_app.html`), layout files (`_layout.hpy`), page-specific `.hpy` files, external Python scripts, static assets, and directories. Define a global app structure, shared layouts, and individual pages, keeping structure, styling, and client-side logic organized. Use a simple `hpy.toml` file for project configuration. `hpy-tool` bundles everything into standard HTML files where your Python code runs directly in the browser (powered by Brython), manages your static assets, and handles different build outputs for development and production.

Inspired by the simplicity of tools like SvelteKit, this tool aims to provide a straightforward development experience for Brython-based projects.

## Project Status & Disclaimer

⚠️ **Please Note:** This project is currently maintained primarily as a learning exercise and for personal use. While it aims to be functional and useful for the described use cases, it's still under active development. There might be bugs, rough edges, or areas for improvement. Treat it as **experimental**. Feedback, bug reports, and contributions are highly encouraged!

## Core Features

*   🚀 **Project Initialization (`hpy init <dir>`):** Quickly scaffold new projects with options for:
    *   **Full Project (default):** Includes `_app.html` (root HTML shell), `_layout.hpy`, example pages (showcasing inline, conventional `.py`, and explicit `<python src="...">`), `hpy.toml`, scripts, and static assets.
    *   **Blank Project:** Minimal structure with `_app.html`, an empty `_layout.hpy`, and `hpy.toml`.
    *   **Single File Project:** A self-contained `app.hpy` and basic `hpy.toml`.
*   ⚙️ **Project Configuration (`hpy.toml`):** Define `input_dir`, `output_dir` (for production), `dev_output_dir` (for development/watch), and `static_dir_name`. CLI flags can override these.
*   📄 **Root HTML App Shell (`_app.html`):** Defines the outermost HTML structure (`<!DOCTYPE html>`, `<html>`, `<head>`, Brython CDN links, `<body>`). Layouts/pages inject content via `<!-- HPY_HEAD_CONTENT -->` and `<!-- HPY_BODY_CONTENT -->`.
*   📁 **Directory-Based Workflow:** Process an entire source directory (`src/` by default).
*   📄 **Layout Support (`_layout.hpy`):** Define shared structure using `<hpy-head>` and `<hpy-body>` tags for app shell injection. Page content fills `<!-- HPY_PAGE_CONTENT -->`.
*   🧩 **Single-File Pages (`.hpy`):** Can provide `<hpy-head>` content for the app shell if not using a layout.
*   🐍 **Flexible Python Logic:**
    *   Inline: `<python>...</python>` blocks.
    *   Conventional: `page.py` alongside `page.hpy`.
    *   Explicit: `<python src="path/script.py">`.
*   🖼️ **Static Asset Handling:** Copies files from `static_dir_name` to the appropriate output directory and syncs in watch mode.
*   🐍 **Brython Integration:** `_app.html` includes Brython. `hpy-tool` manages script processing and DOM helper injection.
*   🌍 **Build Modes:**
    *   **Development (e.g., `hpy watch`, `hpy build`):** Builds to `dev_output_dir` (or `.hpy_dev_output/`). Includes Brython debug and live-reload scripts (for `watch`).
    *   **Production (`hpy build --production`):** Builds to `output_dir` (or `dist/`). Brython debug off, no live-reload scripts.
*   🚀 **Development Server (`hpy serve`, `hpy watch`):** Serves the compiled application locally.
*   🔄 **Live Rebuilding & Reloading (`hpy watch`):** Uses `watchfiles` to monitor changes, rebuilds, syncs assets, and triggers browser live reload.
*   🗣️ **Verbose Mode (`-v` global flag):** Detailed operational logs.
*   💡 **DOM Helpers:** `byid()`, `qs()`, `qsa()` injected into Python scripts.

## Ideal For

*   Building small to medium web apps/dashboards with Python in the browser.
*   Learning Brython in a structured environment.
*   Rapid prototyping with live feedback.

## Installation

A Python virtual environment is strongly recommended.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate

# 2. Install hpy-tool
# Option A: From PyPI (once v1.0.0+ is published)
# pip install hpy-tool

# Option B: From local source code (for development)
# Navigate to the directory containing pyproject.toml
pip install -e .

# Dependencies: 'typer[all]', 'watchfiles', 'tomli' (for Python < 3.11).
```

## Getting Started: New Project

1.  **Initialize a Project:**
    ```bash
    hpy init my-new-app
    cd my-new-app
    ```
    This creates a full project structure (default option when prompted):
    ```
    my-new-app/
    ├── hpy.toml        # Project configuration file
    └── src/            # Default source directory
        ├── _app.html     # Root HTML application shell
        ├── _layout.hpy   # Shared layout file
        ├── index.hpy     # Example page (uses index.py)
        ├── index.py      # Conventional Python for index.hpy
        ├── about.hpy     # Example page (uses explicit src)
        ├── scripts/
        │   └── about_logic.py
        └── static/
            └── logo.svg
    ```
    *(Review `hpy.toml` to optionally set `static_dir_name` or `dev_output_dir`.)*

2.  **Run the Dev Server with Watch & Live Reload:**
    ```bash
    # Make sure you are inside 'my-new-app' directory
    hpy watch
    ```
    *(This builds to the development output directory, starts the watcher, and serves the app with live reload. It uses settings from `hpy.toml` or defaults.)*

3.  **Open your browser:** Navigate to `http://localhost:8000` (or the port specified with `-p`).
4.  **Develop!** Edit files in the `src/` directory. `hpy-tool` automatically rebuilds, and your browser live-reloads.

## Project Structure Explained

*   **`hpy.toml` (Project Root):** Configures `input_dir`, `output_dir` (for production), `dev_output_dir`, and `static_dir_name`.
*   **`src/` (or configured `input_dir`):**
    *   **`_app.html`:** Root HTML. Contains `<!-- HPY_HEAD_CONTENT -->` and `<!-- HPY_BODY_CONTENT -->`. Includes Brython.
    *   **`_layout.hpy`:** Shared layout. Uses `<hpy-head>` and `<hpy-body>`. Its `<hpy-body>` must have `<!-- HPY_PAGE_CONTENT -->`.
    *   **`*.hpy` (Pages):** Page content. HTML part fills `LAYOUT_PLACEHOLDER`. Can provide `<hpy-head>` content.
    *   **`static/`:** Static assets. Requires `static_dir_name` in `hpy.toml`.
    *   **`*.py` / `scripts/`:** External Python scripts.

## `.hpy` File Structure Guide

*   **Main HTML Block:** The primary HTML fragment for the page body or layout body.
    *   In pages, this is typically an `<html>...</html>` fragment (the content between `<html>` tags).
    *   In `_layout.hpy` used with `_app.html`, this content is within the `<hpy-body>` tag.
*   **`<hpy-head>...</hpy-head>` (Optional):** Content injected into `_app.html`'s `<head>`. For `<title>`, `<meta>`, layout/page-specific `<style>`.
*   **`<hpy-body>...</hpy-body>` (In `_layout.hpy` for app shell):** Defines layout's body structure for `_app.html`.
*   **`<style>...</style>`:** CSS rules. Combined globally.
*   **`<python>...</python>`:** Inline Brython. Ignored if `src` or conventional `.py` is used.
*   **`<python src="path/script.py">`:** Links external Python script. Path relative to `.hpy` file.

## Command-Line Interface (CLI)

`hpy-tool` uses a modern, subcommand-based interface.

```
$ hpy --help
Usage: hpy [OPTIONS] COMMAND [ARGS]...

  HPY Tool: Build, serve, and watch .hpy projects with Brython.

Options:
  -v, --verbose  Enable detailed verbose output globally.
  --version      Show version and exit.
  --help         Show this message and exit.

Commands:
  build  Compile an HPY project or single file.
  init   Initialize a new HPY project.
  serve  Build (optional) and serve an HPY project.
  watch  Watch project, rebuild on changes, and serve.```
```
**Common Commands:**

*   **`hpy init <project-name>`:** Creates a new project.
    *   Prompts for project type (Full, Blank, Single File).
*   **`hpy build [source_path]`:** Compiles the project.
    *   Defaults to `input_dir` from `hpy.toml` or `src/`.
    *   Outputs to development output directory (e.g., `.hpy_dev_output/` or configured `dev_output_dir`).
    *   `--production`: Builds for production to `output_dir` (e.g., `dist/`) with optimizations.
    *   `-o, --output <dir>`: Specifies a custom output directory.
*   **`hpy watch [source_path]`:** Builds in development mode, watches for changes, rebuilds, and serves.
    *   `-o, --output <dir>`: Specifies output directory for this session.
    *   `-p, --port <number>`: Sets the server port (default: 8000).
*   **`hpy serve [source_path_for_build]`:** Builds in development mode (unless `--no-build`) and serves.
    *   `-o, --output <dir>`: Specifies output directory.
    *   `-p, --port <number>`: Sets the server port.
    *   `--no-build`: Serves directly from the specified output directory.

*(Some old-style flags like `hpy --init ...` are temporarily supported with deprecation warnings).*

## How it Works

`hpy-tool` first reads `hpy.toml` for project configuration.
When building:
1.  It identifies the `input_dir` and the target `output_dir` (which differs for dev/watch vs. production builds).
2.  Static assets are copied (if `static_dir_name` is configured).
3.  If `_app.html` exists in `input_dir`, it's used as the base HTML shell.
4.  If `_layout.hpy` exists, it's parsed. Its `<hpy-head>` content and processed `<hpy-body>` (with page content injected into `LAYOUT_PLACEHOLDER`) are prepared for insertion into `_app.html`.
5.  For each page `.hpy` file:
    *   It's parsed for its HTML body fragment, optional `<hpy-head>` content, styles, and Python source (inline, conventional, or explicit `src`).
    *   External Python scripts are processed (helpers injected) and placed in the output directory.
    *   Styles are collected.
    *   The final HTML is assembled: page content goes into the layout (if used), then the combined layout/page structure goes into `_app.html` (if used). If no app shell, a full HTML document is generated based on layout/page.
    *   Titles are prioritized: Page `<hpy-head>` > Layout `<hpy-head>` > `_app.html` default.
6.  The `hpy watch` command uses `watchfiles` to monitor source files and triggers rebuilds or asset synchronization, along with browser live reloading.

## Contributing

This project uses standard Python tooling (`setuptools`, `venv`).

*   **Commits:** Please follow conventional commit message standards if possible (e.g., `feat: Add feature X`, `fix: Correct bug Y`).
*   **Reporting Issues:** If you find a bug or have a suggestion, please open an issue on the project repository (if available). Provide clear steps to reproduce the problem.
*   **Pull Requests:** Contributions are welcome! Please discuss larger changes in an issue first. Ensure code is formatted reasonably and includes necessary explanations.

Remember the project status disclaimer - your contributions can help improve it significantly!
## License

This project is licensed under the **BSD 3-Clause License**. See the `LICENSE` file for details.