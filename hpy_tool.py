#!/usr/bin/env python3
"""
HPY Tools - A simple framework for building interactive web applications using .hpy files.

This tool converts .hpy files (containing HTML, CSS, and Python) into web applications
using Brython to run Python code directly in the browser.
"""

import argparse
import os
import re
import sys
import http.server
import socketserver
import webbrowser
import textwrap # For dedenting Python code
import time
import threading
import functools # For partial server handler
from pathlib import Path
from typing import Dict, Optional

# --- Watchdog Imports ---
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    # This allows the script to run without watchdog if --watch is not used
    WATCHDOG_AVAILABLE = False
    # Define dummy classes if watchdog is not available to avoid NameErrors later
    class Observer: pass
    class FileSystemEventHandler: pass
# --- End Watchdog Imports ---

__version__ = '0.1.2' # Incremented version

# Current Brython version to use
BRYTHON_VERSION = "3.11.3"


# --- Parsing ---
def parse_hpy_file(file_path: str) -> Dict[str, str]:
    """
    Parse a .hpy file and extract HTML, CSS, and Python sections.

    Args:
        file_path (str): Path to the .hpy file

    Returns:
        dict: Dictionary containing extracted HTML, CSS, and Python code

    Raises:
        FileNotFoundError: If the specified file doesn't exist
        ValueError: If the file isn't a valid .hpy file or sections are missing
        IOError: If the file cannot be read.
    """
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Input file not found or is a directory: {file_path}")

    if path.suffix.lower() != '.hpy':
        raise ValueError(f"Not a valid .hpy file (requires .hpy extension): {file_path}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        raise IOError(f"Could not read file {file_path}: {e}") from e

    # Use non-greedy matching (.*?) and DOTALL flag. Allow attributes on tags. Ignore case.
    html_match = re.search(r'<html.*?>(.*?)</html>', content, re.DOTALL | re.IGNORECASE)
    style_match = re.search(r'<style.*?>(.*?)</style>', content, re.DOTALL | re.IGNORECASE)
    python_match = re.search(r'<python.*?>(.*?)</python>', content, re.DOTALL | re.IGNORECASE)

    # Provide warnings for missing sections but don't raise errors here
    # Let downstream code decide if missing sections are fatal
    if not html_match:
        print(f"Warning: No <html>...</html> section found in {file_path}", file=sys.stderr)
    if not style_match:
        print(f"Warning: No <style>...</style> section found in {file_path}", file=sys.stderr)
    if not python_match:
        print(f"Warning: No <python>...</python> section found in {file_path}", file=sys.stderr)

    return {
        'html': html_match.group(1).strip() if html_match else '',
        'style': style_match.group(1).strip() if style_match else '',
        'python': python_match.group(1).strip() if python_match else ''
    }


# --- Building Output ---
def build_output_html(hpy_content: Dict[str, str], output_dir: str) -> str:
    """
    Build the final HTML file including CSS and Brython Python code

    Args:
        hpy_content (Dict[str, str]): Dictionary with html, style, and python sections
        output_dir (str): Directory to store output

    Returns:
        str: Path to the generated HTML file

    Raises:
        OSError: If the output directory cannot be created.
        IOError: If the output file cannot be written.
    """
    output_path = Path(output_dir)
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OSError(f"Could not create output directory {output_dir}: {e}") from e

    # Dedent the Python code to fix potential indentation issues
    python_code = textwrap.dedent(hpy_content['python'])

    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HPY Application</title>
    <!-- Brython Core -->
    <script src="https://cdn.jsdelivr.net/npm/brython@{BRYTHON_VERSION}/brython.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/brython@{BRYTHON_VERSION}/brython_stdlib.js"></script>
    <style>
/* --- Start HPY CSS --- */
{hpy_content['style']}
/* --- End HPY CSS --- */
    </style>
</head>
<body onload="brython()">

{hpy_content['html']}

<script type="text/python">
# --- Start HPY Python Code ---
{python_code}
# --- End HPY Python Code ---
</script>

</body>
</html>"""

    index_html_path = output_path / 'index.html'
    try:
        with open(index_html_path, 'w', encoding='utf-8') as f:
            f.write(html_template)
    except IOError as e:
        raise IOError(f"Could not write to output file {index_html_path}: {e}") from e

    return str(index_html_path)


# --- Compilation Orchestration ---
def compile_hpy_file(file_path: str, output_dir: str, verbose: bool = False) -> str:
    """
    Process a .hpy file into a web application using Brython.

    Args:
        file_path (str): Path to the .hpy file
        output_dir (str): Directory to store output
        verbose (bool): Whether to show verbose output

    Returns:
        str: Path to the generated HTML file

    Raises:
        FileNotFoundError, ValueError, IOError, OSError: Passthrough from called functions.
        RuntimeError: For unexpected compilation errors.
    """
    if verbose:
        print(f"Processing {file_path}...")

    try:
        hpy_content = parse_hpy_file(file_path)
        if verbose:
            print(f"  Extracted {len(hpy_content['html'])} bytes of HTML")
            print(f"  Extracted {len(hpy_content['style'])} bytes of CSS")
            print(f"  Extracted {len(hpy_content['python'])} bytes of Python")

        html_path = build_output_html(hpy_content, output_dir)

        if verbose:
            print(f"  Successfully built: {html_path}")

        return html_path

    except (FileNotFoundError, ValueError, IOError, OSError) as e:
        # Re-raise specific, expected errors for main to catch cleanly
        raise e
    except Exception as e:
        # Catch other unexpected errors during compilation
        raise RuntimeError(f"An unexpected error occurred during compilation of {file_path}: {e}") from e


# --- Watchdog Event Handler (only used if WATCHDOG_AVAILABLE is True) ---
if WATCHDOG_AVAILABLE:
    class HpyFileEventHandler(FileSystemEventHandler):
        """Handles file system events for the target .hpy file."""
        def __init__(self, filename: str, callback: callable, verbose: bool = False):
            super().__init__()
            self.filename = os.path.abspath(filename)
            self.callback = callback
            self.verbose = verbose
            self._last_triggered = 0 # For simple debounce
            self._debounce_interval = 0.5 # Seconds (adjust if needed)

        def on_modified(self, event):
            """Called when a file or directory is modified."""
            # Use os.path.abspath to handle potential relative path issues in event.src_path
            if not event.is_directory and os.path.abspath(event.src_path) == self.filename:
                current_time = time.time()
                if current_time - self._last_triggered > self._debounce_interval:
                    base_filename = os.path.basename(self.filename)
                    print(f"\nDetected modification in {base_filename}, rebuilding...")
                    self.callback() # Trigger the rebuild
                    self._last_triggered = current_time
                    if self.verbose:
                        print(f"Rebuild triggered for {base_filename} at {time.strftime('%H:%M:%S')}")


# --- Watcher Function ---
def start_watching(file_path: str, callback: callable, verbose: bool):
    """Starts watching the specified file for changes using watchdog."""
    # This function assumes WATCHDOG_AVAILABLE has been checked before calling it.
    if not WATCHDOG_AVAILABLE:
        # This should not happen if main() checks correctly, but defense in depth
        print("Error: Watchdog library is required for watching but not found.", file=sys.stderr)
        sys.exit(1)

    target_file = Path(file_path).resolve()
    watch_dir = str(target_file.parent)

    print(f"Watching {target_file.name} in directory {watch_dir} for changes...")
    print("Press Ctrl+C to stop.")

    event_handler = HpyFileEventHandler(str(target_file), callback, verbose)
    observer = Observer()
    try:
        # Schedule observer to watch the directory containing the file, non-recursively
        observer.schedule(event_handler, watch_dir, recursive=False)
        observer.start()
        while observer.is_alive():
            # Keep the thread alive, join with timeout allows interrupt check
            observer.join(timeout=1)
    except FileNotFoundError:
        # Handle case where the watched directory or file is deleted while watching
        print(f"\nError: Watched file or directory not found. Stopping watcher.", file=sys.stderr)
        # Observer might already be stopped or will stop due to error
    except KeyboardInterrupt:
        print("\nStopping watcher (Ctrl+C detected)...")
    finally:
        # Ensure observer is stopped and joined cleanly
        if observer.is_alive():
            observer.stop()
        # Wait for the observer thread to terminate completely
        observer.join()
    print("Watcher stopped.")


# --- Development Server ---
def start_dev_server(output_html_path: str, port: int, verbose: bool):
    """
    Start a simple development server using SimpleHTTPRequestHandler.
    Serves files from the directory containing the output HTML file without os.chdir.
    """
    serve_dir = os.path.dirname(os.path.abspath(output_html_path))
    if not os.path.isdir(serve_dir):
        print(f"Error: Cannot serve from non-existent directory: {serve_dir}", file=sys.stderr)
        # Raising an error to be caught by main
        raise FileNotFoundError(f"Server directory not found: {serve_dir}")

    # Define the custom handler inheriting directly from SimpleHTTPRequestHandler
    class CustomLogHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            # The 'directory' kwarg will be passed by functools.partial
            super().__init__(*args, **kwargs)

        def log_message(self, format, *args):
            # Control logging based on the verbose flag
            if verbose:
                sys.stdout.write(f"[Server] {self.address_string()} - {format % args}\n")
            # If not verbose, suppress standard logging by doing nothing here

        # Add No-Cache headers for development to prevent stale content
        def end_headers(self):
            self.send_header('Cache-Control', 'no-store, must-revalidate')
            self.send_header('Expires', '0')
            super().end_headers()

    # Use functools.partial to create a handler factory that pre-sets the directory
    HandlerFactory = functools.partial(CustomLogHandler, directory=serve_dir)

    # Set server address to bind to all interfaces ('') / 0.0.0.0
    server_address = ('', port)
    display_host = "localhost" # For user-friendly URL display and opening browser
    effective_host = "0.0.0.0" # For informative message about network accessibility

    httpd : Optional[socketserver.TCPServer] = None # Define variable before try block
    try:
        # Create and start the server
        httpd = socketserver.TCPServer(server_address, HandlerFactory)

        url = f"http://{display_host}:{port}"
        print("-" * 50)
        print(f"Serving HPY app from: {serve_dir}")
        print(f"Development server running on http://{effective_host}:{port}/ (Press Ctrl+C to stop)")
        print(f"View in browser: {url}")
        print("-" * 50)

        # Open the browser slightly delayed in a separate thread
        # Use try-except for webbrowser in case it fails (e.g., no GUI)
        def open_browser():
            try:
                webbrowser.open(url)
            except Exception as wb_err:
                 if verbose: print(f"[Server] Could not open browser: {wb_err}")

        threading.Timer(0.5, open_browser).start()

        # Blocks here until interrupted or stopped
        httpd.serve_forever()

    except OSError as e:
        # Handle specific errors like port binding failure
        err_no = e.errno
        win_err = getattr(e, 'winerror', None)
        if err_no == 98 or (sys.platform == "win32" and win_err == 10048): # EADDRINUSE
            print(f"\nError: Port {port} is already in use.", file=sys.stderr)
            print("Please stop the other process or use a different port with the -p option.", file=sys.stderr)
        else:
            print(f"\nError starting server: {e}", file=sys.stderr)
        # Re-raise the exception to be handled in main() for proper exit
        raise
    except KeyboardInterrupt:
        print("\nShutting down server (Ctrl+C detected)...")
        # Shutdown is implicitly handled by exiting the 'with' block or calling httpd.shutdown()
    finally:
        # Ensure server is properly shut down if it was created
        if httpd:
             httpd.server_close() # Close the server socket
    print("Server stopped.")


# --- Main CLI Function ---
def main():
    """Main entry point for the HPY Tool CLI"""
    parser = argparse.ArgumentParser(
        description="HPY Tool: Build and serve web apps from single .hpy files using Brython.",
        epilog="Example: python hpy_tool.py my_app.hpy -o build -s -w"
    )

    parser.add_argument(
        "input_file",
        help="Path to the .hpy file to compile."
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="dist",
        help="Directory for compiled output (default: %(default)s)."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable detailed output during build and server requests."
    )
    parser.add_argument(
        "-s", "--serve",
        action="store_true",
        help="Start a development server after compiling."
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=8000,
        help="Port for the development server (default: %(default)s)."
    )
    parser.add_argument(
        "-w", "--watch",
        action="store_true",
        help="Watch the input file for changes and automatically rebuild. Requires 'watchdog' (pip install watchdog)."
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )

    args = parser.parse_args()

    # --- Initial Compilation ---
    output_html_path: Optional[str] = None
    try:
        # Ensure output path is assigned for later use by server/watcher setup
        output_html_path = compile_hpy_file(args.input_file, args.output_dir, args.verbose)
        # Only print success message if not serving or watching (as they provide their own messages)
        if not args.serve and not args.watch:
             print(f"Successfully compiled '{args.input_file}' to '{output_html_path}'")

    except (FileNotFoundError, ValueError, IOError, OSError, RuntimeError) as e:
        print(f"Error during initial compilation: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e: # Catch any other unexpected error during startup
        print(f"An unexpected error occurred during setup: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    # --- Setup Watcher if requested ---
    watcher_thread: Optional[threading.Thread] = None
    rebuild_failed = threading.Event() # Use an event to signal rebuild failures

    if args.watch:
        if not WATCHDOG_AVAILABLE:
            print("Error: --watch requires the 'watchdog' library.", file=sys.stderr)
            print("Install it using: pip install watchdog", file=sys.stderr)
            sys.exit(1)

        # --watch implies --serve for a typical development workflow
        args.serve = True

        def rebuild_callback():
            """Callback function for the watcher. Recompiles the file."""
            try:
                # Recompile the file. Path is stored in closure.
                compile_hpy_file(args.input_file, args.output_dir, args.verbose)
                rebuild_failed.clear() # Signal success
                # Success message is printed by the event handler now
            except Exception as e:
                # Catch errors during rebuild, print them, but keep watching
                print(f"\nError during automatic rebuild: {e}", file=sys.stderr)
                rebuild_failed.set() # Signal failure

        # Make sure input file exists before starting watcher thread
        if not Path(args.input_file).exists():
             print(f"Error: Input file '{args.input_file}' not found. Cannot start watcher.", file=sys.stderr)
             sys.exit(1)

        # Start watcher in a separate thread
        watcher_thread = threading.Thread(
            target=start_watching,
            args=(args.input_file, rebuild_callback, args.verbose),
            daemon=True # Allows main thread to exit even if watcher is running
        )
        watcher_thread.start()
        time.sleep(0.2) # Small delay for watcher initialization message

    # --- Start Server if requested ---
    server_exit_code = 0
    if args.serve:
        if not output_html_path:
             # This should not happen if initial compile succeeded, but check anyway
             print("Error: Cannot start server - initial compilation failed to produce an output path.", file=sys.stderr)
             sys.exit(1)
        try:
            # Server blocks the main thread here until it stops or fails
            start_dev_server(output_html_path, args.port, args.verbose)
            # If start_dev_server completes without raising exception (e.g., Ctrl+C handled within), it's a normal exit for the server part.
        except (OSError, FileNotFoundError) as e:
             # Errors like port binding or missing serve directory are handled here
             # Error message was already printed inside start_dev_server
             server_exit_code = 1
        except Exception as e:
            # Catch any other unexpected errors from the server function
            print(f"An unexpected error occurred in the server process: {e}", file=sys.stderr)
            if args.verbose:
                import traceback
                traceback.print_exc()
            server_exit_code = 1

    # --- Final Exit ---
    # If the watcher thread was started and might still be running when the server stops,
    # daemon=True ensures it won't block exit. No explicit join is strictly necessary here.
    # The start_watching function handles its own cleanup on KeyboardInterrupt.

    # Exit with the server's status code (0 if successful or not run, 1 if server failed)
    # If only compilation happened, exit code is 0 (handled by reaching end of main).
    sys.exit(server_exit_code)


if __name__ == "__main__":
    main()