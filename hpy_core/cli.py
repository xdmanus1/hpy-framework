# hpy_core/cli.py
"""Command-line interface for HPY Tool, using Typer."""

import sys
import time
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import threading
import os
import warnings

import typer
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated


from .config import __version__, load_config, find_project_root, CONFIG_FILENAME
from .config import (
    DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR, DEFAULT_STATIC_DIR_NAME,
    APP_SHELL_FILENAME, DEFAULT_DEV_OUTPUT_DIR_NAME # Added DEFAULT_DEV_OUTPUT_DIR_NAME
)
from .init import init_project as actual_init_project
from .building import compile_directory, compile_hpy_file
from .watching import start_watching, WATCHFILES_AVAILABLE
from .serving import start_dev_server

app = typer.Typer(
    name="hpy",
    help="HPY Tool: Build, serve, and watch .hpy projects with Brython.",
    add_completion=False,
    no_args_is_help=True
)

class GlobalContext:
    def __init__(self, verbose: bool):
        self.verbose = verbose

def _version_callback(value: bool):
    if value:
        typer.echo(f"hpy-tool version {__version__}")
        raise typer.Exit()

@app.callback()
def common_options(
    ctx: typer.Context,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Enable detailed verbose output.")] = False,
    version: Annotated[Optional[bool], typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version and exit.")] = None,
):
    ctx.obj = GlobalContext(verbose=verbose)

def issue_deprecation_warning(old_usage: str, new_usage: str, version_to_remove: str = "2.0.0"):
    # ... (implementation as before) ...
    message = (
        f"Usage '{old_usage}' is deprecated. Please use '{new_usage}'. "
        f"Old style commands will be removed in v{version_to_remove}."
    )
    try:
        from rich.console import Console; console = Console(stderr=True); console.print(f"[yellow]DEPRECATION WARNING:[/yellow] {message}")
    except ImportError: warnings.warn(message, DeprecationWarning, stacklevel=3)


def resolve_project_and_config(
    source_or_context_arg: Optional[str], # Can be source file/dir, or None to use CWD for context
    verbose: bool = False
) -> Tuple[Optional[Path], Dict[str, Any], Path]: # project_root, config, effective_search_start
    project_root_res: Optional[Path] = None
    config_res: Dict[str, Any] = {}
    
    start_search_path = Path.cwd() # Default context is CWD
    if source_or_context_arg:
        potential_path = Path(source_or_context_arg)
        if potential_path.exists(): # If it exists, it defines the context
            start_search_path = potential_path.parent if potential_path.is_file() else potential_path
        # If it doesn't exist (e.g. source for build command that might be a default),
        # find_project_root will search from CWD.
    
    if verbose: print(f"DEBUG: resolve_project_and_config: Project root search context: {start_search_path}")
    project_root_res = find_project_root(start_search_path)
    if project_root_res:
        if verbose: print(f"DEBUG: resolve_project_and_config: Found project root: {project_root_res}")
        config_res = load_config(project_root_res)
    elif verbose: print(f"DEBUG: resolve_project_and_config: No project root found from {start_search_path}.")
    
    return project_root_res, config_res, start_search_path

@app.command("init")
def init_command(
    ctx: typer.Context,
    project_directory: Annotated[Path, typer.Argument(help="Directory to create the project in.", resolve_path=False, path_type=Path, file_okay=False, dir_okay=True, writable=True)]
):
    common_ctx: GlobalContext = ctx.obj
    if common_ctx.verbose: typer.echo(f"DEBUG: Executing 'init' for project '{project_directory}'")
    actual_init_project(str(project_directory.resolve()))

@app.command("build")
def build_command(
    ctx: typer.Context,
    source: Annotated[Optional[Path], typer.Argument(help=f"Source .hpy file or directory (default from hpy.toml or '{DEFAULT_INPUT_DIR}').", resolve_path=False, exists=False, show_default=False)] = None,
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help=f"Output directory (default varies by mode; see below).", resolve_path=False, show_default=False)] = None,
    production: Annotated[bool, typer.Option(help="Create a production-optimized build (outputs to 'output_dir' or 'dist/').")] = False
):
    common_ctx: GlobalContext = ctx.obj
    if common_ctx.verbose: typer.echo(f"DEBUG: Executing 'build'. Source: '{source}', Output: '{output}', Production: {production}")

    project_root_build, config_build, search_context = resolve_project_and_config(str(source) if source else None, common_ctx.verbose)
    
    final_input_src_str = str(source) if source else config_build.get("input_dir", DEFAULT_INPUT_DIR)
    input_path_build = Path(final_input_src_str).resolve()

    # Determine output directory based on production flag and config
    final_output_dir_path: Path
    if output: # CLI -o always overrides config
        final_output_dir_path = Path(str(output)).resolve()
    elif production:
        prod_out_str = config_build.get("output_dir", DEFAULT_OUTPUT_DIR)
        final_output_dir_path = (project_root_build / prod_out_str if project_root_build and not Path(prod_out_str).is_absolute() else Path(prod_out_str)).resolve()
    else: # Development build (not --production)
        if "dev_output_dir" in config_build:
            dev_out_str = config_build["dev_output_dir"]
            final_output_dir_path = (project_root_build / dev_out_str if project_root_build and not Path(dev_out_str).is_absolute() else Path(dev_out_str)).resolve()
        else:
            base_for_default_dev = project_root_build if project_root_build else Path.cwd() # Fallback to CWD if no project root
            final_output_dir_path = (base_for_default_dev / DEFAULT_DEV_OUTPUT_DIR_NAME).resolve()
            
    output_dir_path_build = final_output_dir_path

    is_directory_input_build = input_path_build.is_dir(); is_file_input_build = input_path_build.is_file()
    if not input_path_build.exists(): typer.secho(f"Error: Build input source '{input_path_build}' not found.", fg=typer.colors.RED, err=True); raise typer.Exit(code=1)
    if is_file_input_build and input_path_build.suffix.lower() != ".hpy": typer.secho(f"Error: Build input file '{input_path_build}' must be .hpy.", fg=typer.colors.RED, err=True); raise typer.Exit(code=1)
    if is_directory_input_build:
        try:
            if output_dir_path_build.is_relative_to(input_path_build): typer.secho(f"Error: Output dir '{output_dir_path_build}' cannot be inside input dir '{input_path_build}'.", fg=typer.colors.RED, err=True); raise typer.Exit(code=1)
        except AttributeError: 
            if str(output_dir_path_build).startswith(str(input_path_build) + os.sep): typer.secho(f"Error: Output dir '{output_dir_path_build}' cannot be inside input dir '{input_path_build}'.", fg=typer.colors.RED, err=True); raise typer.Exit(code=1)

    typer.echo(f"--- Starting Build ({'Production' if production else 'Development'}) ---")
    typer.echo(f"Source: '{input_path_build}'"); typer.echo(f"Output: '{output_dir_path_build}'")
    if project_root_build: typer.echo(f"Config: Using '{CONFIG_FILENAME}' from '{project_root_build}'")
    else: typer.echo(f"Config: No '{CONFIG_FILENAME}' found, using defaults.")
    error_count_build = 0
    try:
        if is_directory_input_build:
            _, error_count_build = compile_directory(str(input_path_build), str(output_dir_path_build), common_ctx.verbose, is_dev_watch_mode=False, is_production_build=production)
        else: 
            app_shell_content: Optional[str] = None; sp_parent = input_path_build.parent
            paths_to_check = [sp_parent / APP_SHELL_FILENAME, sp_parent / DEFAULT_INPUT_DIR / APP_SHELL_FILENAME] # Check local then parent's src
            used_app_shell_path : Optional[Path] = None
            for p_path in paths_to_check:
                if p_path.is_file():
                    try: app_shell_content = p_path.read_text(encoding='utf-8'); used_app_shell_path = p_path; break 
                    except IOError:
                        if common_ctx.verbose: typer.secho(f"Warning: Could not read App Shell at '{p_path.resolve()}'.", fg=typer.colors.YELLOW, err=True)
            if used_app_shell_path and common_ctx.verbose: typer.echo(f"Using App Shell '{used_app_shell_path.resolve()}' for single file build.")
            elif not app_shell_content and common_ctx.verbose: typer.echo(f"No App Shell found for single file '{input_path_build.name}'.")
            compile_hpy_file(str(input_path_build), str(output_dir_path_build / input_path_build.with_suffix(".html").name), app_shell_template=app_shell_content, layout_parsed_data=None, external_script_src=None, verbose=common_ctx.verbose, is_dev_watch_mode=False, is_production_build=production)
    except Exception as e:
        typer.secho(f"Build failed: {e}", fg=typer.colors.RED, err=True)
        if common_ctx.verbose: traceback.print_exc()
        raise typer.Exit(code=1)
    if error_count_build == 0: typer.secho(f"\nBuild successful. Output in '{output_dir_path_build}'.", fg=typer.colors.GREEN)
    else: typer.secho(f"\nBuild finished with {error_count_build} errors.", fg=typer.colors.RED, err=True); raise typer.Exit(code=1)

