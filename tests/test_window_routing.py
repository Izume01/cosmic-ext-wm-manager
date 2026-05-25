import unittest
from unittest.mock import patch
import tempfile
import os
import yaml

from cosmic_wm_manager.adapters.backend import Window, Workspace
from cosmic_wm_manager.adapters.cosmic import COSMICWindowBackend
from cosmic_wm_manager.cli import main as cli_main
from cosmic_wm_manager.config.schema import AppConfig, WindowMatchRule
from cosmic_wm_manager.config.schema import ProfileConfig
from cosmic_wm_manager.persistence.session import SessionManager
from cosmic_wm_manager.retry_engine.poll import RetryEngine
from cosmic_wm_manager.window_manager.matcher import WindowMatcher


class RecordingBackend:
    def __init__(self):
        self.moves = []
        self.activations = []
        self.workspaces = [Workspace(index=1, name="Workspace 1", output="eDP-1")]

    async def list_windows(self):
        return [Window(id="win-1", title="Editor", app_id="code", workspace=1)]

    async def move_window(self, window_id: str, workspace_idx: int, output_name=None):
        self.moves.append((window_id, workspace_idx, output_name))
        if not any(ws.index == workspace_idx for ws in self.workspaces):
            self.workspaces.append(Workspace(index=workspace_idx, name=f"Workspace {workspace_idx}", output=output_name or "eDP-1"))
        return True

    async def activate_window(self, window_id: str):
        self.activations.append(window_id)
        return True

    async def get_workspaces(self):
        return self.workspaces


class AlwaysMatch:
    def matches(self, window, rule):
        return True


class RetryEngineRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_local_workspace_for_output_route(self):
        backend = RecordingBackend()
        engine = RetryEngine(
            backend,
            WindowMatcher(),
            workspace_routes={5: ("DP-1", 1)},
            poll_interval=0.01,
            timeout=0.05,
        )
        apps = [
            AppConfig(
                command="code",
                workspace=5,
                match=WindowMatchRule(app_id="code"),
            )
        ]

        result = await engine.arrange_windows(apps)

        self.assertTrue(result)
        self.assertEqual(backend.moves, [("win-1", 1, "DP-1")])
        self.assertEqual(backend.activations, [])

    async def test_falls_back_to_unique_app_id_match_when_title_drifts(self):
        backend = RecordingBackend()
        backend.workspaces = [
            Workspace(index=1, name="Workspace 1", output="eDP-1"),
            Workspace(index=2, name="Workspace 2", output="eDP-1"),
            Workspace(index=3, name="Workspace 3", output="eDP-1"),
        ]

        async def list_discord_windows():
            return [Window(id="discord-1", title="Friends - Discord", app_id="discord", workspace=1)]

        backend.list_windows = list_discord_windows
        engine = RetryEngine(
            backend,
            WindowMatcher(),
            poll_interval=0.01,
            timeout=0.05,
        )
        apps = [
            AppConfig(
                command="flatpak run com.discordapp.Discord",
                workspace=4,
                match=WindowMatchRule(app_id="discord", title="@Oreo - Discord"),
            )
        ]

        result = await engine.arrange_windows(apps)

        self.assertTrue(result)
        self.assertEqual(backend.moves, [("discord-1", 4, None)])
        self.assertEqual(backend.activations, [])

    async def test_defers_high_workspace_until_lower_workspaces_exist(self):
        class SequencedBackend(RecordingBackend):
            async def list_windows(self):
                return [
                    Window(id="term-1", title="New terminal — COSMIC Terminal", app_id="com.system76.CosmicTerm", workspace=1),
                    Window(id="code-1", title="Welcome - Visual Studio Code", app_id="code", workspace=1),
                    Window(id="yt-1", title="youtube music", app_id="com.github.th_ch.youtube_music", workspace=1),
                    Window(id="discord-1", title="Friends - Discord", app_id="discord", workspace=1),
                ]

        backend = SequencedBackend()
        engine = RetryEngine(
            backend,
            WindowMatcher(),
            poll_interval=0.01,
            timeout=0.1,
        )
        apps = [
            AppConfig(command="cosmic-term", workspace=5, match=WindowMatchRule(app_id="com.system76.CosmicTerm")),
            AppConfig(command="code", workspace=2, match=WindowMatchRule(app_id="code")),
            AppConfig(command="youtube", workspace=3, match=WindowMatchRule(app_id="com.github.th_ch.youtube_music")),
            AppConfig(command="discord", workspace=4, match=WindowMatchRule(app_id="discord")),
        ]

        result = await engine.arrange_windows(apps)

        self.assertTrue(result)
        self.assertEqual(
            backend.moves,
            [
                ("code-1", 2, None),
                ("yt-1", 3, None),
                ("discord-1", 4, None),
                ("term-1", 5, None),
            ],
        )


