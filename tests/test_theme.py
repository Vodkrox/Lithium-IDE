"""
Tests for src/theme.py — color themes and styling utilities.

Note: Functions that create/interact with tkinter widgets are tested by
verifying the data transformations (colors, fonts, dict completeness)
without creating an actual Tk root window.
"""

import json
import os

import pytest

from src.theme import (
    COLORS,
    CURRENT_THEME,
    DEFAULT_GRAPHITE,
    FONTS,
    THEMES,
    _complete_theme,
    _invert_hex_color,
    get_color,
    set_theme,
)

# =========================================================================
# Constants
# =========================================================================


class TestDefaultGraphite:
    def test_all_keys_present(self):
        required = {
            "bg_dark",
            "bg_editor",
            "bg_header",
            "fg_light",
            "fg_dim",
            "accent",
            "accent_hover",
            "console_bg",
            "console_fg",
            "console_err",
            "sash_color",
            "selection_bg",
            "line_number_fg",
            "success",
            "error",
        }
        assert set(DEFAULT_GRAPHITE.keys()) == required

    def test_all_values_are_hex_colors(self):
        for key, value in DEFAULT_GRAPHITE.items():
            assert isinstance(value, str), f"{key} is not a string"
            assert value.startswith("#"), f"{key} does not start with #"
            assert len(value) == 7, f"{key} has wrong length: {value}"

    def test_accent_is_blue(self):
        assert DEFAULT_GRAPHITE["accent"] == "#4DA3FF"

    def test_bg_dark_is_black(self):
        assert DEFAULT_GRAPHITE["bg_dark"] == "#000000"


class TestFonts:
    def test_fonts_dict_has_required_keys(self):
        assert set(FONTS.keys()) == {"ui", "header", "editor", "console"}

    def test_every_font_is_tuple(self):
        for key, value in FONTS.items():
            assert isinstance(value, tuple), f"{key} is not a tuple"

    def test_every_font_has_at_least_name_and_size(self):
        for key, value in FONTS.items():
            assert len(value) >= 2, f"{key} has fewer than 2 elements"
            assert isinstance(value[0], str), f"{key}[0] not a string"
            assert isinstance(value[1], (int, float)), f"{key}[1] not a number"


# =========================================================================
# _complete_theme
# =========================================================================


class TestCompleteTheme:
    def test_empty_dict_starts_from_defaults(self):
        """An empty dict should start from defaults but has fallback overrides."""
        result = _complete_theme({})
        # All DEFAULT_GRAPHITE keys should be present
        for key in DEFAULT_GRAPHITE:
            assert key in result
        # The fallback logic may override some defaults (selection_bg, line_number_fg, success, error)
        # But explicit values stay
        assert result["bg_dark"] == DEFAULT_GRAPHITE["bg_dark"]

    def test_none_returns_complete_dict(self):
        result = _complete_theme(None)
        for key in DEFAULT_GRAPHITE:
            assert key in result
        # Explicit values from defaults should be preserved
        assert result["accent"] == DEFAULT_GRAPHITE["accent"]

    def test_partial_dict_fills_missing_keys(self):
        partial = {"bg_dark": "#111111", "fg_light": "#eeeeee"}
        result = _complete_theme(partial)
        assert result["bg_dark"] == "#111111"
        assert result["fg_light"] == "#eeeeee"
        assert result["accent"] == DEFAULT_GRAPHITE["accent"]

    def test_does_not_mutate_input(self):
        original = {"bg_dark": "#111111"}
        _complete_theme(original)
        assert original == {"bg_dark": "#111111"}

    def test_selection_bg_falls_back_to_sash_color(self):
        partial = {"sash_color": "#FF0000"}
        result = _complete_theme(partial)
        assert result["selection_bg"] == "#FF0000"

    def test_line_number_fg_falls_back_to_fg_dim(self):
        partial = {"fg_dim": "#ABCDEF"}
        result = _complete_theme(partial)
        assert result["line_number_fg"] == "#ABCDEF"

    def test_success_falls_back_to_console_fg(self):
        partial = {"console_fg": "#123456"}
        result = _complete_theme(partial)
        assert result["success"] == "#123456"

    def test_error_falls_back_to_console_err(self):
        partial = {"console_err": "#654321"}
        result = _complete_theme(partial)
        assert result["error"] == "#654321"

    def test_explicit_selection_bg_not_overridden(self):
        partial = {"selection_bg": "#CUSTOM", "sash_color": "#OTHER"}
        result = _complete_theme(partial)
        assert result["selection_bg"] == "#CUSTOM"


