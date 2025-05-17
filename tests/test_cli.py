import pytest
from pathlib import Path
import sys
import os
import shutil
from unittest import mock # For patching sys.argv and potentially other things

# Assuming hpy_core.cli.main is the entry point
from hpy_core.cli import main as hpy_main 
from hpy_core.config import DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR, APP_SHELL_FILENAME, LAYOUT_FILENAME, CONFIG_FILENAME

# Helper to run hpy main with specific args
def run_hpy_cli(capsys, *args):
    """Runs the hpy CLI main function with patched sys.argv and captures output."""
    original_argv = sys.argv
    # Prepend 'hpy' as the script name, as argparse expects it
    sys.argv = ['hpy'] + list(args)
    exit_code = None
    try:
        hpy_main() # hpy_main should call sys.exit() on its own
    except SystemExit as e:
        exit_code = e.code
    finally:
        sys.argv = original_argv # Restore original argv
    
    captured = capsys.readouterr()
    return captured.out, captured.err, exit_code

# --- Tests for `hpy init` subcommand ---
def test_cli_init_new_project(tmp_path, capsys):
    project_name = "test_init_subcommand"
    project_dir = tmp_path / project_name
    
    out, err, exit_code = run_hpy_cli(capsys, "init", str(project_dir), "-v") # Add -v for more debug from init
    
    assert exit_code == 0, f"hpy init failed. Error: {err}"
    assert project_dir.is_dir()
    assert (project_dir / DEFAULT_INPUT_DIR).is_dir()
    assert (project_dir / DEFAULT_INPUT_DIR / APP_SHELL_FILENAME).exists()
    assert (project_dir / DEFAULT_INPUT_DIR / LAYOUT_FILENAME).exists()
    assert (project_dir / CONFIG_FILENAME).exists()
    assert "Directory-based HPY project with App Shell initialized" in out # Check for success message

def test_cli_init_new_project_blank(tmp_path, capsys):
    project_name = "test_init_blank"
    project_dir = tmp_path / project_name

    # Simulate user input '3' for blank project
    with mock.patch('builtins.input', return_value='3'):
        out, err, exit_code = run_hpy_cli(capsys, "init", str(project_dir))
    
    assert exit_code == 0, f"hpy init (blank) failed. Error: {err}"
    assert project_dir.is_dir()
    assert (project_dir / DEFAULT_INPUT_DIR / APP_SHELL_FILENAME).exists()
    assert not (project_dir / DEFAULT_INPUT_DIR / "index.hpy").exists() # Should not have example pages
    assert "Blank HPY project with App Shell initialized" in out

def test_cli_init_existing_non_empty_dir(tmp_path, capsys):
    project_name = "test_init_existing"
    project_dir = tmp_path / project_name
    project_dir.mkdir()
    (project_dir / "somefile.txt").write_text("hello")
    
    out, err, exit_code = run_hpy_cli(capsys, "init", str(project_dir))
    
    assert exit_code != 0 # Should fail
    assert "already exists and is not empty" in err

# --- Tests for `hpy build` subcommand ---
@pytest.fixture
def basic_project(tmp_path):
    project_name = "build_proj"
    proj_path = tmp_path / project_name
    # Use init to create a known good structure (full project)
    with mock.patch('builtins.input', return_value='2'): # Choose 'Full Project'
        run_hpy_cli(mock.MagicMock(), "init", str(proj_path)) # Use MagicMock for capsys if not needed
    return proj_path

def test_cli_build_default(basic_project, capsys):
    project_path = basic_project
    output_dir = project_path / DEFAULT_OUTPUT_DIR
    
    # Run build from within the project directory for default source/output
    original_cwd = os.getcwd()
    os.chdir(project_path)
    try:
        out, err, exit_code = run_hpy_cli(capsys, "build", "-v") # Test with verbose
    finally:
        os.chdir(original_cwd)
        
    assert exit_code == 0, f"hpy build failed. Error: {err}"
    assert (output_dir / "index.html").exists()
    assert (output_dir / "about.html").exists()
    assert "Build successful" in out
    assert "Development mode" in out # Check for dev mode message
    # Check that live reload script is NOT injected by default for 'build'
    index_content = (output_dir / "index.html").read_text()
    assert "HPY Tool Live Reload" not in index_content 
    # Check Brython debug level (should be 1 for dev build)
    assert "brython({'debug': 1})" in index_content


