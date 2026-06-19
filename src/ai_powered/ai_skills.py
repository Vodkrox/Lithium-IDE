
import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional, Callable


class AISkillResult:

    def __init__(self, success: bool, message: str, data: Any = None, requires_approval: bool = False):
        self.success = success
        self.message = message
        self.data = data
        self.requires_approval = requires_approval

    def __str__(self):
        status = "✓" if self.success else "✗"
        return f"{status} {self.message}"

    def is_modification(self) -> bool:
        return self.requires_approval


class AISkillsExecutor:

    def __init__(self, editor_getter: Callable, editor_setter: Callable,
                 file_path_getter: Callable, project_folder_getter: Optional[Callable] = None,
                 status_callback: Optional[Callable] = None):
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
        }

    def _log(self, message: str):
        if self.status_callback:
            self.status_callback(message)

    def _get_project_folder(self) -> str:
        if self.project_folder_getter:
            return self.project_folder_getter() or ""
        return ""

    def _is_path_in_project(self, path: str) -> bool:
        project_folder = self._get_project_folder()
        if not project_folder:
            return True

        abs_path = os.path.abspath(path)
        abs_project = os.path.abspath(project_folder)

        return abs_path.startswith(abs_project + os.sep) or abs_path == abs_project

    def _resolve_path(self, path: str) -> tuple:
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
            return path, f"Access denied: path is outside project folder ({self._get_project_folder()})"

        return path, None

    def _get_line_count(self) -> int:
        content = self.editor_getter()
        if not content:
            return 0
        return len(content.splitlines())

    def _preview_add_lines_on_content(self, current_content: str, params: Dict[str, str]) -> AISkillResult:
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

        insert_content = content.rstrip('\n') + '\n'
        if line_idx == len(lines) and lines and not lines[-1].endswith('\n'):
            lines[-1] = lines[-1] + '\n'

        lines.insert(line_idx, insert_content)
        new_content = ''.join(lines)

        return AISkillResult(True, f"Add {len(content.splitlines())} line(s) at line {line_idx + 1}",
                           data={"new_content": new_content, "original_content": current_content},
                           requires_approval=True)

    def _preview_delete_lines_on_content(self, current_content: str, params: Dict[str, str]) -> AISkillResult:
        lines_to_delete = params.get("lines")
        start_line = params.get("line")
        count = params.get("count", "1")

        lines = current_content.splitlines(keepends=True)
        total_lines = len(lines)

        line_nums_to_delete = []
        if lines_to_delete:
            try:
                line_nums_to_delete = [int(l.strip()) - 1 for l in lines_to_delete.split(",")]
                line_nums_to_delete = [l for l in line_nums_to_delete if 0 <= l < total_lines]
            except ValueError:
                return AISkillResult(False, f"Invalid line numbers: {lines_to_delete}")
        elif start_line:
            try:
                start_idx = int(start_line) - 1
                delete_count = int(count)
                if start_idx < 0 or start_idx >= total_lines:
                    return AISkillResult(False, f"Start line {start_line} is out of range")
                end_idx = min(start_idx + delete_count, total_lines)
                line_nums_to_delete = list(range(start_idx, end_idx))
            except ValueError:
                return AISkillResult(False, f"Invalid line or count: {start_line}, {count}")
        else:
            return AISkillResult(False, "No line specification provided")

        new_lines = [line for i, line in enumerate(lines) if i not in line_nums_to_delete]
        new_content = ''.join(new_lines)

        return AISkillResult(True, f"Delete {len(line_nums_to_delete)} line(s)",
                           data={"new_content": new_content, "original_content": current_content},
                           requires_approval=True)

    def _preview_replace_file_on_content(self, current_content: str, params: Dict[str, str]) -> AISkillResult:
        content = params.get("content", "")
        if content is None:
            return AISkillResult(False, "No content provided for replace_file")

        new_content = content
        if not new_content.endswith("\n"):
            new_content += "\n"

        return AISkillResult(True, "Replace entire file content",
                           data={"new_content": new_content, "original_content": current_content},
                           requires_approval=True)

    def preview_add_lines(self, params: Dict[str, str]) -> AISkillResult:
        return self._preview_add_lines_on_content(self.editor_getter(), params)

    def apply_add_lines(self, new_content: str) -> AISkillResult:
        self.editor_setter(new_content)
        lines = new_content.splitlines()
        self._log(f"Added lines")
        return AISkillResult(True, f"Successfully added lines")

    def _skill_add_lines(self, params: Dict[str, str]) -> AISkillResult:
        line_num = params.get("line")
        content = params.get("content", "")

        if not content:
            return AISkillResult(False, "No content provided for add_lines")

        current_content = self.editor_getter()
        lines = current_content.splitlines(keepends=True)

        if line_num:
            try:
                line_idx = int(line_num)
                if line_idx < 0:
                    line_idx = 0
                elif line_idx > len(lines):
                    line_idx = len(lines)
            except ValueError:
                return AISkillResult(False, f"Invalid line number: {line_num}")
        else:
            line_idx = len(lines)

        insert_content = content
        if line_idx < len(lines) and not insert_content.endswith('\n'):
            insert_content += '\n'
        elif line_idx == len(lines) and lines and not lines[-1].endswith('\n'):
            if insert_content and not insert_content.startswith('\n'):
                insert_content = '\n' + insert_content

        lines.insert(line_idx, insert_content)
        new_content = ''.join(lines)
        self.editor_setter(new_content)

        self._log(f"Added lines at position {line_idx + 1}")
        return AISkillResult(True, f"Successfully added {len(content.splitlines())} line(s) at line {line_idx + 1}")

    def _skill_delete_lines(self, params: Dict[str, str]) -> AISkillResult:
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
                    return AISkillResult(False, f"Start line {start_line} is out of range")

                end_idx = min(start_idx + delete_count, total_lines)
                del lines[start_idx:end_idx]

                deleted_count = end_idx - start_idx
            except ValueError:
                return AISkillResult(False, f"Invalid line or count: {start_line}, {count}")
        else:
            return AISkillResult(False, "No line specification provided. Use 'line' and 'count' or 'lines' parameter")

        new_content = ''.join(lines)
        self.editor_setter(new_content)

        self._log(f"Deleted {deleted_count} line(s)")
        return AISkillResult(True, f"Successfully deleted {deleted_count} line(s)")

    def _skill_create_file(self, params: Dict[str, str]) -> AISkillResult:
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

            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

            self._log(f"Created file: {path}")
            return AISkillResult(True, f"Successfully created file: {os.path.basename(path)}")
        except Exception as e:
            return AISkillResult(False, f"Failed to create file: {str(e)}")

    def _skill_delete_file(self, params: Dict[str, str]) -> AISkillResult:
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
                return AISkillResult(True, f"Successfully deleted file: {os.path.basename(path)}")
            else:
                return AISkillResult(False, f"File not found: {path}")
        except Exception as e:
            return AISkillResult(False, f"Failed to delete file: {str(e)}")

    def _skill_create_folder(self, params: Dict[str, str]) -> AISkillResult:
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
            return AISkillResult(True, f"Successfully created folder: {os.path.basename(path)}")
        except Exception as e:
            return AISkillResult(False, f"Failed to create folder: {str(e)}")

    def _skill_delete_folder(self, params: Dict[str, str]) -> AISkillResult:
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
                return AISkillResult(True, f"Successfully deleted folder: {os.path.basename(path)}")
            else:
                return AISkillResult(False, f"Folder not found: {path}")
        except Exception as e:
            return AISkillResult(False, f"Failed to delete folder: {str(e)}")

    def parse_for_preview(self, response_text: str) -> List[tuple]:
        results = []
        simulated_content = self.editor_getter()
        skill_pattern = r'<skill\s+name="([^"]+)">(.*?)</skill>'
        matches = re.finditer(skill_pattern, response_text, re.DOTALL | re.IGNORECASE)

        for match in matches:
            skill_name = match.group(1).strip().lower()
            skill_body = match.group(2)

            params = {}
            param_pattern = r'<parameter\s+name="([^"]+)">(.*?)</parameter>'
            param_matches = re.finditer(param_pattern, skill_body, re.DOTALL | re.IGNORECASE)

            for param_match in param_matches:
                param_name = param_match.group(1).strip().lower()
                param_value = param_match.group(2).strip()
                params[param_name] = param_value

            if skill_name in ("add_lines", "insert_lines"):
                result = self._preview_add_lines_on_content(simulated_content, params)
            elif skill_name in ("delete_lines", "remove_lines"):
                result = self._preview_delete_lines_on_content(simulated_content, params)
            elif skill_name in ("replace_file", "overwrite_file"):
                result = self._preview_replace_file_on_content(simulated_content, params)
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

            if result.success and result.requires_approval and result.data and "new_content" in result.data:
                simulated_content = result.data["new_content"]

            results.append((skill_name, result))

        return results

    def preview_delete_lines(self, params: Dict[str, str]) -> AISkillResult:
        return self._preview_delete_lines_on_content(self.editor_getter(), params)

    def preview_replace_file(self, params: Dict[str, str]) -> AISkillResult:
        return self._preview_replace_file_on_content(self.editor_getter(), params)

    def preview_create_file(self, params: Dict[str, str]) -> AISkillResult:
        path = params.get("path")
        content = params.get("content", "")

        if not path:
            return AISkillResult(False, "No file path provided")

        resolved_path, error = self._resolve_path(path)
        if error:
            return AISkillResult(False, error)

        return AISkillResult(True, f"Create file: {os.path.basename(resolved_path)}",
                           data={"path": resolved_path, "content": content},
                           requires_approval=True)

    def preview_delete_file(self, params: Dict[str, str]) -> AISkillResult:
        path = params.get("path")
        if not path:
            return AISkillResult(False, "No file path provided")

        resolved_path, error = self._resolve_path(path)
        if error:
            return AISkillResult(False, error)

        if not os.path.isfile(resolved_path):
            return AISkillResult(False, f"File not found: {os.path.basename(resolved_path)}")

        return AISkillResult(True, f"Delete file: {os.path.basename(resolved_path)}",
                           data={"path": resolved_path},
                           requires_approval=True)

    def preview_create_folder(self, params: Dict[str, str]) -> AISkillResult:
        path = params.get("path")
        if not path:
            return AISkillResult(False, "No folder path provided")

        resolved_path, error = self._resolve_path(path)
        if error:
            return AISkillResult(False, error)

        return AISkillResult(True, f"Create folder: {os.path.basename(resolved_path)}",
                           data={"path": resolved_path},
                           requires_approval=True)

    def preview_delete_folder(self, params: Dict[str, str]) -> AISkillResult:
        path = params.get("path")
        if not path:
            return AISkillResult(False, "No folder path provided")

        resolved_path, error = self._resolve_path(path)
        if error:
            return AISkillResult(False, error)

        if not os.path.isdir(resolved_path):
            return AISkillResult(False, f"Folder not found: {os.path.basename(resolved_path)}")

        return AISkillResult(True, f"Delete folder: {os.path.basename(resolved_path)}",
                           data={"path": resolved_path},
                           requires_approval=True)

    def apply_skill(self, skill_name: str, result: AISkillResult) -> AISkillResult:
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
        elif skill_name in ("replace_file", "overwrite_file"):
            new_content = data.get("new_content")
            if new_content is not None:
                self.editor_setter(new_content)
                return AISkillResult(True, "File content replaced")
        elif skill_name == "create_file":
            return self._skill_create_file({"path": data.get("path", ""), "content": data.get("content", "")})
        elif skill_name == "delete_file":
            return self._skill_delete_file({"path": data.get("path", "")})
        elif skill_name == "create_folder":
            return self._skill_create_folder({"path": data.get("path", "")})
        elif skill_name == "delete_folder":
            return self._skill_delete_folder({"path": data.get("path", "")})

        return AISkillResult(False, "Failed to apply change")

    def _skill_replace_file(self, params: Dict[str, str]) -> AISkillResult:
        content = params.get("content", "")
        if content is None:
            return AISkillResult(False, "No content provided for replace_file")

        new_content = content
        if not new_content.endswith("\n"):
            new_content += "\n"

        self.editor_setter(new_content)
        self._log("Replaced entire file content")
        return AISkillResult(True, "Successfully replaced file content")

    def execute_skill(self, skill_name: str, params: Dict[str, str]) -> AISkillResult:
        if skill_name not in self._skills:
            return AISkillResult(False, f"Unknown skill: {skill_name}")

        skill_func = self._skills[skill_name]
        return skill_func(params)

    def parse_and_execute(self, response_text: str) -> List[AISkillResult]:
        results = []

        skill_pattern = r'<skill\s+name="([^"]+)">(.*?)</skill>'
        matches = re.finditer(skill_pattern, response_text, re.DOTALL | re.IGNORECASE)

        for match in matches:
            skill_name = match.group(1).strip().lower()
            skill_body = match.group(2)

            params = {}
            param_pattern = r'<parameter\s+name="([^"]+)">(.*?)</parameter>'
            param_matches = re.finditer(param_pattern, skill_body, re.DOTALL | re.IGNORECASE)

            for param_match in param_matches:
                param_name = param_match.group(1).strip().lower()
                param_value = param_match.group(2).strip()
                params[param_name] = param_value

            result = self.execute_skill(skill_name, params)
            results.append(result)

        return results

    def get_clean_response(self, response_text: str) -> str:
        has_skill_blocks = bool(re.search(r'<skill\s+name="[^"]+">', response_text, flags=re.IGNORECASE))
        cleaned = re.sub(r'<skill\s+name="[^"]+">.*?</skill>', '', response_text, flags=re.DOTALL | re.IGNORECASE)
        cleaned = cleaned.strip()
        if has_skill_blocks:
            return ""
        return cleaned

    def get_available_skills(self) -> List[str]:
        return list(self._skills.keys())

    def get_skill_description(self, skill_name: str) -> str:
        descriptions = {
            "add_lines": "Insert lines of code at a specific position in the editor",
            "delete_lines": "Delete lines from the editor",
            "replace_file": "Replace the entire file content",
            "create_file": "Create a new file with optional content",
            "delete_file": "Delete an existing file",
            "create_folder": "Create a new folder",
            "delete_folder": "Delete a folder and its contents",
        }
        return descriptions.get(skill_name, "No description available")

    def configure_capabilities(self, file_scope="open_file", allow_run_commands=False):
        self.file_scope = file_scope if file_scope in ("open_file", "workspace") else "open_file"
        self.allow_run_commands = bool(allow_run_commands)

    def generate_skill_prompt(self, file_scope="open_file") -> str:
        prompt = """
You have skills to manipulate the current open file's content. Use XML tags in responses:

<skill name="add_lines"><parameter name="line">N</parameter><parameter name="content">CODE</parameter></skill> - Insert code at line N
<skill name="delete_lines"><parameter name="line">N</parameter><parameter name="count">C</parameter></skill> - Delete C lines from N
<skill name="replace_file"><parameter name="content">CODE</parameter></skill> - Replace the entire current file when the existing content is invalid or unrelated

IMPORTANT INSTRUCTIONS:
1. ALWAYS read and analyze the existing code BEFORE making any changes
2. Check if the syntax would be correct after your modifications
3. If the existing code has syntax errors or issues, you MUST fix them first
4. Use delete_lines to remove problematic code, then add_lines to insert correct code
5. Ensure proper indentation and code structure
6. If you need to add code at the end of a file, use line number that is beyond the last line
7. If the current file contains plain text or unrelated content and the user asks for code, delete or replace the invalid lines first; do not append code below invalid content
8. If you predict the final file would not compile/run, use delete_lines and add_lines until the proposed final content is valid
9. When replacing a line, use delete_lines for the old line and add_lines at the same line number for the corrected line
10. When the user asks you to edit/generate code in the current file, output ONLY skill XML blocks. Do not output explanations, reminders, or instructions about XML.
11. Never answer with generic text such as "XML tags must be well-formed" or "Propose the changes". Actually emit the required <skill> tags.

Example workflow:
- Read the current code
- Identify any syntax errors or issues
- Use delete_lines to remove broken code if needed
- Use add_lines to insert correct, working code
- Verify the final result would be syntactically correct

Example: if the current Python file is:
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
<skill name="delete_file"><parameter name="path">relative/path.py</parameter></skill>
<skill name="create_folder"><parameter name="path">relative/folder</parameter></skill>
<skill name="delete_folder"><parameter name="path">relative/folder</parameter></skill>

You may modify files anywhere under the opened folder tree, not only the currently open file.
"""
        else:
            prompt += """
SCOPE: You can only modify the currently open file - you cannot create, delete, or modify other files or folders.
"""
        return prompt


_default_executor = None


def get_executor(editor_getter=None, editor_setter=None, file_path_getter=None,
                 project_folder_getter=None, status_callback=None):
    global _default_executor

    if _default_executor is None:
        if editor_getter is None or editor_setter is None or file_path_getter is None:
            raise ValueError("First initialization of AI Skills Executor requires all callback functions")
        _default_executor = AISkillsExecutor(editor_getter, editor_setter, file_path_getter,
                                             project_folder_getter, status_callback)

    return _default_executor


def reset_executor():
    global _default_executor
    _default_executor = None
