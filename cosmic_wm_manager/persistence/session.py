import os
import re
import yaml
import psutil
from collections import Counter
from typing import List, Optional, Dict, Any
from rich.console import Console
from ..adapters.backend import WindowBackend, Window
from ..config.schema import ProfileConfig, AppConfig, WindowMatchRule

class SessionManager:
    """
    Handles capturing, serialization, and restoration of workspace environments.
    Translates currently active windows into standard YAML profile configs.
    """

    def __init__(self, backend: WindowBackend, console: Optional[Console] = None):
        self.backend = backend
        self.console = console or Console()
        self.sessions_dir = os.path.expanduser("~/.config/cosmic-wm-manager/sessions")
        os.makedirs(self.sessions_dir, exist_ok=True)

    def _find_command_from_desktop_file(self, app_id: str) -> Optional[str]:
        """
        Scans .desktop launchers for StartupWMClass matching app_id and returns the Exec path.
        """
        search_dirs = [
            os.path.expanduser("~/.local/share/applications"),
            "/usr/share/applications"
        ]
        for s_dir in search_dirs:
            if not os.path.exists(s_dir):
                continue
            try:
                for filename in os.listdir(s_dir):
                    if not filename.endswith(".desktop"):
                        continue
                    filepath = os.path.join(s_dir, filename)
                    try:
                        with open(filepath, "r", errors="ignore") as f:
                            content = f.read()
                        
                        has_matching_class = False
                        
                        # 1. Match StartupWMClass
                        for line in content.splitlines():
                            if line.startswith("StartupWMClass="):
                                wm_class = line.split("=", 1)[1].strip()
                                if wm_class.lower() == app_id.lower():
                                    has_matching_class = True
                                    break
                        
                        # 2. Match App filename directly
                        if not has_matching_class and filename.lower() == f"{app_id.lower()}.desktop":
                            has_matching_class = True
                            
                        if has_matching_class:
                            for line in content.splitlines():
                                if line.startswith("Exec="):
                                    exec_val = line.split("=", 1)[1].strip()
                                    # Strip arguments like %U, %F, %f, %u
                                    exec_val = re.sub(r'\s+%\w', '', exec_val)
                                    return exec_val
                    except Exception:
                        continue
            except Exception:
                continue
        return None

    def _resolve_process_cmd(self, app_id: str, title: str) -> str:
        """
        Attempts to scan active system processes to reconstruct the launch command
        corresponding to a window's app_id or title. Fallbacks to app_id.
        """
        if not app_id:
            return ""

        # 1. Common Sandbox & Class overrides (e.g. Flatpaks, special executables)
        clean_app_id = app_id.lower()
        if "zen" in clean_app_id:
            return "flatpak run app.zen_browser.zen"
        if "youtube_music" in clean_app_id or "youtube-music" in clean_app_id:
            return '"/opt/YouTube Music/youtube-music"'
        if "discord" in clean_app_id:
            return "flatpak run com.discordapp.Discord"
        if "code" in clean_app_id:
            return "code"
        if "kitty" in clean_app_id:
            return "kitty"
        if "alacritty" in clean_app_id:
            return "alacritty"

        # 2. Check installed desktop launchers for matched Exec commands
        desktop_cmd = self._find_command_from_desktop_file(app_id)
        if desktop_cmd:
            return desktop_cmd

        # 3. Check for Flatpak ID pattern
        if "." in app_id and not app_id.endswith(".exe"):
            # Check if this is a standard reverse-dns flatpak application
            return f"flatpak run {app_id}"

        # 4. Search psutil process tree as a fallback
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                p_name = (proc.info["name"] or "").lower()
                cmdline = proc.info["cmdline"]
                if not cmdline:
                    continue

                if clean_app_id in p_name or any(clean_app_id in str(arg).lower() for arg in cmdline):
                    # Do not capture internal flatpak sandbox paths directly
                    if "/app/" in cmdline[0]:
                        continue
                    return " ".join(cmdline)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Fallback to direct app_id
        return app_id

    async def save_session(self, session_name: str) -> Optional[str]:
        """
        Inspects running application windows and writes a snapshot YAML profile.
        Returns the path to the saved session file if successful.
        """
        self.console.log("[blue]💾 Saving active session snapshot...[/blue]")
        
        try:
            windows = await self.backend.list_windows()
            if not windows:
                self.console.log("[yellow]⚠ No active application windows detected. Nothing to save.[/yellow]")
                return None

            app_id_counts = Counter(
                win.app_id
                for win in windows
                if win.app_id and not win.app_id.startswith("cosmic-")
            )
            apps_config = []
            for win in windows:
                # Filter out system panels, status docks or empty IDs
                if not win.app_id or win.app_id.startswith("cosmic-"):
                    continue

                cmd = self._resolve_process_cmd(win.app_id, win.title)
                if not cmd:
                    continue

                apps_config.append(AppConfig(
                    command=cmd,
                    workspace=win.workspace,
                    match=WindowMatchRule(
                        app_id=win.app_id,
                        title=win.title[:30] if win.title and app_id_counts[win.app_id] > 1 else None
                    )
                ))

            if not apps_config:
                self.console.log("[yellow]⚠ No saveable applications identified.[/yellow]")
                return None

            # Build Profile Config
            profile = ProfileConfig(
                name=session_name,
                description=f"Snapshot captured dynamically on user request",
                apps=apps_config
            )

            # Save to disk
            filepath = os.path.join(self.sessions_dir, f"{session_name}.yaml")
            with open(filepath, "w") as f:
                yaml.dump(profile.model_dump(by_alias=True, exclude_none=True), f, sort_keys=False)

            self.console.log(f"[green]✔ Saved session profile to [bold]{filepath}[/bold][/green]")
            return filepath

        except Exception as e:
            self.console.log(f"[bold red]Failed to capture session: {str(e)}[/bold red]")
            return None

    def get_session_path(self, session_name: str) -> str:
        """Returns the file path of a saved session."""
        return os.path.join(self.sessions_dir, f"{session_name}.yaml")
