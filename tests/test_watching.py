# tests/test_watching.py (Updated for resolved path assertions)

import unittest
import sys
import os
import shutil
import time
from pathlib import Path
from typing import Dict, Any, Optional, Type 

PROJECT_ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT_DIR))

from hpy_core import watching
from hpy_core.config import LAYOUT_FILENAME, CONFIG_FILENAME, DEFAULT_STATIC_DIR_NAME
from hpy_core.watching import HpyDirectoryEventHandler 

if watching.WATCHDOG_AVAILABLE:
    from watchdog.events import FileSystemEvent, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent, FileMovedEvent
else:
    class FileSystemEvent: # type: ignore
        EVENT_TYPE_MODIFIED = 'modified'
        EVENT_TYPE_CREATED = 'created'
        EVENT_TYPE_DELETED = 'deleted'
        EVENT_TYPE_MOVED = 'moved'
        is_directory: bool = False
        def __init__(self, src_path):
            self.src_path = str(src_path) 
            try: self.is_directory = Path(src_path).is_dir()
            except OSError: self.is_directory = False
    class FileModifiedEvent(FileSystemEvent): event_type = FileSystemEvent.EVENT_TYPE_MODIFIED # type: ignore
    class FileCreatedEvent(FileSystemEvent): event_type = FileSystemEvent.EVENT_TYPE_CREATED # type: ignore
    class FileDeletedEvent(FileSystemEvent): event_type = FileSystemEvent.EVENT_TYPE_DELETED # type: ignore
    class FileMovedEvent(FileSystemEvent): # type: ignore
        event_type = FileSystemEvent.EVENT_TYPE_MOVED
        def __init__(self, src_path, dest_path):
            super().__init__(src_path)
            self.dest_path = str(dest_path)

