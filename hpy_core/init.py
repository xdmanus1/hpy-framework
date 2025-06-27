# hpy_core/init.py
"""Project initialization logic - loads templates from files."""

import sys
import time
from pathlib import Path
import os
from typing import Optional

from .config import (
    LAYOUT_FILENAME, BRYTHON_VERSION, LAYOUT_PLACEHOLDER,
    CONFIG_FILENAME, DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR,
    DEFAULT_STATIC_DIR_NAME, DEFAULT_COMPONENTS_DIR,
    APP_SHELL_FILENAME, APP_SHELL_HEAD_PLACEHOLDER, APP_SHELL_BODY_PLACEHOLDER
)

# Base path for templates within the package
TEMPLATE_DIR = Path(__file__).parent / "project_templates"

def _load_template(filename: str, **kwargs) -> str:
    """Loads a template file and selectively formats it with known placeholders."""
    try:
        template_path = TEMPLATE_DIR / filename
        content = template_path.read_text(encoding="utf-8")
        
        known_placeholders = {
            "BRYTHON_VERSION": BRYTHON_VERSION,
            "LAYOUT_PLACEHOLDER": LAYOUT_PLACEHOLDER,
            "DEFAULT_INPUT_DIR": DEFAULT_INPUT_DIR,
            "DEFAULT_OUTPUT_DIR": DEFAULT_OUTPUT_DIR,
            "DEFAULT_STATIC_DIR_NAME": DEFAULT_STATIC_DIR_NAME,
            "DEFAULT_DEV_OUTPUT_DIR_NAME": ".hpy_dev_output",
            "DEFAULT_COMPONENTS_DIR": DEFAULT_COMPONENTS_DIR,
            "APP_SHELL_FILENAME": APP_SHELL_FILENAME,
            "APP_SHELL_HEAD_PLACEHOLDER": APP_SHELL_HEAD_PLACEHOLDER,
            "APP_SHELL_BODY_PLACEHOLDER": APP_SHELL_BODY_PLACEHOLDER,
            "CONFIG_FILENAME": CONFIG_FILENAME,
            "LAYOUT_FILENAME": LAYOUT_FILENAME,
            "CURRENT_YEAR": time.strftime('%Y'),
        }
        known_placeholders.update(kwargs)

        for key, value in known_placeholders.items():
            placeholder_tag = "{" + key + "}" 
            content = content.replace(placeholder_tag, str(value))
            
        return content

    except FileNotFoundError:
        print(f"FATAL ERROR: Template file '{filename}' not found in '{TEMPLATE_DIR}'.", file=sys.stderr)
        print("This indicates an issue with the hpy-tool installation.", file=sys.stderr)
        sys.exit(1)
    except Exception as e: 
        print(f"FATAL ERROR: Could not load or process template '{filename}': {e}", file=sys.stderr)
        if isinstance(e, KeyError):
             print(f"  This might be due to an unescaped curly brace in a template that is not a known placeholder for _load_template: {e}", file=sys.stderr)
        sys.exit(1)

