import asyncio
import os
import shutil
import subprocess
import typer
from typing import Optional, List, Set
from rich.console import Console
from rich.table import Table

import sys
import yaml
from ..adapters.backend import Window
from ..config.schema import ProfileConfig, AppConfig, WindowMatchRule
from ..launcher.async_launcher import AsyncAppLauncher
from ..window_manager.matcher import WindowMatcher
from ..retry_engine.poll import RetryEngine
from ..persistence.session import SessionManager
from ..adapters.cosmic import COSMICWindowBackend
from ..adapters.mock import MockWindowBackend
from ..utils.validation import check_command_exists

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
        # Get active monitors/workspaces to warn about missing outputs
        try:
            workspaces = await backend.get_workspaces()
            connected_monitors = {ws.output for ws in workspaces if ws.output}
        except Exception:
            connected_monitors = set()

        if cfg.monitors and connected_monitors:
            for mon in cfg.monitors:
                if mon.output not in connected_monitors:
                    console.print(
                        f"[bold yellow]⚠ Warning: Configured monitor '{mon.output}' is not currently connected.[/bold yellow] "
                        f"Workspaces routed to it will fall back to active displays."
                    )

        current_windows = await backend.list_windows()
        initial_workspace = next(
            (win.workspace for win in current_windows if win.is_active and win.workspace > 0),
            None,
        )
        claimed_window_ids: Set[str] = set()

        apps_to_launch_configs = []
        apps_to_reuse = []

        for app_cfg in cfg.apps:
            existing_window = _find_existing_window_for_app(
                app_cfg,
                current_windows,
                matcher,
                claimed_window_ids,
            )
            if existing_window is not None:
                claimed_window_ids.add(existing_window.id)
                apps_to_reuse.append((app_cfg, existing_window))
            else:
                apps_to_launch_configs.append(app_cfg)

        missing_apps = []
        for app_cfg in apps_to_launch_configs:
            if not check_command_exists(app_cfg.command):
                missing_apps.append(app_cfg)

        apps_to_skip = []
        final_apps_to_launch = []

        if missing_apps:
            is_interactive = sys.stdin.isatty() and not dry_run
            if is_interactive:
                console.print("\n[bold yellow]⚠ Missing application(s) detected in this profile:[/bold yellow]")
                for app_cfg in missing_apps:
                    console.print(f"  • [cyan]{app_cfg.command}[/cyan] (target Workspace {app_cfg.workspace})")
                
                console.print("\n[bold]Choose an action:[/bold]")
                console.print("  [s] Skip launching these apps (recommended to avoid 30s timeout)")
                console.print("  [e] Edit configuration to update or remove these apps permanently")
                console.print("  [c] Continue anyway")
                
                action = typer.prompt("Select action", default="s", show_choices=True).lower().strip()
                
                if action == "e":
                    config_changed = False
                    apps_to_remove = []
                    for app_cfg in missing_apps:
                        console.print(f"\n[bold]App Config: [cyan]'{app_cfg.command}'[/cyan] (Workspace {app_cfg.workspace})[/bold]")
                        choice = typer.prompt(
                            "Action (s: skip, r: remove permanently, c: change command)",
                            default="s",
                            show_choices=True
                        ).lower().strip()
                        
                        if choice == "r":
                            apps_to_remove.append(app_cfg)
                            config_changed = True
                            console.print("[green]✔ Marked for permanent removal.[/green]")
                        elif choice == "c":
                            while True:
                                new_cmd = typer.prompt("Enter new launch command (or press Enter to cancel)")
                                if not new_cmd:
                                    break
                                if check_command_exists(new_cmd):
                                    app_cfg.command = new_cmd
                                    config_changed = True
                                    console.print(f"[green]✔ Command updated to: '{new_cmd}'[/green]")
                                    
                                    # Optionally update app_id in match rule
                                    if app_cfg.match and app_cfg.match.app_id:
                                        update_match = typer.confirm(
                                            f"Update matching class/app_id rule? (current: '{app_cfg.match.app_id}')",
                                            default=True
                                        )
                                        if update_match:
                                            from ..utils.validation import parse_executable
                                            new_exec = parse_executable(new_cmd)
                                            if new_exec:
                                                app_cfg.match.app_id = new_exec
                                                console.print(f"[green]✔ Match rule app_id updated to: '{new_exec}'[/green]")
                                    break
                                else:
                                    console.print("[red]✗ That executable still does not exist on your system. Please try again.[/red]")
                    
                    # Apply permanent removals
                    for app_cfg in apps_to_remove:
                        if app_cfg in cfg.apps:
                            cfg.apps.remove(app_cfg)
                        if app_cfg in apps_to_launch_configs:
                            apps_to_launch_configs.remove(app_cfg)
                    
                    # Write back if changed
                    if config_changed:
                        try:
                            with open(path, "w") as f:
                                yaml.dump(cfg.model_dump(by_alias=True, exclude_none=True), f, sort_keys=False)
                            console.print(f"[bold green]✔ Successfully updated profile config: {path}[/bold green]")
                        except Exception as e:
                            console.print(f"[bold red]✘ Failed to write updated config: {str(e)}[/bold red]")
                    
                    # Re-evaluate which apps to launch/skip after editing
                    for app_cfg in apps_to_launch_configs:
                        if not check_command_exists(app_cfg.command):
                            apps_to_skip.append(app_cfg)
                        else:
                            final_apps_to_launch.append(app_cfg)
                
                elif action == "c":
                    apps_to_skip = []
                    final_apps_to_launch = apps_to_launch_configs
                else: # "s" or empty
                    apps_to_skip = missing_apps
                    final_apps_to_launch = [a for a in apps_to_launch_configs if a not in missing_apps]
            
            else:
                # Non-interactive mode (Autostart / script)
                for app_cfg in missing_apps:
                    console.print(
                        f"[bold yellow]⚠ Warning: Missing application '{app_cfg.command}' (workspace {app_cfg.workspace}) "
                        f"is not installed/executable. Automatically skipping to prevent system hang.[/bold yellow]"
                    )
                apps_to_skip = missing_apps
                final_apps_to_launch = [a for a in apps_to_launch_configs if a not in missing_apps]
        else:
            apps_to_skip = []
            final_apps_to_launch = apps_to_launch_configs

        # Process reusing windows
        for app_cfg, existing_window in apps_to_reuse:
            console.log(
                f"[dim]Reusing existing window: {existing_window.title or existing_window.app_id} "
                f"(app_id: {existing_window.app_id})[/dim]"
            )

        # Launch verified new apps
        for app_cfg in final_apps_to_launch:
            await launcher.launch(app_cfg.command)

        # Only arrange apps that weren't skipped
        apps_to_arrange = [app for app in cfg.apps if app not in apps_to_skip]
        await engine.arrange_windows(apps_to_arrange)

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
