"""
Tests for src/ai_powered/ai_skill_settings.py.
"""

import pytest

from src.ai_powered.ai_skill_settings import (
    DEFAULTS,
    FILE_SCOPE_OPTIONS,
    SETTINGS_KEYS,
    SKILL_TOGGLE_LABELS,
    AISkillSettings,
)


class MockSettingsManager:
    """A simple mock that stores values in memory."""

    def __init__(self):
        self._store = {}

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set(self, key, value):
        self._store[key] = value


@pytest.fixture
def skill_settings():
    mock = MockSettingsManager()
    return AISkillSettings(mock), mock


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    def test_file_scope_options_valid(self):
        options = dict(FILE_SCOPE_OPTIONS)
        assert "open_file" in options
        assert "workspace" in options

    def test_skill_toggle_labels_valid(self):
        labels = dict(SKILL_TOGGLE_LABELS)
        assert "web_search" in labels
        assert "reasoning" in labels
        assert "auto_approve" in labels

    def test_settings_keys_match_defaults(self):
        for key in DEFAULTS:
            assert key in SETTINGS_KEYS, f"Missing SETTINGS_KEYS entry for {key}"


# =========================================================================
# AISkillSettings — load
# =========================================================================


class TestLoad:
    def test_load_uses_defaults_when_no_stored_values(self, skill_settings):
        settings, _ = skill_settings
        settings.load()
        assert settings.get("file_scope") == "open_file"
        assert settings.get("web_search") is False
        assert settings.get("auto_approve") is False

    def test_load_reads_stored_values(self, skill_settings):
        settings, mock = skill_settings
        mock.set("ai_skill_file_scope", "workspace")
        mock.set("ai_skill_web_search", True)
        settings.load()
        assert settings.get("file_scope") == "workspace"
        assert settings.get("web_search") is True

    def test_load_invalid_file_scope_falls_back(self, skill_settings):
        settings, mock = skill_settings
        mock.set("ai_skill_file_scope", "invalid_scope")
        settings.load()
        assert settings.get("file_scope") == "open_file"


# =========================================================================
# AISkillSettings — get / set
# =========================================================================


class TestGetSet:
    def test_set_string_value(self, skill_settings):
        settings, mock = skill_settings
        settings.set("file_scope", "workspace")
        assert settings.get("file_scope") == "workspace"
        assert mock.get("ai_skill_file_scope") == "workspace"

    def test_set_bool_value(self, skill_settings):
        settings, mock = skill_settings
        settings.set("web_search", True)
        assert settings.get("web_search") is True
        assert mock.get("ai_skill_web_search") is True

    def test_set_invalid_file_scope_uses_default(self, skill_settings):
        settings, mock = skill_settings
        settings.set("file_scope", "not_valid")
        assert settings.get("file_scope") == "open_file"

    def test_set_non_bool_converted_to_bool(self, skill_settings):
        settings, mock = skill_settings
        settings.set("reasoning", "yes")  # truthy string
        assert settings.get("reasoning") is True
        assert mock.get("ai_skill_reasoning") is True

    def test_get_nonexistent_returns_default(self, skill_settings):
        settings, _ = skill_settings
        assert settings.get("nonexistent") is None

    def test_get_with_custom_default(self, skill_settings):
        settings, _ = skill_settings
        assert settings.get("nonexistent", "fallback") == "fallback"


# =========================================================================
# AISkillSettings — helpers
# =========================================================================


class TestHelpers:
    def test_is_workspace_scope_true(self, skill_settings):
        settings, _ = skill_settings
        settings.set("file_scope", "workspace")
        assert settings.is_workspace_scope() is True

    def test_is_workspace_scope_false(self, skill_settings):
        settings, _ = skill_settings
        settings.set("file_scope", "open_file")
        assert settings.is_workspace_scope() is False

    def test_active_count_with_no_skills(self, skill_settings):
        settings, _ = skill_settings
        settings.load()
        assert settings.active_count() == 0

    def test_active_count_with_one_skill(self, skill_settings):
        settings, _ = skill_settings
        settings.set("web_search", True)
        assert settings.active_count() >= 1

    def test_active_count_includes_workspace(self, skill_settings):
        settings, _ = skill_settings
        settings.set("file_scope", "workspace")
        assert settings.active_count() >= 1


# =========================================================================
# build_system_prompt_addendum
# =========================================================================


class TestBuildPromptAddendum:
    def test_open_file_scope_in_prompt(self, skill_settings):
        settings, _ = skill_settings
        settings.set("file_scope", "open_file")
        prompt = settings.build_system_prompt_addendum()
        assert "currently open file" in prompt

    def test_workspace_scope_in_prompt(self, skill_settings):
        settings, _ = skill_settings
        settings.set("file_scope", "workspace")
        prompt = settings.build_system_prompt_addendum()
        assert "project folder" in prompt

    def test_reasoning_in_prompt(self, skill_settings):
        settings, _ = skill_settings
        settings.set("reasoning", True)
        prompt = settings.build_system_prompt_addendum()
        assert "step by step" in prompt

    def test_explain_actions_in_prompt(self, skill_settings):
        settings, _ = skill_settings
        settings.set("explain_actions", True)
        prompt = settings.build_system_prompt_addendum()
        assert "explain what you are doing" in prompt

    def test_web_search_in_prompt(self, skill_settings):
        settings, _ = skill_settings
        settings.set("web_search", True)
        prompt = settings.build_system_prompt_addendum()
        assert "Web search" in prompt

    def test_run_commands_in_prompt(self, skill_settings):
        settings, _ = skill_settings
        settings.set("run_commands", True)
        prompt = settings.build_system_prompt_addendum()
        assert "Shell command" in prompt

    def test_auto_approve_in_prompt(self, skill_settings):
        settings, _ = skill_settings
        settings.set("auto_approve", True)
        prompt = settings.build_system_prompt_addendum()
        assert "automatically" in prompt

    def test_prompt_is_string(self, skill_settings):
        settings, _ = skill_settings
        result = settings.build_system_prompt_addendum()
        assert isinstance(result, str)

    def test_empty_when_no_skills(self, skill_settings):
        settings, _ = skill_settings
        settings.load()  # All defaults = disabled
        result = settings.build_system_prompt_addendum()
        assert "currently open file" in result  # Always has file scope
