# hpy_core/components.py
"""Component System: Discovery and Registry."""

import re
from pathlib import Path
from typing import Dict, Optional

# Regex to find {props.key} placeholders.
PROPS_REGEX = re.compile(r'\{props\.([a-zA-Z0-9_]+)\}')

class ComponentRegistry:
    """Discovers and holds references to all found .hpy components."""
    def __init__(self, components_base_dir: Path, input_dir: Path, verbose: bool = False):
        self.base_dir = components_base_dir
        self.input_dir = input_dir
        self.verbose = verbose
        self.mapping: Dict[str, Path] = {}
        self.scan()

    def scan(self):
        """Scans the components directory recursively to build the name-to-path mapping."""
        self.mapping = {}
        if not self.base_dir.is_dir():
            if self.verbose:
                # Use relative path for cleaner logging
                rel_base_dir = self.base_dir.relative_to(self.input_dir.parent) if self.base_dir.is_relative_to(self.input_dir.parent) else self.base_dir
                print(f"[Components] Directory '{rel_base_dir}' not found. No components loaded.")
            return

        rel_base_dir = self.base_dir.relative_to(self.input_dir.parent) if self.base_dir.is_relative_to(self.input_dir.parent) else self.base_dir
        if self.verbose:
            print(f"[Components] Scanning for components in '{rel_base_dir}'...")
        
        for hpy_file in self.base_dir.rglob('*.hpy'):
            if hpy_file.stem.startswith('_'): # Skip private/utility components
                continue
            
            # Create a capitalized, dot-separated name from the path
            relative_path = hpy_file.relative_to(self.base_dir)
            name_parts = [part.capitalize() for part in relative_path.with_suffix('').parts]
            component_name = ".".join(name_parts)
            
            if component_name in self.mapping:
                print(f"Warning: Duplicate component name '{component_name}'. Overwriting '{self.mapping[component_name]}' with '{hpy_file}'")

            self.mapping[component_name] = hpy_file
            if self.verbose:
                rel_hpy_file = hpy_file.relative_to(self.input_dir) if hpy_file.is_relative_to(self.input_dir) else hpy_file
                print(f"  Registered component: <{component_name}> -> {rel_hpy_file}")

    def get_path(self, name: str) -> Optional[Path]:
        """Gets the file path for a given component name."""
        return self.mapping.get(name)

# NOTE: The standalone `render_component` function that caused the import error
# has been removed. The rendering logic is now correctly and fully handled within
# `hpy_core/building.py` by the `_render_content_recursively` function. This
# prevents circular dependencies and keeps the build orchestration in one place.