def test_cli_build_production(basic_project, capsys):
    project_path = basic_project
    output_dir = project_path / DEFAULT_OUTPUT_DIR
    
    original_cwd = os.getcwd()
    os.chdir(project_path)
    try:
        out, err, exit_code = run_hpy_cli(capsys, "build", "--production", "-v")
    finally:
        os.chdir(original_cwd)
        
    assert exit_code == 0, f"hpy build --production failed. Error: {err}"
    assert (output_dir / "index.html").exists()
    assert "Build successful" in out
    assert "Production mode" in out # Check for production mode message
    index_content = (output_dir / "index.html").read_text()
    assert "brython({'debug': 0})" in index_content # Brython debug should be 0
    assert "HPY Tool Live Reload" not in index_content # No live reload script

def test_cli_build_specific_source_output(tmp_path, basic_project, capsys):
    # Use basic_project's src dir as source, output to a new custom dir
    src_dir = basic_project / DEFAULT_INPUT_DIR
    custom_output_dir = tmp_path / "custom_build_out"
    
    out, err, exit_code = run_hpy_cli(capsys, "build", str(src_dir), "-o", str(custom_output_dir))
    
    assert exit_code == 0, f"hpy build with specific src/out failed. Error: {err}"
    assert (custom_output_dir / "index.html").exists()
    assert "Build successful" in out

def test_cli_build_single_file(tmp_path, capsys):
    # Create a single app.hpy file
    app_hpy = tmp_path / "app.hpy"
    app_hpy.write_text("<html><body>Single Page Test</body></html><style>p{color:blue}</style><python>print('single')</python>")
    custom_output_dir = tmp_path / "single_out"
    
    out, err, exit_code = run_hpy_cli(capsys, "build", str(app_hpy), "-o", str(custom_output_dir))

    assert exit_code == 0, f"hpy build single file failed. Error: {err}"
    assert (custom_output_dir / "app.html").exists()
    assert "Build successful" in out

# --- Tests for `hpy serve` and `hpy watch` (more complex, might need mocking for server/watcher threads) ---
# For now, let's test if they attempt to start, relying on previous tests for build correctness.

@mock.patch('hpy_core.serving.start_dev_server') # Mock to prevent actual server start
@mock.patch('hpy_core.cli._perform_initial_build_for_serve_watch') # Mock initial build
def test_cli_serve_starts(mock_build, mock_server, basic_project, capsys):
    project_path = basic_project
    mock_build.return_value = (project_path / DEFAULT_INPUT_DIR, project_path / DEFAULT_OUTPUT_DIR, 0) # input_path, output_path, errors

    original_cwd = os.getcwd()
    os.chdir(project_path)
    try:
        out, err, exit_code = run_hpy_cli(capsys, "serve", "-p", "8088")
    finally:
        os.chdir(original_cwd)

    assert exit_code is None or exit_code == 0 # Server start might be interrupted by test end
    mock_build.assert_called_once()
    mock_server.assert_called_once()
    assert str(project_path / DEFAULT_OUTPUT_DIR) in str(mock_server.call_args[0][0]) # Check serve dir
    assert mock_server.call_args[0][1] == 8088 # Check port