def _perform_initial_build_for_serve_watch_typer( # CLI args passed directly
    source_arg_cli: Optional[Path], 
    output_arg_cli: Optional[Path], 
    common_ctx: GlobalContext, 
    is_watch_mode_build: bool
) -> Tuple[Path, Path, int]: # input_path, actual_output_dir_for_dev, error_count
    
    project_root_sw, config_sw, search_context = resolve_project_and_config(str(source_arg_cli) if source_arg_cli else None, verbose=common_ctx.verbose)

    final_input_src_str = str(source_arg_cli) if source_arg_cli else config_sw.get("input_dir", DEFAULT_INPUT_DIR)
    input_path_sw = Path(final_input_src_str).resolve()

    # Determine output path for dev/watch
    dev_output_dir_path_actual: Path
    if output_arg_cli: # CLI -o given to serve/watch overrides all
        dev_output_dir_path_actual = Path(str(output_arg_cli)).resolve()
    elif "dev_output_dir" in config_sw:
        dev_out_config = Path(config_sw["dev_output_dir"])
        if not dev_out_config.is_absolute() and project_root_sw:
            dev_output_dir_path_actual = (project_root_sw / dev_out_config).resolve()
        else: # Absolute or no project root (resolve from CWD implicitly)
            dev_output_dir_path_actual = dev_out_config.resolve()
    else: # Default dev output dir, relative to project root if found, else CWD
        base_for_default_dev_out = project_root_sw if project_root_sw else Path.cwd()
        dev_output_dir_path_actual = (base_for_default_dev_out / DEFAULT_DEV_OUTPUT_DIR_NAME).resolve()
            
    output_dir_path_sw = dev_output_dir_path_actual

    is_dir_input = input_path_sw.is_dir(); is_file_input = input_path_sw.is_file()
    if not input_path_sw.exists(): typer.secho(f"Error: Input source '{input_path_sw}' not found.", fg=typer.colors.RED, err=True); raise typer.Exit(code=1)
    if is_file_input and input_path_sw.suffix.lower() != ".hpy": typer.secho(f"Error: Input file '{input_path_sw}' must be .hpy.", fg=typer.colors.RED, err=True); raise typer.Exit(code=1)
    
    typer.echo(f"--- Initial Build for {'Watch' if is_watch_mode_build else 'Serve'} (Output: {output_dir_path_sw}) ---")
    typer.echo(f"Source: '{input_path_sw}'")
    if project_root_sw: typer.echo(f"Config: Using '{CONFIG_FILENAME}' from '{project_root_sw}'")
    else: typer.echo(f"Config: No '{CONFIG_FILENAME}' found, using defaults.")

    error_count_sw = 0
    try:
        if is_dir_input:
            _, error_count_sw = compile_directory(str(input_path_sw), str(output_dir_path_sw), common_ctx.verbose,is_dev_watch_mode=is_watch_mode_build, is_production_build=False)
        else:
            app_shell_content_sw: Optional[str] = None; sp_parent_sw = input_path_sw.parent
            paths_to_check_sw = [sp_parent_sw / APP_SHELL_FILENAME, sp_parent_sw / DEFAULT_INPUT_DIR / APP_SHELL_FILENAME]
            used_app_shell_path_sw : Optional[Path] = None
            for p_path_sw in paths_to_check_sw:
                if p_path_sw.is_file():
                    try: app_shell_content_sw = p_path_sw.read_text(encoding='utf-8'); used_app_shell_path_sw = p_path_sw; break
                    except IOError:
                        if common_ctx.verbose: typer.secho(f"Warning: Could not read App Shell at '{p_path_sw.resolve()}'.", fg=typer.colors.YELLOW, err=True)
            if used_app_shell_path_sw and common_ctx.verbose: typer.echo(f"Using App Shell '{used_app_shell_path_sw.resolve()}' for single file.")
            elif not app_shell_content_sw and common_ctx.verbose: typer.echo(f"No App Shell found for single file '{input_path_sw.name}'.")
            compile_hpy_file(str(input_path_sw), str(output_dir_path_sw / input_path_sw.with_suffix(".html").name), app_shell_template=app_shell_content_sw, layout_parsed_data=None, external_script_src=None, verbose=common_ctx.verbose, is_dev_watch_mode=is_watch_mode_build, is_production_build=False)
    except Exception as e: 
        typer.secho(f"Initial build failed: {e}", fg=typer.colors.RED, err=True)
        if common_ctx.verbose: traceback.print_exc()
        raise typer.Exit(code=1)
    if error_count_sw > 0: typer.secho(f"Initial build failed with {error_count_sw} errors. Aborting.", fg=typer.colors.RED, err=True); raise typer.Exit(code=1)
    typer.secho("Initial build successful.", fg=typer.colors.GREEN)
    return input_path_sw, output_dir_path_sw, error_count_sw

