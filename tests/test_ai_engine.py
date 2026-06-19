"""
Tests for src/ai_powered/ai_engine.py — AI engine functions.

We test only the pure-logic / no-hardware-dependent parts of the engine.
Functions that require llama_cpp, transformers, torch, or network access
are tested with mocking or skipped.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

from src.ai_powered.ai_engine import (
    DEFAULT_SYSTEM_PROMPT,
    _get_appdata_dir,
    _fit_prompt_to_context,
    _normalize_source,
    _subprocess_creationflags,
    clear_model_cache,
    find_local_model,
    get_models_dir,
    list_model_candidates,
    resolve_model_source,
)

# =========================================================================
# App data / models directories
# =========================================================================


class TestAppDataDir:
    def test_returns_absolute_path(self):
        result = _get_appdata_dir()
        assert os.path.isabs(result)

    def test_ends_with_lithiumide(self):
        result = _get_appdata_dir()
        assert result.endswith("LithiumIDE")

    def test_models_dir_ends_with_models(self):
        result = get_models_dir()
        assert result.endswith("models")
        assert "LithiumIDE" in result


# =========================================================================
# _normalize_source
# =========================================================================


class TestNormalizeSource:
    def test_none_returns_none(self):
        assert _normalize_source(None) is None

    def test_empty_string_returns_none(self):
        assert _normalize_source("") is None

    def test_whitespace_string_strips_to_empty(self):
        """Whitespace-only strings strip to empty string, not None."""
        assert _normalize_source("  ") == ""

    def test_normal_url_unchanged(self):
        url = "https://example.com/model.gguf"
        assert _normalize_source(url) == url

    def test_file_url_stripped(self):
        assert _normalize_source("file:///path/to/model") == "/path/to/model"

    def test_strips_whitespace(self):
        result = _normalize_source("  https://example.com  ")
        assert result == "https://example.com"

    def test_hf_url_preserved(self):
        url = "hf://author/model"
        assert _normalize_source(url) == url


# =========================================================================
# resolve_model_source (with mocking)
# =========================================================================


class TestResolveModelSource:
    def test_empty_source_raises_value_error(self):
        with pytest.raises(ValueError, match="No AI model source"):
            resolve_model_source("")

    def test_none_source_raises_value_error(self):
        with pytest.raises(ValueError, match="No AI model source"):
            resolve_model_source(None)

    def test_local_existing_path(self, tmp_path):
        model_file = tmp_path / "model.gguf"
        model_file.write_text("dummy content")
        result = resolve_model_source(str(model_file))
        assert result == str(model_file)

    def test_local_nonexistent_path_raises(self):
        with pytest.raises(FileNotFoundError, match="Local model not found"):
            resolve_model_source("/nonexistent/path/to/model.gguf")

    @patch("src.ai_powered.ai_engine._download_model_url")
    def test_http_url_calls_download(self, mock_download):
        mock_download.return_value = "/downloaded/model.gguf"
        result = resolve_model_source("https://example.com/model.gguf")
        mock_download.assert_called_once_with("https://example.com/model.gguf")
        assert result == "/downloaded/model.gguf"

    def test_hf_url_returns_target_dir_if_exists(self, monkeypatch, tmp_path):
        """hf:// URLs return the target directory if it already exists."""
        models_dir = tmp_path / "models"
        target_dir = models_dir / "author-model"
        target_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "src.ai_powered.ai_engine.get_models_dir",
            lambda: str(models_dir),
        )
        result = resolve_model_source("hf://author/model")
        assert result == str(target_dir)

    def test_hf_url_raises_if_not_downloaded(self, monkeypatch, tmp_path):
        """hf:// URLs raise FileNotFoundError if the model hasn't been downloaded."""
        monkeypatch.setattr(
            "src.ai_powered.ai_engine.get_models_dir",
            lambda: str(tmp_path / "models"),
        )
        with pytest.raises(FileNotFoundError, match="has not been downloaded"):
            resolve_model_source("hf://author/model")


