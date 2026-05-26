import os
import shlex
import shutil
import subprocess
from typing import List, Optional

def parse_executable(command: str) -> Optional[str]:
    """
    Parses a shell command string to extract the primary executable or Flatpak app ID.
    Supports env variable assignments and basic shell prefixes.
    """
    if not command:
        return None

    expanded = os.path.expanduser(command)
    try:
        parts = shlex.split(expanded)
    except Exception:
        parts = expanded.split()

    if not parts:
        return None

    # Skip 'env' prefix and environment variable assignments
    idx = 0
    if parts[idx] == "env":
        idx += 1
    while idx < len(parts) and "=" in parts[idx]:
        idx += 1

    if idx >= len(parts):
        return None

    # Handle control flow or pipe operators by only checking the first executable
    cmd = parts[idx]
    if cmd in ("&&", "||", ";", "|"):
        return None

    return cmd

def check_command_exists(command: str) -> bool:
    """
    Robustly checks if a command's executable is installed/executable on the system.
    Supports system executables, relative/absolute paths, and Flatpak applications.
    """
    cmd = parse_executable(command)
    if not cmd:
        return False

    # Check for Flatpak application command pattern
    if cmd == "flatpak":
        try:
            parts = shlex.split(os.path.expanduser(command))
        except Exception:
            parts = command.split()
            
        if len(parts) >= 3 and parts[1] == "run":
            # flatpak run [FLAGS] <APP_ID> [ARGS]
            app_id = None
            for part in parts[2:]:
                if not part.startswith("-"):
                    app_id = part
                    break
            
            if not app_id:
                # 'flatpak run' is incomplete, but flatpak binary itself could be present
                return shutil.which("flatpak") is not None

            # First, verify if 'flatpak' itself is installed on the host
            if shutil.which("flatpak") is None:
                return False

            # Ultra-fast check: Look up standard flatpak installation directories
            user_flatpak_dir = os.path.expanduser("~/.local/share/flatpak/app")
            system_flatpak_dir = "/var/lib/flatpak/app"
            if os.path.isdir(os.path.join(user_flatpak_dir, app_id)) or \
               os.path.isdir(os.path.join(system_flatpak_dir, app_id)):
                return True

            # Fallback check: Execute 'flatpak info'
            try:
                res = subprocess.run(
                    ["flatpak", "info", app_id],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2.0
                )
                return res.returncode == 0
            except Exception:
                return False

    # Check for absolute or relative path
    if "/" in cmd or cmd.startswith("."):
        return os.path.exists(cmd) and os.access(cmd, os.X_OK)

    # Check standard path executable
    return shutil.which(cmd) is not None