@app.command("serve")
def serve_command(
    ctx: typer.Context,
    source_for_build: Annotated[Optional[Path], typer.Argument(help=f"Source to build before serving (default from hpy.toml or '{DEFAULT_INPUT_DIR}').", resolve_path=False, exists=False, show_default=False)] = None,
    output_dir_served: Annotated[Optional[Path], typer.Option("-o", "--output", help=f"Output directory to serve (and build to if not --no-build) (default varies, see notes).", resolve_path=False, show_default=False)] = None,
    port: Annotated[int, typer.Option("-p", "--port", help="Port for the server (default: 8000).")] = 8000,
    no_build: Annotated[bool, typer.Option(help="Serve directly from output directory without building.")] = False
):
    common_ctx: GlobalContext = ctx.obj
    if common_ctx.verbose: typer.echo(f"DEBUG: Executing 'serve'. Source: '{source_for_build}', Output: '{output_dir_served}', Port: {port}, No-Build: {no_build}")
    
    output_to_serve_path: Path
    if not no_build:
        _, output_path_after_build, _ = _perform_initial_build_for_serve_watch_typer(source_for_build, output_dir_served, common_ctx, is_watch_mode_build=False)
        output_to_serve_path = output_path_after_build
    else: 
        # If --no-build, determine output dir to serve: CLI -o > config dev_output_dir > config output_dir > default dev output
        project_r_nb, config_nb, _ = resolve_project_and_config(str(source_for_build) if source_for_build else None, verbose=common_ctx.verbose) # Context for config
        
        if output_dir_served: # CLI -o wins
            output_to_serve_path = Path(str(output_dir_served)).resolve()
        elif "dev_output_dir" in config_nb:
            dev_out_str_nb = config_nb["dev_output_dir"]
            output_to_serve_path = (project_r_nb / dev_out_str_nb if project_r_nb and not Path(dev_out_str_nb).is_absolute() else Path(dev_out_str_nb)).resolve()
        elif "output_dir" in config_nb: # Fallback to main output if dev_output_dir not set
            main_out_str_nb = config_nb["output_dir"]
            output_to_serve_path = (project_r_nb / main_out_str_nb if project_r_nb and not Path(main_out_str_nb).is_absolute() else Path(main_out_str_nb)).resolve()
        else: # Absolute default
            base_for_default = project_r_nb if project_r_nb else Path.cwd()
            output_to_serve_path = (base_for_default / DEFAULT_DEV_OUTPUT_DIR_NAME).resolve()

        if not output_to_serve_path.is_dir(): typer.secho(f"Error: Output directory '{output_to_serve_path}' does not exist and --no-build was specified.", fg=typer.colors.RED, err=True); raise typer.Exit(code=1)
        typer.echo(f"Serving directly from '{output_to_serve_path}' without building (--no-build).")
    
    start_dev_server(str(output_to_serve_path), port, common_ctx.verbose)

