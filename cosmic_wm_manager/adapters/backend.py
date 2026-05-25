from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class WindowGeometry(BaseModel):
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

class Window(BaseModel):
    id: str = Field(description="Unique identifier of the window (usually window index or ID)")
    title: str = Field(default="", description="The title of the window")
    app_id: str = Field(default="", description="The application ID (app_id under Wayland, WM_CLASS under X11)")
    workspace: int = Field(default=0, description="Index of the workspace the window is on")
    geometry: WindowGeometry = Field(default_factory=WindowGeometry)
    is_active: bool = Field(default=False, description="Whether this window is currently focused")
    process_id: Optional[int] = Field(default=None, description="System process ID if available")

class Workspace(BaseModel):
    index: int = Field(description="Numeric index of the workspace")
    name: str = Field(default="", description="Optional human-readable name of the workspace")
    is_active: bool = Field(default=False, description="Whether this workspace is active")
    output: str = Field(default="", description="Name of the output/monitor this workspace belongs to")

class WindowBackend(ABC):
    """
    Abstract Base Class for window compositor integration.
    Allows easy swapping between COSMIC, GNOME, and Mock (Dry-run) environments.
    """

    @abstractmethod
    async def list_windows(self) -> List[Window]:
        """List all open application windows currently managed by the compositor."""
        pass

    @abstractmethod
    async def move_window(self, window_id: str, workspace_idx: int, output_name: Optional[str] = None) -> bool:
        """Move a specific window to a designated workspace by index on a target output monitor."""
        pass

    @abstractmethod
    async def activate_window(self, window_id: str) -> bool:
        """Bring a specific window to the foreground and focus it."""
        pass

    @abstractmethod
    async def get_workspaces(self) -> List[Workspace]:
        """List all active workspaces."""
        pass

    @abstractmethod
    async def switch_workspace(self, workspace_idx: int) -> bool:
        """Switch active view focus to the given workspace index."""
        pass

    @abstractmethod
    async def create_workspace(self, workspace_idx: int, output: Optional[str] = None) -> bool:
        """Create a new workspace at the given index, optionally bound to an output."""
        pass
