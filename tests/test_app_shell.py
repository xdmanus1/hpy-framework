import pytest
from pathlib import Path
import shutil # For cleaning up test directories if needed

# Assuming your core modules are accessible for import
from hpy_core.building import compile_directory, compile_hpy_file
from hpy_core.init import init_project # To create test project structures
from hpy_core.config import (
    DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR, APP_SHELL_FILENAME, LAYOUT_FILENAME,
    APP_SHELL_HEAD_PLACEHOLDER, APP_SHELL_BODY_PLACEHOLDER
)

# Helper to create a basic project structure
def create_test_project_structure(base_path: Path, project_type: str = "shell_layout_page"):
    """
    Creates a project structure for testing.
    Types:
    - "shell_layout_page": _app.html, _layout.hpy, index.hpy
    - "shell_page_only": _app.html, index.hpy (no layout)
    - "layout_page_only": _layout.hpy (old style), index.hpy (no app shell)
    - "page_only": index.hpy (no app shell, no layout)
    - "shell_blank_layout_page": _app.html, blank _layout.hpy, index.hpy
    """
    src_dir = base_path / DEFAULT_INPUT_DIR
    src_dir.mkdir(parents=True, exist_ok=True)

    # Default _app.html
    app_shell_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>App Shell Default Title</title>
    {APP_SHELL_HEAD_PLACEHOLDER}
</head>
<body>
    <div id="app-shell-wrapper">
        {APP_SHELL_BODY_PLACEHOLDER}
    </div>
</body>
</html>"""

    # Default _layout.hpy (for app shell)
    layout_content_for_shell = f"""<hpy-head>
    <title>Layout Title</title>
    <meta name="layout-meta" content="layout-head-data">
    <style>.layout-style {{ color: blue; }}</style>
</hpy-head>
<hpy-body>
    <div class="layout-body">
        <header>Layout Header</header>
        <!-- HPY_PAGE_CONTENT -->
        <footer>Layout Footer</footer>
    </div>
    <script type="text/python">print("Layout Python")</script>
</hpy-body>"""

    # Legacy _layout.hpy (full HTML)
    legacy_layout_content = f"""<!DOCTYPE html>
<html>
<head><title>Legacy Layout Title</title><style>.legacy-layout {{font-style: italic;}}</style></head>
<body>
    <div class="legacy-layout-body">
        <!-- HPY_PAGE_CONTENT -->
    </div>
    <script type="text/python">print("Legacy Layout Python")</script>
</body>
</html>"""
    
    # Blank _layout.hpy (for app shell)
    blank_layout_content_for_shell = f"""<hpy-head>
    <title>Blank Layout Title</title>
</hpy-head>
<hpy-body>
    <!-- HPY_PAGE_CONTENT -->
</hpy-body>"""


    # Default index.hpy
    index_hpy_content = f"""<html>
    <div class="page-content">Page Content for Index</div>
    <p>Index Para</p>
</html>
<hpy-head>
    <title>Index Page Title</title>
    <meta name="page-meta" content="page-head-data">
</hpy-head>
<style>.page-style {{ color: red; }}</style>
<python>print("Index Page Python")</python>"""

    # Simpler index.hpy for page_only test
    simple_index_hpy_content = f"""<!DOCTYPE html>
<html>
<head><title>Simple Page Title</title><style>.simple-page {{font-weight:bold;}}</style></head>
<body>
    <div>Simple Page Content</div>
    <script type="text/python">print("Simple Page Python")</script>
