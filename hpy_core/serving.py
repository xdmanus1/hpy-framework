# hpy_core/serving.py
"""Development server logic."""

import http.server
import socketserver
import webbrowser
import threading
import functools
import sys
import os  # Need os for path joining
from pathlib import Path
from typing import Optional
from urllib.parse import unquote


def start_dev_server(serve_dir_str: str, port: int, verbose: bool):
    """Starts the development server."""
    serve_dir = Path(serve_dir_str).resolve()
    if not serve_dir.is_dir():
        raise FileNotFoundError(f"Server directory not found: {serve_dir}")

    class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, directory: str = None, **kwargs):
            # Store the serve directory passed via functools.partial
            self.serve_directory = directory or os.getcwd()  # Fallback just in case
            # The directory argument is passed to the superclass init
            super().__init__(*args, directory=self.serve_directory, **kwargs)

        def do_GET(self):
            """Serve GET requests. Modified to serve app.html as default if index.html is missing."""
            # Decode path for file system checks
            path = unquote(self.path).split("?", 1)[0]
            fs_path_requested = Path(self.serve_directory) / path.lstrip("/")

            # If requesting the root directory ('/' or '')
            if path.endswith("/") or path == "":
                # Check if index.html exists
                index_path = fs_path_requested / "index.html"
                # Check if app.html exists (our single-file default)
                app_path = fs_path_requested / "app.html"

                if not index_path.is_file() and app_path.is_file():
                    # index.html missing, but app.html exists: rewrite path to serve app.html
                    if verbose:
                        print(
                            f"[Server] No index.html, serving app.html for path '{self.path}'"
                        )
                    self.path = os.path.join(path, "app.html").replace(
                        "\\", "/"
                    )  # Ensure forward slashes
                    # Let the default handler serve app.html now
                    return http.server.SimpleHTTPRequestHandler.do_GET(self)

            # Otherwise, fall back to the default GET handler (serves file, index.html, or directory listing)
            return http.server.SimpleHTTPRequestHandler.do_GET(self)

        def log_message(self, format, *args):
            """Control logging based on verbose flag."""
            if verbose:
                sys.stdout.write(
                    f"[Server] {self.address_string()} - {format % args}\n"
                )

        def end_headers(self):
            """Add No-Cache headers."""
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.send_header("Expires", "0")
            super().end_headers()

    # Create the handler factory using partial, passing the serve directory
    HandlerFactory = functools.partial(
        CustomHTTPRequestHandler, directory=str(serve_dir)
    )

    server_address = ("", port)
    display_host = "localhost"
    effective_host = "0.0.0.0"
    httpd: Optional[socketserver.TCPServer] = None

    try:
        httpd = socketserver.TCPServer(server_address, HandlerFactory)
        url = f"http://{display_host}:{port}/"
        print("-" * 50)
        print(f"Serving files from : {serve_dir}")
        print(f"Development server on http://{effective_host}:{port}/")
        print(f"View application at: {url}")
        print("Press Ctrl+C to stop server.")
        print("-" * 50)

        def open_browser():
            try:
                webbrowser.open(url)
            except Exception as wb_err:
                if verbose:
                    print(f"[Server] Could not open browser: {wb_err}")

        threading.Timer(0.5, open_browser).start()
        httpd.serve_forever()
    except OSError as e:
        err_no = e.errno
        win_err = getattr(e, "winerror", None)
        if err_no == 98 or (sys.platform == "win32" and win_err == 10048):
            print(f"\nError: Port {port} is already in use.", file=sys.stderr)
        else:
            print(f"\nError starting server: {e}", file=sys.stderr)
        raise
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        if httpd:
            httpd.server_close()
    print("Server stopped.")
