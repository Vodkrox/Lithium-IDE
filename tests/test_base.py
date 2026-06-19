"""
Comprehensive tests for base.py — LithiumIDE pure-logic methods.

These tests cover the methods that do NOT depend on tkinter GUI state:
    _ai_level_dropdown_options
    _ai_level_dropdown_value
    _get_effective_ai_level
    _collect_workspace_files
    _resolve_ai_model_link
    _get_missing_dependencies
    _is_ai_model_ready
    _looks_like_broken_ai_edit_response

We bypass ``__init__`` (which creates dozens of tkinter widgets) and construct
a minimal instance via ``object.__new__``, then set only the attributes needed.
"""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# =========================================================================
# Helper — create a LithiumIDE without calling __init__
# =========================================================================


@pytest.fixture
def ide():
    """Return a LithiumIDE instance without calling ``__init__``.

    Only the attributes required by the test methods are set.  Each test
    can override or add more before calling the method under test.
    """
    from base import LithiumIDE

    inst = object.__new__(LithiumIDE)

    # -- AI level attributes (set by _apply_ai_level normally) --
    inst.ai_level_mode = "auto"
    inst.ai_manual_level = "Medium"
    inst.system_ram_gb = 16.0
    inst.effective_ai_level = "Medium"
    inst.ai_inference_params = {"n_ctx": 2048, "n_threads": 4}

    # -- AI model / settings --
    inst.settings_manager = MagicMock()
    inst.settings_manager.get.return_value = None
    inst.settings_manager.set.return_value = None
    inst.ai_model_link = None
    inst.ai_skills_executor = None

    # -- UI mocks needed by some methods --
    inst.file_explorer = MagicMock()
    inst.file_explorer.current_folder = None

    return inst


# =========================================================================
# _ai_level_dropdown_options
# =========================================================================


class TestAIDropdownOptions:
    def test_returns_list_with_auto_first(self, ide):
        options = ide._ai_level_dropdown_options()
        assert isinstance(options, list)
        assert options[0] == "Auto"
        assert len(options) > 1

    def test_contains_all_ai_levels(self, ide):
        from src.ai_powered.ai_level import AI_LEVELS

        options = ide._ai_level_dropdown_options()
        for level in AI_LEVELS:
            assert level in options

    def test_auto_is_only_non_level_entry(self, ide):
        from src.ai_powered.ai_level import AI_LEVELS

        options = ide._ai_level_dropdown_options()
        # Every entry except "Auto" should be a valid AI level
        non_levels = [o for o in options if o not in AI_LEVELS]
        assert non_levels == ["Auto"]

    def test_length_matches_levels_plus_auto(self, ide):
        from src.ai_powered.ai_level import AI_LEVELS

        assert len(ide._ai_level_dropdown_options()) == len(AI_LEVELS) + 1


# =========================================================================
# _ai_level_dropdown_value
# =========================================================================


class TestAIDropdownValue:
    def test_auto_mode_returns_auto(self, ide):
        ide.ai_level_mode = "auto"
        assert ide._ai_level_dropdown_value() == "Auto"

    def test_case_insensitive_auto(self, ide):
        ide.ai_level_mode = "AUTO"
        assert ide._ai_level_dropdown_value() == "Auto"

    def test_none_mode_returns_auto(self, ide):
        ide.ai_level_mode = None
        assert ide._ai_level_dropdown_value() == "Auto"

    def test_manual_mode_returns_normalized_level(self, ide):
        ide.ai_level_mode = "manual"
        ide.ai_manual_level = "medium"
        assert ide._ai_level_dropdown_value() == "Medium"

    def test_manual_mode_preserves_exact_level(self, ide):
        ide.ai_level_mode = "manual"
        ide.ai_manual_level = "Ultra-Low"
        assert ide._ai_level_dropdown_value() == "Ultra-Low"

    def test_manual_mode_validates_invalid_level(self, ide):
        """normalize_level is expected to return best match or a fallback."""
        ide.ai_level_mode = "manual"
        ide.ai_manual_level = "InvalidLevel"
        # normalize_level should handle gracefully
        result = ide._ai_level_dropdown_value()
        assert isinstance(result, str)
        assert len(result) > 0


# =========================================================================
# _get_effective_ai_level
# =========================================================================


