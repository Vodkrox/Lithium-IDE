"""
Comprehensive tests for src/ai_powered/ai_level.py.

Covers every public function, edge case, and constant in the module.
"""

import pytest

from src.ai_powered.ai_level import (
    _RAM_THRESHOLDS_GB,
    AI_LEVELS,
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_URL,
    LEVEL_CONFIG,
    detect_ai_level_from_ram,
    format_billions_label,
    get_default_model,
    get_effective_level,
    get_inference_params,
    get_level_config,
    get_system_ram_gb,
    normalize_level,
)

# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    """Verify that module-level constants are well-defined."""

    def test_ai_levels_is_correct_list(self):
        assert AI_LEVELS == [
            "Ultra-Low",
            "Low",
            "Low-Medium",
            "Medium",
            "Medium-High",
            "High",
            "Ultra-High",
        ]

    def test_ai_levels_count(self):
        assert len(AI_LEVELS) == 7

    def test_ram_thresholds_count(self):
        """One threshold per level except the last (Ultra-High has no upper bound)."""
        assert len(_RAM_THRESHOLDS_GB) == len(AI_LEVELS) - 1

    def test_ram_thresholds_are_ascending(self):
        for i in range(1, len(_RAM_THRESHOLDS_GB)):
            assert _RAM_THRESHOLDS_GB[i] > _RAM_THRESHOLDS_GB[i - 1]

    def test_ram_thresholds_values(self):
        assert _RAM_THRESHOLDS_GB == [4, 8, 12, 16, 24, 63]

    def test_every_level_has_config(self):
        for level in AI_LEVELS:
            assert level in LEVEL_CONFIG, f"Missing config for {level}"

    def test_default_model_name_is_non_empty_string(self):
        assert isinstance(DEFAULT_MODEL_NAME, str)
        assert len(DEFAULT_MODEL_NAME) > 0

    def test_default_model_url_is_valid_url(self):
        assert isinstance(DEFAULT_MODEL_URL, str)
        assert DEFAULT_MODEL_URL.startswith("https://")
        assert ".gguf" in DEFAULT_MODEL_URL


# =========================================================================
# LEVEL_CONFIG structure
# =========================================================================


class TestLevelConfig:
    """Validate the structure of every level configuration entry."""

    REQUIRED_KEYS = {
        "billions",
        "max_tokens",
        "n_ctx",
        "n_batch",
        "n_threads",
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "frequency_penalty",
        "presence_penalty",
        "repeat_penalty",
        "repeat_last_n",
    }

    def test_all_levels_have_required_keys(self):
        for level, config in LEVEL_CONFIG.items():
            missing = self.REQUIRED_KEYS - set(config.keys())
            assert not missing, f"{level} is missing keys: {missing}"

    def test_all_levels_have_no_extra_keys(self):
        for level, config in LEVEL_CONFIG.items():
            extra = set(config.keys()) - self.REQUIRED_KEYS
            assert not extra, f"{level} has unexpected keys: {extra}"

    def test_billions_increase_with_level(self):
        billions = [LEVEL_CONFIG[level]["billions"] for level in AI_LEVELS]
        for i in range(1, len(billions)):
            assert billions[i] > billions[i - 1], (
                f"billions not strictly increasing at index {i}"
            )

    def test_billions_range(self):
        for level in AI_LEVELS:
            b = LEVEL_CONFIG[level]["billions"]
            assert 1 <= b <= 7, f"{level} billions={b} out of range [1, 7]"

    def test_max_tokens_increase_with_level(self):
        tokens = [LEVEL_CONFIG[level]["max_tokens"] for level in AI_LEVELS]
        for i in range(1, len(tokens)):
            assert tokens[i] > tokens[i - 1], (
                f"max_tokens not strictly increasing at index {i}"
            )

    def test_temperature_within_range(self):
        for level in AI_LEVELS:
            t = LEVEL_CONFIG[level]["temperature"]
            assert 0.0 < t < 1.0, f"{level} temperature={t} out of range (0, 1)"

    def test_repeat_penalty_within_range(self):
        for level in AI_LEVELS:
            rp = LEVEL_CONFIG[level]["repeat_penalty"]
            assert 1.0 <= rp <= 2.0, f"{level} repeat_penalty={rp} out of range [1, 2]"

    def test_n_threads_positive(self):
        for level in AI_LEVELS:
            assert LEVEL_CONFIG[level]["n_threads"] >= 1, f"{level} n_threads < 1"

    def test_n_ctx_positive(self):
        for level in AI_LEVELS:
            assert LEVEL_CONFIG[level]["n_ctx"] > 0, f"{level} n_ctx <= 0"

    def test_n_batch_positive(self):
        for level in AI_LEVELS:
            assert LEVEL_CONFIG[level]["n_batch"] > 0, f"{level} n_batch <= 0"


