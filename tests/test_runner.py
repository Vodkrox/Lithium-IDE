"""
Tests for src/runner.py — code execution management.

Note: run_code() requires tkinter (console_widget), so it's not tested here.
We test the process management functions with mocking.
"""

import subprocess
import threading
from unittest.mock import Mock, patch

import pytest

from src.runner import (
    _set_current_process,
    is_running,
    stop_code,
)


@pytest.fixture(autouse=True)
def reset_process():
    """Reset global process state before each test."""
    _set_current_process(None)
    yield
    _set_current_process(None)


class TestSetCurrentProcess:
    def test_set_none_makes_not_running(self):
        _set_current_process(None)
        assert is_running() is False

    def test_set_mock_process_makes_running(self):
        mock = Mock()
        mock.poll.return_value = None
        _set_current_process(mock)
        assert is_running() is True


class TestIsRunning:
    def test_no_process_returns_false(self):
        assert is_running() is False

    def test_finished_process_returns_false(self):
        mock = Mock()
        mock.poll.return_value = 0  # Process has finished
        _set_current_process(mock)
        assert is_running() is False

    def test_running_process_returns_true(self):
        mock = Mock()
        mock.poll.return_value = None  # Process is still running
        _set_current_process(mock)
        assert is_running() is True


class TestStopCode:
    def test_no_process_returns_false(self):
        assert stop_code() is False

    def test_finished_process_returns_false(self):
        mock = Mock()
        mock.poll.return_value = 0
        _set_current_process(mock)
        assert stop_code() is False
        mock.terminate.assert_not_called()

    def test_running_process_terminates(self):
        mock = Mock()
        mock.poll.return_value = None
        _set_current_process(mock)
        assert stop_code() is True
        mock.terminate.assert_called_once()

    def test_terminate_failure_falls_back_to_kill(self):
        mock = Mock()
        mock.poll.return_value = None
        mock.terminate.side_effect = Exception("terminate failed")
        _set_current_process(mock)
        assert stop_code() is True
        mock.kill.assert_called_once()

    def test_both_terminate_and_kill_fail_returns_false(self):
        mock = Mock()
        mock.poll.return_value = None
        mock.terminate.side_effect = Exception("fail")
        mock.kill.side_effect = Exception("kill fail too")
        _set_current_process(mock)
        assert stop_code() is False


class TestThreadSafety:
    def test_set_and_check_from_different_threads(self):
        """Verify basic concurrency (smoke test)."""
        results = []

        def worker():
            mock = Mock()
            mock.poll.return_value = None
            _set_current_process(mock)
            results.append(is_running())

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(timeout=5)
        assert len(results) == 1
        assert results[0] is True
