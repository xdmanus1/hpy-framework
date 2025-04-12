# hpy_core/config.py
"""Configuration constants and loading logic for hpy-tool."""

import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Try importing the standard library tomllib (Python 3.11+)
# Fall back to the 'tomli' package dependency
try:
    import tomllib
except ImportError:
    # If tomllib is not available (Python < 3.11), use tomli
    try:
        import tomli as tomllib
    except ImportError:
        # This should not happen if dependencies are installed via pyproject.toml
        # but handle it defensively.
        print("Error: 'tomli' package is required but not installed.", file=sys.stderr)
        print("Please install it: pip install tomli", file=sys.stderr)
        sys.exit(1)

__version__ = "0.7.0"  # Version bump for new features

# --- Default Configuration Values ---
DEFAULT_INPUT_DIR = "src"
DEFAULT_OUTPUT_DIR = "dist"
DEFAULT_STATIC_DIR_NAME = "static"  # Default name for static asset folder
CONFIG_FILENAME = "hpy.toml"

# --- Core Constants ---
# Current Brython version to use
BRYTHON_VERSION = "3.11.3"
# Convention for the layout file
LAYOUT_FILENAME = "_layout.hpy"
# Placeholder in layout HTML
LAYOUT_PLACEHOLDER = "<!-- HPY_PAGE_CONTENT -->"
# Watchdog debounce interval
WATCHER_DEBOUNCE_INTERVAL = 0.5

# --- Configuration Loading Function ---


def find_project_root(start_path: Path) -> Optional[Path]:
    """
    Find the project root by searching upwards for the config file from a starting path.
    """
    current = start_path.resolve()
    while current != current.parent:  # Stop at the filesystem root
        if (current / CONFIG_FILENAME).is_file():
            return current
        current = current.parent
    # Check filesystem root itself
    if (current / CONFIG_FILENAME).is_file():
        return current
    return None


def load_config(project_root: Optional[Path]) -> Dict[str, Any]:
    """
    Load configuration from hpy.toml found in the project_root.
    Returns a dictionary with loaded settings, or an empty dict if not found/error.
    """
    config: Dict[str, Any] = {}
    if not project_root:
        # print(f"Debug: No project root provided for config loading.", file=sys.stderr) # Optional debug
        return config  # No root to search in

    config_file_path = project_root / CONFIG_FILENAME
    # print(f"Debug: Attempting to load config from: {config_file_path}", file=sys.stderr) # Optional debug

    if config_file_path.is_file():
        try:
            with open(config_file_path, "rb") as f:  # Use binary mode for tomllib
                toml_data = tomllib.load(f)
            # Look for settings under [tool.hpy] table
            hpy_config = toml_data.get("tool", {}).get("hpy", {})

            # Validate and store known config keys
            if isinstance(hpy_config.get("input_dir"), str):
                config["input_dir"] = hpy_config["input_dir"]
            if isinstance(hpy_config.get("output_dir"), str):
                config["output_dir"] = hpy_config["output_dir"]
            # Add static_dir_name loading (for Phase 2, but load it now if present)
            if isinstance(hpy_config.get("static_dir_name"), str):
                config["static_dir_name"] = hpy_config["static_dir_name"]

            # print(f"Debug: Loaded config: {config}", file=sys.stderr) # Optional debug
            return config
        except tomllib.TOMLDecodeError as e:
            print(f"Warning: Error parsing '{CONFIG_FILENAME}': {e}", file=sys.stderr)
        except IOError as e:
            print(f"Warning: Could not read '{CONFIG_FILENAME}': {e}", file=sys.stderr)
        except Exception as e:  # Catch unexpected errors during loading
            print(
                f"Warning: Unexpected error loading '{CONFIG_FILENAME}': {e}",
                file=sys.stderr,
            )
    # else:
    # print(f"Debug: Config file not found at {config_file_path}", file=sys.stderr) # Optional debug

    return config  # Return empty config if file not found or error occurred
