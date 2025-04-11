# hpy_core/config.py
"""Configuration constants for hpy-tool."""

__version__ = '0.6.0' # Version bump for refactoring

# Current Brython version to use
BRYTHON_VERSION = "3.11.3"
# Convention for the layout file
LAYOUT_FILENAME = "_layout.hpy"
# Placeholder in layout HTML
LAYOUT_PLACEHOLDER = "<!-- HPY_PAGE_CONTENT -->"
# Watchdog debounce interval
WATCHER_DEBOUNCE_INTERVAL = 0.5