</body>
</html>"""


    if "shell" in project_type:
        (src_dir / APP_SHELL_FILENAME).write_text(app_shell_content, encoding='utf-8')

    if project_type == "shell_layout_page":
        (src_dir / LAYOUT_FILENAME).write_text(layout_content_for_shell, encoding='utf-8')
        (src_dir / "index.hpy").write_text(index_hpy_content, encoding='utf-8')
    elif project_type == "shell_page_only":
        (src_dir / "index.hpy").write_text(index_hpy_content, encoding='utf-8') # index.hpy has <hpy-head>
    elif project_type == "layout_page_only": # No app shell
        (src_dir / LAYOUT_FILENAME).write_text(legacy_layout_content, encoding='utf-8')
        (src_dir / "index.hpy").write_text(index_hpy_content.replace("<hpy-head>", "<!--").replace("</hpy-head>", "-->"), encoding='utf-8') # Comment out hpy-head for this case
    elif project_type == "page_only": # No app shell, no layout
        (src_dir / "index.hpy").write_text(simple_index_hpy_content, encoding='utf-8')
    elif project_type == "shell_blank_layout_page":
        (src_dir / LAYOUT_FILENAME).write_text(blank_layout_content_for_shell, encoding='utf-8')
        (src_dir / "index.hpy").write_text(index_hpy_content, encoding='utf-8')

    # Create dummy hpy.toml
    (base_path / "hpy.toml").write_text(f"[tool.hpy]\ninput_dir = \"{DEFAULT_INPUT_DIR}\"\noutput_dir = \"{DEFAULT_OUTPUT_DIR}\"\n", encoding='utf-8')
    return src_dir, base_path / DEFAULT_OUTPUT_DIR

# --- Test Cases ---

def test_compile_with_app_shell_and_layout(tmp_path):
    src_dir, out_dir = create_test_project_structure(tmp_path, "shell_layout_page")
    
    # Compile the directory (is_dev_watch_mode=False for standard build test)
    _, errors = compile_directory(str(src_dir), str(out_dir), verbose=False, is_dev_watch_mode=False)
    assert errors == 0
    
    output_html = out_dir / "index.html"
    assert output_html.exists()
    content = output_html.read_text(encoding='utf-8')

    # Check for App Shell structure
    assert "<html lang=\"en\">" in content
    assert "<div id=\"app-shell-wrapper\">" in content
    
    # Check for Layout's head content (title, meta, style) in head
    assert "<title>Layout Title</title>" in content # Layout title should override page title if layout's <hpy-head> is processed first
    # OR if page title overrides layout: assert "<title>Index Page Title</title>" in content 
    # This depends on the combination logic, let's assume for now layout <hpy-head> + page <hpy-head> are additive
    # and title replacement logic favors the most specific one.
    # The current building.py logic: page_head_fragment contains both, title extracted from it.
    assert "<title>Index Page Title</title>" in content # Page <hpy-head> title should win
    assert "<meta name=\"layout-meta\" content=\"layout-head-data\">" in content
    assert "<meta name=\"page-meta\" content=\"page-head-data\">" in content
    assert ".layout-style { color: blue; }" in content
    assert ".page-style { color: red; }" in content # Page style should also be there

    # Check for Layout's body content
    assert "<div class=\"layout-body\">" in content
    assert "<header>Layout Header</header>" in content
    assert "<footer>Layout Footer</footer>" in content
    
    # Check for Page's body content inside layout
    assert "<div class=\"page-content\">Page Content for Index</div>" in content
    assert "<p>Index Para</p>" in content
    
    # Check for Python scripts
    assert "print(\"Layout Python\")" in content
    assert "print(\"Index Page Python\")" in content
    assert "Live Reload" not in content # is_dev_watch_mode=False

def test_compile_with_app_shell_page_only(tmp_path):
    src_dir, out_dir = create_test_project_structure(tmp_path, "shell_page_only")
    _, errors = compile_directory(str(src_dir), str(out_dir), verbose=False, is_dev_watch_mode=False)
    assert errors == 0
    output_html = out_dir / "index.html"
    assert output_html.exists()
    content = output_html.read_text(encoding='utf-8')

    assert "<div id=\"app-shell-wrapper\">" in content
    assert "<title>Index Page Title</title>" in content # Page's <hpy-head> title
    assert "<meta name=\"page-meta\" content=\"page-head-data\">" in content
    assert ".page-style { color: red; }" in content
    assert "<div class=\"page-content\">Page Content for Index</div>" in content # Page body
    assert "print(\"Index Page Python\")" in content
    assert "Layout Header" not in content # No layout

def test_compile_fallback_no_app_shell_with_layout(tmp_path):
    src_dir, out_dir = create_test_project_structure(tmp_path, "layout_page_only") # No _app.html
    _, errors = compile_directory(str(src_dir), str(out_dir), verbose=False, is_dev_watch_mode=False)
    assert errors == 0
    output_html = out_dir / "index.html"
    assert output_html.exists()
    content = output_html.read_text(encoding='utf-8')

    assert "<!DOCTYPE html>" in content # Fallback generates full doc
    assert "<div id=\"app-shell-wrapper\">" not in content
    assert "<title>Legacy Layout Title</title>" in content # From legacy layout
    # Page's hpy-head was commented out for this test case
    assert "<meta name=\"page-meta\" content=\"page-head-data\">" not in content 
    assert ".legacy-layout {font-style: italic;}" in content # Layout style
    assert ".page-style { color: red; }" in content # Page style
    assert "<div class=\"legacy-layout-body\">" in content
    assert "<div class=\"page-content\">Page Content for Index</div>" in content
    assert "print(\"Legacy Layout Python\")" in content
    assert "print(\"Index Page Python\")" in content


def test_compile_fallback_no_app_shell_no_layout(tmp_path):
    src_dir, out_dir = create_test_project_structure(tmp_path, "page_only") # No _app.html, no _layout.hpy
    _, errors = compile_directory(str(src_dir), str(out_dir), verbose=False, is_dev_watch_mode=False)
    assert errors == 0
    output_html = out_dir / "index.html" # Assuming index.hpy is named index.hpy
    assert output_html.exists()
    content = output_html.read_text(encoding='utf-8')

    assert "<title>Simple Page Title</title>" in content
    assert ".simple-page {font-weight:bold;}" in content
    assert "<div>Simple Page Content</div>" in content
    assert "print(\"Simple Page Python\")" in content
    assert "<div id=\"app-shell-wrapper\">" not in content
    assert "Layout Header" not in content

def test_compile_with_app_shell_and_blank_layout(tmp_path):
    src_dir, out_dir = create_test_project_structure(tmp_path, "shell_blank_layout_page")
    _, errors = compile_directory(str(src_dir), str(out_dir), verbose=False, is_dev_watch_mode=False)
    assert errors == 0
    output_html = out_dir / "index.html"
    assert output_html.exists()
    content = output_html.read_text(encoding='utf-8')

    assert "<div id=\"app-shell-wrapper\">" in content
    # Title priority: Page's <hpy-head> -> Layout's <hpy-head> -> App Shell
    assert "<title>Index Page Title</title>" in content 
    assert "<meta name=\"page-meta\" content=\"page-head-data\">" in content # From page's <hpy-head>
    assert ".page-style { color: red; }" in content # Page style
    # Blank layout's body is just the page content placeholder
    assert "<div class=\"page-content\">Page Content for Index</div>" in content
    assert "Layout Header" not in content # Blank layout doesn't have this
    assert "print(\"Index Page Python\")" in content


def test_live_reload_script_injection_with_app_shell(tmp_path):
    src_dir, out_dir = create_test_project_structure(tmp_path, "shell_layout_page")
    # Compile with is_dev_watch_mode=True
    _, errors = compile_directory(str(src_dir), str(out_dir), verbose=False, is_dev_watch_mode=True)
    assert errors == 0
    output_html = out_dir / "index.html"
    content = output_html.read_text(encoding='utf-8')
    
    assert "// HPY Tool Live Reload v" in content
    assert "const RELOAD_FILE = '/.hpy_reload';" in content

def test_live_reload_script_NOT_injected_without_watch_mode(tmp_path):
    src_dir, out_dir = create_test_project_structure(tmp_path, "shell_layout_page")
    _, errors = compile_directory(str(src_dir), str(out_dir), verbose=False, is_dev_watch_mode=False)
    assert errors == 0
    output_html = out_dir / "index.html"
    content = output_html.read_text(encoding='utf-8')
    
    assert "// HPY Tool Live Reload v" not in content

# Further tests could include:
# - Layout without <hpy-head> but with <hpy-body>
# - Page without <hpy-head> used with layout and app_shell
# - App shell with missing placeholders (to check warnings, though build might still proceed)
# - More complex Python script interactions and helper injections with app shell