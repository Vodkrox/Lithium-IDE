"""
Tests for src/settings.py — SettingsManager.
"""

import json
import os
import tempfile

import pytest

from src.settings import SettingsManager


@pytest.fixture
def temp_settings(monkeypatch, tmp_path):
    """Create a SettingsManager that writes to a temp directory."""
    monkeypatch.setattr(
        "src.settings.SettingsManager._get_settings_path",
        lambda self: os.path.join(str(tmp_path), "settings.json"),
    )
    manager = SettingsManager()
    # Reset to defaults after loading (temp file is fresh)
    manager.settings = dict(SettingsManager.DEFAULTS)
    return manager


class TestSettingsDefaults:
    def test_default_theme(self, temp_settings):
        assert temp_settings.get("theme") == "Graphite"

    def test_default_language(self, temp_settings):
        assert temp_settings.get("language") == "Python"

    def test_default_ai_level_mode(self, temp_settings):
        assert temp_settings.get("ai_level_mode") == "auto"

    def test_default_ai_level(self, temp_settings):
        assert temp_settings.get("ai_level") == "Medium"

    def test_all_defaults_present(self, temp_settings):
        for key, value in SettingsManager.DEFAULTS.items():
            assert temp_settings.get(key) == value, f"Default mismatch for {key}"

    def test_get_nonexistent_key_returns_none(self, temp_settings):
        assert temp_settings.get("nonexistent") is None


class TestSettingsSetAndGet:
    def test_set_string_value(self, temp_settings):
        temp_settings.set("theme", "Monokai")
        assert temp_settings.get("theme") == "Monokai"

    def test_set_bool_value(self, temp_settings):
        temp_settings.set("ai_skill_web_search", True)
        assert temp_settings.get("ai_skill_web_search") is True

    def test_set_none_value(self, temp_settings):
        temp_settings.set("last_file", "/path/to/file.py")
        assert temp_settings.get("last_file") == "/path/to/file.py"

    def test_set_overwrites(self, temp_settings):
        temp_settings.set("language", "JavaScript")
        temp_settings.set("language", "Rust")
        assert temp_settings.get("language") == "Rust"

    def test_get_with_custom_default(self, temp_settings):
        assert temp_settings.get("nonexistent", "fallback") == "fallback"

    def test_get_returns_saved_value_not_default(self, temp_settings):
        """If a value was saved, get() returns the saved value, not the default."""
        temp_settings.set("language", "Go")
        assert temp_settings.get("language") == "Go"


class TestSettingsPersistence:
    def test_save_and_load_preserves_values(self, temp_settings):
        temp_settings.set("theme", "Monokai")
        temp_settings.set("ai_skill_reasoning", True)
        temp_settings.set("last_folder", "/projects/myapp")
        temp_settings.save()

        # Simulate a fresh load
        temp_settings.load()
        assert temp_settings.get("theme") == "Monokai"
        assert temp_settings.get("ai_skill_reasoning") is True
        assert temp_settings.get("last_folder") == "/projects/myapp"

    def test_load_missing_file_does_not_crash(self, temp_settings):
        """Loading when no settings file exists should keep defaults."""
        # The temp file doesn't exist yet, load() should not raise
        temp_settings.load()
        assert temp_settings.get("theme") == "Graphite"

    def test_load_corrupted_json_uses_defaults(self, temp_settings, tmp_path):
        """A corrupt JSON file should not break the settings."""
        settings_path = os.path.join(str(tmp_path), "settings.json")
        with open(settings_path, "w") as f:
            f.write("{invalid json!!!}")
        temp_settings.load()
        assert temp_settings.get("theme") == "Graphite"

    def test_save_creates_file(self, temp_settings, tmp_path):
        filepath = os.path.join(str(tmp_path), "settings.json")
        assert not os.path.exists(filepath)
        temp_settings.save()
        assert os.path.exists(filepath)

    def test_saved_file_is_valid_json(self, temp_settings, tmp_path):
        filepath = os.path.join(str(tmp_path), "settings.json")
        temp_settings.save()
        with open(filepath, "r") as f:
            data = json.load(f)
        assert isinstance(data, dict)


class TestSettingsEdgeCases:
    def test_double_load_keeps_values(self, temp_settings):
        """Loading twice should not reset previously saved values."""
        temp_settings.set("language", "Rust")
        temp_settings.save()
        temp_settings.load()
        assert temp_settings.get("language") == "Rust"

    def test_non_dict_json_ignored(self, temp_settings, tmp_path):
        """If the JSON file contains a list (not dict), defaults are kept."""
        filepath = os.path.join(str(tmp_path), "settings.json")
        with open(filepath, "w") as f:
            json.dump(["not", "a", "dict"], f)
        temp_settings.load()
        assert temp_settings.get("theme") == "Graphite"

    def test_unknown_keys_in_file_are_loaded(self, temp_settings, tmp_path):
        """Extra keys in the JSON should be loaded into settings."""
        filepath = os.path.join(str(tmp_path), "settings.json")
        with open(filepath, "w") as f:
            json.dump({"custom_key": "custom_value"}, f)
        temp_settings.load()
        assert temp_settings.get("custom_key") == "custom_value"