# =========================================================================
# detect_ai_level_from_ram
# =========================================================================


class TestDetectAiLevelFromRam:
    """Test mapping from RAM (GB) to AI level."""

    @pytest.mark.parametrize(
        "ram_gb,expected",
        [
            (0.0, "Ultra-Low"),
            (1.0, "Ultra-Low"),
            (4.0, "Ultra-Low"),
            (4.1, "Low"),
            (8.0, "Low"),
            (8.1, "Low-Medium"),
            (12.0, "Low-Medium"),
            (12.1, "Medium"),
            (16.0, "Medium"),
            (16.1, "Medium-High"),
            (24.0, "Medium-High"),
            (24.1, "High"),
            (63.0, "High"),
            (63.1, "Ultra-High"),
            (100.0, "Ultra-High"),
            (999.0, "Ultra-High"),
        ],
    )
    def test_with_various_ram_values(self, ram_gb, expected):
        assert detect_ai_level_from_ram(ram_gb) == expected

    def test_edge_case_zero_ram(self):
        """0 GB should still map to Ultra-Low (first threshold is 4)."""
        assert detect_ai_level_from_ram(0) == "Ultra-Low"

    def test_edge_case_negative_ram(self):
        """Negative RAM should map to Ultra-Low."""
        assert detect_ai_level_from_ram(-1) == "Ultra-Low"

    def test_none_ram_falls_back_to_system(self, monkeypatch):
        """When ram_gb=None, it should call get_system_ram_gb()."""
        monkeypatch.setattr("src.ai_powered.ai_level.get_system_ram_gb", lambda: 16.0)
        assert detect_ai_level_from_ram() == "Medium"

    def test_none_ram_and_system_fails_returns_medium(self, monkeypatch):
        """When ram_gb=None and get_system_ram_gb() returns None, return Medium."""
        monkeypatch.setattr("src.ai_powered.ai_level.get_system_ram_gb", lambda: None)
        assert detect_ai_level_from_ram() == "Medium"


# =========================================================================
# normalize_level
# =========================================================================


class TestNormalizeLevel:
    """Test level name normalization."""

    @pytest.mark.parametrize("level", AI_LEVELS)
    def test_valid_level_returns_unchanged(self, level):
        assert normalize_level(level) == level

    def test_invalid_level_returns_medium(self):
        assert normalize_level("Super-High") == "Medium"
        assert normalize_level("") == "Medium"
        assert normalize_level("UltraLow") == "Medium"

    def test_none_returns_medium(self):
        assert normalize_level(None) == "Medium"

    def test_case_sensitivity(self):
        """The function should be case-sensitive (only exact matches)."""
        assert normalize_level("ultra-low") == "Medium"
        assert normalize_level("ULTRA-LOW") == "Medium"


# =========================================================================
# get_level_config
# =========================================================================