# =========================================================================
# list_model_candidates
# =========================================================================


class TestListModelCandidates:
    def test_returns_list(self):
        result = list_model_candidates()
        assert isinstance(result, list)

    def test_first_item_is_tuple_of_two_strings(self):
        result = list_model_candidates()
        if result:
            name, url = result[0]
            assert isinstance(name, str)
            assert isinstance(url, str)


# =========================================================================
# clear_model_cache
# =========================================================================


class TestClearModelCache:
    def test_does_not_raise(self):
        """clear_model_cache should never raise, even if cache is empty."""
        clear_model_cache()


# =========================================================================
# _subprocess_creationflags
# =========================================================================


class TestSubprocessCreationFlags:
    def test_returns_int(self):
        result = _subprocess_creationflags()
        assert isinstance(result, int)


# =========================================================================
# DEFAULT_SYSTEM_PROMPT
# =========================================================================


class TestDefaultSystemPrompt:
    def test_is_string(self):
        assert isinstance(DEFAULT_SYSTEM_PROMPT, str)

    def test_contains_key_instructions(self):
        assert "expert code-editing assistant" in DEFAULT_SYSTEM_PROMPT
        assert "Lithium IDE" in DEFAULT_SYSTEM_PROMPT
        assert "<skill>" in DEFAULT_SYSTEM_PROMPT

    def test_is_reasonably_long(self):
        assert len(DEFAULT_SYSTEM_PROMPT) > 100


# =========================================================================
# _fit_prompt_to_context
# =========================================================================


class TestFitPromptToContext:
    def test_short_prompt_remains_unchanged(self):
        system_prompt = "system"
        user_prompt = "user"
        sys_out, user_out, max_tokens = _fit_prompt_to_context(
            system_prompt, user_prompt, max_tokens=64, n_ctx=512
        )
        assert sys_out == system_prompt
        assert user_out == user_prompt
        assert max_tokens == 64

    def test_long_prompt_is_trimmed(self):
        system_prompt = "system"
        user_prompt = "x" * 20000
        _, user_out, max_tokens = _fit_prompt_to_context(
            system_prompt, user_prompt, max_tokens=1536, n_ctx=4096
        )
        assert "trimmed to fit the model context window" in user_out
        assert len(user_out) < len(user_prompt)
        assert max_tokens < 1536


# =========================================================================
# find_local_model
# =========================================================================


class TestFindLocalModel:
    def test_no_models_dir_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "src.ai_powered.ai_engine.get_models_dir",
            lambda: str(tmp_path / "nonexistent"),
        )
        result = find_local_model()
        assert result is None

    def test_empty_models_dir_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "src.ai_powered.ai_engine.get_models_dir", lambda: str(tmp_path)
        )
        result = find_local_model()
        assert result is None

    def test_finds_gguf_file(self, tmp_path, monkeypatch):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        model_file = models_dir / "my_model.gguf"
        model_file.write_text("dummy")
        monkeypatch.setattr(
            "src.ai_powered.ai_engine.get_models_dir", lambda: str(models_dir)
        )
        result = find_local_model()
        assert result == str(model_file)

    def test_finds_gguf_file_in_subdirectory(self, tmp_path, monkeypatch):
        models_dir = tmp_path / "models"
        subdir = models_dir / "subfolder"
        subdir.mkdir(parents=True)
        model_file = subdir / "nested.gguf"
        model_file.write_text("dummy")
        monkeypatch.setattr(
            "src.ai_powered.ai_engine.get_models_dir", lambda: str(models_dir)
        )
        result = find_local_model()
        assert result == str(model_file)

    def test_ignores_non_gguf_files(self, tmp_path, monkeypatch):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "model.bin").write_text("dummy")
        monkeypatch.setattr(
            "src.ai_powered.ai_engine.get_models_dir", lambda: str(models_dir)
        )
        result = find_local_model()
        assert result is None
