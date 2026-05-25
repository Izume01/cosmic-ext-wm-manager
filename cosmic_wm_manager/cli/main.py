import asyncio
import os
import shutil
import subprocess
import typer
from typing import Optional, List, Set
from rich.console import Console
from rich.table import Table

from ..adapters.backend import Window
from ..config.schema import ProfileConfig, AppConfig, WindowMatchRule
from ..launcher.async_launcher import AsyncAppLauncher
from ..window_manager.matcher import WindowMatcher
from ..retry_engine.poll import RetryEngine
from ..persistence.session import SessionManager
from ..adapters.cosmic import COSMICWindowBackend
from ..adapters.mock import MockWindowBackend

app = typer.Typer(help="Wayland-native session restore and workspace automation for COSMIC Desktop", add_completion=False)
console = Console()

def get_backend(dry_run: bool):
    """Returns the requested window manager integration backend."""
    if dry_run:
        return MockWindowBackend(console)
    return COSMICWindowBackend(console)


def _find_existing_window_for_app(
    app_cfg: AppConfig,
    windows: List[Window],
    matcher: WindowMatcher,
    claimed_window_ids: Set[str],
) -> Optional[Window]:
    """Find an already-open window that satisfies this app config."""
    if not app_cfg.match:
        return None

    strict_matches = [
        win
        for win in windows
        if win.id not in claimed_window_ids and matcher.matches(win, app_cfg.match)
    ]
    if strict_matches:
        return strict_matches[0]

    if not app_cfg.match.app_id or not app_cfg.match.title:
        return None

    relaxed_rule = WindowMatchRule(app_id=app_cfg.match.app_id)
    relaxed_matches = [
        win
        for win in windows
        if win.id not in claimed_window_ids and matcher.matches(win, relaxed_rule)
    ]
    if len(relaxed_matches) == 1:
        return relaxed_matches[0]

    return None

def _start_profile(path: str, dry_run: bool, timeout: float, debug: bool):
    """Core logic to run workspace profile activation."""
    try:
        cfg = ProfileConfig.load_from_yaml(path)
    except Exception as e:
        console.print(f"[bold red]✘ Schema validation failed: {str(e)}[/bold red]")
        raise typer.Exit(1)

    console.print(f"[bold green]🚀 Launching profile: '{cfg.name}'...[/bold green]")
    if cfg.description:
        console.print(f"[dim]{cfg.description}[/dim]")

    workspace_routes = {}
    if cfg.monitors:
        for w_idx in range(1, 20):
            workspace_routes[w_idx] = cfg.resolve_workspace_output(w_idx)

    backend = get_backend(dry_run)
    launcher = AsyncAppLauncher(console)
    matcher = WindowMatcher(console)
    engine = RetryEngine(backend, matcher, console, timeout=timeout, workspace_routes=workspace_routes)

    async def _run():
        current_windows = await backend.list_windows()
        initial_workspace = next(
            (win.workspace for win in current_windows if win.is_active and win.workspace > 0),
            None,
        )
        claimed_window_ids: Set[str] = set()

        for app_cfg in cfg.apps:
            existing_window = _find_existing_window_for_app(
                app_cfg,
                current_windows,
                matcher,
                claimed_window_ids,
            )
            if existing_window is not None:
                claimed_window_ids.add(existing_window.id)
                console.log(
                    f"[dim]Reusing existing window: {existing_window.title or existing_window.app_id} "
                    f"(app_id: {existing_window.app_id})[/dim]"
                )
                continue
            await launcher.launch(app_cfg.command)

        await engine.arrange_windows(cfg.apps)

        if initial_workspace is not None:
            await backend.switch_workspace(initial_workspace)

    asyncio.run(_run())

@app.command()
def start(
    profile: str = typer.Argument(..., help="Name of profile in profiles/ or full path to YAML file"),
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Print actions instead of executing them"),
    timeout: float = typer.Option(30.0, "--timeout", "-t", help="Timeout for window placement engine (seconds)"),
    debug: bool = typer.Option(False, "--debug", help="Enable verbose debug printing")
):
    """Launches application profile and organizes windows onto workspaces."""
    if os.path.exists(profile):
        path = profile
    else:
        path = os.path.expanduser(f"~/.config/cosmic-wm-manager/profiles/{profile}.yaml")
        if not os.path.exists(path):
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "profiles", f"{profile}.yaml")
            if not os.path.exists(path):
                console.print(f"[bold red]✘ Profile not found: {profile}[/bold red]")
                raise typer.Exit(1)

    _start_profile(path, dry_run, timeout, debug)