class TestGetLevelConfig:
    """Test retrieving configuration for a level."""

    def test_returns_copy(self):
        """Should return a new dict, not the original reference."""
        config = get_level_config("Medium")
        config["billions"] = 999
        original = LEVEL_CONFIG["Medium"]["billions"]
        assert original == 4, "Mutation should not affect original LEVEL_CONFIG"

    def test_valid_level_keys_match(self):
        config = get_level_config("High")
        assert set(config.keys()) == {
            "billions",
            "max_tokens",
            "n_ctx",
            "n_batch",
            "n_threads",
            "temperature",
            "top_p",
            "top_k",
            "min_p",
            "frequency_penalty",
            "presence_penalty",
            "repeat_penalty",
            "repeat_last_n",
        }

    @pytest.mark.parametrize("level", AI_LEVELS)
    def test_all_valid_levels(self, level):
        config = get_level_config(level)
        assert config["billions"] == LEVEL_CONFIG[level]["billions"]

    def test_invalid_level_falls_back_to_medium(self):
        config = get_level_config("NonExistent")
        assert config["billions"] == 4  # Medium's billions
        assert config["max_tokens"] == 768  # Medium's max_tokens

    def test_none_falls_back_to_medium(self):
        config = get_level_config(None)
        assert config["billions"] == 4
        assert config["max_tokens"] == 768


# =========================================================================
# get_effective_level
# =========================================================================


class TestGetEffectiveLevel:
    """Test resolving the effective AI level from mode and manual override."""

    def test_auto_mode_uses_ram_detection(self, monkeypatch):
        monkeypatch.setattr(
            "src.ai_powered.ai_level.detect_ai_level_from_ram", lambda ram: "High"
        )
        assert get_effective_level("auto") == "High"

    def test_auto_mode_passes_ram_gb(self, monkeypatch):
        captured = []

        def fake_detect(ram):
            captured.append(ram)
            return "Medium"

        monkeypatch.setattr(
            "src.ai_powered.ai_level.detect_ai_level_from_ram", fake_detect
        )
        get_effective_level("auto", ram_gb=32.0)
        assert captured == [32.0]

    def test_manual_mode_with_valid_level(self):
        assert get_effective_level("manual", manual_level="Ultra-High") == "Ultra-High"

    def test_manual_mode_with_invalid_level_normalizes_to_medium(self):
        assert get_effective_level("manual", manual_level="Invalid") == "Medium"

    def test_manual_mode_without_manual_level_falls_back_to_auto(self, monkeypatch):
        """When mode='manual' but no level given, falls back to auto-detection."""
        monkeypatch.setattr(
            "src.ai_powered.ai_level.detect_ai_level_from_ram", lambda ram: "Low"
        )
        assert get_effective_level("manual") == "Low"

    def test_auto_mode_explicit(self):
        """'AUTO' with different casing should still work (case-insensitive mode)."""
        assert get_effective_level("AUTO") is not None

    def test_none_mode_auto_detects(self, monkeypatch):
        monkeypatch.setattr(
            "src.ai_powered.ai_level.detect_ai_level_from_ram", lambda ram: "Low"
        )
        assert get_effective_level(None) == "Low"

    def test_empty_string_mode_auto_detects(self, monkeypatch):
        monkeypatch.setattr(
            "src.ai_powered.ai_level.detect_ai_level_from_ram", lambda ram: "Low"
        )
        assert get_effective_level("") == "Low"

    def test_whitespace_mode_auto_detects(self, monkeypatch):
        monkeypatch.setattr(
            "src.ai_powered.ai_level.detect_ai_level_from_ram", lambda ram: "Low"
        )
        assert get_effective_level("  ") == "Low"


# =========================================================================
# get_default_model
# =========================================================================


class TestGetDefaultModel:
    """Test the default model getter."""

    def test_returns_tuple_of_two_strings(self):
        result = get_default_model()
        assert isinstance(result, tuple)
        assert len(result) == 2
        name, url = result
        assert isinstance(name, str)
        assert isinstance(url, str)

    def test_returns_expected_values(self):
        name, url = get_default_model()
        assert name == DEFAULT_MODEL_NAME
        assert url == DEFAULT_MODEL_URL

    def test_url_points_to_gguf_file(self):
        _, url = get_default_model()
        assert url.endswith(".gguf")


# =========================================================================
# get_inference_params
# =========================================================================