def _read_raw_template(filename: str) -> str:
    """Simply reads a template file without any formatting."""
    try:
        template_path = TEMPLATE_DIR / filename
        return template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"FATAL ERROR: Raw template file '{filename}' not found in '{TEMPLATE_DIR}'.", file=sys.stderr)
        print("This indicates an issue with the hpy-tool installation.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"FATAL ERROR: Could not load raw template '{filename}': {e}", file=sys.stderr)
        sys.exit(1)

# --- Template Getter Functions ---

def _get_app_shell_template() -> str: return _load_template("app_shell.html.template")
def _get_modified_layout_template() -> str: return _load_template("layout_for_shell.hpy.template")
def _get_layout_index_template() -> str: return _load_template("page_index.hpy.template")
def _get_layout_about_template() -> str: return _load_template("page_about.hpy.template")
def _get_single_file_template() -> str: return _load_template("single_file_app.hpy.template")
def _get_hpy_toml_template() -> str: return _load_template("hpy.toml.template")
def _get_hpy_toml_for_single_file() -> str: return _load_template("hpy_single_file.toml.template")
def _get_logo_svg_template() -> str: return _read_raw_template("logo.svg.template")
def _get_layout_index_py_template() -> str: return _read_raw_template("script_index.py.template")
def _get_layout_about_py_template() -> str: return _read_raw_template("script_about.py.template")
def _get_blank_layout_template() -> str: return _load_template("blank_layout_for_shell.hpy.template")
def _get_component_card_template() -> str: return _read_raw_template("component_card.hpy.template")
def _get_main_css_template() -> str: return _read_raw_template("main.css.template") # NEW


# --- Core Project Creation Logic ---

def _create_hpy_toml(project_path: Path, for_single_file_project: bool = False):
    hpy_toml_path = project_path / CONFIG_FILENAME
    try:
        if for_single_file_project:
            content = _get_hpy_toml_for_single_file()
        else:
            content = _get_hpy_toml_template()
        with open(hpy_toml_path, "w", encoding="utf-8") as f:
            f.write(content)
        return hpy_toml_path
    except IOError as e:
        print(f"Error writing config file '{hpy_toml_path.name}': {e}", file=sys.stderr)
        raise

def _create_single_file_project(project_path: Path):
    app_hpy_path = project_path / "app.hpy"
    hpy_toml_path: Optional[Path] = None
    try:
        project_path.mkdir(parents=True, exist_ok=True)
        hpy_toml_path = _create_hpy_toml(project_path, for_single_file_project=True)
        with open(app_hpy_path, "w", encoding="utf-8") as f:
            f.write(_get_single_file_template())
    except Exception as e:
        print(f"Error creating single file project at '{project_path}': {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n✓ Simple single-file HPY project initialized in '{project_path}'.")
    if hpy_toml_path: print(f"✓ Config:  {hpy_toml_path.relative_to(project_path)}")
    print(f"✓ Page:    {app_hpy_path.relative_to(project_path)}")
    print("\nTo get started:")
    print(f"  cd {project_path.name}")
    print(f"  hpy watch app.hpy")


def _create_layout_project(project_path: Path, blank: bool = False):
    hpy_toml_path: Optional[Path] = None
    src_dir_path = project_path / DEFAULT_INPUT_DIR
    try:
        project_path.mkdir(parents=True, exist_ok=True)
        hpy_toml_path = _create_hpy_toml(project_path) 
        src_dir_path.mkdir(exist_ok=True)

        app_shell_path = src_dir_path / APP_SHELL_FILENAME
        with open(app_shell_path, "w", encoding="utf-8") as f:
            f.write(_get_app_shell_template())

        layout_hpy_path = src_dir_path / LAYOUT_FILENAME
        if blank:
            with open(layout_hpy_path, "w", encoding="utf-8") as f:
                f.write(_get_blank_layout_template())
        else:
            with open(layout_hpy_path, "w", encoding="utf-8") as f:
                f.write(_get_modified_layout_template())
        
        static_dir_path = src_dir_path / DEFAULT_STATIC_DIR_NAME
        static_dir_path.mkdir(exist_ok=True)

        if not blank:
            # Create main.css stylesheet
            with open(src_dir_path / "main.css", "w", encoding="utf-8") as f: f.write(_get_main_css_template())

            index_hpy_path = src_dir_path / "index.hpy"
            index_py_path = src_dir_path / "index.py"
            with open(index_hpy_path, "w", encoding="utf-8") as f: f.write(_get_layout_index_template())
            with open(index_py_path, "w", encoding="utf-8") as f: f.write(_get_layout_index_py_template())

            about_hpy_path = src_dir_path / "about.hpy"
            scripts_dir_path = src_dir_path / "scripts"
            scripts_dir_path.mkdir(exist_ok=True)
            about_py_path = scripts_dir_path / "about_logic.py"
            with open(about_hpy_path, "w", encoding="utf-8") as f: f.write(_get_layout_about_template())
            with open(about_py_path, "w", encoding="utf-8") as f: f.write(_get_layout_about_py_template())

            logo_path = static_dir_path / "logo.svg"
            with open(logo_path, "w", encoding="utf-8") as f: f.write(_get_logo_svg_template())

            components_dir_path = src_dir_path / DEFAULT_COMPONENTS_DIR
            components_dir_path.mkdir(exist_ok=True)
            with open(components_dir_path / "Card.hpy", "w", encoding="utf-8") as f: f.write(_get_component_card_template())

    except Exception as e:
        print(f"Error creating layout project at '{project_path}': {e}", file=sys.stderr)
        if isinstance(e, (OSError, IOError)):
            print("Please check permissions and available disk space.", file=sys.stderr)
        sys.exit(1)

    if blank:
        print(f"\n✓ Blank HPY project initialized in '{project_path}'.")
    else:
        print(f"\n✓ Full HPY project with Component Demo initialized in '{project_path}'.")

    print("Created:")
    if hpy_toml_path: print(f"  - {hpy_toml_path.relative_to(project_path)}")
    print(f"  - {src_dir_path.relative_to(project_path)}/")
    print(f"    - {APP_SHELL_FILENAME}")
    print(f"    - {LAYOUT_FILENAME} (links to main.css)") # MODIFIED
    
    if not blank:
        print(f"    - main.css") # NEW
        print(f"    - {DEFAULT_COMPONENTS_DIR}/Card.hpy")
        print(f"    - index.hpy (uses the Card component)")
        print(f"    - index.py")
        print(f"    - about.hpy")
        print(f"    - scripts/about_logic.py")
        print(f"    - {static_dir_path.relative_to(src_dir_path).name}/logo.svg")
    else:
        print(f"    - {static_dir_path.relative_to(src_dir_path).name}/")
        print(f"    (Minimal content - add your pages and components to '{src_dir_path.name}')")
    
    print("\nTo get started:")
    print(f"  cd {project_path.name}")
    print(f"  # Edit hpy.toml to configure static assets and components directories.")
    print(f"  hpy watch")


def init_project(project_dir_str: str):
    project_path = Path(project_dir_str).resolve()
    if project_path.exists() and project_path.is_dir() and any(project_path.iterdir()):
         print(f"Error: Directory '{project_dir_str}' already exists and is not empty.", file=sys.stderr); sys.exit(1)
    elif project_path.exists() and not project_path.is_dir():
         print(f"Error: '{project_dir_str}' exists and is not a directory.", file=sys.stderr); sys.exit(1)
    
    print("Choose a project template:")
    print("  1: Simple Single File (app.hpy + hpy.toml)")
    print("  2: Full Project (App Shell, Layout, Examples, and Component Demo)")
    print("  3: Blank Project (App Shell, Minimal Layout)")
    
    choice = "";
    while choice not in ["1", "2", "3"]:
        choice = input("Enter choice (default: 2): ").strip();
        if not choice: choice = "2"
        if choice not in ["1", "2", "3"]: print("Invalid choice. Please enter 1, 2, or 3.")
            
    if choice == "1":
        _create_single_file_project(project_path)
    elif choice == "2":
        _create_layout_project(project_path, blank=False)
    elif choice == "3":
        _create_layout_project(project_path, blank=True)