@mock.patch('hpy_core.serving.start_dev_server')
@mock.patch('hpy_core.watching.start_watching')
@mock.patch('hpy_core.cli._perform_initial_build_for_serve_watch')
def test_cli_watch_starts(mock_build, mock_watcher, mock_server, basic_project, capsys):
    project_path = basic_project
    input_p = project_path / DEFAULT_INPUT_DIR
    output_p = project_path / DEFAULT_OUTPUT_DIR
    mock_build.return_value = (input_p, output_p, 0)

    original_cwd = os.getcwd()
    os.chdir(project_path)
    try:
        out, err, exit_code = run_hpy_cli(capsys, "watch", "-p", "8099", "-v")
    finally:
        os.chdir(original_cwd)
        
    assert exit_code is None or exit_code == 0
    mock_build.assert_called_once()
    # Check that is_watch_mode_build was True for the initial build
    assert mock_build.call_args[0][2] == True # common_args.verbose
    assert mock_build.call_args[0][3] == True # is_watch_mode_build
    
    mock_watcher.assert_called_once()
    assert str(input_p) == mock_watcher.call_args[0][0] # Watch source
    
    mock_server.assert_called_once()
    assert str(output_p) == mock_server.call_args[0][0] # Serve dir
    assert mock_server.call_args[0][1] == 8099 # Port

# --- Tests for Deprecated Commands ---
@mock.patch('hpy_core.cli.handle_init_command') # Mock the actual handler
def test_cli_deprecated_init(mock_handler, tmp_path, capsys):
    project_dir = tmp_path / "old_init"
    out, err, exit_code = run_hpy_cli(capsys, "--init-old", str(project_dir)) # Using the distinct dest
    
    assert exit_code == 0
    assert "deprecated" in err.lower() # Check for deprecation warning in stderr
    assert "hpy init DIR" in err
    mock_handler.assert_called_once()
    assert mock_handler.call_args[0][0].project_directory == str(project_dir)

@mock.patch('hpy_core.cli.handle_watch_command')
def test_cli_deprecated_watch(mock_handler, tmp_path, capsys):
    # Setup a dummy source file for the watch command to find if it tries
    src_dir = tmp_path / DEFAULT_INPUT_DIR
    src_dir.mkdir()
    (src_dir / "index.hpy").write_text("<html></html>")

    out, err, exit_code = run_hpy_cli(capsys, "-w", "-p", "7000", str(src_dir)) # Old style with source
    
    assert exit_code is None or exit_code == 0 # Watch involves server, might not exit cleanly in test
    assert "deprecated" in err.lower()
    assert "hpy watch" in err
    mock_handler.assert_called_once()
    # Check that mapped args are reasonable
    assert mock_handler.call_args[0][0].source_to_watch == str(src_dir)
    assert mock_handler.call_args[0][0].port == 7000

@mock.patch('hpy_core.cli.handle_build_command')
def test_cli_deprecated_implicit_build(mock_handler, tmp_path, capsys):
    src_file = tmp_path / "app.hpy"
    src_file.write_text("<html></html>")
    
    out, err, exit_code = run_hpy_cli(capsys, str(src_file)) # e.g. hpy app.hpy
    
    assert exit_code == 0
    assert "deprecated" in err.lower()
    assert "hpy build" in err
    mock_handler.assert_called_once()
    assert mock_handler.call_args[0][0].source == str(src_file)

# More deprecated tests:
# - hpy -s (old serve)
# - hpy [SOURCE] -o [OUTPUT_DIR_OLD] (old build with output)
# - hpy -w -o [OUTPUT_DIR_OLD]
# - hpy (no args, should print help for new structure)

def test_cli_no_args_prints_help(capsys):
    out, err, exit_code = run_hpy_cli(capsys)
    assert exit_code == 0 # Main help prints and exits 0
    assert "Available Commands" in out
    assert "hpy <command> --help" in out

def test_cli_verbose_global_flag(tmp_path, capsys):
    # Test if global -v is picked up by a subcommand
    project_name = "test_verbose_init"
    project_dir = tmp_path / project_name
    
    # Run 'hpy -v init <dir>'
    original_argv = sys.argv
    sys.argv = ['hpy', '-v', 'init', str(project_dir)]
    exit_code = None
    try:
        hpy_main()
    except SystemExit as e:
        exit_code = e.code
    finally:
        sys.argv = original_argv
    
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DEBUG: Executing 'init'" in captured.out # Check for debug print from handler