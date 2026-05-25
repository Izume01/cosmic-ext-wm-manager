import re
from typing import Optional
import psutil
from rich.console import Console
from ..adapters.backend import Window
from ..config.schema import WindowMatchRule

class WindowMatcher:
    """
    Evaluates window attributes against matching rules defined in profiles.
    Supports app_id/class matching, window title substring/regex matching,
    and process name matching.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def matches(self, window: Window, rule: WindowMatchRule) -> bool:
        """
        Check if a given window satisfies the specifications of a match rule.
        All specified fields in the rule must match (logical AND).
        """
        # 1. Match application ID / Class (partial, case-insensitive)
        if rule.app_id:
            win_app_id = window.app_id or ""
            if rule.app_id.lower() not in win_app_id.lower():
                return False

        # 2. Match Window Title (supports regex or simple case-insensitive substring)
        if rule.title:
            win_title = window.title or ""
            try:
                # Try compiling as a regex
                pattern = re.compile(rule.title, re.IGNORECASE)
                if not pattern.search(win_title):
                    return False
            except re.error:
                # Fallback to standard substring match if regex is invalid
                if rule.title.lower() not in win_title.lower():
                    return False

        # 3. Match Process Name (uses psutil to check process hierarchy of window.process_id)
        if rule.process_name:
            if not window.process_id:
                # Cannot match process name if no PID is linked
                return False
            try:
                proc = psutil.Process(window.process_id)
                proc_name = proc.name()
                if rule.process_name.lower() not in proc_name.lower():
                    # Check parent process as well just in case (e.g. terminal wrapper scripts)
                    parent = proc.parent()
                    if parent and rule.process_name.lower() in parent.name().lower():
                        pass
                    else:
                        return False
            except Exception:
                return False

        # If we got here and at least one rule criteria was checked, return True.
        # If the rule was completely empty, return False to avoid matching everything.
        has_any_criteria = bool(rule.app_id or rule.title or rule.process_name)
        return has_any_criteria