@app.command("watch")
def watch_command(
    ctx: typer.Context,
    source_to_watch: Annotated[Optional[Path], typer.Argument(help=f"Source .hpy file or directory to watch (default from hpy.toml or '{DEFAULT_INPUT_DIR}').", resolve_path=False, exists=False, show_default=False)] = None,
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help=f"Output directory (default to dev output dir, see notes).", resolve_path=False, show_default=False)] = None,
    port: Annotated[int, typer.Option("-p", "--port", help="Port for the server (default: 8000).")] = 8000
):
    common_ctx: GlobalContext = ctx.obj
    if common_ctx.verbose: typer.echo(f"DEBUG: Executing 'watch'. Source: '{source_to_watch}', Output: '{output}', Port: {port}")
    if not WATCHFILES_AVAILABLE: typer.secho("Error: 'watch' command requires 'watchfiles'.", fg=typer.colors.RED, err=True); raise typer.Exit(code=1)
    
    input_path, output_dir_path, _ = _perform_initial_build_for_serve_watch_typer(source_to_watch, output, common_ctx, is_watch_mode_build=True)
    is_directory_input = input_path.is_dir()
    input_dir_context = input_path.parent if not is_directory_input else input_path
    
    watcher_thread = threading.Thread(target=start_watching, args=(str(input_path), is_directory_input, str(input_dir_context), str(output_dir_path), common_ctx.verbose), daemon=True)
    watcher_thread.start(); time.sleep(0.3)
    start_dev_server(str(output_dir_path), port, common_ctx.verbose)