@app.command()
def save(
    name: str = typer.Argument("default", help="Name of the session snapshot to save")
):
    """Takes a snapshot of currently open apps and window layouts."""
    backend = get_backend(False)
    manager = SessionManager(backend, console)
    asyncio.run(manager.save_session(name))

@app.command()
def restore(
    name: str = typer.Argument("default", help="Name of the session snapshot to restore"),
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Simulate restoration"),
    timeout: float = typer.Option(30.0, "--timeout", "-t", help="Timeout for window placement engine (seconds)"),
    debug: bool = typer.Option(False, "--debug", help="Enable verbose debug printing")
):
    """Restores a previously captured session layout snapshot."""
    backend = get_backend(dry_run)
    manager = SessionManager(backend, console)
    path = manager.get_session_path(name)
    if not os.path.exists(path):
        console.print(f"[bold red]✘ Saved session '{name}' not found at {path}[/bold red]")
        raise typer.Exit(1)

    console.print(f"[bold green]🔄 Restoring session snapshot '{name}'...[/bold green]")
    _start_profile(path, dry_run, timeout, debug)

@app.command()
def status():
    """Lists current workspaces, screens, and application windows."""
    backend = get_backend(False)

    async def _run():
        windows = await backend.list_windows()
        workspaces = await backend.get_workspaces()

        table = Table(title="Active COSMIC Applications")
        table.add_column("Index", style="dim")
        table.add_column("App ID", style="cyan")
        table.add_column("Window Title", style="green")
        table.add_column("Workspace", style="magenta", justify="center")
        table.add_column("Focused", justify="center")

        for win in windows:
            table.add_row(
                win.id,
                win.app_id,
                win.title[:40] + ("..." if len(win.title) > 40 else ""),
                str(win.workspace),
                "[bold green]●[/bold green]" if win.is_active else "[dim]○[/dim]"
            )
        console.print(table)
        console.print(f"\n[dim]Total workspaces active: {len(workspaces)}[/dim]")

    asyncio.run(_run())

@app.command()
def autostart(
    enable: bool = typer.Option(None, "--enable", help="Enable auto-session restore on login"),
    disable: bool = typer.Option(None, "--disable", help="Disable auto-session restore on login")
):
    """Configures session autostart for the COSMIC Desktop environment."""
    autostart_dir = os.path.expanduser("~/.config/autostart")
    os.makedirs(autostart_dir, exist_ok=True)
    filepath = os.path.join(autostart_dir, "cosmic-wm-manager.desktop")

    if enable:
        content = """[Desktop Entry]
Type=Application
Name=cosmic-session-manager
Comment=Restore saved COSMIC sessions and workspace layouts
Exec=cosmic-wm restore default
Icon=system-run
Terminal=false
StartupNotify=false
Categories=Utility;
"""
        with open(filepath, "w") as f:
            f.write(content)
        console.print("[green]✔ Autostart successfully enabled. 'default' session will restore at login.[/green]")
    elif disable:
        if os.path.exists(filepath):
            os.remove(filepath)
            console.print("[green]✔ Autostart successfully disabled.[/green]")
        else:
            console.print("[yellow]⚠ Autostart was not enabled.[/yellow]")
    else:
        console.print("[yellow]Please specify either --enable or --disable.[/yellow]")

@app.command()
def update():
    """Recompiles the native Rust helper to guarantee resilience against COSMIC desktop updates."""
    console.print("[blue]🔄 Pulling and recompiling cos-cli from git main...[/blue]")
    try:
        res = subprocess.run(["cargo", "install", "--git", "https://github.com/estin/cos-cli"], check=True)
        if res.returncode == 0:
            console.print("[bold green]✔ Successfully compiled and updated Wayland helper binary![/bold green]")
        else:
            console.print("[bold red]✘ Failed compiling helper binary.[/bold red]")
    except Exception as e:
        console.print(f"[bold red]✘ Build failed: {str(e)}[/bold red]")

if __name__ == "__main__":
    app()