class StubCOSMICWindowBackend(COSMICWindowBackend):
    def __init__(self):
        super().__init__()
        self.commands = []
        self._workspaces = [1, 2]
        self.switched_workspaces = []

    async def _get_output_routes(self):
        return {
            "DP-1": {
                "group_index": 2,
                "output_index": 1,
                "workspace_numbers": [1],
            }
        }

    async def _run_command(self, *args: str):
        self.commands.append(args)
        if args[:4] == ("move", "-i", "42", "-w"):
            target_workspace = int(args[4]) + 1
            current_tail = max(self._workspaces)
            if target_workspace > current_tail + 1:
                return None
            if target_workspace == current_tail:
                next_workspace = target_workspace + 1
                if next_workspace not in self._workspaces:
                    self._workspaces.append(next_workspace)
            elif target_workspace == current_tail + 1:
                self._workspaces.append(target_workspace)
        if args[:4] == ("move", "-i", "99", "-w"):
            target_workspace = int(args[4]) + 1
            current_tail = max(self._workspaces)
            if target_workspace > current_tail + 1:
                return None
            if target_workspace == current_tail:
                next_workspace = target_workspace + 1
                if next_workspace not in self._workspaces:
                    self._workspaces.append(next_workspace)
            elif target_workspace == current_tail + 1:
                self._workspaces.append(target_workspace)
        return ""

    async def get_workspaces(self):
        return [
            Workspace(index=idx, name=f"Workspace {idx}", output="DP-1")
            for idx in sorted(self._workspaces)
        ]

    async def switch_workspace(self, workspace_idx: int) -> bool:
        self.switched_workspaces.append(workspace_idx)
        if workspace_idx not in self._workspaces:
            self._workspaces.append(workspace_idx)
        return True


class CosmicBackendRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_move_window_steps_through_plain_workspace_growth(self):
        backend = StubCOSMICWindowBackend()

        result = await backend.move_window("99", 5)

        self.assertTrue(result)
        self.assertEqual(backend.switched_workspaces, [])
        self.assertEqual(
            backend.commands,
            [
                ("move", "-i", "99", "-w", "1"),
                ("move", "-i", "99", "-w", "2"),
                ("move", "-i", "99", "-w", "3"),
                ("move", "-i", "99", "-w", "4"),
            ],
        )

    async def test_move_window_routes_through_workspace_group(self):
        backend = StubCOSMICWindowBackend()
        backend._workspaces = [1, 2, 3, 4]

        result = await backend.move_window("42", 5, output_name="DP-1")

        self.assertTrue(result)
        self.assertEqual(
            backend.commands,
            [
                ("move", "-i", "42", "-w", "3", "-g", "2"),
                ("move", "-i", "42", "-w", "4", "-g", "2"),
            ],
        )