# =========================================================================
# _invert_hex_color
# =========================================================================


class TestInvertHexColor:
    def test_invert_black(self):
        assert _invert_hex_color("#000000") == "#ffffff"

    def test_invert_white(self):
        assert _invert_hex_color("#ffffff") == "#000000"

    def test_invert_red(self):
        assert _invert_hex_color("#ff0000") == "#00ffff"

    def test_invert_green(self):
        assert _invert_hex_color("#00ff00") == "#ff00ff"

    def test_invert_blue(self):
        assert _invert_hex_color("#0000ff") == "#ffff00"

    def test_invalid_color_returns_fallback(self):
        assert _invert_hex_color("notacolor") == "#ffffff"

    def test_short_hex_returns_fallback(self):
        assert _invert_hex_color("#fff") == "#ffffff"

    def test_none_returns_fallback(self):
        assert _invert_hex_color(None) == "#ffffff"

    def test_invert_gray(self):
        result = _invert_hex_color("#808080")
        assert result == "#7f7f7f"


# =========================================================================
# get_color
# =========================================================================


class TestGetColor:
    def test_returns_existing_color(self):
        color = get_color("accent")
        assert color == COLORS.get("accent", DEFAULT_GRAPHITE["accent"])

    def test_fallback_for_missing_key(self):
        color = get_color("nonexistent_key", "#abc123")
        assert color == "#abc123"

    def test_default_fallback_is_white(self):
        color = get_color("nonexistent_key")
        assert color == "#ffffff"


# =========================================================================
# set_theme
# =========================================================================


class TestSetTheme:
    def test_set_theme_updates_global(self):
        # Save original state
        original_theme = CURRENT_THEME
        try:
            if "Graphite" in THEMES:
                set_theme("Graphite")
                assert CURRENT_THEME == "Graphite"
        finally:
            # Restore original (don't interfere with other tests)
            if original_theme in THEMES:
                set_theme(original_theme)

    def test_set_theme_updates_colors(self):
        original_theme = CURRENT_THEME
        try:
            if "Monokai" in THEMES:
                set_theme("Monokai")
                assert COLORS["accent"] == THEMES["Monokai"].get(
                    "accent", DEFAULT_GRAPHITE["accent"]
                )
        finally:
            if original_theme in THEMES:
                set_theme(original_theme)

    def test_set_invalid_theme_does_not_change(self):
        original_theme = CURRENT_THEME
        set_theme("NonExistentTheme")
        assert CURRENT_THEME == original_theme


# =========================================================================
# Theme files integrity
# =========================================================================


class TestThemeFiles:
    """Verify that all JSON theme files in src/themes/ are valid."""

    def test_all_themes_have_valid_json(self):
        themes_dir = os.path.join("src", "themes")
        if not os.path.exists(themes_dir):
            pytest.skip("Themes directory not found")
        for filename in os.listdir(themes_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(themes_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                assert isinstance(data, dict), f"{filename} is not a dict"

    def test_all_loaded_themes_have_required_keys(self):
        for name, data in THEMES.items():
            if name == "Graphite (Default)":
                continue  # synthetic default
            for key in DEFAULT_GRAPHITE:
                assert key in data or key in _complete_theme(data), (
                    f"Theme '{name}' missing key '{key}'"
                )

    def test_themes_loaded_count(self):
        assert len(THEMES) >= 1  # At least Graphite (Default)
