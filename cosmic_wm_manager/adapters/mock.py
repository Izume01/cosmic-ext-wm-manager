from typing import List, Optional
from rich.console import Console
from .backend import WindowBackend, Window, Workspace, WindowGeometry

class MockWindowBackend(WindowBackend):
    """
    Mock implementation of WindowBackend used for --dry-run or testing.
    Prints actions to console using Rich instead of invoking compositor commands.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.current_workspace_idx = 1
        self.workspaces = [
            Workspace(index=1, name="Dev", is_active=True, output="eDP-1"),
            Workspace(index=2, name="Web", is_active=False, output="eDP-1"),
            Workspace(index=3, name="Chat", is_active=False, output="eDP-1"),
        ]
        self.windows = [
            Window(
                id="win-1",
                title="project-terminal",
                app_id="kitty",
                workspace=1,
                geometry=WindowGeometry(x=0, y=0, width=960, height=1080),
                is_active=True,
                process_id=1234
            )
        ]

    async def list_windows(self) -> List[Window]:
        self.console.log(f"[dim]Mock: Listing windows (count={len(self.windows)})[/dim]")
        return self.windows

    async def move_window(self, window_id: str, workspace_idx: int, output_name: Optional[str] = None) -> bool:
        self.console.log(
            f"[bold cyan]Mock: Move window '{window_id}' -> "
            f"Workspace {workspace_idx} on Output [bold yellow]'{output_name or 'eDP-1'}'[/bold yellow][/bold cyan]"
        )
        for win in self.windows:
            if win.id == window_id:
                win.workspace = workspace_idx
                return True
        return False

    async def activate_window(self, window_id: str) -> bool:
        self.console.log(f"[bold magenta]Mock: Focus window '{window_id}'[/bold magenta]")
        for win in self.windows:
            win.is_active = (win.id == window_id)
        return True

    async def get_workspaces(self) -> List[Workspace]:
        self.console.log("[dim]Mock: Fetching workspace list[/dim]")
        return self.workspaces

    async def switch_workspace(self, workspace_idx: int) -> bool:
        self.console.log(f"[bold yellow]Mock: Switch to Workspace {workspace_idx}[/bold yellow]")
        self.current_workspace_idx = workspace_idx
        for ws in self.workspaces:
            ws.is_active = (ws.index == workspace_idx)
        return True

    async def create_workspace(self, workspace_idx: int, output: Optional[str] = None) -> bool:
        self.console.log(f"[bold green]Mock: Create Workspace {workspace_idx} on Output {output or 'default'}[/bold green]")
        if not any(ws.index == workspace_idx for ws in self.workspaces):
            self.workspaces.append(Workspace(
                index=workspace_idx,
                name=f"Workspace-{workspace_idx}",
                is_active=False,
                output=output or "eDP-1"
            ))
        return True
