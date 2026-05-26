import unittest
from unittest.mock import patch, MagicMock
import os
import shutil
import subprocess

from cosmic_wm_manager.utils.validation import parse_executable, check_command_exists

class TestCommandValidation(unittest.TestCase):
    def test_parse_executable_simple(self):
        self.assertEqual(parse_executable("kitty"), "kitty")
        self.assertEqual(parse_executable("code --verbose"), "code")

    def test_parse_executable_env_prefix(self):
        self.assertEqual(parse_executable("env WINEPREFIX=/path/to/prefix wine game.exe"), "wine")
        self.assertEqual(parse_executable("MY_VAR=val path/to/binary"), "path/to/binary")
        self.assertEqual(parse_executable("env A=1 B=2 /usr/bin/python3 -m unittest"), "/usr/bin/python3")

    def test_parse_executable_empty(self):
        self.assertIsNone(parse_executable(""))
        self.assertIsNone(parse_executable("   "))
        self.assertIsNone(parse_executable("env"))
        self.assertIsNone(parse_executable("env A=1"))

    def test_check_command_exists_path(self):
        # We know python/python3 or sh exist in PATH
        self.assertTrue(check_command_exists("sh"))
        self.assertFalse(check_command_exists("nonexistent-executable-12345"))

    @patch("shutil.which")
    def test_check_command_exists_mocked(self, mock_which):
        mock_which.side_effect = lambda x: "/usr/bin/" + x if x == "kitty" else None
        
        self.assertTrue(check_command_exists("kitty"))
        self.assertFalse(check_command_exists("alacritty"))

    @patch("os.path.exists")
    @patch("os.access")
    def test_check_command_exists_absolute_relative(self, mock_access, mock_exists):
        mock_exists.return_value = True
        mock_access.return_value = True
        
        self.assertTrue(check_command_exists("/usr/bin/my-app"))
        self.assertTrue(check_command_exists("./my-app"))
        
        mock_exists.return_value = False
        self.assertFalse(check_command_exists("/usr/bin/my-app"))

    @patch("shutil.which")
    @patch("os.path.isdir")
    @patch("subprocess.run")
    def test_check_command_exists_flatpak(self, mock_run, mock_isdir, mock_which):
        # Setup flatpak available
        mock_which.side_effect = lambda x: "/usr/bin/flatpak" if x == "flatpak" else None
        
        # Test flatpak app is found in directory check (user path)
        mock_isdir.side_effect = lambda x: "org.gnome.Nautilus" in x
        self.assertTrue(check_command_exists("flatpak run org.gnome.Nautilus"))
        self.assertTrue(check_command_exists("flatpak run --branch=stable org.gnome.Nautilus --verbose"))
        
        # Test flatpak app is not in directory but flatpak info succeeds
        mock_isdir.return_value = False
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_run.return_value = mock_process
        
        self.assertTrue(check_command_exists("flatpak run com.discordapp.Discord"))
        mock_run.assert_called_with(
            ["flatpak", "info", "com.discordapp.Discord"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0
        )

        # Test flatpak app is missing completely
        mock_process.returncode = 1
        self.assertFalse(check_command_exists("flatpak run com.nonexistent.App"))

        # Test flatpak not installed on host
        mock_which.side_effect = None
        mock_which.return_value = None
        self.assertFalse(check_command_exists("flatpak run org.gnome.Nautilus"))