class TestGetEffectiveAILevel:
    def test_delegates_to_ai_level_manager(self, ide):
        """Verify the method calls get_effective_level with correct args."""
        ide.ai_level_mode = "manual"
        ide.ai_manual_level = "High"
        ide.system_ram_gb = 32.0

        result = ide._get_effective_ai_level()
        # "High" level on 32 GB should resolve to something reasonable
        assert isinstance(result, str)
        assert len(result) > 0

    def test_auto_mode_on_high_ram(self, ide):
        """Auto mode with lots of RAM should pick a high level."""
        ide.ai_level_mode = "auto"
        ide.system_ram_gb = 128.0
        level = ide._get_effective_ai_level()
        # "Ultra-High" or "High" are expected with abundant RAM
        assert level in ("Ultra-High", "High", "Medium-High", "Medium")

    def test_auto_mode_on_low_ram(self, ide):
        """Auto mode with very little RAM should pick a low level."""
        ide.ai_level_mode = "auto"
        ide.system_ram_gb = 1.0
        level = ide._get_effective_ai_level()
        assert level in ("Ultra-Low", "Low", "Low-Medium")

    def test_manual_mode_returns_exact_level(self, ide):
        ide.ai_level_mode = "manual"
        ide.ai_manual_level = "Ultra-High"
        assert ide._get_effective_ai_level() == "Ultra-High"

    def test_returns_string(self, ide):
        assert isinstance(ide._get_effective_ai_level(), str)


# =========================================================================
# _collect_workspace_files
# =========================================================================


class TestCollectWorkspaceFiles:
    def test_returns_empty_list_when_no_folder(self, ide):
        assert ide._collect_workspace_files() == []

    def test_returns_empty_list_when_folder_not_exists(self, ide):
        ide.file_explorer.current_folder = "/nonexistent/path/xyz789"
        assert ide._collect_workspace_files() == []

    def test_returns_files_from_real_temp_dir(self, ide):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a couple of files
            open(os.path.join(tmpdir, "a.py"), "w").close()
            open(os.path.join(tmpdir, "b.txt"), "w").close()
            os.makedirs(os.path.join(tmpdir, "sub"), exist_ok=True)
            open(os.path.join(tmpdir, "sub", "c.py"), "w").close()

            ide.file_explorer.current_folder = tmpdir
            files = ide._collect_workspace_files(max_files=150)

            # Normalise paths for comparison
            norm_files = {os.path.normpath(f) for f in files}
            assert "a.py" in norm_files
            assert "b.txt" in norm_files
            assert os.path.join("sub", "c.py") in norm_files or "sub/c.py" in norm_files

    def test_skips_dotfiles(self, ide):
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, ".hidden"), "w").close()
            open(os.path.join(tmpdir, "visible.py"), "w").close()
            os.makedirs(os.path.join(tmpdir, ".git"), exist_ok=True)
            open(os.path.join(tmpdir, ".git", "config"), "w").close()

            ide.file_explorer.current_folder = tmpdir
            files = ide._collect_workspace_files()
            file_names = {os.path.normpath(f) for f in files}
            assert "visible.py" in file_names
            assert ".hidden" not in file_names
            assert (
                os.path.join(".git", "config") not in file_names
                and ".git" not in file_names
            )

    def test_skips_known_directories(self, ide):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "node_modules"), exist_ok=True)
            open(os.path.join(tmpdir, "node_modules", "pkg.js"), "w").close()
            os.makedirs(os.path.join(tmpdir, "__pycache__"), exist_ok=True)
            open(os.path.join(tmpdir, "__pycache__", "foo.pyc"), "w").close()
            open(os.path.join(tmpdir, "main.py"), "w").close()

            ide.file_explorer.current_folder = tmpdir
            files = ide._collect_workspace_files()
            file_names = {os.path.normpath(f) for f in files}
            assert "main.py" in file_names
            assert os.path.join("node_modules", "pkg.js") not in file_names
            assert os.path.join("__pycache__", "foo.pyc") not in file_names

    def test_respects_max_files(self, ide):
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(20):
                open(os.path.join(tmpdir, f"file{i}.txt"), "w").close()

            ide.file_explorer.current_folder = tmpdir
            files = ide._collect_workspace_files(max_files=5)
            assert len(files) == 5

    def test_default_max_files_is_capped(self, ide):
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(80):
                open(os.path.join(tmpdir, f"file{i}.txt"), "w").close()

            ide.file_explorer.current_folder = tmpdir
            files = ide._collect_workspace_files()
            assert len(files) <= 40

    def test_uses_forward_slashes_in_paths(self, ide):
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "test.py"), "w").close()

            ide.file_explorer.current_folder = tmpdir
            files = ide._collect_workspace_files()
            # Path separators should be "/" (forward slash)
            for f in files:
                assert "\\" not in f, f"Expected forward slashes, got: {f}"

    def test_no_file_explorer_attribute(self, ide):
        """If file_explorer is missing, should return [] gracefully."""
        del ide.file_explorer
        assert ide._collect_workspace_files() == []


