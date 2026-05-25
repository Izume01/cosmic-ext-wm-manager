import asyncio
from typing import List, Set, Dict, Optional, Tuple
from rich.console import Console
from ..adapters.backend import WindowBackend, Window, Workspace
from ..config.schema import AppConfig
from ..config.schema import WindowMatchRule
from ..window_manager.matcher import WindowMatcher

class RetryEngine:
    """
    Asynchronously monitors running windows and assigns them to their target workspaces.
    Avoids rigid sleeps by polling the window list at high frequency with a timeout.
    """

    def __init__(
        self,
        backend: WindowBackend,
        matcher: WindowMatcher,
        console: Optional[Console] = None,
        poll_interval: float = 0.5,
        timeout: float = 30.0,
        workspace_routes: Optional[Dict[int, Tuple[str, int]]] = None
    ):
        self.backend = backend
        self.matcher = matcher
        self.console = console or Console()
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.workspace_routes = workspace_routes or {}

    @staticmethod
    def _is_transient_window(window: Window) -> bool:
        title = (window.title or "").lower()
        return any(marker in title for marker in ("updater", "loading", "installer", "splash"))

    def _resolve_destination(self, app: AppConfig) -> Tuple[Optional[str], int]:
        route = self.workspace_routes.get(app.workspace)
        if route:
            return route[0], route[1]
        return None, app.workspace

    def _can_attempt_move(self, app: AppConfig, workspaces: List[Workspace]) -> bool:
        output_name, target_workspace = self._resolve_destination(app)
        relevant_workspaces = [
            ws.index
            for ws in workspaces
            if ws.index > 0 and (output_name is None or ws.output == output_name)
        ]
        current_max = max(relevant_workspaces, default=1)
        return target_workspace <= current_max + 1

    def _find_fallback_match(
        self,
        windows: List[Window],
        app: AppConfig,
        placed_indices: Set[str],
    ) -> Optional[Window]:
        """
        If a strict title-based match fails, fall back to a unique app-id-only match.
        This keeps volatile titles like Discord from blocking restores, while avoiding
        ambiguous placements when multiple same-app windows exist.
        """
        if not app.match or not app.match.app_id or not app.match.title:
            return None

        relaxed_rule = WindowMatchRule(app_id=app.match.app_id)
        candidates = [
            win
            for win in windows
            if win.id not in placed_indices and self.matcher.matches(win, relaxed_rule)
            and not self._is_transient_window(win)
        ]
        if len(candidates) == 1:
            return candidates[0]
        return None

    async def arrange_windows(self, apps: List[AppConfig]) -> bool:
        """
        Polls the window list and moves windows matching configured apps to their workspaces.
        Returns True if all apps with match rules were successfully placed, False if timed out.
        """
        apps_to_match = sorted(
            [(idx, app) for idx, app in enumerate(apps) if app.match is not None],
            key=lambda item: (item[1].workspace, item[0]),
        )
        if not apps_to_match:
            self.console.log("[yellow]⚠ No window matching rules defined in profile. Skipping arrangement.[/yellow]")
            return True

        self.console.log(f"[blue]🔍 Window retry engine active. Polling for {len(apps_to_match)} application window(s)...[/blue]")
        
        placed_indices: Set[str] = set()
        matched_apps: Set[int] = set()
        
        elapsed = 0.0
        while elapsed < self.timeout:
            if len(matched_apps) == len(apps_to_match):
                self.console.log("[green]✔ All application windows matched and successfully organized![/green]")
                return True

            try:
                current_windows = await self.backend.list_windows()
            except Exception as e:
                self.console.log(f"[yellow]⚠ Failed to list windows: {str(e)}. Retrying...[/yellow]")
                current_windows = []

            try:
                current_workspaces = await self.backend.get_workspaces()
            except Exception as e:
                self.console.log(f"[yellow]⚠ Failed to list workspaces: {str(e)}. Retrying...[/yellow]")
                current_workspaces = []

            for app_idx, app in apps_to_match:
                if app_idx in matched_apps:
                    continue
                if not self._can_attempt_move(app, current_workspaces):
                    continue

                matched_window: Optional[Window] = None
                used_fallback_match = False
                for win in current_windows:
                    if win.id in placed_indices:
                        continue

                    if self.matcher.matches(win, app.match):
                        matched_window = win
                        break

                if matched_window is None:
                    matched_window = self._find_fallback_match(current_windows, app, placed_indices)
                    used_fallback_match = matched_window is not None

                if matched_window is None:
                    continue

                output_name, target_workspace = self._resolve_destination(app)
                dest_info = f"Workspace {app.workspace}"
                if output_name:
                    if target_workspace != app.workspace:
                        dest_info += f" (local {target_workspace})"
                    dest_info += f" on Output '{output_name}'"

                match_label = "Fallback match found!" if used_fallback_match else "Match found!"
                if used_fallback_match:
                    match_label += " [dim](app_id-only)[/dim]"

                self.console.log(
                    f"[bold green]{match_label}[/bold green] Window "
                    f"[cyan]'{matched_window.title}'[/cyan] (app_id: {matched_window.app_id}) "
                    f"-> {dest_info}"
                )
                
                success = await self.backend.move_window(
                    matched_window.id,
                    target_workspace,
                    output_name=output_name,
                )
                if success:
                    placed_indices.add(matched_window.id)
                    matched_apps.add(app_idx)
                else:
                    self.console.log(f"[red]✘ Failed to move window '{matched_window.title}'[/red]")

            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval

        missing_apps = [app.command for app_idx, app in apps_to_match if app_idx not in matched_apps]
        self.console.log(
            f"[yellow]⚠ Timeout of {self.timeout}s reached. "
            f"Could not locate matching windows for: {', '.join(missing_apps)}[/yellow]"
        )
        return False
