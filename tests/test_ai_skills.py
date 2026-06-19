"""
Tests for src/ai_powered/ai_skills.py — AI skills parsing and preview.
"""

import os
from unittest.mock import Mock

import pytest

from src.ai_powered.ai_skills import (
    AISkillResult,
    AISkillsExecutor,
)

# =========================================================================
# AISkillResult
# =========================================================================


class TestAISkillResult:
    def test_success_result(self):
        r = AISkillResult(True, "OK")
        assert r.success is True
        assert r.message == "OK"
        assert r.data is None
        assert r.requires_approval is False

    def test_failure_result(self):
        r = AISkillResult(False, "Error occurred")
        assert r.success is False
        assert r.message == "Error occurred"

    def test_with_data(self):
        r = AISkillResult(True, "Created", data={"path": "/tmp/file.txt"})
        assert r.data["path"] == "/tmp/file.txt"

    def test_requires_approval(self):
        r = AISkillResult(True, "Needs approval", requires_approval=True)
        assert r.requires_approval is True

    def test_str_success(self):
        r = AISkillResult(True, "Done")
        assert "✓" in str(r)
        assert "Done" in str(r)

    def test_str_failure(self):
        r = AISkillResult(False, "Failed")
        assert "✗" in str(r)
        assert "Failed" in str(r)

    def test_is_modification_true(self):
        r = AISkillResult(True, "Modify", requires_approval=True)
        assert r.is_modification() is True

    def test_is_modification_false(self):
        r = AISkillResult(True, "Read only")
        assert r.is_modification() is False


# =========================================================================
# Test fixtures
# =========================================================================


@pytest.fixture
def executor():
    """Create an AISkillsExecutor with simple mock callbacks."""
    editor_getter = Mock(return_value="line1\nline2\nline3\n")
    editor_setter = Mock()
    file_path_getter = Mock(return_value="/project/main.py")
    project_folder_getter = Mock(return_value="/project")
    return AISkillsExecutor(
        editor_getter=editor_getter,
        editor_setter=editor_setter,
        file_path_getter=file_path_getter,
        project_folder_getter=project_folder_getter,
    )


@pytest.fixture
def executor_no_folder():
    """Executor without a project folder (no security restriction)."""
    return AISkillsExecutor(
        editor_getter=Mock(return_value="line1\nline2\n"),
        editor_setter=Mock(),
        file_path_getter=Mock(return_value="/tmp/test.py"),
        project_folder_getter=Mock(return_value=""),
    )


# =========================================================================
# XML parsing
# =========================================================================


class TestParseAndExecute:
    def test_parse_chat_skill_returns_success(self, executor):
        response = (
            '<skill name="respond_in_chat">'
            '<parameter name="content">Hello there!</parameter>'
            "</skill>"
        )
        results = executor.parse_and_execute(response)
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].message == "Hello there!"

    def test_empty_response_returns_empty(self, executor):
        results = executor.parse_and_execute("")
        assert results == []

    def test_response_with_no_skills_returns_empty(self, executor):
        results = executor.parse_and_execute("Hello, how can I help?")
        assert results == []

    def test_parse_add_lines(self, executor):
        response = (
            '<skill name="add_lines">'
            '<parameter name="line">2</parameter>'
            '<parameter name="content">new_line</parameter>'
            "</skill>"
        )
        results = executor.parse_and_execute(response)
        assert len(results) == 1
        assert results[0].success is True

    def test_parse_delete_lines(self, executor):
        response = (
            '<skill name="delete_lines">'
            '<parameter name="start">1</parameter>'
            '<parameter name="end">1</parameter>'
            "</skill>"
        )
        results = executor.parse_and_execute(response)
        assert len(results) == 1

    def test_parse_replace_file(self, executor):
        response = (
            '<skill name="replace_file">'
            '<parameter name="content">new content here</parameter>'
            "</skill>"
        )
        results = executor.parse_and_execute(response)
        assert len(results) == 1
        assert results[0].success is True
        executor.editor_setter.assert_called_once()

    def test_parse_unknown_skill(self, executor):
        response = (
            '<skill name="unknown_skill"><parameter name="foo">bar</parameter></skill>'
        )
        results = executor.parse_and_execute(response)
        assert len(results) == 1
        assert results[0].success is False
        assert "Unknown skill" in results[0].message

    def test_multiple_skills_executed_in_order(self, executor):
        response = (
            '<skill name="replace_file">'
            '<parameter name="content">new_content</parameter>'
            "</skill>"
            '<skill name="add_lines">'
            '<parameter name="line">1</parameter>'
            '<parameter name="content">first line</parameter>'
            "</skill>"
        )
        results = executor.parse_and_execute(response)
        assert len(results) == 2

    def test_skill_case_insensitivity(self, executor):
        response = (
            '<skill name="ADD_LINES">'
            '<parameter name="line">1</parameter>'
            '<parameter name="content">test</parameter>'
            "</skill>"
        )
        results = executor.parse_and_execute(response)
        assert len(results) == 1

    def test_insert_lines_alias(self, executor):
        response = (
            '<skill name="insert_lines">'
            '<parameter name="line">1</parameter>'
            '<parameter name="content">inserted</parameter>'
            "</skill>"
        )
        results = executor.parse_and_execute(response)
        assert len(results) == 1
        assert results[0].success is True


# =========================================================================
# get_clean_response
# =========================================================================