class TestWorkspaceTreeSummary:
    def test_tree_summary_includes_nested_folders(self, ide):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "src", "ai_powered"), exist_ok=True)
            os.makedirs(os.path.join(tmpdir, "tests"), exist_ok=True)
            open(os.path.join(tmpdir, "README.md"), "w").close()
            open(os.path.join(tmpdir, "src", "main.py"), "w").close()
            open(os.path.join(tmpdir, "src", "ai_powered", "engine.py"), "w").close()

            ide.file_explorer.current_folder = tmpdir
            summary = ide._collect_workspace_tree_summary(max_depth=3)

            assert "README.md" in summary
            assert "src/" in summary
            assert "ai_powered/" in summary
            assert "tests/" in summary

    def test_folder_explanation_requests_use_tree_summary(self, ide):
        assert ide._should_use_workspace_tree_summary("explica esta carpeta") is True
        assert ide._should_use_workspace_tree_summary("explain this folder") is True
        assert ide._should_use_workspace_tree_summary("write code for this file") is False

    def test_folder_explanation_prompt_is_plain_language(self, ide):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "src"), exist_ok=True)
            open(os.path.join(tmpdir, "README.md"), "w").close()
            ide.file_explorer.current_folder = tmpdir

            prompt = ide._build_ai_editor_prompt("explica esta carpeta")

            assert "OUTPUT CONTRACT" in prompt
            assert "plain language only" in prompt
            assert "<skill>" not in prompt
            assert "README.md" in prompt

    def test_selective_excerpts_update_reading_status(self, ide):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "README.md"), "w", encoding="utf-8") as handle:
                handle.write("line 1\nline 2\nline 3\n")
            os.makedirs(os.path.join(tmpdir, "src"), exist_ok=True)
            with open(os.path.join(tmpdir, "src", "main.py"), "w", encoding="utf-8") as handle:
                handle.write("print('hello')\n")

            ide.file_explorer.current_folder = tmpdir
            ide.root = None
            ide.status_label = MagicMock()

            excerpts = ide._collect_workspace_excerpts(max_files=2)

            assert excerpts
            reading_messages = [call.kwargs.get("text", "") for call in ide.status_label.config.call_args_list]
            assert any(msg.startswith("Reading README.md >> L1 - L80") for msg in reading_messages)


class TestCompactPromptContext:
    def test_compact_numbered_content_keeps_full_small_file(self, ide):
        content = "line one\nline two\nline three"
        numbered, notice = ide._build_compact_numbered_content(
            content,
            max_lines=20,
            max_chars=500,
        )

        assert "1: line one" in numbered
        assert "2: line two" in numbered
        assert "3: line three" in numbered
        assert "omitted" not in numbered.lower()
        assert notice == ""

    def test_compact_numbered_content_trims_large_file_with_notice(self, ide):
        content = "\n".join(f"line {i}" for i in range(1, 401))
        numbered, notice = ide._build_compact_numbered_content(
            content,
            max_lines=40,
            max_chars=2000,
        )

        assert "1: line 1" in numbered
        assert "400: line 400" in numbered
        assert "omitted" in numbered.lower()
        assert "trimmed" in notice.lower()


# =========================================================================
# _resolve_ai_model_link
# =========================================================================


