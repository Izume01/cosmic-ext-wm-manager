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
        if rule.app_id:
            win_app_id = window.app_id or ""
            if rule.app_id.lower() not in win_app_id.lower():
                return False

        if rule.title:
            win_title = window.title or ""
            try:
                pattern = re.compile(rule.title, re.IGNORECASE)
                if not pattern.search(win_title):
                    return False
            except re.error:
                if rule.title.lower() not in win_title.lower():
                    return False

        if rule.process_name:
            if not window.process_id:
                return False
            try:
                proc = psutil.Process(window.process_id)
                proc_name = proc.name()
                if rule.process_name.lower() not in proc_name.lower():
                    parent = proc.parent()
                    if parent and rule.process_name.lower() in parent.name().lower():
                        pass
                    else:
                        return False
            except Exception:
                return False

        has_any_criteria = bool(rule.app_id or rule.title or rule.process_name)
        return has_any_criteria
