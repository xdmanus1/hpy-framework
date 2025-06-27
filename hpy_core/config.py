# hpy_core/config.py

import sys
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("Error: 'tomli' package is required but not installed.", file=sys.stderr)
        print("Please install it: pip install tomli", file=sys.stderr)
        sys.exit(1)

__version__ = "0.8.2" # Version bump for Component System Foundations

# --- Default Configuration Values ---
DEFAULT_INPUT_DIR = "src"
DEFAULT_OUTPUT_DIR = "dist"
DEFAULT_DEV_OUTPUT_DIR_NAME = ".hpy_dev_output"
DEFAULT_STATIC_DIR_NAME = "static"
DEFAULT_COMPONENTS_DIR = "components" # NEW
CONFIG_FILENAME = "hpy.toml"

# --- Core Constants ---
BRYTHON_VERSION = "3.11.3"
LAYOUT_FILENAME = "_layout.hpy"
LAYOUT_PLACEHOLDER = "<!-- HPY_PAGE_CONTENT -->"

# --- App Shell Constants ---
APP_SHELL_FILENAME = "_app.html"
APP_SHELL_HEAD_PLACEHOLDER = "<!-- HPY_HEAD_CONTENT -->"
APP_SHELL_BODY_PLACEHOLDER = "<!-- HPY_BODY_CONTENT -->"

WATCHER_DEBOUNCE_INTERVAL = 0.5 # In seconds

def find_project_root(start_path: Path) -> Optional[Path]:
    current = start_path.resolve()
    while current.exists() and current != current.parent:
        if (current / CONFIG_FILENAME).is_file():
            return current
        current = current.parent
    if current.exists() and (current / CONFIG_FILENAME).is_file():
        return current
    return None

def load_config(project_root: Optional[Path]) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    if not project_root:
        return config

    config_file_path = project_root / CONFIG_FILENAME
    if config_file_path.is_file():
        try:
            with open(config_file_path, "rb") as f:
                toml_data = tomllib.load(f)
            hpy_config = toml_data.get("tool", {}).get("hpy", {})

            if isinstance(hpy_config.get("input_dir"), str):
                config["input_dir"] = hpy_config["input_dir"]
            if isinstance(hpy_config.get("output_dir"), str):
                config["output_dir"] = hpy_config["output_dir"]
            if isinstance(hpy_config.get("static_dir_name"), str):
                config["static_dir_name"] = hpy_config["static_dir_name"]
            if isinstance(hpy_config.get("dev_output_dir"), str):
                config["dev_output_dir"] = hpy_config["dev_output_dir"]
            # --- NEW: Load components_dir ---
            if isinstance(hpy_config.get("components_dir"), str):
                config["components_dir"] = hpy_config["components_dir"]
            # --- END NEW ---
            
            return config
        except tomllib.TOMLDecodeError as e:
            print(f"Warning: Error parsing '{CONFIG_FILENAME}': {e}", file=sys.stderr)
        except IOError as e:
            print(f"Warning: Could not read '{CONFIG_FILENAME}': {e}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Unexpected error loading '{CONFIG_FILENAME}': {e}", file=sys.stderr)
    return config