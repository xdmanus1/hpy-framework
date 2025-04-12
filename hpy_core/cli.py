# hpy_core/cli.py
"""Command-line interface logic using argparse."""

import argparse
import sys
import time
import traceback
from pathlib import Path
from typing import Optional, Dict, Any
import threading
import os  # Added os import back for path validation fallback

# Import from other modules in the package
from .config import __version__, load_config, find_project_root, CONFIG_FILENAME

# --- Corrected Import ---
from .config import (
    DEFAULT_INPUT_DIR,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATIC_DIR_NAME,
)  # Import added constant

# --- End Correction ---
from .init import init_project
from .building import compile_directory, compile_hpy_file
from .watching import start_watching, WATCHDOG_AVAILABLE
from .serving import start_dev_server


def main():
    """Main entry point for the HPY Tool CLI"""

    # --- Initial Argument Parsing (Minimal, to find input source if provided) ---
    # We need the input source potentially to find the project root before full parsing
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "input_src", nargs="?", default=None
    )  # Don't use default yet
    pre_parser.add_argument("--init", metavar="PROJECT_DIR", default=None)
    pre_args, _ = pre_parser.parse_known_args()

    project_root: Optional[Path] = None
    config: Dict[str, Any] = {}
    input_src_from_cli = pre_args.input_src

    if not pre_args.init:
        # Determine where to start searching for hpy.toml
        # If input_src is provided, start search from its location (or its parent if it's a file).
        # Otherwise, start from the current working directory.
        start_search_path = Path.cwd()
        if input_src_from_cli:
            potential_path = Path(input_src_from_cli)
            # Check if path exists before deciding parent/self
            if potential_path.exists():
                if potential_path.is_file():
                    start_search_path = potential_path.parent
                elif potential_path.is_dir():
                    start_search_path = potential_path
            # If path doesn't exist yet, CWD remains a reasonable starting point.

        project_root = find_project_root(start_search_path)
        if project_root:
            # print(f"Debug: Found project root at: {project_root}", file=sys.stderr) # Optional debug
            config = load_config(project_root)
        # else:
        # print(f"Debug: No project root found starting from {start_search_path}.", file=sys.stderr) # Optional debug

    # --- Determine Effective Defaults ---
    # Precedence: Config File > Built-in Default
    effective_input_dir = config.get("input_dir", DEFAULT_INPUT_DIR)
    effective_output_dir = config.get("output_dir", DEFAULT_OUTPUT_DIR)
    # Note: static_dir_name will be handled in Phase 2 logic

    # --- Full Argument Parsing ---
    parser = argparse.ArgumentParser(
        prog="hpy",
        description=f"HPY Tool: Compile/serve .hpy projects. Configurable via {CONFIG_FILENAME}.",
        # --- Corrected Epilog ---
        # Uses the now-imported DEFAULT_STATIC_DIR_NAME
        epilog=f"""Examples:
  hpy --init my_app          # Initialize project 'my_app' (creates {CONFIG_FILENAME})
  hpy                        # Compile project (uses '{effective_input_dir}' -> '{effective_output_dir}' by default or from {CONFIG_FILENAME})
  hpy src -o build           # Compile specific dir, overriding config/defaults
  hpy src/app.hpy            # Compile single file (no layout used)
  hpy -s -p 8080             # Compile default/config source and serve from default/config output dir
  hpy -w                     # Watch default/config source, rebuild, and serve

Configuration (`{CONFIG_FILENAME}` in project root):
  [tool.hpy]
  input_dir = "app_source"  # Default: "{DEFAULT_INPUT_DIR}"
  output_dir = "public"     # Default: "{DEFAULT_OUTPUT_DIR}"
  # static_dir_name = "assets" # Default: "{DEFAULT_STATIC_DIR_NAME}" (for static files)
""",
        # --- End Correction ---
        formatter_class=argparse.RawTextHelpFormatter,
    )
    # Use effective defaults, but allow None for input_src to detect if user supplied it
    parser.add_argument(
        "input_src",
        metavar="SOURCE",
        nargs="?",
        # Default is based on config/hardcoded, but only if user supplies NOTHING
        default=argparse.SUPPRESS,  # We handle default logic below
        help=f"Path to source .hpy file or directory.\n(default: '{effective_input_dir}' from {CONFIG_FILENAME} or built-in)",
    )
    parser.add_argument(
        "--init",
        metavar="PROJECT_DIR",
        help=f"Initialize a new HPY project structure (creates {CONFIG_FILENAME}). Ignores SOURCE.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        metavar="DIR",
        default=None,
        help=f"Directory for compiled output.\n(overrides {CONFIG_FILENAME}, default: '{effective_output_dir}')",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable detailed output."
    )
    parser.add_argument(
        "-s",
        "--serve",
        action="store_true",
        help="Start a dev server serving the output directory.",
    )
    parser.add_argument(
        "-p",
        "--port",
        metavar="PORT",
        type=int,
        default=8000,
        help="Port for the development server.\n(default: %(default)s)",
    )
    parser.add_argument(
        "-w",
        "--watch",
        action="store_true",
        help=f"Watch source for changes and rebuild. Requires 'watchdog'.\nUsing -w implies -s and uses the effective input/output dirs.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    args = parser.parse_args()

    # --- Project Initialization ---
    if args.init:
        # Pass project root for init to place config file correctly
        init_project(args.init)
        sys.exit(0)

    # --- Determine Final Input/Output Paths ---
    # Precedence: CLI Argument > Config File > Built-in Default

    # Input Source
    final_input_src: str
    if hasattr(args, "input_src") and args.input_src is not None:
        final_input_src = args.input_src
        # If CLI provided input, re-evaluate project root if not found before
        if not project_root:
            potential_path = Path(final_input_src)
            # Check existence again before determining parent/self
            start_search_path = Path.cwd()  # Default if path doesn't exist
            if potential_path.exists():
                start_search_path = (
                    potential_path.parent
                    if potential_path.is_file()
                    else potential_path
                )
            # else: start_search_path remains CWD

            project_root = find_project_root(start_search_path)
            if project_root and not config:  # Load config only if not loaded before
                config = load_config(project_root)
                # Re-evaluate effective output_dir based on potentially newly found config
                effective_output_dir = config.get("output_dir", DEFAULT_OUTPUT_DIR)

    else:
        final_input_src = effective_input_dir  # Use default from config or hardcoded

    # Output Directory
    final_output_dir: str
    if args.output_dir is not None:
        final_output_dir = args.output_dir
    else:
        final_output_dir = effective_output_dir  # Use default from config or hardcoded

    # --- Path Validation and Build ---
    input_path = Path(final_input_src).resolve()
    output_dir_path = Path(final_output_dir).resolve()

    is_directory_input = input_path.is_dir()
    is_file_input = input_path.is_file()

    if not is_directory_input and not is_file_input:
        print(
            f"Error: Input source '{final_input_src}' not found or not a file/directory.",
            file=sys.stderr,
        )
        sys.exit(1)
    if is_file_input and input_path.suffix.lower() != ".hpy":
        print(f"Error: Input file '{final_input_src}' must be .hpy.", file=sys.stderr)
        sys.exit(1)

    # Check output dir isn't inside input dir (Robust check)
    if is_directory_input:
        try:
            # Use is_relative_to if available (Python 3.9+)
            if output_dir_path.is_relative_to(input_path):
                print(
                    f"Error: Output directory '{final_output_dir}' cannot be inside input directory '{final_input_src}'.",
                    file=sys.stderr,
                )
                sys.exit(1)
        except AttributeError:
            # Fallback for Python 3.8
            try:
                # Check if resolved output path string starts with resolved input path string + separator
                input_str = str(input_path.resolve()) + os.sep
                output_str = str(output_dir_path.resolve())
                if output_str.startswith(input_str):
                    print(
                        f"Error: Output directory '{final_output_dir}' cannot be inside input directory '{final_input_src}'.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            except OSError as path_err:  # Catch potential resolution errors
                print(
                    f"Warning: Could not reliably check if output is inside input: {path_err}",
                    file=sys.stderr,
                )

    input_dir_context_abs = str(input_path.parent if is_file_input else input_path)
    error_count = 0
    print("--- Starting Build ---")
    print(
        f"Source: '{final_input_src}'{' (Directory)' if is_directory_input else ' (File)'}"
    )
    print(f"Output: '{final_output_dir}'")
    if project_root:
        print(f"Config: Using '{CONFIG_FILENAME}' from '{project_root}'")

    try:
        if is_directory_input:
            _, error_count = compile_directory(
                str(input_path), str(output_dir_path), args.verbose
            )
        else:  # Single file input
            # Place single file output directly into output dir, named after the input file
            output_html_path = output_dir_path / input_path.with_suffix(".html").name
            output_dir_path.mkdir(
                parents=True, exist_ok=True
            )  # Ensure output dir exists
            compile_hpy_file(
                str(input_path),
                str(output_html_path),
                layout_content=None,
                verbose=args.verbose,
            )
            error_count = 0  # Assume success if no exception
        if error_count == 0 and not args.serve and not args.watch:
            print(f"\nBuild successful. Output written to '{final_output_dir}'.")
        elif error_count > 0:
            pass  # Summary already printed by compile_directory

    except RuntimeError as e:
        print(f"Build stopped due to fatal error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nBuild failed with unexpected error: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()  # Corrected Syntax
        sys.exit(1)  # Corrected Syntax

    if error_count > 0 and not args.watch and not args.serve:
        sys.exit(1)

    # --- Watch and Serve ---
    watcher_thread: Optional[threading.Thread] = None
    effective_serve = args.serve or args.watch  # Watch implies serve

    if args.watch:
        if not WATCHDOG_AVAILABLE:
            print("Error: --watch requires 'watchdog'.", file=sys.stderr)
            sys.exit(1)
        if error_count > 0:
            print("Skipping watch/serve due to compile errors.", file=sys.stderr)
            sys.exit(1)
        watcher_thread = threading.Thread(
            target=start_watching,
            args=(
                str(input_path),
                is_directory_input,
                input_dir_context_abs,
                str(output_dir_path),
                args.verbose,
            ),
            daemon=True,
        )
        watcher_thread.start()
        time.sleep(0.2)  # Give watcher a moment to initialize

    server_exit_code = 0
    if effective_serve:
        if error_count > 0:
            print("Skipping serve due to compile errors.", file=sys.stderr)
            sys.exit(1)
        if not output_dir_path.is_dir():
            # Create output dir if only serving (e.g., hpy -s without prior build)
            try:
                output_dir_path.mkdir(parents=True, exist_ok=True)
                print(f"Created output directory '{final_output_dir}' for server.")
            except OSError as e:
                print(
                    f"Error: Cannot create output directory '{final_output_dir}': {e}",
                    file=sys.stderr,
                )
                sys.exit(1)
        try:
            start_dev_server(str(output_dir_path), args.port, args.verbose)
        except (OSError, FileNotFoundError) as e:
            # Error message likely printed inside start_dev_server or is generic like "Port in use"
            # No need to print e again unless more detail is needed.
            server_exit_code = 1
        except KeyboardInterrupt:
            print(
                "\nServer stopped by user (KeyboardInterrupt in cli.py)."
            )  # More specific message
            server_exit_code = 0  # Not an error exit in this case
        except Exception as e:  # Catch other potential server errors
            print(f"Server encountered an unexpected error: {e}", file=sys.stderr)
            if args.verbose:
                traceback.print_exc()
            server_exit_code = 1
        finally:
            # If watcher was started, ensure it stops if server stops/crashes
            if watcher_thread and watcher_thread.is_alive():
                # Still relying on Ctrl+C or daemon=True nature.
                # A more graceful shutdown would require inter-thread communication (e.g., Event).
                pass

    exit_code = 1 if error_count > 0 else server_exit_code
    # print(f"Exiting with code: {exit_code}") # Optional debug
    sys.exit(exit_code)