def create_file(path: Path, content: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    time.sleep(0.05) 

def modify_file(path: Path, new_content: Optional[str] = None, append_content: Optional[str] = None):
    if not path.exists(): create_file(path, new_content or ""); return
    if new_content is not None: path.write_text(new_content, encoding='utf-8')
    if append_content is not None:
        path.write_text(path.read_text(encoding='utf-8') + append_content, encoding='utf-8')
    time.sleep(0.05)

def delete_file(path: Path):
    if path.is_file(): path.unlink()
    elif path.is_dir(): shutil.rmtree(path)
    time.sleep(0.05)

def move_file(src_path: Path, dest_path: Path):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if src_path.exists(): shutil.move(str(src_path), str(dest_path))
    time.sleep(0.05)


@unittest.skipIf(not watching.WATCHDOG_AVAILABLE, "Watchdog library not installed, skipping watcher tests.")
class TestWatchingCSSDependencies(unittest.TestCase):
    base_temp_dir = Path("temp_test_hpy_watcher")

    def setUp(self):
        self.base_temp_dir.mkdir(exist_ok=True)
        self.test_dir = self.base_temp_dir / self.id().split('.')[-1]
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.input_dir = self.test_dir / "src"
        self.output_dir = self.test_dir / "dist"
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True) 
        create_file(self.test_dir / CONFIG_FILENAME, "[tool.hpy]")
        self.handler = HpyDirectoryEventHandler(
            str(self.input_dir.resolve()), str(self.output_dir.resolve()), verbose=False)
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

    def _get_output_mtime(self, hpy_filename: str) -> Optional[float]:
        output_file = self.output_dir / Path(hpy_filename).with_suffix(".html")
        return output_file.stat().st_mtime if output_file.exists() else None

    def _dispatch_event(self, event_type: Type[FileSystemEvent], src_path_rel: str, dest_path_rel: Optional[str] = None):
        abs_src_path = str(self.input_dir / src_path_rel)
        event: FileSystemEvent
        is_delete_event = event_type is FileDeletedEvent

        if dest_path_rel and event_type is FileMovedEvent: 
            abs_dest_path = str(self.input_dir / dest_path_rel)
            event = event_type(abs_src_path, abs_dest_path) 
        else:
            event = event_type(abs_src_path) 
        
        # Reset debounce
        path_to_clear_debounce_for_src = abs_src_path
        try: path_to_clear_debounce_for_src = str(Path(abs_src_path).resolve())
        except FileNotFoundError: pass
        self.handler._last_triggered[path_to_clear_debounce_for_src] = 0
        
        if hasattr(event, 'dest_path'):
            path_to_clear_debounce_for_dest = getattr(event, 'dest_path')
            try: path_to_clear_debounce_for_dest = str(Path(path_to_clear_debounce_for_dest).resolve())
            except FileNotFoundError: pass
            self.handler._last_triggered[path_to_clear_debounce_for_dest] = 0
            
        self.handler.dispatch(event)
        time.sleep(0.1) 

    def test_01_css_modification_rebuilds_dependent_hpy(self):
        css_rel_path = "styles/page.css"
        hpy_rel_path = "index.hpy"
        create_file(self.input_dir / css_rel_path, ".initial { color: blue; }")
        create_file(self.input_dir / hpy_rel_path, f'<html>Test</html><style src="{css_rel_path}"></style>')
        self.handler._build_dependency_map() 
        self.handler._rebuild_single_page(self.input_dir / hpy_rel_path)
        initial_mtime = self._get_output_mtime(hpy_rel_path)
        self.assertIsNotNone(initial_mtime)
        time.sleep(0.1) 
        modify_file(self.input_dir / css_rel_path, new_content=".modified { color: red; }")
        self._dispatch_event(FileModifiedEvent, css_rel_path) 
        new_mtime = self._get_output_mtime(hpy_rel_path)
        self.assertIsNotNone(new_mtime)
        self.assertGreater(new_mtime, initial_mtime, "Output HTML should have been rebuilt.")
        content = (self.output_dir / Path(hpy_rel_path).with_suffix(".html")).read_text()
        self.assertIn(".modified { color: red; }", content)
        self.assertNotIn(".initial { color: blue; }", content)

    def test_02_css_deletion_rebuilds_dependent_hpy(self):
        css_rel_path = "styles/delete_me.css"
        hpy_rel_path = "page_using_deleted_css.hpy"
        abs_css_path = (self.input_dir / css_rel_path).resolve() # Use resolved path for checks

        create_file(self.input_dir / css_rel_path, ".exists {}")
        create_file(self.input_dir / hpy_rel_path, f'<html>Data</html><style src="{css_rel_path}"></style>')
        self.handler._build_dependency_map()
        self.handler._rebuild_single_page(self.input_dir / hpy_rel_path)
        initial_mtime = self._get_output_mtime(hpy_rel_path)
        self.assertTrue((self.output_dir / Path(hpy_rel_path).with_suffix(".html")).read_text().count(".exists {}") > 0)
        
        self.assertTrue(abs_css_path in self.handler.css_dependents, # Use resolved path for assertion
                        f"CSS {abs_css_path} not in dependents: {list(self.handler.css_dependents.keys())}")

        delete_file(self.input_dir / css_rel_path)
        self._dispatch_event(FileDeletedEvent, css_rel_path) 
        new_mtime = self._get_output_mtime(hpy_rel_path)
        self.assertIsNotNone(new_mtime)
        self.assertTrue(new_mtime >= initial_mtime, "Output HTML mtime should be same or newer.")
        content_after_delete = (self.output_dir / Path(hpy_rel_path).with_suffix(".html")).read_text()
        self.assertNotIn(".exists {}", content_after_delete, "Deleted CSS content should be gone.")
        self.assertNotIn(abs_css_path, self.handler.css_dependents, # Use resolved path
                         "Deleted CSS file should be removed from css_dependents map.")

    def test_03_hpy_modification_updates_css_dependencies(self):
        css1_rel_path = "s1.css"
        css2_rel_path = "s2.css"
        hpy_rel_path = "multi_css_page.hpy"
        abs_css1_path = (self.input_dir / css1_rel_path).resolve() # Resolved
        abs_css2_path = (self.input_dir / css2_rel_path).resolve() # Resolved
        abs_hpy_path = (self.input_dir / hpy_rel_path).resolve()   # Resolved

        create_file(self.input_dir / css1_rel_path, ".s1{}")
        create_file(self.input_dir / css2_rel_path, ".s2{}")
        create_file(self.input_dir / hpy_rel_path, f'<html>Hi</html><style src="{css1_rel_path}"></style>')
        self.handler._build_dependency_map()

        self.assertTrue(abs_css1_path in self.handler.css_dependents,
                        f"CSS1 {abs_css1_path} not in dependents. Keys: {list(self.handler.css_dependents.keys())}")
        self.assertFalse(abs_css2_path in self.handler.css_dependents, 
                         f"CSS2 {abs_css2_path} should not initially be in css_dependents. Keys: {list(self.handler.css_dependents.keys())}")
        self.assertEqual(self.handler.hpy_style_dependencies.get(abs_hpy_path), {abs_css1_path})

        modify_file(self.input_dir / hpy_rel_path, new_content=f'<html>Hi V2</html><style src="{css2_rel_path}"></style>')
        self._dispatch_event(FileModifiedEvent, hpy_rel_path) 
        
        css1_dependents = self.handler.css_dependents.get(abs_css1_path, set())
        self.assertNotIn(abs_hpy_path, css1_dependents, "HPY file should no longer depend on CSS1.")
        if not css1_dependents:
             self.assertNotIn(abs_css1_path, self.handler.css_dependents, "CSS1 should be removed if it has no dependents.")

        self.assertTrue(abs_css2_path in self.handler.css_dependents)
        self.assertEqual(self.handler.css_dependents[abs_css2_path], {abs_hpy_path})
        self.assertEqual(self.handler.hpy_style_dependencies.get(abs_hpy_path), {abs_css2_path})

    def test_04_layout_css_modification_rebuilds_page(self):
        layout_css_rel_path = "css/layout.css"
        page_rel_path = "page.hpy"
        abs_layout_css_path = (self.input_dir / layout_css_rel_path).resolve() # Resolved
        abs_layout_hpy_path = (self.input_dir / LAYOUT_FILENAME).resolve()     # Resolved
        abs_page_hpy_path = (self.input_dir / page_rel_path).resolve()       # Resolved

        create_file(self.input_dir / layout_css_rel_path, ".layout-initial {}")
        create_file(self.input_dir / LAYOUT_FILENAME, f'<html><style src="{layout_css_rel_path}"></style><!-- HPY_PAGE_CONTENT --></html>')
        create_file(self.input_dir / page_rel_path, "<html>Page Data</html>")
        self.handler._build_dependency_map() 
        self.handler.layout_content = self.handler._parse_layout() 
        self.handler._rebuild_single_page(abs_page_hpy_path)
        initial_mtime = self._get_output_mtime(page_rel_path)
        self.assertIsNotNone(initial_mtime)
        time.sleep(0.1)
        modify_file(self.input_dir / layout_css_rel_path, new_content=".layout-modified {}")
        self._dispatch_event(FileModifiedEvent, layout_css_rel_path) 
        new_mtime = self._get_output_mtime(page_rel_path)
        self.assertIsNotNone(new_mtime)
        self.assertGreater(new_mtime, initial_mtime, "Page HTML should have been rebuilt.")
        content = (self.output_dir / Path(page_rel_path).with_suffix(".html")).read_text()
        self.assertIn(".layout-modified {}", content)

    def test_05_unrelated_css_modification_does_not_rebuild(self):
        tracked_css_rel_path = "styles/used.css"
        unrelated_css_rel_path = "styles/unused.css"
        hpy_rel_path = "index.hpy"
        abs_hpy_path = (self.input_dir / hpy_rel_path).resolve() # Resolved

        create_file(self.input_dir / tracked_css_rel_path, ".used {}")
        create_file(self.input_dir / unrelated_css_rel_path, ".unused {}")
        create_file(self.input_dir / hpy_rel_path, f'<html>Test</html><style src="{tracked_css_rel_path}"></style>')
        self.handler._build_dependency_map()
        self.handler._rebuild_single_page(abs_hpy_path)
        initial_mtime = self._get_output_mtime(hpy_rel_path)
        modify_file(self.input_dir / unrelated_css_rel_path, new_content=".unused-modified {}")
        self._dispatch_event(FileModifiedEvent, unrelated_css_rel_path) 
        new_mtime = self._get_output_mtime(hpy_rel_path)
        self.assertEqual(new_mtime, initial_mtime, "Output HTML should NOT have been rebuilt.")

if __name__ == '__main__':
    if TestWatchingCSSDependencies.base_temp_dir.exists():
        shutil.rmtree(TestWatchingCSSDependencies.base_temp_dir)
    unittest.main(verbosity=1)