import asyncio
import os
import sys
import shlex
import psutil
from typing import Optional, Dict, Any
from rich.console import Console

class AsyncAppLauncher:
    """
    Handles asynchronous execution and detaching of application processes.
    Ensures launched applications survive after the CLI finishes.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    async def launch(self, command: str, cwd: Optional[str] = None) -> Optional[int]:
        """
        Asynchronously launch an application command in a detached shell.
        Returns the process ID (PID) if successfully launched.
        """
        # Expand home directory in paths
        if cwd:
            cwd = os.path.expanduser(cwd)
        else:
            cwd = os.path.expanduser("~")

        expanded_cmd = os.path.expanduser(command)
        
        self.console.log(f"[dim]Spawning process: {expanded_cmd} (Cwd: {cwd})[/dim]")
        
        try:
            # We use preexec_fn=os.setsid to completely detach the process 
            # from the parent terminal session, making sure it survives CLI exit.
            process = await asyncio.create_subprocess_shell(
                expanded_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                stdin=asyncio.subprocess.DEVNULL,
                cwd=cwd,
                preexec_fn=os.setsid if sys.platform != "win32" else None
            )
            
            # Allow a tiny sleep to let the OS register the pid
            await asyncio.sleep(0.05)
            
            pid = process.pid
            self.console.log(f"[green]✔ Successfully launched '{expanded_cmd}' [dim](PID: {pid})[/dim][/green]")
            return pid
            
        except Exception as e:
            self.console.log(f"[bold red]✘ Failed to launch '{expanded_cmd}': {str(e)}[/bold red]")
            return None

    def is_process_running(self, pid: int) -> bool:
        """Check if a process with a given PID is still active on the system."""
        try:
            return psutil.pid_exists(pid)
        except Exception:
            return False
