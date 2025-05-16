# hpy_core/cli.py
"""Command-line interface logic using argparse."""

import argparse
import sys
import time
import traceback
from pathlib import Path
from typing import Optional, Dict, Any
import threading
import os

# Import from other modules in the package
from .config import __version__, load_config, find_project_root, CONFIG_FILENAME
from .config import (
    DEFAULT_INPUT_DIR,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATIC_DIR_NAME,
)
from .init import init_project
from .building import compile_directory, compile_hpy_file
# --- Updated import for watcher ---
from .watching import start_watching, WATCHFILES_AVAILABLE
# --- End updated import ---
from .serving import start_dev_server


def main():
    """Main entry point for the HPY Tool CLI"""

    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "input_src", nargs="?", default=None
    )
    pre_parser.add_argument("--init", metavar="PROJECT_DIR", default=None)
    pre_args, _ = pre_parser.parse_known_args()

    project_root: Optional[Path] = None
    config: Dict[str, Any] = {}
    input_src_from_cli = pre_args.input_src

    if not pre_args.init:
        start_search_path = Path.cwd()
        if input_src_from_cli:
            potential_path = Path(input_src_from_cli)
            if potential_path.exists():
                if potential_path.is_file():
                    start_search_path = potential_path.parent
                elif potential_path.is_dir():
                    start_search_path = potential_path
        project_root = find_project_root(start_search_path)
        if project_root:
            config = load_config(project_root)

    effective_input_dir = config.get("input_dir", DEFAULT_INPUT_DIR)
    effective_output_dir = config.get("output_dir", DEFAULT_OUTPUT_DIR)

    parser = argparse.ArgumentParser(
        prog="hpy",
        description=f"HPY Tool: Compile/serve .hpy projects. Configurable via {CONFIG_FILENAME}.",
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
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "input_src",
        metavar="SOURCE",
        nargs="?",
        default=argparse.SUPPRESS,
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
        # --- Updated help message for watch ---
        help=f"Watch source for changes and rebuild. Requires 'watchfiles'.\nUsing -w implies -s and uses the effective input/output dirs.",
        # --- End updated help message ---
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    args = parser.parse_args()

    if args.init:
        init_project(args.init)
        sys.exit(0)

    final_input_src: str
    if hasattr(args, "input_src") and args.input_src is not None:
        final_input_src = args.input_src
        if not project_root:
            potential_path = Path(final_input_src)
            start_search_path = Path.cwd()
            if potential_path.exists():
                start_search_path = (
                    potential_path.parent
                    if potential_path.is_file()
                    else potential_path
                )
            project_root = find_project_root(start_search_path)
            if project_root and not config:
                config = load_config(project_root)
                effective_output_dir = config.get("output_dir", DEFAULT_OUTPUT_DIR)
    else:
        final_input_src = effective_input_dir

    final_output_dir: str
    if args.output_dir is not None:
        final_output_dir = args.output_dir
    else:
        final_output_dir = effective_output_dir

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

    if is_directory_input:
        try:
            if output_dir_path.is_relative_to(input_path):
                print(
                    f"Error: Output directory '{final_output_dir}' cannot be inside input directory '{final_input_src}'.",
                    file=sys.stderr,
                )
                sys.exit(1)
        except AttributeError:
            try:
                input_str = str(input_path.resolve()) + os.sep
                output_str = str(output_dir_path.resolve())
                if output_str.startswith(input_str):
                    print(
                        f"Error: Output directory '{final_output_dir}' cannot be inside input directory '{final_input_src}'.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            except OSError as path_err:
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
        else:
            output_html_path = output_dir_path / input_path.with_suffix(".html").name
            output_dir_path.mkdir(parents=True, exist_ok=True)
            # For single file compilation, no layout is passed by default.
            # External script src is also not determined here, compile_hpy_file will handle it
            # based on inline <python src=...> or conventional page.py.
            compile_hpy_file(
                str(input_path),
                str(output_html_path),
                layout_content=None,      # No layout for single file compile
                external_script_src=None, # building.py/parsing.py will figure this out
                verbose=args.verbose
            )
            # Assuming compile_hpy_file raises on error
            error_count = 0
        if error_count == 0 and not args.serve and not args.watch:
            print(f"\nBuild successful. Output written to '{final_output_dir}'.")
        elif error_count > 0:
            pass

    except RuntimeError as e:
        print(f"Build stopped due to fatal error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nBuild failed with unexpected error: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)

    if error_count > 0 and not args.watch and not args.serve:
        sys.exit(1)

    watcher_thread: Optional[threading.Thread] = None
    effective_serve = args.serve or args.watch

    if args.watch:
        # --- Updated check for watcher library ---
        if not WATCHFILES_AVAILABLE:
            print("Error: --watch requires the 'watchfiles' library. `pip install watchfiles`", file=sys.stderr)
            sys.exit(1)
        # --- End updated check ---
        if error_count > 0:
            print("Skipping watch/serve due to compile errors.", file=sys.stderr)
            sys.exit(1)

        # The arguments to start_watching will need to be compatible with the new watchfiles version
        # watch_target_str, is_directory_mode, input_dir_abs_str, output_dir_abs_str, verbose
        watch_target_for_thread = str(input_path) # input_path is already resolved
        input_dir_for_thread = input_dir_context_abs # This is the resolved input dir context

        watcher_thread = threading.Thread(
            target=start_watching,
            args=(
                watch_target_for_thread,    # The path to watch (file or directory)
                is_directory_input,         # True if input_path is a directory
                input_dir_for_thread,       # Absolute path of the input directory context
                str(output_dir_path),       # Absolute path of the output directory
                args.verbose,
            ),
            daemon=True,
        )
        watcher_thread.start()
        time.sleep(0.2)

    server_exit_code = 0
    if effective_serve:
        if error_count > 0:
            print("Skipping serve due to compile errors.", file=sys.stderr)
            sys.exit(1)
        if not output_dir_path.is_dir():
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
            server_exit_code = 1
        except KeyboardInterrupt:
            print(
                "\nServer stopped by user (KeyboardInterrupt in cli.py)."
            )
            server_exit_code = 0
        except Exception as e:
            print(f"Server encountered an unexpected error: {e}", file=sys.stderr)
            if args.verbose:
                traceback.print_exc()
            server_exit_code = 1
        finally:
            if watcher_thread and watcher_thread.is_alive():
                pass

    exit_code = 1 if error_count > 0 else server_exit_code
    sys.exit(exit_code)