class CliWorkspaceCreationTests(unittest.TestCase):
    def test_start_profile_does_not_precreate_app_workspaces_without_monitors(self):
        created_workspaces = []
        launched_commands = []
        arranged_apps = []
        switched_workspaces = []

        class Backend:
            async def list_windows(self):
                return [
                    Window(
                        id="current",
                        title="Current terminal",
                        app_id="com.system76.CosmicTerm",
                        workspace=1,
                        is_active=True,
                    )
                ]

            async def create_workspace(self, workspace_idx: int, output=None):
                created_workspaces.append((workspace_idx, output))
                return True

            async def switch_workspace(self, workspace_idx: int):
                switched_workspaces.append(workspace_idx)
                return True

        class Launcher:
            async def launch(self, command: str):
                launched_commands.append(command)
                return 1

        class Engine:
            async def arrange_windows(self, apps):
                arranged_apps.extend(apps)
                return True

        cfg = ProfileConfig(
            name="coding",
            apps=[
                AppConfig(command="cosmic-term", workspace=5),
                AppConfig(command="code", workspace=2),
            ],
        )

        with patch.object(cli_main.ProfileConfig, "load_from_yaml", return_value=cfg), \
             patch.object(cli_main, "get_backend", return_value=Backend()), \
             patch.object(cli_main, "AsyncAppLauncher", return_value=Launcher()), \
             patch.object(cli_main, "WindowMatcher"), \
             patch.object(cli_main, "RetryEngine", return_value=Engine()):
            cli_main._start_profile("/tmp/coding.yaml", dry_run=False, timeout=1.0, debug=False)

        self.assertEqual(
            created_workspaces,
            [],
        )
        self.assertEqual(launched_commands, ["cosmic-term", "code"])
        self.assertEqual(arranged_apps, cfg.apps)
        self.assertEqual(switched_workspaces, [1])

    def test_start_profile_reuses_matching_windows_without_relaunching(self):
        launched_commands = []
        arranged_apps = []

        class Backend:
            async def list_windows(self):
                return [
                    Window(
                        id="term-1",
                        title="New terminal — COSMIC Terminal",
                        app_id="com.system76.CosmicTerm",
                        workspace=1,
                        is_active=True,
                    ),
                    Window(
                        id="code-1",
                        title="Welcome - Visual Studio Code",
                        app_id="code",
                        workspace=1,
                    ),
                    Window(
                        id="discord-1",
                        title="Friends - Discord",
                        app_id="discord",
                        workspace=1,
                    ),
                ]

            async def create_workspace(self, workspace_idx: int, output=None):
                return True

            async def switch_workspace(self, workspace_idx: int):
                return True

        class Launcher:
            async def launch(self, command: str):
                launched_commands.append(command)
                return 1

        class Engine:
            async def arrange_windows(self, apps):
                arranged_apps.extend(apps)
                return True

        cfg = ProfileConfig(
            name="coding",
            apps=[
                AppConfig(
                    command="cosmic-term",
                    workspace=5,
                    match=WindowMatchRule(app_id="com.system76.CosmicTerm", title="New terminal — COSMIC Terminal"),
                ),
                AppConfig(
                    command="code",
                    workspace=1,
                    match=WindowMatchRule(app_id="code", title="Welcome - Visual Studio Code"),
                ),
                AppConfig(
                    command="flatpak run com.discordapp.Discord",
                    workspace=4,
                    match=WindowMatchRule(app_id="discord", title="@Oreo - Discord"),
                ),
            ],
        )

        with patch.object(cli_main.ProfileConfig, "load_from_yaml", return_value=cfg), \
             patch.object(cli_main, "get_backend", return_value=Backend()), \
             patch.object(cli_main, "AsyncAppLauncher", return_value=Launcher()), \
             patch.object(cli_main, "RetryEngine", return_value=Engine()):
            cli_main._start_profile("/tmp/coding.yaml", dry_run=False, timeout=1.0, debug=False)

        self.assertEqual(launched_commands, [])
        self.assertEqual(arranged_apps, cfg.apps)

    def test_start_profile_only_launches_missing_duplicate_window_count(self):
        launched_commands = []

        class Backend:
            async def list_windows(self):
                return [
                    Window(
                        id="code-1",
                        title="Welcome - Visual Studio Code",
                        app_id="code",
                        workspace=1,
                        is_active=True,
                    )
                ]

            async def create_workspace(self, workspace_idx: int, output=None):
                return True

            async def switch_workspace(self, workspace_idx: int):
                return True

        class Launcher:
            async def launch(self, command: str):
                launched_commands.append(command)
                return 1

        class Engine:
            async def arrange_windows(self, apps):
                return True

        cfg = ProfileConfig(
            name="coding",
            apps=[
                AppConfig(
                    command="code",
                    workspace=1,
                    match=WindowMatchRule(app_id="code", title="Welcome - Visual Studio Code"),
                ),
                AppConfig(
                    command="code",
                    workspace=2,
                    match=WindowMatchRule(app_id="code", title="Welcome - Visual Studio Code"),
                ),
            ],
        )

        with patch.object(cli_main.ProfileConfig, "load_from_yaml", return_value=cfg), \
             patch.object(cli_main, "get_backend", return_value=Backend()), \
             patch.object(cli_main, "AsyncAppLauncher", return_value=Launcher()), \
             patch.object(cli_main, "RetryEngine", return_value=Engine()):
            cli_main._start_profile("/tmp/coding.yaml", dry_run=False, timeout=1.0, debug=False)

        self.assertEqual(launched_commands, ["code"])


class SessionCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_singleton_app_ids_do_not_persist_volatile_titles(self):
        class Backend:
            async def list_windows(self):
                return [
                    Window(
                        id="term-1",
                        title="nyx — COSMIC Terminal",
                        app_id="com.system76.CosmicTerm",
                        workspace=5,
                    ),
                    Window(
                        id="discord-1",
                        title="Friends - Discord",
                        app_id="discord",
                        workspace=4,
                    ),
                ]

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SessionManager(Backend())
            manager.sessions_dir = tmpdir

            with patch.object(manager, "_resolve_process_cmd", side_effect=["cosmic-term", "flatpak run com.discordapp.Discord"]):
                path = await manager.save_session("coding")

            self.assertIsNotNone(path)
            with open(path, "r") as handle:
                data = yaml.safe_load(handle)

        self.assertEqual(
            data["apps"],
            [
                {
                    "command": "cosmic-term",
                    "workspace": 5,
                    "match": {"class": "com.system76.CosmicTerm"},
                },
                {
                    "command": "flatpak run com.discordapp.Discord",
                    "workspace": 4,
                    "match": {"class": "discord"},
                },
            ],
        )

    async def test_duplicate_app_ids_keep_titles_for_disambiguation(self):
        class Backend:
            async def list_windows(self):
                return [
                    Window(
                        id="code-1",
                        title="Welcome - Visual Studio Code",
                        app_id="code",
                        workspace=1,
                    ),
                    Window(
                        id="code-2",
                        title="docs - Visual Studio Code",
                        app_id="code",
                        workspace=2,
                    ),
                ]

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SessionManager(Backend())
            manager.sessions_dir = tmpdir

            with patch.object(manager, "_resolve_process_cmd", side_effect=["code", "code"]):
                path = await manager.save_session("coding")

            self.assertIsNotNone(path)
            with open(path, "r") as handle:
                data = yaml.safe_load(handle)

        self.assertEqual(
            data["apps"],
            [
                {
                    "command": "code",
                    "workspace": 1,
                    "match": {"class": "code", "title": "Welcome - Visual Studio Code"},
                },
                {
                    "command": "code",
                    "workspace": 2,
                    "match": {"class": "code", "title": "docs - Visual Studio Code"},
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
