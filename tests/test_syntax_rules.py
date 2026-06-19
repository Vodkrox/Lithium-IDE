"""
Tests for src/syntax.py — syntax highlighting rules and token definitions.

Note: The SyntaxHighlighter class requires tkinter and is not tested here.
We test the language rules, token types, and color definitions which are
pure data / regex patterns.
"""

import re

import pytest

from src.syntax import (
    DEFAULT_TOKEN_COLORS,
    LANGUAGE_RULES,
    TOKEN_TYPES,
)

# =========================================================================
# LANGUAGE_RULES structure
# =========================================================================


class TestLanguageRulesStructure:
    def test_language_rules_is_dict(self):
        assert isinstance(LANGUAGE_RULES, dict)

    def test_has_expected_languages(self):
        expected = {
            "Python",
            "JavaScript",
            "TypeScript",
            "JSX",
            "TSX",
            "HTML",
            "CSS",
            "SCSS",
            "Sass",
            "Less",
            "Java",
            "C",
            "C++",
            "C#",
            "Objective-C",
            "Go",
            "Rust",
            "PHP",
            "Ruby",
            "SQL",
            "Bash",
            "Shell",
            "Zsh",
            "YAML",
            "Markdown",
            "JSON",
            "XML",
            "SVG",
        }
        assert set(LANGUAGE_RULES.keys()) == expected

    def test_every_language_has_list_of_tuples(self):
        for lang, rules in LANGUAGE_RULES.items():
            assert isinstance(rules, list), f"{lang} rules is not a list"
            for rule in rules:
                assert isinstance(rule, tuple), f"{lang} rule is not a tuple"
                assert len(rule) >= 2, f"{lang} rule length < 2"
                pattern, token_type = rule[0], rule[1]
                assert isinstance(pattern, str), f"{lang} pattern is not str"
                assert isinstance(token_type, str), f"{lang} token_type is not str"


# =========================================================================
# Regex compilation — all patterns must be valid
# =========================================================================


class TestRegexCompilation:
    """Every regex pattern in every language must compile without error."""

    def test_all_patterns_compile(self):
        for lang, rules in LANGUAGE_RULES.items():
            for rule in rules:
                pattern = rule[0]
                flags = rule[2] if len(rule) > 2 else 0
                try:
                    re.compile(pattern, flags)
                except re.error as e:
                    pytest.fail(f"{lang}: invalid regex {pattern!r}: {e}")

    def test_all_patterns_match_something(self):
        """Smoke: each pattern should at least compile and not be empty."""
        for lang, rules in LANGUAGE_RULES.items():
            for rule in rules:
                assert len(rule[0]) > 0, f"{lang} has empty pattern"

    def test_python_keywords_match(self):
        """Verify Python keyword patterns match actual keywords."""
        rules = LANGUAGE_RULES["Python"]
        keyword_pattern = None
        for rule in rules:
            if rule[1] == "keyword":
                keyword_pattern = re.compile(rule[0])
                break
        assert keyword_pattern is not None
        assert keyword_pattern.search("def foo():") is not None
        assert keyword_pattern.search("return True") is not None
        assert keyword_pattern.search("if x > 0:") is not None
        assert keyword_pattern.search("import os") is not None

    def test_python_comment_match(self):
        rules = LANGUAGE_RULES["Python"]
        comment_pattern = None
        for rule in rules:
            if rule[1] == "comment":
                comment_pattern = re.compile(rule[0])
                break
        assert comment_pattern is not None
        assert comment_pattern.search("# this is a comment") is not None

    def test_python_string_match(self):
        rules = LANGUAGE_RULES["Python"]
        string_patterns = []
        for rule in rules:
            if rule[1] == "string":
                string_patterns.append(re.compile(rule[0]))
        assert len(string_patterns) > 0
        for p in string_patterns:
            if p.search('"hello"'):
                break
        else:
            pytest.fail("No string pattern matched a simple double-quoted string")

    def test_javascript_comment_match(self):
        rules = LANGUAGE_RULES["JavaScript"]
        comment_patterns = []
        for rule in rules:
            if rule[1] == "comment":
                comment_patterns.append(re.compile(rule[0]))
        assert len(comment_patterns) > 0
        assert any(p.search("// line comment") for p in comment_patterns)
        assert any(p.search("/* block */") for p in comment_patterns)

    def test_html_tag_match(self):
        rules = LANGUAGE_RULES["HTML"]
        keyword_pattern = None
        for rule in rules:
            if rule[1] == "keyword":
                keyword_pattern = re.compile(rule[0])
                break
        assert keyword_pattern is not None
        assert keyword_pattern.search("<div>") is not None
        assert keyword_pattern.search("</div>") is not None
        assert keyword_pattern.search("<br />") is not None


# =========================================================================
# TOKEN_TYPES
# =========================================================================


class TestTokenTypes:
    def test_all_token_types_are_strings(self):
        for t in TOKEN_TYPES:
            assert isinstance(t, str)

    def test_token_types_are_unique(self):
        assert len(TOKEN_TYPES) == len(set(TOKEN_TYPES))

    def test_required_token_types_present(self):
        required = {"keyword", "string", "comment", "number", "function", "class"}
        for r in required:
            assert r in TOKEN_TYPES, f"Missing required token type: {r}"

    def test_every_rule_uses_defined_token_type(self):
        """Every rule's token_type must be in TOKEN_TYPES."""
        valid_types = set(TOKEN_TYPES)
        for lang, rules in LANGUAGE_RULES.items():
            for rule in rules:
                token_type = rule[1]
                assert token_type in valid_types, (
                    f"{lang} uses undefined token type: {token_type}"
                )


# =========================================================================
# DEFAULT_TOKEN_COLORS
# =========================================================================


class TestDefaultTokenColors:
    def test_all_colors_are_valid_hex(self):
        for token_type, color in DEFAULT_TOKEN_COLORS.items():
            assert isinstance(color, str), f"{token_type} color not str"
            assert color.startswith("#"), (
                f"{token_type} color {color} doesn't start with #"
            )
            assert len(color) == 7, f"{token_type} color {color} wrong length"

    def test_all_token_types_have_colors(self):
        for t in TOKEN_TYPES:
            assert t in DEFAULT_TOKEN_COLORS, f"Missing color for {t}"

    def test_no_extra_colors(self):
        for t in DEFAULT_TOKEN_COLORS:
            assert t in TOKEN_TYPES, f"Extra color for undefined token type {t}"