class TestGetCleanResponse:
    def test_chat_skill_text_is_preserved(self, executor):
        text = (
            '<skill name="respond_in_chat">'
            '<parameter name="content">Talk directly in chat.</parameter>'
            "</skill>"
        )
        assert executor.get_clean_response(text) == "Talk directly in chat."

    def test_html_break_tags_normalize_to_newlines(self, executor):
        text = "Line one</br>Line two<br/>Line three"
        assert executor.get_clean_response(text) == "Line one\nLine two\nLine three"

    def test_response_without_skills_unchanged(self, executor):
        text = "Hello! This is a regular response."
        assert executor.get_clean_response(text) == text

    def test_response_with_skills_preserves_text(self, executor):
        """Conversational text before/between skill blocks should be preserved."""
        text = (
            'Here are the changes:\n<skill name="add_lines">'
            '<parameter name="line">1</parameter>'
            '<parameter name="content">new</parameter>'
            "</skill>"
        )
        result = executor.get_clean_response(text)
        assert "Here are the changes" in result
        assert "<skill" not in result

    def test_pure_skill_response_returns_empty(self, executor):
        text = (
            '<skill name="replace_file">'
            '<parameter name="content">new</parameter>'
            "</skill>"
        )
        assert executor.get_clean_response(text) == ""

    def test_only_conversational_text_kept(self, executor):
        text = "Just a normal message without any skill tags."
        assert executor.get_clean_response(text) == text


# =========================================================================
# Preview functions
# =========================================================================


class TestPreviewAddLines:
    def test_add_lines_to_position(self, executor):
        params = {"line": "2", "content": "inserted_line"}
        result = executor._preview_add_lines_on_content("a\nb\nc\n", params)
        assert result.success is True
        assert "inserted_line" in result.data["new_content"]

    def test_add_lines_no_line_appends_to_end(self, executor):
        params = {"content": "new_last_line"}
        result = executor._preview_add_lines_on_content("a\nb\n", params)
        assert result.success is True
        assert result.data["new_content"].endswith("new_last_line\n")

    def test_add_lines_no_content_returns_failure(self, executor):
        params = {"line": "1"}
        result = executor._preview_add_lines_on_content("a\nb\n", params)
        assert result.success is False
        assert "No content" in result.message

    def test_add_lines_negative_line_goes_to_start(self, executor):
        params = {"line": "-5", "content": "first"}
        result = executor._preview_add_lines_on_content("a\nb\nc\n", params)
        assert result.success is True
        assert result.data["new_content"].startswith("first\n")


class TestPreviewDeleteLines:
    def test_delete_single_line(self, executor):
        params = {"line": "2", "count": "1"}
        result = executor._preview_delete_lines_on_content(
            "line1\nline2\nline3\n", params
        )
        assert result.success is True
        assert "line2" not in result.data["new_content"]

    def test_delete_range(self, executor):
        params = {"line": "1", "count": "2"}
        result = executor._preview_delete_lines_on_content("a\nb\nc\n", params)
        assert result.success is True
        assert result.data["new_content"] == "c\n"

    def test_delete_no_params_returns_failure(self, executor):
        params = {}
        result = executor._preview_delete_lines_on_content("a\nb\n", params)
        assert result.success is False


class TestPreviewReplaceFile:
    def test_replace_content(self, executor):
        params = {"content": "brand new content"}
        result = executor._preview_replace_file_on_content("old content\n", params)
        assert result.success is True
        assert result.data["new_content"] == "brand new content\n"

    def test_replace_adds_newline(self, executor):
        params = {"content": "no_newline"}
        result = executor._preview_replace_file_on_content("old\n", params)
        assert result.data["new_content"].endswith("\n")


# =========================================================================
# Path resolution and security
# =========================================================================


class TestResolvePath:
    def test_absolute_path_passthrough(self, executor):
        path, error = executor._resolve_path("/project/subdir/file.py")
        assert error is None
        assert path == "/project/subdir/file.py"

    def test_relative_path_resolved(self, executor):
        path, error = executor._resolve_path("subdir/file.py")
        assert error is None
        assert os.path.normpath(path) == os.path.normpath("/project/subdir/file.py")

    def test_empty_path_returns_error(self, executor):
        path, error = executor._resolve_path("")
        assert error == "No path provided"

    def test_none_path_returns_error(self, executor):
        path, error = executor._resolve_path(None)
        assert error == "No path provided"

    def test_outside_project_denied(self, executor):
        path, error = executor._resolve_path("/outside/file.txt")
        assert error is not None
        assert "Access denied" in error
        assert "outside project folder" in error

    def test_no_project_folder_allows_any_path(self, executor_no_folder):
        path, error = executor_no_folder._resolve_path("/anywhere/file.txt")
        assert error is None


class TestIsPathInProject:
    def test_within_project(self, executor):
        assert executor._is_path_in_project("/project/file.py") is True

    def test_subdirectory(self, executor):
        assert executor._is_path_in_project("/project/sub/file.py") is True

    def test_outside_project(self, executor):
        assert executor._is_path_in_project("/other/file.py") is False

    def test_no_project_folder_allows_all(self, executor_no_folder):
        assert executor_no_folder._is_path_in_project("/anywhere") is True


# =========================================================================
# get_available_skills
# =========================================================================


class TestGetAvailableSkills:
    def test_returns_list(self, executor):
        skills = executor.get_available_skills()
        assert isinstance(skills, list)

    def test_contains_expected_skills(self, executor):
        skills = executor.get_available_skills()
        assert "respond_in_chat" in skills
        assert "add_lines" in skills
        assert "delete_lines" in skills
        assert "replace_file" in skills
