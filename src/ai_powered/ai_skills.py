"""
AI Skills Module - Provides file and editor manipulation capabilities for the AI assistant.

This module defines a set of "skills" that the AI can use to manipulate files and code:
- add_lines / insert_lines: Insert lines at a specific position in the editor
- delete_lines / remove_lines: Delete lines from the editor
- edit_lines: Replace specific lines with new content (more efficient than delete+add)
- find_replace: Search and replace specific text in the file
- insert_at_cursor: Insert content at a position identified by a search string
- append_lines: Append lines to the end of the file
- replace_file / overwrite_file: Replace the entire file content
- create_file: Create a new file with content
- delete_file: Delete a file
- create_folder: Create a new folder
- delete_folder: Delete a folder (and its contents)

The AI responses are parsed for special XML-like tags that indicate skill usage:
<skill name="skill_name">
  <parameter name="param1">value1</parameter>
  <parameter name="param2">value2</parameter>
  ...
</skill>
"""

import os
import re
from typing import Any, Callable, Dict, List, Optional


class AISkillResult:
    """Represents the result of executing an AI skill."""

    def __init__(
        self,
        success: bool,
        message: str,
        data: Any = None,
        requires_approval: bool = False,
    ):
        self.success = success
        self.message = message
        self.data = data
        self.requires_approval = requires_approval

    def __str__(self):
        status = "✓" if self.success else "✗"
        return f"{status} {self.message}"

    def is_modification(self) -> bool:
        """Check if this skill modifies files or code."""
        return self.requires_approval