def run_deprecated_command_shim(argv: list[str], common_ctx_shim: GlobalContext) -> bool:
    # Simplified shim: only handles --init. Other old styles will show Typer help.
    if "--init" in argv:
        try:
            idx = argv.index("--init")
            if idx + 1 < len(argv) and not argv[idx+1].startswith("-"):
                project_dir_str = argv[idx + 1]
                issue_deprecation_warning("hpy --init DIR", "hpy init DIR")
                # Manually create a context for the Typer command function
                # This is a bit of a hack for Typer; ideally, map to Typer app invocation.
                # For simplicity, we'll just call the underlying logic.
                if common_ctx_shim.verbose: typer.echo(f"DEBUG: Shim: Executing 'init' for project '{project_dir_str}'")
                actual_init_project(project_dir_str) # Call the core logic directly
                return True 
        except ValueError: pass 
        except Exception as e: typer.secho(f"Error processing deprecated --init: {e}", fg=typer.colors.RED, err=True); return True
    return False

def main(): # Script entry point
    try:
        _temp_verbose_for_shim = "-v" in sys.argv or "--verbose" in sys.argv
        _common_ctx_for_shim = GlobalContext(verbose=_temp_verbose_for_shim)
        
        # Check if a non-Typer command (only --init for now) is being attempted first
        # This shim is very basic. More complex old commands will fall through to Typer.
        if len(sys.argv) > 1 and sys.argv[1] not in ['init', 'build', 'serve', 'watch', '--help', '--version'] and \
           (sys.argv[1].startswith('-') and sys.argv[1] not in ['-v', '--verbose']):
            if run_deprecated_command_shim(sys.argv[1:], _common_ctx_for_shim):
                raise typer.Exit(code=0)
        app()
    except typer.Exit as e:
        sys.exit(e.exit_code)
    except SystemExit:
        raise 
    except Exception as e:
        is_verbose_mode = "-v" in sys.argv or "--verbose" in sys.argv
        typer.secho(f"An unexpected critical error occurred in CLI: {e}", fg=typer.colors.RED, err=True)
        if is_verbose_mode:
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()