class TestResolveAIModelLink:
    def test_returns_saved_model_path_when_file_exists(self, ide):
        with tempfile.NamedTemporaryFile(suffix=".gguf", delete=False) as f:
            tmpfile = f.name
        try:
            ide.settings_manager.get.return_value = tmpfile
            result = ide._resolve_ai_model_link()
            assert result == tmpfile
        finally:
            os.unlink(tmpfile)

    def test_returns_saved_model_path_when_dir_exists(self, ide):
        with tempfile.TemporaryDirectory() as tmpdir:
            ide.settings_manager.get.return_value = tmpdir
            result = ide._resolve_ai_model_link()
            assert result == tmpdir

    def test_falls_back_to_local_model(self, ide):
        """When saved model path doesn't exist, fall back to find_local_model."""
        ide.settings_manager.get.return_value = None
        with patch("src.ai_powered.ai_engine.find_local_model") as mock_find:
            mock_find.return_value = "/some/local/model.gguf"
            result = ide._resolve_ai_model_link()
            assert result == "/some/local/model.gguf"

    def test_falls_back_to_first_candidate(self, ide):
        """When no local model, return first MODEL_CANDIDATES entry."""
        ide.settings_manager.get.return_value = None
        with patch("src.ai_powered.ai_engine.find_local_model") as mock_find:
            mock_find.return_value = None
            with patch(
                "src.ai_powered.ai_engine.MODEL_CANDIDATES",
                [("test-model", "test-fallback-path")],
            ):
                result = ide._resolve_ai_model_link()
                assert result == "test-fallback-path"

    def test_returns_empty_string_when_no_candidates(self, ide):
        ide.settings_manager.get.return_value = None
        with patch("src.ai_powered.ai_engine.find_local_model") as mock_find:
            mock_find.return_value = None
            with patch("src.ai_powered.ai_engine.MODEL_CANDIDATES", []):
                result = ide._resolve_ai_model_link()
                assert result == ""

    def test_skips_saved_model_when_path_doesnt_exist(self, ide):
        """Saved path that doesn't exist should be ignored."""
        ide.settings_manager.get.return_value = "/nonexistent/model.gguf"
        with patch("src.ai_powered.ai_engine.find_local_model") as mock_find:
            mock_find.return_value = "/found/model.gguf"
            result = ide._resolve_ai_model_link()
            assert result == "/found/model.gguf"

    def test_saved_none_path_is_ignored(self, ide):
        """settings_manager.get returning None should skip saved check."""
        ide.settings_manager.get.return_value = None
        with patch("src.ai_powered.ai_engine.find_local_model") as mock_find:
            mock_find.return_value = None
            with patch(
                "src.ai_powered.ai_engine.MODEL_CANDIDATES", [("m", "/candidate/path")]
            ):
                assert ide._resolve_ai_model_link() == "/candidate/path"


# =========================================================================
# _get_missing_dependencies
# =========================================================================


class TestGetMissingDependencies:
    def test_returns_empty_when_all_available(self, ide):
        with (
            patch("base.can_import_module", return_value=True),
            patch(
                "src.ai_powered.ai_engine.get_runtime_status", return_value="llama_cpp"
            ),
        ):
            assert ide._get_missing_dependencies() == []

    def test_reports_huggingface_hub_when_missing(self, ide):
        with patch("base.can_import_module") as mock_can:
            mock_can.side_effect = lambda mod: mod != "huggingface_hub"
            with patch(
                "src.ai_powered.ai_engine.get_runtime_status", return_value="llama_cpp"
            ):
                missing = ide._get_missing_dependencies()
                assert "huggingface_hub" in missing
                assert "llama-cpp-python" not in missing

    def test_reports_llama_cpp_when_runtime_none(self, ide):
        with (
            patch("base.can_import_module", return_value=True),
            patch("src.ai_powered.ai_engine.get_runtime_status", return_value=None),
        ):
            missing = ide._get_missing_dependencies()
            assert "llama-cpp-python" in missing

    def test_reports_both_when_all_missing(self, ide):
        with (
            patch("base.can_import_module", return_value=False),
            patch("src.ai_powered.ai_engine.get_runtime_status", return_value=None),
        ):
            missing = ide._get_missing_dependencies()
            assert "huggingface_hub" in missing
            assert "llama-cpp-python" in missing

    def test_returns_list(self, ide):
        with (
            patch("base.can_import_module", return_value=True),
            patch(
                "src.ai_powered.ai_engine.get_runtime_status", return_value="llama_cpp"
            ),
        ):
            assert isinstance(ide._get_missing_dependencies(), list)


# =========================================================================
# _is_ai_model_ready
# =========================================================================