class AISkillsExecutor:
    """
    Executes AI skills for file and editor manipulation.

    The executor maintains a set of registered skills and can parse
    AI responses to find and execute skill invocations.

    All file operations are restricted to the project folder for security.
    """

    def __init__(
        self,
        editor_getter: Callable,
        editor_setter: Callable,
        file_path_getter: Callable,
        project_folder_getter: Optional[Callable] = None,
        status_callback: Optional[Callable] = None,
    ):
        """
        Initialize the AI Skills Executor.

        Args:
            editor_getter: Function that returns the current editor content as a string
            editor_setter: Function that sets the editor content (receives a string)
            file_path_getter: Function that returns the current file path
            project_folder_getter: Function that returns the project folder path (for security restrictions)
            status_callback: Optional function to call with status updates
        """
        self.editor_getter = editor_getter
        self.editor_setter = editor_setter
        self.file_path_getter = file_path_getter
        self.project_folder_getter = project_folder_getter
        self.status_callback = status_callback
        self.file_scope = "open_file"
        self.allow_run_commands = False

        self._skills = {
            "add_lines": self._skill_add_lines,
            "delete_lines": self._skill_delete_lines,
            "insert_lines": self._skill_add_lines,
            "remove_lines": self._skill_delete_lines,
            "replace_file": self._skill_replace_file,
            "overwrite_file": self._skill_replace_file,
            "edit_lines": self._skill_edit_lines,
            "find_replace": self._skill_find_replace,
            "insert_at_cursor": self._skill_insert_at_cursor,
            "append_lines": self._skill_append_lines,
        }

    def _log(self, message: str):
        """Log a status message if callback is available."""
        if self.status_callback:
            self.status_callback(message)

    def _get_project_folder(self) -> str:
        """Get the project folder path. Returns empty string if not set."""
        if self.project_folder_getter:
            return self.project_folder_getter() or ""
        return ""

    def _is_path_in_project(self, path: str) -> bool:
        """Check if a path is within the project folder for security."""
        project_folder = self._get_project_folder()
        if not project_folder:
            return True

        abs_path = os.path.abspath(path)
        abs_project = os.path.abspath(project_folder)

        return abs_path.startswith(abs_project + os.sep) or abs_path == abs_project

    def _resolve_path(self, path: str) -> tuple:
        """
        Resolve a path and check if it's within the project folder.
        Returns (resolved_path, error_message) - error_message is None if valid.
        """
        if not path:
            return None, "No path provided"

        if not os.path.isabs(path):
            project_folder = self._get_project_folder()
            if project_folder:
                path = os.path.join(project_folder, path)
            else:
                current_file = self.file_path_getter()
                if current_file:
                    path = os.path.join(os.path.dirname(current_file), path)
                else:
                    path = os.path.join(os.getcwd(), path)

        if not self._is_path_in_project(path):
            return (
                path,
                f"Access denied: path is outside project folder ({self._get_project_folder()})",
            )

        return path, None

    def _get_line_count(self) -> int:
        """Get the current number of lines in the editor."""
        content = self.editor_getter()
        if not content:
            return 0
        return len(content.splitlines())

    # ------------------------------------------------------------------
    # Content validation
    # ------------------------------------------------------------------

    def _warn_if_empty(self, content: str, skill_name: str = "") -> None:
        """Log a warning if the resulting content is empty after a modification.

        For replace_file, an empty result may be intentional so no warning is issued.
        For other modification skills, emptying the file is likely unintended.
        """
        if not content or content.strip() == "":
            if skill_name != "replace_file":
                self._log(f"Warning: Resulting content is empty after '{skill_name}'")

    # ------------------------------------------------------------------
    # Preview helpers (operate on explicit content for sequential simulation)
    # ------------------------------------------------------------------

    def _preview_add_lines_on_content(
        self, current_content: str, params: Dict[str, str]
    ) -> AISkillResult:
        """Preview adding lines against explicit content.

        This is used by parse_for_preview to simulate multiple AI skills in order.
        Without sequential simulation, a delete_lines followed by add_lines could be
        previewed against the original file twice and reintroduce deleted content.
        """
        line_num = params.get("line")
        content = params.get("content", "")

        if not content:
            return AISkillResult(False, "No content provided for add_lines")

        lines = current_content.splitlines(keepends=True)

        if line_num:
            try:
                line_idx = int(line_num) - 1
                if line_idx < 0:
                    line_idx = 0
                elif line_idx > len(lines):
                    line_idx = len(lines)
            except ValueError:
                return AISkillResult(False, f"Invalid line number: {line_num}")
        else:
            line_idx = len(lines)

        insert_content = content.rstrip("\n") + "\n"
        if line_idx == len(lines) and lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"

        lines.insert(line_idx, insert_content)
        new_content = "".join(lines)

        return AISkillResult(
            True,
            f"Add {len(content.splitlines())} line(s) at line {line_idx + 1}",
            data={"new_content": new_content, "original_content": current_content},
            requires_approval=True,
        )

    def _preview_delete_lines_on_content(
        self, current_content: str, params: Dict[str, str]
    ) -> AISkillResult:
        """Preview deleting lines against explicit content for sequential simulation."""
        lines_to_delete = params.get("lines")
        start_line = params.get("line")
        count = params.get("count", "1")

        lines = current_content.splitlines(keepends=True)
        total_lines = len(lines)

        line_nums_to_delete = []
        if lines_to_delete:
            try:
                line_nums_to_delete = [
                    int(l.strip()) - 1 for l in lines_to_delete.split(",")
                ]
                line_nums_to_delete = [
                    l for l in line_nums_to_delete if 0 <= l < total_lines
                ]
            except ValueError:
                return AISkillResult(False, f"Invalid line numbers: {lines_to_delete}")
        elif start_line:
            try:
                start_idx = int(start_line) - 1
                delete_count = int(count)
                if start_idx < 0 or start_idx >= total_lines:
                    return AISkillResult(
                        False, f"Start line {start_line} is out of range"
                    )
                end_idx = min(start_idx + delete_count, total_lines)
                line_nums_to_delete = list(range(start_idx, end_idx))
            except ValueError:
                return AISkillResult(
                    False, f"Invalid line or count: {start_line}, {count}"
                )
        else:
            return AISkillResult(False, "No line specification provided")

        new_lines = [
            line for i, line in enumerate(lines) if i not in line_nums_to_delete
        ]
        new_content = "".join(new_lines)

        return AISkillResult(
            True,
            f"Delete {len(line_nums_to_delete)} line(s)",
            data={"new_content": new_content, "original_content": current_content},
            requires_approval=True,
        )

    def _preview_replace_file_on_content(
        self, current_content: str, params: Dict[str, str]
    ) -> AISkillResult:
        """Preview replacing the entire editor content."""
        content = params.get("content", "")
        if content is None:
            return AISkillResult(False, "No content provided for replace_file")

        new_content = content
        if not new_content.endswith("\n"):
            new_content += "\n"

        return AISkillResult(
            True,
            "Replace entire file content",
            data={"new_content": new_content, "original_content": current_content},
            requires_approval=True,
        )

    def _preview_edit_lines_on_content(
        self, current_content: str, params: Dict[str, str]
    ) -> AISkillResult:
        """Preview replacing specific lines with new content for sequential simulation."""
        line_num = params.get("line")
        content = params.get("content", "")
        count = params.get("count", "1")

        if not content:
            return AISkillResult(False, "No content provided for edit_lines")
        if not line_num:
            return AISkillResult(False, "No line number provided for edit_lines")

        lines = current_content.splitlines(keepends=True)
        total_lines = len(lines)

        try:
            start_idx = int(line_num) - 1
            replace_count = int(count)
            if start_idx < 0:
                start_idx = 0
            if start_idx >= total_lines:
                return AISkillResult(False, f"Start line {line_num} is out of range")
            end_idx = min(start_idx + replace_count, total_lines)
        except ValueError:
            return AISkillResult(False, f"Invalid line or count: {line_num}, {count}")

        del lines[start_idx:end_idx]

        insert_content = content
        if start_idx < len(lines) and not insert_content.endswith("\n"):
            insert_content += "\n"
        elif start_idx == len(lines) and lines and not lines[-1].endswith("\n"):
            if insert_content and not insert_content.startswith("\n"):
                insert_content = "\n" + insert_content

        lines.insert(start_idx, insert_content)
        new_content = "".join(lines)

        return AISkillResult(
            True,
            f"Edit lines at position {start_idx + 1}",
            data={"new_content": new_content, "original_content": current_content},
            requires_approval=True,
        )

    def _preview_find_replace_on_content(
        self, current_content: str, params: Dict[str, str]
    ) -> AISkillResult:
        """Preview find and replace for sequential simulation."""
        find = params.get("find")
        replace = params.get("replace", "")

        if not find:
            return AISkillResult(False, "No search text provided for find_replace")

        if find not in current_content:
            return AISkillResult(False, f"Text not found: {find[:50]}...")

        new_content = current_content.replace(find, replace)

        return AISkillResult(
            True,
            "Replace text",
            data={"new_content": new_content, "original_content": current_content},
            requires_approval=True,
        )

    def _preview_insert_at_cursor_on_content(
        self, current_content: str, params: Dict[str, str]
    ) -> AISkillResult:
        """Preview inserting content after a search string for sequential simulation."""
        after = params.get("after")
        content = params.get("content", "")

        if not after:
            return AISkillResult(
                False, "No insertion point text provided for insert_at_cursor"
            )
        if not content:
            return AISkillResult(False, "No content provided for insert_at_cursor")

        lines = current_content.splitlines(keepends=True)

        target_line_idx = -1
        for i, line in enumerate(lines):
            if after in line:
                target_line_idx = i
                break

        if target_line_idx == -1:
            return AISkillResult(False, f"Insertion point not found: {after[:50]}...")

        insert_idx = target_line_idx + 1
        insert_content = content
        if insert_idx < len(lines) and not insert_content.endswith("\n"):
            insert_content += "\n"
        elif insert_idx == len(lines) and lines and not lines[-1].endswith("\n"):
            if insert_content and not insert_content.startswith("\n"):
                insert_content = "\n" + insert_content

        lines.insert(insert_idx, insert_content)
        new_content = "".join(lines)

        return AISkillResult(
            True,
            f"Insert content after '{after[:50]}'",
            data={"new_content": new_content, "original_content": current_content},
            requires_approval=True,
        )

    def _preview_append_lines_on_content(
        self, current_content: str, params: Dict[str, str]
    ) -> AISkillResult:
        """Preview appending lines to the end for sequential simulation."""
        content = params.get("content", "")

        if not content:
            return AISkillResult(False, "No content provided for append_lines")

        new_content = current_content
        if new_content and not new_content.endswith("\n"):
            new_content += "\n"
        if not content.endswith("\n"):
            content += "\n"
        new_content += content

        return AISkillResult(
            True,
            "Append lines to end",
            data={"new_content": new_content, "original_content": current_content},
            requires_approval=True,
        )

    # ------------------------------------------------------------------
    # Public preview methods
    # ------------------------------------------------------------------

    def preview_add_lines(self, params: Dict[str, str]) -> AISkillResult:
        """
        Preview adding lines to the editor (without applying).
        Returns the proposed new content for approval.
        """
        return self._preview_add_lines_on_content(self.editor_getter(), params)

    def preview_edit_lines(self, params: Dict[str, str]) -> AISkillResult:
        """
        Preview replacing lines in the editor (without applying).
        Returns the proposed new content for approval.
        """
        return self._preview_edit_lines_on_content(self.editor_getter(), params)

    def apply_add_lines(self, new_content: str) -> AISkillResult:
        """Apply the approved add_lines change."""
        self.editor_setter(new_content)
        lines = new_content.splitlines()
        self._log(f"Added lines")
        return AISkillResult(True, f"Successfully added lines")

    def preview_delete_lines(self, params: Dict[str, str]) -> AISkillResult:
        """Preview deleting lines (without applying)."""
        return self._preview_delete_lines_on_content(self.editor_getter(), params)

    def preview_replace_file(self, params: Dict[str, str]) -> AISkillResult:
        """Preview replacing the entire current file content."""
        return self._preview_replace_file_on_content(self.editor_getter(), params)

    def preview_create_file(self, params: Dict[str, str]) -> AISkillResult:
        """Preview creating a file (without applying)."""
        path = params.get("path")
        content = params.get("content", "")

        if not path:
            return AISkillResult(False, "No file path provided")

        resolved_path, error = self._resolve_path(path)
        if error:
            return AISkillResult(False, error)

        return AISkillResult(
            True,
            f"Create file: {os.path.basename(resolved_path)}",
            data={"path": resolved_path, "content": content},
            requires_approval=True,
        )

    def preview_delete_file(self, params: Dict[str, str]) -> AISkillResult:
        """Preview deleting a file (without applying)."""
        path = params.get("path")
        if not path:
            return AISkillResult(False, "No file path provided")

        resolved_path, error = self._resolve_path(path)
        if error:
            return AISkillResult(False, error)

        if not os.path.isfile(resolved_path):
            return AISkillResult(
                False, f"File not found: {os.path.basename(resolved_path)}"
            )

        return AISkillResult(
            True,
            f"Delete file: {os.path.basename(resolved_path)}",
            data={"path": resolved_path},
            requires_approval=True,
        )

    def preview_create_folder(self, params: Dict[str, str]) -> AISkillResult:
        """Preview creating a folder (without applying)."""
        path = params.get("path")
        if not path:
            return AISkillResult(False, "No folder path provided")

        resolved_path, error = self._resolve_path(path)
        if error:
            return AISkillResult(False, error)

        return AISkillResult(
            True,
            f"Create folder: {os.path.basename(resolved_path)}",
            data={"path": resolved_path},
            requires_approval=True,
        )

    def preview_delete_folder(self, params: Dict[str, str]) -> AISkillResult:
        """Preview deleting a folder (without applying)."""
        path = params.get("path")
        if not path:
            return AISkillResult(False, "No folder path provided")

        resolved_path, error = self._resolve_path(path)
        if error:
            return AISkillResult(False, error)

        if not os.path.isdir(resolved_path):
            return AISkillResult(
                False, f"Folder not found: {os.path.basename(resolved_path)}"
            )

        return AISkillResult(
            True,
            f"Delete folder: {os.path.basename(resolved_path)}",
            data={"path": resolved_path},
            requires_approval=True,
        )

    # ------------------------------------------------------------------
    # Skill implementations
    # ------------------------------------------------------------------

    def _skill_add_lines(self, params: Dict[str, str]) -> AISkillResult:
        """
        Add lines to the editor at a specific position (1-indexed).
        """
        line_num = params.get("line")
        content = params.get("content", "")

        if not content:
            return AISkillResult(False, "No content provided for add_lines")

        current_content = self.editor_getter()
        lines = current_content.splitlines(keepends=True)

        if line_num:
            try:
                # Convert from 1-indexed to 0-indexed
                line_idx = int(line_num) - 1
                if line_idx < 0:
                    line_idx = 0
                elif line_idx > len(lines):
                    line_idx = len(lines)
            except ValueError:
                return AISkillResult(False, f"Invalid line number: {line_num}")
        else:
            line_idx = len(lines)

        insert_content = content
        if line_idx < len(lines) and not insert_content.endswith("\n"):
            insert_content += "\n"
        elif line_idx == len(lines) and lines and not lines[-1].endswith("\n"):
            if insert_content and not insert_content.startswith("\n"):
                insert_content = "\n" + insert_content

        lines.insert(line_idx, insert_content)
        new_content = "".join(lines)
        self.editor_setter(new_content)

        self._warn_if_empty(new_content, "add_lines")
        self._log(f"Added lines at position {line_idx + 1}")
        return AISkillResult(
            True,
            f"Successfully added {len(content.splitlines())} line(s) at line {line_idx + 1}",
        )

    def _skill_delete_lines(self, params: Dict[str, str]) -> AISkillResult:
        """
        Delete lines from the editor.

        Parameters:
            line: The starting line number to delete (1-indexed)
            count: Number of lines to delete (default: 1)
            OR
            lines: Comma-separated list of line numbers to delete
        """
        lines_to_delete = params.get("lines")
        start_line = params.get("line")
        count = params.get("count", "1")

        current_content = self.editor_getter()
        lines = current_content.splitlines(keepends=True)
        total_lines = len(lines)

        if lines_to_delete:
            try:
                line_nums = [int(l.strip()) - 1 for l in lines_to_delete.split(",")]
                line_nums = [l for l in line_nums if 0 <= l < total_lines]
                line_nums.sort(reverse=True)

                for line_idx in line_nums:
                    del lines[line_idx]

                deleted_count = len(line_nums)
            except ValueError:
                return AISkillResult(False, f"Invalid line numbers: {lines_to_delete}")
        elif start_line:
            try:
                start_idx = int(start_line) - 1
                delete_count = int(count)

                if start_idx < 0 or start_idx >= total_lines:
                    return AISkillResult(
                        False, f"Start line {start_line} is out of range"
                    )

                end_idx = min(start_idx + delete_count, total_lines)
                del lines[start_idx:end_idx]

                deleted_count = end_idx - start_idx
            except ValueError:
                return AISkillResult(
                    False, f"Invalid line or count: {start_line}, {count}"
                )
        else:
            return AISkillResult(
                False,
                "No line specification provided. Use 'line' and 'count' or 'lines' parameter",
            )

        new_content = "".join(lines)
        self.editor_setter(new_content)

        self._warn_if_empty(new_content, "delete_lines")
        self._log(f"Deleted {deleted_count} line(s)")
        return AISkillResult(True, f"Successfully deleted {deleted_count} line(s)")

    def _skill_edit_lines(self, params: Dict[str, str]) -> AISkillResult:
        """
        Replace specific lines in the editor with new content.

        More efficient than using delete_lines + add_lines when you want
        to change the content of existing lines without changing the
        surrounding structure.

        Parameters:
            line: The starting line number to replace (1-indexed)
            content: The new content to insert
            count: Number of lines to replace (default: 1)
        """
        line_num = params.get("line")
        content = params.get("content", "")
        count = params.get("count", "1")

        if not content:
            return AISkillResult(False, "No content provided for edit_lines")
        if not line_num:
            return AISkillResult(False, "No line number provided for edit_lines")

        current_content = self.editor_getter()
        lines = current_content.splitlines(keepends=True)
        total_lines = len(lines)

        try:
            start_idx = int(line_num) - 1
            replace_count = int(count)
            if start_idx < 0:
                start_idx = 0
            if start_idx >= total_lines:
                return AISkillResult(False, f"Start line {line_num} is out of range")
            end_idx = min(start_idx + replace_count, total_lines)
        except ValueError:
            return AISkillResult(False, f"Invalid line or count: {line_num}, {count}")

        # Remove the old lines
        del lines[start_idx:end_idx]

        # Insert the new content
        insert_content = content
        if start_idx < len(lines) and not insert_content.endswith("\n"):
            insert_content += "\n"
        elif start_idx == len(lines) and lines and not lines[-1].endswith("\n"):
            if insert_content and not insert_content.startswith("\n"):
                insert_content = "\n" + insert_content

        lines.insert(start_idx, insert_content)
        new_content = "".join(lines)
        self.editor_setter(new_content)

        self._warn_if_empty(new_content, "edit_lines")
        self._log(f"Edited lines at position {start_idx + 1}")
        return AISkillResult(
            True,
            f"Successfully replaced {replace_count} line(s) with new content at line {start_idx + 1}",
        )

    def _skill_find_replace(self, params: Dict[str, str]) -> AISkillResult:
        """
        Search and replace text in the current editor content.

        All occurrences of the search text are replaced. This is a plain-text
        search (not a regex), making it safe and predictable.

        Parameters:
            find: The exact text to search for
            replace: The replacement text
        """
        find = params.get("find")
        replace = params.get("replace", "")

        if not find:
            return AISkillResult(False, "No search text provided for find_replace")

        current_content = self.editor_getter()
        if find not in current_content:
            return AISkillResult(False, f"Text '{find[:80]}' not found in current file")

        new_content = current_content.replace(find, replace)
        self.editor_setter(new_content)

        occurrences = current_content.count(find)
        self._warn_if_empty(new_content, "find_replace")
        self._log(f"Replaced {occurrences} occurrence(s) of text")
        return AISkillResult(
            True, f"Successfully replaced {occurrences} occurrence(s) of '{find[:50]}'"
        )

    def _skill_insert_at_cursor(self, params: Dict[str, str]) -> AISkillResult:
        """
        Insert content at a position identified by searching for specific text.

        The new content is inserted on a new line immediately after the line
        that contains the search text.

        Parameters:
            after: Text to search for (inserts after the line containing this text)
            content: The content to insert
        """
        after = params.get("after")
        content = params.get("content", "")

        if not after:
            return AISkillResult(
                False, "No insertion point text provided for insert_at_cursor"
            )
        if not content:
            return AISkillResult(False, "No content provided for insert_at_cursor")

        current_content = self.editor_getter()
        lines = current_content.splitlines(keepends=True)

        # Find the line containing the target text
        target_line_idx = -1
        for i, line in enumerate(lines):
            if after in line:
                target_line_idx = i
                break

        if target_line_idx == -1:
            return AISkillResult(
                False, f"Insertion point '{after[:80]}' not found in current file"
            )

        insert_idx = target_line_idx + 1
        insert_content = content
        if insert_idx < len(lines) and not insert_content.endswith("\n"):
            insert_content += "\n"
        elif insert_idx == len(lines) and lines and not lines[-1].endswith("\n"):
            if insert_content and not insert_content.startswith("\n"):
                insert_content = "\n" + insert_content

        lines.insert(insert_idx, insert_content)
        new_content = "".join(lines)
        self.editor_setter(new_content)

        self._warn_if_empty(new_content, "insert_at_cursor")
        self._log(f"Inserted content after line containing '{after[:60]}'")
        return AISkillResult(
            True, f"Successfully inserted content after '{after[:60]}'"
        )

    def _skill_append_lines(self, params: Dict[str, str]) -> AISkillResult:
        """
        Append lines to the end of the current editor content.

        Parameters:
            content: The content to append
        """
        content = params.get("content", "")

        if not content:
            return AISkillResult(False, "No content provided for append_lines")

        current_content = self.editor_getter()

        if current_content and not current_content.endswith("\n"):
            content = "\n" + content
        if not content.endswith("\n"):
            content += "\n"

        new_content = current_content + content
        self.editor_setter(new_content)

        self._log("Appended lines to end of file")
        return AISkillResult(True, "Successfully appended lines to end of file")

    def _skill_create_file(self, params: Dict[str, str]) -> AISkillResult:
        """
        Create a new file with content.

        Parameters:
            path: The file path (relative to project or absolute)
            content: The file content (optional)
        """
        path = params.get("path")
        content = params.get("content", "")

        if not path:
            return AISkillResult(False, "No file path provided for create_file")

        if not os.path.isabs(path):
            current_file = self.file_path_getter()
            if current_file:
                base_dir = os.path.dirname(current_file)
            else:
                base_dir = os.getcwd()
            path = os.path.join(base_dir, path)

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            self._log(f"Created file: {path}")
            return AISkillResult(
                True, f"Successfully created file: {os.path.basename(path)}"
            )
        except Exception as e:
            return AISkillResult(False, f"Failed to create file: {str(e)}")

    def _skill_delete_file(self, params: Dict[str, str]) -> AISkillResult:
        """
        Delete a file.

        Parameters:
            path: The file path to delete
        """
        path = params.get("path")

        if not path:
            return AISkillResult(False, "No file path provided for delete_file")

        if not os.path.isabs(path):
            current_file = self.file_path_getter()
            if current_file:
                base_dir = os.path.dirname(current_file)
            else:
                base_dir = os.getcwd()
            path = os.path.join(base_dir, path)

        try:
            if os.path.isfile(path):
                os.remove(path)
                self._log(f"Deleted file: {path}")
                return AISkillResult(
                    True, f"Successfully deleted file: {os.path.basename(path)}"
                )
            else:
                return AISkillResult(False, f"File not found: {path}")
        except Exception as e:
            return AISkillResult(False, f"Failed to delete file: {str(e)}")

    def _skill_create_folder(self, params: Dict[str, str]) -> AISkillResult:
        """
        Create a new folder.

        Parameters:
            path: The folder path to create
        """
        path = params.get("path")

        if not path:
            return AISkillResult(False, "No folder path provided for create_folder")

        if not os.path.isabs(path):
            current_file = self.file_path_getter()
            if current_file:
                base_dir = os.path.dirname(current_file)
            else:
                base_dir = os.getcwd()
            path = os.path.join(base_dir, path)

        try:
            os.makedirs(path, exist_ok=True)
            self._log(f"Created folder: {path}")
            return AISkillResult(
                True, f"Successfully created folder: {os.path.basename(path)}"
            )
        except Exception as e:
            return AISkillResult(False, f"Failed to create folder: {str(e)}")

    def _skill_delete_folder(self, params: Dict[str, str]) -> AISkillResult:
        """
        Delete a folder and its contents.

        Parameters:
            path: The folder path to delete
            recursive: Whether to delete recursively (default: true)
        """
        path = params.get("path")
        recursive = params.get("recursive", "true").lower() == "true"

        if not path:
            return AISkillResult(False, "No folder path provided for delete_folder")

        if not os.path.isabs(path):
            current_file = self.file_path_getter()
            if current_file:
                base_dir = os.path.dirname(current_file)
            else:
                base_dir = os.getcwd()
            path = os.path.join(base_dir, path)

        try:
            if os.path.isdir(path):
                if recursive:
                    import shutil

                    shutil.rmtree(path)
                else:
                    os.rmdir(path)
                self._log(f"Deleted folder: {path}")
                return AISkillResult(
                    True, f"Successfully deleted folder: {os.path.basename(path)}"
                )
            else:
                return AISkillResult(False, f"Folder not found: {path}")
        except Exception as e:
            return AISkillResult(False, f"Failed to delete folder: {str(e)}")

    def _skill_replace_file(self, params: Dict[str, str]) -> AISkillResult:
        """
        Replace the entire current file content.

        Parameters:
            content: The new file content
        """
        content = params.get("content", "")
        if content is None:
            return AISkillResult(False, "No content provided for replace_file")

        new_content = content
        if not new_content.endswith("\n"):
            new_content += "\n"

        self.editor_setter(new_content)
        self._log("Replaced entire file content")
        return AISkillResult(True, "Successfully replaced file content")

    # ------------------------------------------------------------------
    # Parsing and execution
    # ------------------------------------------------------------------

    def parse_for_preview(self, response_text: str) -> List[tuple]:
        """Parse AI response for skill invocations and generate previews (without executing).
        Returns list of tuples: (skill_name, AISkillResult)"""
        results = []
        simulated_content = self.editor_getter()
        skill_pattern = r'<skill\s+name="([^"]+)">(.*?)</skill>'
        matches = re.finditer(skill_pattern, response_text, re.DOTALL | re.IGNORECASE)

        for match in matches:
            skill_name = match.group(1).strip().lower()
            skill_body = match.group(2)

            params = {}
            param_pattern = r'<parameter\s+name="([^"]+)">(.*?)</parameter>'
            param_matches = re.finditer(
                param_pattern, skill_body, re.DOTALL | re.IGNORECASE
            )

            for param_match in param_matches:
                param_name = param_match.group(1).strip().lower()
                param_value = param_match.group(2).strip()
                params[param_name] = param_value

            if skill_name in ("add_lines", "insert_lines"):
                result = self._preview_add_lines_on_content(simulated_content, params)
            elif skill_name in ("delete_lines", "remove_lines"):
                result = self._preview_delete_lines_on_content(
                    simulated_content, params
                )
            elif skill_name == "edit_lines":
                result = self._preview_edit_lines_on_content(simulated_content, params)
            elif skill_name == "find_replace":
                result = self._preview_find_replace_on_content(
                    simulated_content, params
                )
            elif skill_name == "insert_at_cursor":
                result = self._preview_insert_at_cursor_on_content(
                    simulated_content, params
                )
            elif skill_name == "append_lines":
                result = self._preview_append_lines_on_content(
                    simulated_content, params
                )
            elif skill_name in ("replace_file", "overwrite_file"):
                result = self._preview_replace_file_on_content(
                    simulated_content, params
                )
            elif self.file_scope == "workspace" and skill_name == "create_file":
                result = self.preview_create_file(params)
            elif self.file_scope == "workspace" and skill_name == "delete_file":
                result = self.preview_delete_file(params)
            elif self.file_scope == "workspace" and skill_name == "create_folder":
                result = self.preview_create_folder(params)
            elif self.file_scope == "workspace" and skill_name == "delete_folder":
                result = self.preview_delete_folder(params)
            else:
                result = AISkillResult(False, f"Unknown skill: {skill_name}")

            if (
                result.success
                and result.requires_approval
                and result.data
                and "new_content" in result.data
            ):
                simulated_content = result.data["new_content"]

            results.append((skill_name, result))

        return results

    def apply_skill(self, skill_name: str, result: AISkillResult) -> AISkillResult:
        """Apply an approved skill change."""
        data = result.data or {}

        if skill_name in ("add_lines", "insert_lines"):
            new_content = data.get("new_content")
            if new_content is not None:
                self.editor_setter(new_content)
                return AISkillResult(True, "Changes applied")
        elif skill_name in ("delete_lines", "remove_lines"):
            new_content = data.get("new_content")
            if new_content is not None:
                self.editor_setter(new_content)
                return AISkillResult(True, "Lines deleted")
        elif skill_name == "edit_lines":
            new_content = data.get("new_content")
            if new_content is not None:
                self.editor_setter(new_content)
                return AISkillResult(True, "Lines edited")
        elif skill_name == "find_replace":
            new_content = data.get("new_content")
            if new_content is not None:
                self.editor_setter(new_content)
                return AISkillResult(True, "Text replaced")
        elif skill_name == "insert_at_cursor":
            new_content = data.get("new_content")
            if new_content is not None:
                self.editor_setter(new_content)
                return AISkillResult(True, "Content inserted")
        elif skill_name == "append_lines":
            new_content = data.get("new_content")
            if new_content is not None:
                self.editor_setter(new_content)
                return AISkillResult(True, "Lines appended")
        elif skill_name in ("replace_file", "overwrite_file"):
            new_content = data.get("new_content")
            if new_content is not None:
                self.editor_setter(new_content)
                return AISkillResult(True, "File content replaced")
        elif skill_name == "create_file":
            return self._skill_create_file(
                {"path": data.get("path", ""), "content": data.get("content", "")}
            )
        elif skill_name == "delete_file":
            return self._skill_delete_file({"path": data.get("path", "")})
        elif skill_name == "create_folder":
            return self._skill_create_folder({"path": data.get("path", "")})
        elif skill_name == "delete_folder":
            return self._skill_delete_folder({"path": data.get("path", "")})

        return AISkillResult(False, "Failed to apply change")

    def execute_skill(self, skill_name: str, params: Dict[str, str]) -> AISkillResult:
        """
        Execute a specific skill with the given parameters.

        Args:
            skill_name: The name of the skill to execute
            params: Dictionary of parameters for the skill

        Returns:
            AISkillResult indicating success or failure
        """
        if skill_name not in self._skills:
            return AISkillResult(False, f"Unknown skill: {skill_name}")

        skill_func = self._skills[skill_name]
        return skill_func(params)

    def parse_and_execute(self, response_text: str) -> List[AISkillResult]:
        """
        Parse an AI response for skill invocations and execute them.

        The parser looks for XML-like skill tags:
        <skill name="skill_name">
          <parameter name="param1">value1</parameter>
          <parameter name="param2">value2</parameter>
        </skill>

        Args:
            response_text: The AI response text to parse

        Returns:
            List of AISkillResult objects for each executed skill
        """
        results = []

        skill_pattern = r'<skill\s+name="([^"]+)">(.*?)</skill>'
        matches = re.finditer(skill_pattern, response_text, re.DOTALL | re.IGNORECASE)

        for match in matches:
            skill_name = match.group(1).strip().lower()
            skill_body = match.group(2)

            params = {}
            param_pattern = r'<parameter\s+name="([^"]+)">(.*?)</parameter>'
            param_matches = re.finditer(
                param_pattern, skill_body, re.DOTALL | re.IGNORECASE
            )

            for param_match in param_matches:
                param_name = param_match.group(1).strip().lower()
                param_value = param_match.group(2).strip()
                params[param_name] = param_value

            result = self.execute_skill(skill_name, params)
            results.append(result)

        return results

    def get_clean_response(self, response_text: str) -> str:
        """
        Remove skill tags from the response to show only the conversational text.

        Args:
            response_text: The original AI response

        Returns:
            The response with skill tags removed. Any conversational text
            appearing before, between, or after skill blocks is preserved.
        """
        cleaned = re.sub(
            r'<skill\s+name="[^"]+">.*?</skill>',
            "",
            response_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleaned = cleaned.strip()
        return cleaned

    def get_available_skills(self) -> List[str]:
        """Return a list of available skill names."""
        return list(self._skills.keys())

    def get_skill_description(self, skill_name: str) -> str:
        """Get a description of what a skill does."""
        descriptions = {
            "add_lines": "Insert lines of code at a specific line position in the editor",
            "insert_lines": "Insert lines of code at a specific line position in the editor (alias for add_lines)",
            "delete_lines": "Delete lines from the editor by line number or comma-separated list",
            "remove_lines": "Delete lines from the editor (alias for delete_lines)",
            "edit_lines": "Replace specific lines with new content; more efficient than delete_lines+add_lines",
            "find_replace": "Search and replace specific text throughout the file (plain text, not regex)",
            "insert_at_cursor": "Insert new content after the line containing a specific search string",
            "append_lines": "Append lines to the end of the current file",
            "replace_file": "Replace the entire content of the current file",
            "overwrite_file": "Replace the entire content of the current file (alias for replace_file)",
            "create_file": "Create a new file with optional content (workspace scope)",
            "delete_file": "Delete an existing file (workspace scope)",
            "create_folder": "Create a new folder (workspace scope)",
            "delete_folder": "Delete a folder and its contents (workspace scope)",
        }
        return descriptions.get(skill_name, "No description available")

    def configure_capabilities(self, file_scope="open_file", allow_run_commands=False):
        self.file_scope = (
            file_scope if file_scope in ("open_file", "workspace") else "open_file"
        )
        self.allow_run_commands = bool(allow_run_commands)

    def generate_skill_prompt(self, file_scope="open_file") -> str:
        """
        Generate a concise prompt that explains available skills to the AI.
        This should be appended to the system prompt.

        Note: Only editor manipulation skills are available (no file/folder creation/deletion)
        unless workspace scope is enabled.
        """
        prompt = """
You have skills to manipulate the current open file's content. Use XML tags in responses.

THINK BEFORE YOU ACT:
1. Analyze the existing code and understand its structure before making any changes
2. Choose the most efficient skill for each task
3. Verify your changes will result in correct, compilable code
4. Always ensure proper indentation and code structure

AVAILABLE SKILLS:

<skill name="add_lines"><parameter name="line">N</parameter><parameter name="content">CODE</parameter></skill>
  - Insert code at line N (1-indexed). Omit 'line' to append at the end.

<skill name="delete_lines"><parameter name="line">N</parameter><parameter name="count">C</parameter></skill>
  - Delete C lines starting at line N.

<skill name="edit_lines"><parameter name="line">N</parameter><parameter name="content">CODE</parameter><parameter name="count">C</parameter></skill>
  - Replace C lines starting at line N with new content (default count=1).
  - PREFER this over delete_lines+add_lines when simply changing existing lines.

<skill name="find_replace"><parameter name="find">TEXT</parameter><parameter name="replace">TEXT</parameter></skill>
  - Replace ALL occurrences of a specific string with another.
  - Useful for renaming identifiers, changing fixed values, etc.
  - Plain-text search, not regex.

<skill name="insert_at_cursor"><parameter name="after">TEXT</parameter><parameter name="content">CODE</parameter></skill>
  - Insert new content on a new line after the line containing TEXT.
  - Useful for adding imports, new methods, etc. at a specific location.

<skill name="append_lines"><parameter name="content">CODE</parameter></skill>
  - Append lines to the very end of the file. Simple alias for adding without a line number.

<skill name="replace_file"><parameter name="content">CODE</parameter></skill>
  - Replace the entire current file when the existing content is invalid or unrelated.

BEST PRACTICES FOR CODE EDITS:
- Use edit_lines when you need to change the content of existing lines (simpler than delete+add)
- Use find_replace when the same text appears in a limited context and you want to rename/change it globally
- Use insert_at_cursor when you need to add code near a known landmark (e.g. after the imports, after a specific function)
- Use add_lines with a line number to insert at a precise position
- Use append_lines as a shorthand for adding content at the very end
- For complex multi-line replacements, edit_lines with count is cleaner than delete_lines + add_lines
- When replacing entire file content because the existing content is completely wrong, use replace_file
- NEVER use replace_file just to make a small edit - use the more targeted skills instead

IMPORTANT INSTRUCTIONS:
1. ALWAYS read and analyze the existing code BEFORE making any changes
2. Check if the syntax would be correct after your modifications
3. If the existing code has syntax errors or issues, you MUST fix them first
4. Prefer edit_lines over delete_lines + add_lines when only changing content of existing lines
5. Use edit_lines with count=N to replace an entire block with different-sized content
6. Ensure proper indentation and code structure
7. If you need to add code at the end of a file, use append_lines or add_lines without line parameter
8. If the current file contains plain text or unrelated content and the user asks for code, replace_file is appropriate
9. If you predict the final file would not compile/run, use targeted edits until the proposed final content is valid
10. When the user asks you to edit/generate code in the current file, output ONLY skill XML blocks. Do not output explanations, reminders, or instructions about XML.
11. Never answer with generic text such as "XML tags must be well-formed" or "Propose the changes". Actually emit the required <skill> tags.

EXAMPLES:

Example 1: Changing a variable name (use find_replace)
<skill name="find_replace"><parameter name="find">old_variable</parameter><parameter name="replace">new_variable</parameter></skill>

Example 2: Editing a single line (use edit_lines)
If line 5 currently says "x = 1" and you want it to say "x = 2":
<skill name="edit_lines"><parameter name="line">5</parameter><parameter name="content">x = 2</parameter></skill>

Example 3: Adding an import after existing imports
<skill name="insert_at_cursor"><parameter name="after">import os</parameter><parameter name="content">import sys</parameter></skill>

Example 4: Replacing a 3-line block with a 2-line block
<skill name="edit_lines"><parameter name="line">10</parameter><parameter name="count">3</parameter><parameter name="content">def new_function():
    pass</parameter></skill>

Example 5: Appending at end of file (simple)
<skill name="append_lines"><parameter name="content"># End of file</parameter></skill>

Example 6: If the current Python file is:
1: Documento con texto
and the user asks for "hello world", the correct proposal is NOT to append print below that text.
The correct proposal is:
<skill name="delete_lines"><parameter name="line">1</parameter><parameter name="count">1</parameter></skill>
<skill name="add_lines"><parameter name="line">1</parameter><parameter name="content">print("Hello, world!")</parameter></skill>

When a change is needed, your final answer must look like the XML above, not like a description of what should be done.
"""
        if file_scope == "workspace":
            prompt += """
WORKSPACE SKILLS (paths relative to the opened project folder):
<skill name="create_file"><parameter name="path">relative/path.py</parameter><parameter name="content">CODE</parameter></skill>
  - Create a new file at the given path with the provided content.

<skill name="delete_file"><parameter name="path">relative/path.py</parameter></skill>
  - Delete an existing file at the given path.

<skill name="create_folder"><parameter name="path">relative/folder</parameter></skill>
  - Create a new folder at the given path.

<skill name="delete_folder"><parameter name="path">relative/folder</parameter></skill>
  - Delete a folder and all its contents at the given path.

You may modify files anywhere under the opened folder tree, not only the currently open file.
"""
        else:
            prompt += """
SCOPE: You can only modify the currently open file - you cannot create, delete, or modify other files or folders.
"""
        return prompt


_default_executor = None


def get_executor(
    editor_getter=None,
    editor_setter=None,
    file_path_getter=None,
    project_folder_getter=None,
    status_callback=None,
):
    """
    Get or create the default AI Skills Executor.

    Args:
        editor_getter: Function that returns the current editor content
        editor_setter: Function that sets the editor content
        file_path_getter: Function that returns the current file path
        project_folder_getter: Function that returns the project folder path (for security)
        status_callback: Optional function for status updates

    Returns:
        AISkillsExecutor instance
    """
    global _default_executor

    if _default_executor is None:
        if editor_getter is None or editor_setter is None or file_path_getter is None:
            raise ValueError(
                "First initialization of AI Skills Executor requires all callback functions"
            )
        _default_executor = AISkillsExecutor(
            editor_getter,
            editor_setter,
            file_path_getter,
            project_folder_getter,
            status_callback,
        )

    return _default_executor


def reset_executor():
    """Reset the default executor (useful for testing)."""
    global _default_executor
    _default_executor = None
