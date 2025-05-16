# tests/test_building.py (Reverted)

import unittest
import sys
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

PROJECT_ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT_DIR))

from hpy_core import building
from hpy_core.config import LAYOUT_FILENAME, LAYOUT_PLACEHOLDER, CONFIG_FILENAME, DEFAULT_STATIC_DIR_NAME

def create_file(path: Path, content: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')

class TestBuildingRefactored(unittest.TestCase):
    base_temp_dir = Path("temp_test_hpy_projects")

    def setUp(self):
        self.base_temp_dir.mkdir(exist_ok=True)
        self.test_dir = self.base_temp_dir / self.id().split('.')[-1]
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.input_dir = self.test_dir / "src"
        self.output_dir = self.test_dir / "dist"
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')

    def tearDown(self):
        sys.stdout.close(); sys.stderr.close()
        sys.stdout = self._original_stdout; sys.stderr = self._original_stderr
        if self.test_dir.exists(): shutil.rmtree(self.test_dir)
        try:
            if not any(self.base_temp_dir.iterdir()): self.base_temp_dir.rmdir()
        except OSError: pass

    def test_01_empty_project(self):
        compiled_files, errors = building.compile_directory(str(self.input_dir), str(self.output_dir), verbose=False)
        self.assertEqual(errors, 0); self.assertEqual(len(compiled_files), 0); self.assertTrue(self.output_dir.exists())

    def test_02_single_hpy_file_no_layout_no_script(self):
        create_file(self.input_dir / "index.hpy", "<html><p>Hello</p></html><style>p{color:red;}</style>")
        compiled_files, errors = building.compile_directory(str(self.input_dir), str(self.output_dir))
        self.assertEqual(errors, 0); self.assertEqual(len(compiled_files), 1)
        output_html = self.output_dir / "index.html"; self.assertTrue(output_html.exists())
        content = output_html.read_text()
        self.assertIn("<p>Hello</p>", content); self.assertIn("p{color:red;}", content)
        self.assertIn(building.HELPER_FUNCTION_CODE, content)

    def test_03_hpy_file_with_inline_python(self):
        create_file(self.input_dir / "app.hpy", "<html><div>Test</div></html><python>print('inline')</python>")
        compiled_files, errors = building.compile_directory(str(self.input_dir), str(self.output_dir))
        self.assertEqual(errors, 0); output_html = self.output_dir / "app.html"; self.assertTrue(output_html.exists())
        content = output_html.read_text()
        self.assertIn("print('inline')", content); self.assertIn(building.HELPER_FUNCTION_CODE, content)

    def test_04_with_layout(self):
        create_file(self.input_dir / LAYOUT_FILENAME, f"<html><header>Layout</header>{LAYOUT_PLACEHOLDER}</html><style>body{{margin:0}}</style><python>print('layout_py')</python>")
        create_file(self.input_dir / "page.hpy", "<html><p>Page Content</p></html><style>p{color:blue;}</style><python>print('page_py')</python>")
        compiled_files, errors = building.compile_directory(str(self.input_dir), str(self.output_dir))
        self.assertEqual(errors, 0); self.assertEqual(len(compiled_files), 1)
        output_html = self.output_dir / "page.html"; self.assertTrue(output_html.exists())
        content = output_html.read_text()
        self.assertIn("<header>Layout</header>", content); self.assertIn("<p>Page Content</p>", content)
        self.assertIn("body{margin:0}", content); self.assertIn("p{color:blue;}", content)
        self.assertIn("print('layout_py')", content); self.assertIn("print('page_py')", content)
        self.assertIn(building.HELPER_FUNCTION_CODE, content)

    def test_05_conventional_python_script(self):
        create_file(self.input_dir / "conv.hpy", "<html>Data</html>")
        create_file(self.input_dir / "conv.py", "print('conventional_script')")
        compiled_files, errors = building.compile_directory(str(self.input_dir), str(self.output_dir))
        self.assertEqual(errors, 0)
        output_html = self.output_dir / "conv.html"; output_py = self.output_dir / "conv.py"
        self.assertTrue(output_html.exists()); self.assertTrue(output_py.exists())
        html_content = output_html.read_text(); py_content = output_py.read_text()
        self.assertIn('<script type="text/python" src="conv.py"></script>', html_content)
        self.assertIn("print('conventional_script')", py_content); self.assertIn(building.HELPER_FUNCTION_CODE, py_content)

    def test_06_explicit_python_script(self):
        create_file(self.input_dir / "explicit.hpy", '<html>Test</html><python src="scripts/my_script.py"></python>')
        create_file(self.input_dir / "scripts" / "my_script.py", "print('explicit_script')")
        compiled_files, errors = building.compile_directory(str(self.input_dir), str(self.output_dir))
        self.assertEqual(errors, 0)
        output_html = self.output_dir / "explicit.html"; output_py = self.output_dir / "scripts" / "my_script.py"
        self.assertTrue(output_html.exists()); self.assertTrue(output_py.exists())
        html_content = output_html.read_text(); py_content = output_py.read_text()
        self.assertIn('<script type="text/python" src="scripts/my_script.py"></script>', html_content.replace("\\","/"))
        self.assertIn("print('explicit_script')", py_content); self.assertIn(building.HELPER_FUNCTION_CODE, py_content)

    def test_07_static_files(self):
        create_file(self.test_dir / CONFIG_FILENAME, f"[tool.hpy]\ninput_dir=\"src\"\noutput_dir=\"dist\"\nstatic_dir_name=\"{DEFAULT_STATIC_DIR_NAME}\"")
        create_file(self.input_dir / DEFAULT_STATIC_DIR_NAME / "style.css", "body{font-size:16px;}")
        create_file(self.input_dir / DEFAULT_STATIC_DIR_NAME / "img" / "logo.png", "dummy_image_data")
        compiled_files, errors = building.compile_directory(str(self.input_dir), str(self.output_dir))
        self.assertEqual(errors, 0)
        self.assertTrue((self.output_dir / DEFAULT_STATIC_DIR_NAME / "style.css").exists())
        self.assertTrue((self.output_dir / DEFAULT_STATIC_DIR_NAME / "img" / "logo.png").exists())
        self.assertEqual((self.output_dir / DEFAULT_STATIC_DIR_NAME / "img" / "logo.png").read_text(), "dummy_image_data")

    def test_08_shared_explicit_script(self):
        create_file(self.input_dir / "page1.hpy", '<html>Page1</html><python src="shared/common.py"></python>')
        create_file(self.input_dir / "page2.hpy", '<html>Page2</html><python src="shared/common.py"></python>')
        create_file(self.input_dir / "shared" / "common.py", "print('shared_code')")
        import io; captured_output = io.StringIO(); original_stdout = sys.stdout; sys.stdout = captured_output
        compiled_files, errors = building.compile_directory(str(self.input_dir), str(self.output_dir), verbose=True)
        sys.stdout = original_stdout; log_content = captured_output.getvalue()
        self.assertEqual(errors, 0); self.assertEqual(len(compiled_files), 2)
        self.assertTrue((self.output_dir / "shared" / "common.py").exists())
        self.assertEqual(log_content.count("Processing external python script: common.py"), 1)
        self.assertEqual(log_content.count("Injected helpers and copied python script: common.py"), 1)

    def test_09_error_missing_explicit_script(self):
        create_file(self.input_dir / "error.hpy", '<html>Fail</html><python src="nonexistent.py"></python>')
        compiled_files, errors = building.compile_directory(str(self.input_dir), str(self.output_dir))
        self.assertEqual(errors, 1); self.assertEqual(len(compiled_files), 0); self.assertFalse((self.output_dir / "error.html").exists())

    def test_10_error_script_outside_input_dir(self):
        create_file(self.test_dir / "external_script.py", "print('danger')")
        create_file(self.input_dir / "page.hpy", '<html>Content</html><python src="../external_script.py"></python>')
        compiled_files, errors = building.compile_directory(str(self.input_dir), str(self.output_dir))
        self.assertEqual(errors, 1); self.assertEqual(len(compiled_files), 0)

    def test_11_error_script_in_static_dir(self):
        create_file(self.test_dir / CONFIG_FILENAME, f"[tool.hpy]\ninput_dir=\"src\"\noutput_dir=\"dist\"\nstatic_dir_name=\"assets\"")
        create_file(self.input_dir / "assets" / "static_script.py", "print('static code')")
        create_file(self.input_dir / "page.hpy", '<html>Content</html><python src="assets/static_script.py"></python>')
        compiled_files, errors = building.compile_directory(str(self.input_dir), str(self.output_dir))
        self.assertEqual(errors, 1); self.assertEqual(len(compiled_files), 0)

    def test_12_error_layout_missing_placeholder(self):
        create_file(self.input_dir / LAYOUT_FILENAME, "<html>No Placeholder Here</html>")
        create_file(self.input_dir / "page.hpy", "<html>Page Content</html>")
        compiled_files, errors = building.compile_directory(str(self.input_dir), str(self.output_dir))
        self.assertEqual(errors, 1); self.assertEqual(len(compiled_files), 0)

    def test_13_nested_hpy_files_and_scripts(self):
        create_file(self.input_dir / "subdir" / "nested_page.hpy", '<html>Nested Page</html><python src="scripts/nested_script.py"></python>')
        create_file(self.input_dir / "subdir" / "scripts" / "nested_script.py", "print('nested_explicit')")
        create_file(self.input_dir / "another" / "conv_page.hpy", "<html>Another Conv Page</html>")
        create_file(self.input_dir / "another" / "conv_page.py", "print('another_conventional')")
        compiled_files, errors = building.compile_directory(str(self.input_dir), str(self.output_dir))
        self.assertEqual(errors, 0); self.assertEqual(len(compiled_files), 2)
        self.assertTrue((self.output_dir / "subdir" / "nested_page.html").exists())
        self.assertTrue((self.output_dir / "subdir" / "scripts" / "nested_script.py").exists())
        html_content_nested = (self.output_dir / "subdir" / "nested_page.html").read_text()
        self.assertIn('<script type="text/python" src="scripts/nested_script.py"></script>', html_content_nested.replace("\\","/"))
        self.assertTrue((self.output_dir / "another" / "conv_page.html").exists())
        self.assertTrue((self.output_dir / "another" / "conv_page.py").exists())
        html_content_conv = (self.output_dir / "another" / "conv_page.html").read_text()
        self.assertIn('<script type="text/python" src="conv_page.py"></script>', html_content_conv.replace("\\","/"))

    # Removed tests 14-20

if __name__ == '__main__':
    if TestBuildingRefactored.base_temp_dir.exists(): shutil.rmtree(TestBuildingRefactored.base_temp_dir)
    unittest.main(verbosity=1)