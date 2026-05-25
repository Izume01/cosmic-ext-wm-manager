import asyncio
import json
import shutil
import os
from typing import Any, Dict, List, Optional
from rich.console import Console
from .backend import WindowBackend, Window, Workspace, WindowGeometry

class COSMICWindowBackend(WindowBackend):
    """
    COSMIC Desktop compositor integration wrapping the 'cos-cli' utility.
    Runs Wayland-native operations using IPC.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self._cos_cli_path = self._find_cos_cli()

    def _find_cos_cli(self) -> str:
        """Locates the 'cos-cli' binary on the system."""
        path = shutil.which("cos-cli")
        if path:
            return path
        
        cargo_bin = os.path.expanduser("~/.cargo/bin/cos-cli")
        if os.path.exists(cargo_bin):
            return cargo_bin
            
        return "cos-cli"

    async def _run_command(self, *args: str) -> Optional[str]:
        """Helper to execute cos-cli with arguments asynchronously."""
        try:
            process = await asyncio.create_subprocess_exec(
                self._cos_cli_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                err_msg = stderr.decode().strip()
                self.console.log(f"[yellow]⚠ cos-cli command error: {err_msg}[/yellow]")
                return None
                
            return stdout.decode().strip()
        except Exception as e:
            self.console.log(f"[yellow]⚠ Failed to execute cos-cli: {str(e)}[/yellow]")
            return None

    async def _get_info(self) -> Optional[Dict[str, Any]]:
        """Fetches and parses compositor state once for reuse across operations."""
        output = await self._run_command("info", "--json")
        if not output:
            return None

        try:
            return json.loads(output)
        except Exception as e:
            self.console.log(f"[red]Failed to parse compositor info: {str(e)}[/red]")
            return None

    @staticmethod
    def _coerce_int(value: Any, default: Optional[int] = None) -> Optional[int]:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    def _extract_workspace_number(self, workspace_data: Dict[str, Any]) -> int:
        """Parses a human-facing 1-based workspace number from cos-cli JSON."""
        ws_name = workspace_data.get("name") or workspace_data.get("workspace")
        parsed_name = self._coerce_int(ws_name)
        if parsed_name is not None:
            return parsed_name

        return self._coerce_int(workspace_data.get("index"), 0) + 1

    @staticmethod
    def _extract_output_names(group_outputs: Any, default_output: str) -> List[str]:
        if not group_outputs:
            return [default_output] if default_output else []

        output_names: List[str] = []
        for entry in group_outputs:
            if isinstance(entry, str):
                output_names.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("name")
                if name:
                    output_names.append(str(name))
        return output_names

    async def _get_output_routes(self) -> Dict[str, Dict[str, Any]]:
        """
        Maps output names to the indices cos-cli expects for output-aware workspace moves.
        """
        data = await self._get_info()
        if not data:
            return {}

        outputs = data.get("outputs", [])
        default_output = outputs[0].get("name", "eDP-1") if outputs else "eDP-1"

        output_indices: Dict[str, int] = {}
        for position, output in enumerate(outputs):
            name = output.get("name")
            if not name:
                continue
            output_indices[name] = self._coerce_int(output.get("index"), position)

        routes: Dict[str, Dict[str, Any]] = {}
        for position, group in enumerate(data.get("workspace_groups", [])):
            group_index = self._coerce_int(group.get("index"), position)
            workspace_numbers = [
                self._extract_workspace_number(ws)
                for ws in group.get("workspaces", [])
            ]

            for output_name in self._extract_output_names(group.get("outputs"), default_output):
                route = routes.setdefault(
                    output_name,
                    {
                        "group_index": group_index,
                        "output_index": output_indices.get(output_name),
                        "workspace_numbers": [],
                    },
                )
                route["workspace_numbers"].extend(workspace_numbers)
                if route["group_index"] is None:
                    route["group_index"] = group_index
                if route["output_index"] is None:
                    route["output_index"] = output_indices.get(output_name)

        for output_name, output_index in output_indices.items():
            routes.setdefault(
                output_name,
                {
                    "group_index": None,
                    "output_index": output_index,
                    "workspace_numbers": [],
                },
            )

        return routes

    async def _get_workspace_numbers(self, output_name: Optional[str] = None) -> List[int]:
        """Returns sorted 1-based workspace numbers, optionally filtered to a single output."""
        workspaces = await self.get_workspaces()
        return sorted({
            ws.index
            for ws in workspaces
            if ws.index > 0 and (output_name is None or ws.output == output_name)
        })

    async def _wait_for_workspace_number(
        self,
        workspace_number: int,
        output_name: Optional[str] = None,
        timeout: float = 3.0,
        poll_interval: float = 0.1,
    ) -> bool:
        """Polls until a workspace number becomes available."""
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            workspace_numbers = await self._get_workspace_numbers(output_name)
            if workspace_number in workspace_numbers:
                return True
            await asyncio.sleep(poll_interval)
        return False

    async def list_windows(self) -> List[Window]:
        """Fetches active application windows via 'cos-cli info --json'."""
        data = await self._get_info()
        if not data:
            return []

        try:
            apps = data.get("apps", [])
            windows = []
            
            for app in apps:
                app_id = app.get("app_id") or app.get("name") or ""
                idx = str(app.get("index", ""))
                
                app_workspaces = app.get("workspaces", [])
                workspace_idx = 1
                if app_workspaces:
                    workspace_idx = self._extract_workspace_number(app_workspaces[0])

                states = app.get("state", [])
                is_active = "activated" in states
                
                windows.append(Window(
                    id=idx,
                    title=app.get("title", ""),
                    app_id=app_id,
                    workspace=workspace_idx,
                    is_active=is_active
                ))
            return windows
        except Exception as e:
            self.console.log(f"[red]Failed to parse window info: {str(e)}[/red]")
            return []

    async def move_window(self, window_id: str, workspace_idx: int, output_name: Optional[str] = None) -> bool:
        """Moves a window to the requested workspace, optionally routing it to a specific output."""
        target_idx = max(0, workspace_idx - 1)
        route_args: List[str] = []

        if output_name:
            routes = await self._get_output_routes()
            route = routes.get(output_name)
            if route:
                group_index = route.get("group_index")
                output_index = route.get("output_index")
                if group_index is not None:
                    route_args = ["-g", str(group_index)]
                elif output_index is not None:
                    route_args = ["-o", str(output_index)]
            else:
                self.console.log(
                    f"[yellow]⚠ Output '{output_name}' not found in COSMIC topology. "
                    f"Falling back to workspace-only move.[/yellow]"
                )

        workspace_scope = output_name if route_args else None
        workspace_numbers = await self._get_workspace_numbers(workspace_scope)
        max_existing = max(workspace_numbers, default=1) - 1

        if target_idx <= max_existing:
            result = await self._run_command("move", "-i", window_id, "-w", str(target_idx), *route_args)
            return result is not None

        current_tail = max_existing
        while current_tail < target_idx:
            # COSMIC only materializes the next workspace after a window is moved into
            # the current tail workspace, so seed each hop from the current visible end.
            result = await self._run_command("move", "-i", window_id, "-w", str(current_tail), *route_args)
            if result is None:
                self.console.log(
                    f"[yellow]⚠ Failed stepping through tail workspace index {current_tail}[/yellow]"
                )
                return False

            # COSMIC appends the next empty workspace asynchronously after moving into the current tail.
            next_workspace_number = current_tail + 2
            ready = await self._wait_for_workspace_number(next_workspace_number, workspace_scope)
            if not ready:
                self.console.log(
                    f"[yellow]⚠ Timed out waiting for workspace {next_workspace_number} to appear[/yellow]"
                )
                return False

            current_tail += 1

        result = await self._run_command("move", "-i", window_id, "-w", str(target_idx), *route_args)
        return result is not None

    async def activate_window(self, window_id: str) -> bool:
        """Focuses the given application window."""
        result = await self._run_command("activate", "-i", window_id)
        return result is not None

    async def get_workspaces(self) -> List[Workspace]:
        """Fetches workspace list from 'cos-cli info --json'."""
        data = await self._get_info()
        if not data:
            return []

        try:
            workspace_groups = data.get("workspace_groups", [])
            outputs_data = data.get("outputs", [])
            default_output = outputs_data[0].get("name", "eDP-1") if outputs_data else "eDP-1"

            workspaces = []
            for group in workspace_groups:
                ws_list = group.get("workspaces", [])
                output_names = self._extract_output_names(group.get("outputs"), default_output)
                output_name = output_names[0] if output_names else default_output
                for ws in ws_list:
                    idx = self._extract_workspace_number(ws)
                    workspaces.append(Workspace(
                        index=idx,
                        name=f"Workspace {idx}",
                        is_active=False,
                        output=output_name
                    ))
            return workspaces
        except Exception as e:
            self.console.log(f"[red]Failed to parse workspace info: {str(e)}[/red]")
            return []

    async def switch_workspace(self, workspace_idx: int) -> bool:
        """Switch current view to the specified workspace."""
        cos_workspace_idx = max(0, workspace_idx - 1)
        result = await self._run_command("ws-activate", "-w", str(cos_workspace_idx))
        return result is not None

    async def create_workspace(self, workspace_idx: int, output: Optional[str] = None) -> bool:
        """Ensures a workspace exists on the compositor."""
        return True
