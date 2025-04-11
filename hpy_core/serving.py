# hpy_core/serving.py
"""Development server logic."""

import http.server
import socketserver
import webbrowser
import threading
import functools
import sys
from pathlib import Path
from typing import Optional

def start_dev_server(serve_dir_str: str, port: int, verbose: bool):
    """Starts the development server."""
    serve_dir = Path(serve_dir_str).resolve()
    if not serve_dir.is_dir(): raise FileNotFoundError(f"Server directory not found: {serve_dir}")

    class CustomLogHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs): super().__init__(*args, **kwargs)
        def log_message(self, format, *args):
            if verbose: sys.stdout.write(f"[Server] {self.address_string()} - {format % args}\n")
        def end_headers(self): self.send_header('Cache-Control', 'no-store, must-revalidate'); self.send_header('Expires', '0'); super().end_headers()

    HandlerFactory = functools.partial(CustomLogHandler, directory=str(serve_dir))
    server_address = ('', port); display_host = "localhost"; effective_host = "0.0.0.0"
    httpd : Optional[socketserver.TCPServer] = None
    try:
        httpd = socketserver.TCPServer(server_address, HandlerFactory)
        url = f"http://{display_host}:{port}/"
        print("-" * 50); print(f"Serving files from : {serve_dir}"); print(f"Development server on http://{effective_host}:{port}/"); print(f"View application at: {url}"); print("Press Ctrl+C to stop server."); print("-" * 50)
        def open_browser():
            try: webbrowser.open(url)
            except Exception as wb_err:
                 if verbose: print(f"[Server] Could not open browser: {wb_err}")
        threading.Timer(0.5, open_browser).start()
        httpd.serve_forever()
    except OSError as e:
        err_no = e.errno; win_err = getattr(e, 'winerror', None)
        if err_no == 98 or (sys.platform == "win32" and win_err == 10048): print(f"\nError: Port {port} is already in use.", file=sys.stderr)
        else: print(f"\nError starting server: {e}", file=sys.stderr)
        raise
    except KeyboardInterrupt: print("\nShutting down server...")
    finally:
        if httpd: httpd.server_close()
    print("Server stopped.")