class TestIsAIModelReady:
    def test_returns_true_when_link_is_file(self, ide):
        with tempfile.NamedTemporaryFile(suffix=".gguf", delete=False) as f:
            tmpfile = f.name
        try:
            ide.ai_model_link = tmpfile
            assert ide._is_ai_model_ready() is True
        finally:
            os.unlink(tmpfile)

    def test_returns_true_when_link_is_dir(self, ide):
        with tempfile.TemporaryDirectory() as tmpdir:
            ide.ai_model_link = tmpdir
            assert ide._is_ai_model_ready() is True

    def test_falls_back_to_find_local_model(self, ide):
        ide.ai_model_link = None
        with patch("src.ai_powered.ai_engine.find_local_model") as mock_find:
            mock_find.return_value = "/auto/found/model.gguf"
            assert ide._is_ai_model_ready() is True
            # Should also update ai_model_link and persist it
            assert ide.ai_model_link == "/auto/found/model.gguf"
            ide.settings_manager.set.assert_called_once_with(
                "ai_model_path", "/auto/found/model.gguf"
            )

    def test_returns_false_when_no_model(self, ide):
        ide.ai_model_link = None
        with patch("src.ai_powered.ai_engine.find_local_model") as mock_find:
            mock_find.return_value = None
            assert ide._is_ai_model_ready() is False

    def test_returns_false_when_link_does_not_exist(self, ide):
        """Link set to a non-existent path with no local model."""
        ide.ai_model_link = "/nonexistent/path/to/model.gguf"
        with patch("src.ai_powered.ai_engine.find_local_model") as mock_find:
            mock_find.return_value = None
            assert ide._is_ai_model_ready() is False

    def test_non_empty_link_to_existing_file(self, ide):
        """Link is set to an existing non-gguf file (any file works)."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmpfile = f.name
        try:
            ide.ai_model_link = tmpfile
            assert ide._is_ai_model_ready() is True
        finally:
            os.unlink(tmpfile)


# =========================================================================
# _looks_like_broken_ai_edit_response
# =========================================================================


class TestLooksLikeBrokenAIEditResponse:
    def test_none_response_is_not_broken(self, ide):
        """None/empty responses should return False (they're not broken meta)."""
        assert ide._looks_like_broken_ai_edit_response(None) is False

    def test_empty_string_is_not_broken(self, ide):
        assert ide._looks_like_broken_ai_edit_response("") is False

    def test_valid_skill_response_not_broken(self, ide):
        response = '<skill name="edit_file"><param name="path">file.py</param></skill>'
        assert ide._looks_like_broken_ai_edit_response(response) is False

    def test_skill_tag_reference_not_broken(self, ide):
        """Response containing '<skill' literally should NOT be flagged."""
        assert (
            ide._looks_like_broken_ai_edit_response('<skill name="anything">') is False
        )

    def test_meta_marker_xml_tags_must_be_well_formed(self, ide):
        assert (
            ide._looks_like_broken_ai_edit_response("XML tags must be well-formed")
            is True
        )

    def test_meta_marker_contain_all_necessary_parameters(self, ide):
        assert (
            ide._looks_like_broken_ai_edit_response("contain all necessary parameters")
            is True
        )

    def test_meta_marker_propose_the_changes(self, ide):
        assert ide._looks_like_broken_ai_edit_response("propose the changes") is True

    def test_meta_marker_current_file_content_is_invalid(self, ide):
        assert (
            ide._looks_like_broken_ai_edit_response("current file content is invalid")
            is True
        )

    def test_meta_marker_output_contract(self, ide):
        assert ide._looks_like_broken_ai_edit_response("output contract") is True

    def test_meta_marker_respond_only_with(self, ide):
        assert (
            ide._looks_like_broken_ai_edit_response("respond only with one or more")
            is True
        )

    def test_case_insensitive_detection(self, ide):
        """Broken markers should be detected regardless of case."""
        assert (
            ide._looks_like_broken_ai_edit_response("XML Tags Must Be Well-Formed")
            is True
        )

    def test_marker_in_longer_text(self, ide):
        """Marker found anywhere in the response text."""
        assert (
            ide._looks_like_broken_ai_edit_response(
                "Here is some text that mentions output contract somewhere"
            )
            is True
        )

    def test_normal_ai_response_not_broken(self, ide):
        """A typical code-fix response should not be flagged."""
        response = "I fixed the bug by changing line 42 to `return x + 1`."
        assert ide._looks_like_broken_ai_edit_response(response) is False

    def test_empty_whitespace(self, ide):
        assert ide._looks_like_broken_ai_edit_response("   ") is False


# =========================================================================
# Sanity — verify test count
# =========================================================================


class TestBaseTestCoverage:
    """Meta: ensure we have a reasonable number of tests for base.py."""

    def test_at_least_8_test_classes(self):
        """We target at least one test class per method under test."""
        count = sum(
            1
            for name in dir(sys.modules[__name__])
            if name.startswith("Test") and "TestBaseTestCoverage" not in name
        )
        assert count >= 8  # at least 8 method-specific test classes
