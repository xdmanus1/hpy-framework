# hpy_core/cli.py
"""Command-line interface logic using argparse."""

import argparse
import sys
import time
import traceback
from pathlib import Path
from typing import Optional
import threading

# Import from other modules in the package
from .config import __version__
from .init import init_project
from .building import compile_directory, compile_hpy_file
from .watching import start_watching, WATCHDOG_AVAILABLE
from .serving import start_dev_server

def main():
    """Main entry point for the HPY Tool CLI"""
    parser = argparse.ArgumentParser(
        prog="hpy",
        description="HPY Tool: Compile/serve .hpy projects (with layout support). Initialize new projects.",
        epilog="""Examples:
  hpy --init my_app          # Initialize project 'my_app'
  hpy src -o build           # Compile src/ to build/ (uses _layout.hpy)
  hpy src -s -p 8080         # Compile src/ and serve from dist/ on port 8080
  hpy src/app.hpy -w         # Watch single file (no layout used)
  hpy src -w                 # Watch src/ recursively, rebuild on changes""",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("input_src",metavar="SOURCE",nargs="?",default="src",help="Path to source .hpy file or directory.\n(default: %(default)s)")
    parser.add_argument("--init",metavar="PROJECT_DIR",help="Initialize a new HPY project structure. Ignores SOURCE.")
    parser.add_argument("-o","--output-dir",metavar="DIR",default="dist",help="Directory for compiled output.\n(default: %(default)s)")
    parser.add_argument("-v","--verbose",action="store_true",help="Enable detailed output.")
    parser.add_argument("-s","--serve",action="store_true",help="Start a dev server serving the output directory.")
    parser.add_argument("-p","--port",metavar="PORT",type=int,default=8000,help="Port for the development server.\n(default: %(default)s)")
    parser.add_argument("-w","--watch",action="store_true",help="Watch source for changes and rebuild. Requires 'watchdog'.\nUsing -w implies -s.")
    parser.add_argument('--version',action='version',version=f'%(prog)s {__version__}')
    args = parser.parse_args()

    if args.init:
        init_project(args.init)
        sys.exit(0)

    input_path = Path(args.input_src).resolve()
    output_dir_path = Path(args.output_dir).resolve()
    is_directory_input = input_path.is_dir()
    is_file_input = input_path.is_file()

    if not is_directory_input and not is_file_input: print(f"Error: Input source '{args.input_src}' not found.", file=sys.stderr); sys.exit(1)
    if is_file_input and input_path.suffix.lower() != '.hpy': print(f"Error: Input file '{args.input_src}' must be .hpy.", file=sys.stderr); sys.exit(1)
    try: # Check output dir isn't inside input dir
        if is_directory_input and output_dir_path.resolve().relative_to(input_path.resolve()): print(f"Error: Output dir cannot be inside input dir.", file=sys.stderr); sys.exit(1)
    except ValueError: pass # OK if not relative

    input_dir_context_abs = str(input_path.parent if is_file_input else input_path)
    error_count = 0
    print("--- Starting Build ---")
    try:
        if is_directory_input:
            _, error_count = compile_directory(str(input_path), str(output_dir_path), args.verbose)
        else:
            output_html_path = output_dir_path / input_path.with_suffix('.html').name
            output_dir_path.mkdir(parents=True, exist_ok=True)
            compile_hpy_file(str(input_path), str(output_html_path), layout_content=None, verbose=args.verbose)
            error_count = 0
        if error_count == 0 and not args.serve and not args.watch: print(f"\nBuild successful. Output written to '{args.output_dir}'.")
        elif error_count > 0: pass # Summary already printed
    except RuntimeError as e: print(f"Build stopped due to fatal error: {e}", file=sys.stderr); sys.exit(1)
    except Exception as e:
        print(f"\nBuild failed with unexpected error: {e}", file=sys.stderr)
        if args.verbose: traceback.print_exc(); sys.exit(1) # <<< SYNTAX ERROR HERE

    if error_count > 0 and not args.watch and not args.serve: sys.exit(1)

    watcher_thread: Optional[threading.Thread] = None
    if args.watch:
        if not WATCHDOG_AVAILABLE: print("Error: --watch requires 'watchdog'.", file=sys.stderr); sys.exit(1)
        if error_count > 0: print("Skipping watch/serve due to compile errors.", file=sys.stderr); sys.exit(1)
        args.serve = True
        watcher_thread = threading.Thread(target=start_watching, args=(str(input_path), is_directory_input, input_dir_context_abs, str(output_dir_path), args.verbose), daemon=True)
        watcher_thread.start()
        time.sleep(0.2)

    server_exit_code = 0
    if args.serve:
        if error_count > 0: print("Skipping serve due to compile errors.", file=sys.stderr); sys.exit(1)
        if not output_dir_path.is_dir(): print(f"Error: Output dir '{args.output_dir}' not found.", file=sys.stderr); sys.exit(1)
        try: start_dev_server(str(output_dir_path), args.port, args.verbose)
        except (OSError, FileNotFoundError): server_exit_code = 1
        except Exception as e: print(f"Server error: {e}", file=sys.stderr); server_exit_code = 1

    exit_code = 1 if error_count > 0 else server_exit_code
    sys.exit(exit_code)