class TestGetInferenceParams:
    """Test inference parameter generation."""

    REQUIRED_PARAMS = {
        "max_tokens",
        "n_ctx",
        "n_batch",
        "n_threads",
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "frequency_penalty",
        "presence_penalty",
        "repeat_penalty",
        "repeat_last_n",
    }

    def test_returns_dict_with_all_required_keys(self):
        params = get_inference_params("Medium")
        assert set(params.keys()) == self.REQUIRED_PARAMS

    def test_returns_copy(self):
        params = get_inference_params("Medium")
        params["max_tokens"] = 999
        original = LEVEL_CONFIG["Medium"]["max_tokens"]
        assert original == 768, "Mutation should not affect original LEVEL_CONFIG"

    @pytest.mark.parametrize("level", AI_LEVELS)
    def test_params_match_level_config(self, level):
        params = get_inference_params(level)
        config = LEVEL_CONFIG[level]
        for key in self.REQUIRED_PARAMS:
            assert params[key] == config[key], (
                f"Mismatch for {level}.{key}: {params[key]} != {config[key]}"
            )

    def test_invalid_level_returns_medium_params(self):
        params = get_inference_params("NonExistent")
        assert params["max_tokens"] == 768  # Medium's max_tokens


# =========================================================================
# format_billions_label
# =========================================================================


class TestFormatBillionsLabel:
    """Test formatting the billions label for display."""

    @pytest.mark.parametrize(
        "level,expected",
        [
            ("Ultra-Low", "1B"),
            ("Low", "2B"),
            ("Low-Medium", "3B"),
            ("Medium", "4B"),
            ("Medium-High", "5B"),
            ("High", "6B"),
            ("Ultra-High", "7B"),
        ],
    )
    def test_all_levels(self, level, expected):
        assert format_billions_label(level) == expected

    def test_invalid_level_falls_back_to_medium(self):
        assert format_billions_label("NonExistent") == "4B"

    def test_returns_string(self):
        assert isinstance(format_billions_label("Low"), str)


# =========================================================================
# get_system_ram_gb (platform-dependent, lightweight smoke test)
# =========================================================================


class TestGetSystemRamGb:
    """Smoke tests for the system RAM detection function.

    These tests are intentionally light because the function calls OS-level APIs.
    We only verify that it returns something reasonable (or None) without crashing.
    """

    def test_returns_float_or_none(self):
        result = get_system_ram_gb()
        assert result is None or isinstance(result, (int, float))

    def test_if_returns_value_it_is_positive(self):
        result = get_system_ram_gb()
        if result is not None:
            assert result > 0

    def test_if_returns_value_it_is_reasonable(self):
        """A computer should have between 0.5 GB and 8192 GB of RAM."""
        result = get_system_ram_gb()
        if result is not None:
            assert 0.5 <= result <= 8192


# =========================================================================
# Integration: chain of calls
# =========================================================================


class TestIntegration:
    """Test that functions work together correctly."""

    def test_full_pipeline_with_manual_level(self):
        """From manual level to inference params."""
        level = get_effective_level("manual", manual_level="High")
        assert level == "High"
        params = get_inference_params(level)
        assert params["max_tokens"] == 1536
        assert params["n_threads"] == 6

    def test_full_pipeline_with_auto_level(self, monkeypatch):
        """From auto detection to billions label."""
        monkeypatch.setattr(
            "src.ai_powered.ai_level.detect_ai_level_from_ram", lambda ram: "Low-Medium"
        )
        level = get_effective_level("auto", ram_gb=10.0)
        assert level == "Low-Medium"
        label = format_billions_label(level)
        assert label == "3B"

    def test_normalize_then_config(self):
        """Invalid level → normalized to Medium → correct config."""
        config = get_level_config("Totally-Real-Level")
        assert config["billions"] == 4
        assert config["temperature"] == 0.45

    def test_all_levels_are_reachable(self):
        """Every AI_LEVELS entry can be used in a round-trip."""
        for level in AI_LEVELS:
            assert normalize_level(level) == level
            config = get_level_config(level)
            assert config["billions"] == LEVEL_CONFIG[level]["billions"]
            params = get_inference_params(level)
            assert params["n_ctx"] == LEVEL_CONFIG[level]["n_ctx"]
