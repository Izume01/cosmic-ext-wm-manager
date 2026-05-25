from typing import List, Optional, Tuple
import os
import yaml
from pydantic import BaseModel, Field, field_validator

class MonitorConfig(BaseModel):
    output: str = Field(description="Name of the monitor (e.g. eDP-1, DP-1)")
    primary: bool = Field(default=False, description="Whether this is the primary monitor")
    workspace_count: int = Field(default=4, description="Number of workspaces to ensure on this monitor")

class WindowMatchRule(BaseModel):
    app_id: Optional[str] = Field(default=None, alias="class", description="Matches application class or app_id")
    title: Optional[str] = Field(default=None, description="Regex or substring match against window title")
    process_name: Optional[str] = Field(default=None, description="Matches system process name")
    
    class Config:
        populate_by_name = True

class AppConfig(BaseModel):
    command: str = Field(description="Shell command to launch the application")
    workspace: int = Field(description="Workspace index to assign this application's windows to")
    match: Optional[WindowMatchRule] = Field(default=None, description="Rules to identify this application's windows")
    layout: Optional[str] = Field(default=None, description="Position layout: left, right, maximize, floating")
    urls: Optional[List[str]] = Field(default=None, description="URLs to open if the app is a browser")

class ProfileConfig(BaseModel):
    name: str = Field(description="Name of the workspace profile")
    description: Optional[str] = Field(default=None, description="Short summary of the environment purpose")
    monitors: List[MonitorConfig] = Field(default_factory=list, description="Monitor/workspace layouts")
    apps: List[AppConfig] = Field(default_factory=list, description="List of applications to start up")

    @classmethod
    def load_from_yaml(cls, filepath: str) -> "ProfileConfig":
        """Loads a workspace profile config from a YAML file."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Profile config file not found: {filepath}")
        
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)
            
        return cls.model_validate(data)

    def resolve_workspace_output(self, workspace_idx: int) -> Tuple[str, int]:
        """
        Resolves a global 1-based workspace index into the correct output monitor name
        and local 1-based workspace index on that monitor.
        """
        if not self.monitors:
            return "eDP-1", workspace_idx

        sorted_monitors = sorted(self.monitors, key=lambda m: not m.primary)
        
        current_offset = 0
        for mon in sorted_monitors:
            if current_offset < workspace_idx <= current_offset + mon.workspace_count:
                local_idx = workspace_idx - current_offset
                return mon.output, local_idx
            current_offset += mon.workspace_count
            
        fallback_mon = sorted_monitors[-1]
        local_idx = max(1, workspace_idx - (current_offset - fallback_mon.workspace_count))
        return fallback_mon.output, local_idx
