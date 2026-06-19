"""
Tests for src/utils.py — utility helpers.
"""

import os
import shutil
import subprocess
import sys

import pytest

from src.utils import (
    _subprocess_creationflags,
    get_python_executable,
    resource_path,
)


class TestResourcePath:
    def test_returns_absolute_path(self):
        result = resource_path("src/assets/icon.png")
        assert os.path.isabs(result)

    def test_appends_relative_path(self):
        result = resource_path("foo/bar.txt")
        # Normalize path separators for cross-platform comparison
        assert os.path.normpath(result).endswith(os.path.join("foo", "bar.txt"))

    def test_contains_project_root(self):
        result = resource_path("")
        assert "Lithium-IDE" in result or "src" in result


class TestGetPythonExecutable:
    def test_returns_string(self):
        result = get_python_executable()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_existing_file(self):
        result = get_python_executable()
        # When not frozen, returns sys.executable which is always valid
        assert os.path.exists(result) or shutil.which(result) is not None

    def test_is_absolute_or_on_path(self):
        result = get_python_executable()
        assert os.path.isabs(result) or shutil.which(result) is not None


class TestSubprocessCreationflags:
    def test_returns_int(self):
        result = _subprocess_creationflags()
        assert isinstance(result, int)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only flag")
    def test_windows_has_create_no_window(self):
        result = _subprocess_creationflags()
        assert result == subprocess.CREATE_NO_WINDOW

    @pytest.mark.skipif(sys.platform == "win32", reason="Only on non-Windows")
    def test_non_windows_returns_zero(self):
        assert _subprocess_creationflags() == 0
