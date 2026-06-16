"""
AI Skills Module - Provides file and editor manipulation capabilities for the AI assistant.

This module defines a set of "skills" that the AI can use to manipulate files and code:
- add_lines: Insert lines at a specific position in the editor
- delete_lines: Delete lines from the editor
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
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional, Callable


class AISkillResult:
    """Represents the result of executing an AI skill."""
    
    def __init__(self, success: bool, message: str, data: Any = None, requires_approval: bool = False):
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
    
    def __init__(self, editor_getter: Callable, editor_setter: Callable, 
                 file_path_getter: Callable, project_folder_getter: Optional[Callable] = None,
                 status_callback: Optional[Callable] = None):
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
        
        # Register built-in skills
        self._skills = {
            "add_lines": self._skill_add_lines,
            "delete_lines": self._skill_delete_lines,
            "insert_lines": self._skill_add_lines,  # Alias
            "remove_lines": self._skill_delete_lines,  # Alias
            "create_file": self._skill_create_file,
            "add_file": self._skill_create_file,  # Alias
            "delete_file": self._skill_delete_file,
            "remove_file": self._skill_delete_file,  # Alias
            "create_folder": self._skill_create_folder,
            "add_folder": self._skill_create_folder,  # Alias
            "mkdir": self._skill_create_folder,  # Alias
            "delete_folder": self._skill_delete_folder,
            "remove_folder": self._skill_delete_folder,  # Alias
            "rmdir": self._skill_delete_folder,  # Alias
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
            # If no project folder is set, allow operations in current working directory
            return True
        
        # Normalize paths
        abs_path = os.path.abspath(path)
        abs_project = os.path.abspath(project_folder)
        
        # Check if path is within project folder
        return abs_path.startswith(abs_project + os.sep) or abs_path == abs_project
    
    def _resolve_path(self, path: str) -> tuple:
        """
        Resolve a path and check if it's within the project folder.
        Returns (resolved_path, error_message) - error_message is None if valid.
        """
        if not path:
            return None, "No path provided"
        
        # Resolve path - if relative, use project folder or current file directory
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
        
        # Check if path is within project folder
        if not self._is_path_in_project(path):
            return path, f"Access denied: path is outside project folder ({self._get_project_folder()})"
        
        return path, None
    
    def _get_line_count(self) -> int:
        """Get the current number of lines in the editor."""
        content = self.editor_getter()
        if not content:
            return 0
        return len(content.splitlines())
    
    def preview_add_lines(self, params: Dict[str, str]) -> AISkillResult:
        """
        Preview adding lines to the editor (without applying).
        Returns the proposed new content for approval.
        """
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
        
        return AISkillResult(True, f"Add {len(content.splitlines())} line(s) at line {line_idx + 1}", 
                           data={"new_content": new_content, "original_content": current_content},
                           requires_approval=True)
    
    def apply_add_lines(self, new_content: str) -> AISkillResult:
        """Apply the approved add_lines change."""
        self.editor_setter(new_content)
        lines = new_content.splitlines()
        self._log(f"Added lines")
        return AISkillResult(True, f"Successfully added lines")
    
    def _skill_add_lines(self, params: Dict[str, str]) -> AISkillResult:
        """
        Add lines to the editor at a specific position.
        """
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
            # Parse comma-separated line numbers
            try:
                line_nums = [int(l.strip()) - 1 for l in lines_to_delete.split(",")]
                line_nums = [l for l in line_nums if 0 <= l < total_lines]
                line_nums.sort(reverse=True)  # Delete from end to start to preserve indices
                
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
        
        # Resolve path - if relative, use the directory of the current file or current working directory
        if not os.path.isabs(path):
            current_file = self.file_path_getter()
            if current_file:
                base_dir = os.path.dirname(current_file)
            else:
                base_dir = os.getcwd()
            path = os.path.join(base_dir, path)
        
        try:
            # Create parent directories if they don't exist
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self._log(f"Created file: {path}")
            return AISkillResult(True, f"Successfully created file: {os.path.basename(path)}")
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
        
        # Resolve path
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
        """
        Create a new folder.
        
        Parameters:
            path: The folder path to create
        """
        path = params.get("path")
        
        if not path:
            return AISkillResult(False, "No folder path provided for create_folder")
        
        # Resolve path
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
        
        # Resolve path
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
        """Parse AI response for skill invocations and generate previews (without executing).
        Returns list of tuples: (skill_name, AISkillResult)"""
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
            
            if skill_name in ("add_lines", "insert_lines"):
                result = self.preview_add_lines(params)
            elif skill_name in ("delete_lines", "remove_lines"):
                result = self.preview_delete_lines(params)
            elif skill_name in ("create_file", "add_file"):
                result = self.preview_create_file(params)
            elif skill_name in ("delete_file", "remove_file"):
                result = self.preview_delete_file(params)
            elif skill_name in ("create_folder", "add_folder", "mkdir"):
                result = self.preview_create_folder(params)
            elif skill_name in ("delete_folder", "remove_folder", "rmdir"):
                result = self.preview_delete_folder(params)
            else:
                result = AISkillResult(False, f"Unknown skill: {skill_name}")
            
            results.append((skill_name, result))
        
        return results
    
    def preview_delete_lines(self, params: Dict[str, str]) -> AISkillResult:
        """Preview deleting lines (without applying)."""
        lines_to_delete = params.get("lines")
        start_line = params.get("line")
        count = params.get("count", "1")
        
        current_content = self.editor_getter()
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
    
    def preview_create_file(self, params: Dict[str, str]) -> AISkillResult:
        """Preview creating a file (without applying)."""
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
        """Preview deleting a file (without applying)."""
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
        """Preview creating a folder (without applying)."""
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
        """Preview deleting a folder (without applying)."""
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
        """Apply an approved skill change."""
        data = result.data or {}
        
        if skill_name in ("add_lines", "insert_lines"):
            new_content = data.get("new_content")
            if new_content:
                self.editor_setter(new_content)
                return AISkillResult(True, "Changes applied")
        elif skill_name in ("delete_lines", "remove_lines"):
            new_content = data.get("new_content")
            if new_content:
                self.editor_setter(new_content)
                return AISkillResult(True, "Lines deleted")
        elif skill_name in ("create_file", "add_file"):
            path = data.get("path")
            content = data.get("content", "")
            if path:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return AISkillResult(True, f"File created: {os.path.basename(path)}")
        elif skill_name in ("delete_file", "remove_file"):
            path = data.get("path")
            if path and os.path.isfile(path):
                os.remove(path)
                return AISkillResult(True, f"File deleted: {os.path.basename(path)}")
        elif skill_name in ("create_folder", "add_folder", "mkdir"):
            path = data.get("path")
            if path:
                os.makedirs(path, exist_ok=True)
                return AISkillResult(True, f"Folder created: {os.path.basename(path)}")
        elif skill_name in ("delete_folder", "remove_folder", "rmdir"):
            path = data.get("path")
            if path and os.path.isdir(path):
                import shutil
                shutil.rmtree(path)
                return AISkillResult(True, f"Folder deleted: {os.path.basename(path)}")
        
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
        
        # Find all skill blocks
        skill_pattern = r'<skill\s+name="([^"]+)">(.*?)</skill>'
        matches = re.finditer(skill_pattern, response_text, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            skill_name = match.group(1).strip().lower()
            skill_body = match.group(2)
            
            # Parse parameters from the skill body
            params = {}
            param_pattern = r'<parameter\s+name="([^"]+)">(.*?)</parameter>'
            param_matches = re.finditer(param_pattern, skill_body, re.DOTALL | re.IGNORECASE)
            
            for param_match in param_matches:
                param_name = param_match.group(1).strip().lower()
                param_value = param_match.group(2).strip()
                params[param_name] = param_value
            
            # Execute the skill
            result = self.execute_skill(skill_name, params)
            results.append(result)
        
        return results
    
    def get_clean_response(self, response_text: str) -> str:
        """
        Remove skill tags from the response to show only the conversational text.
        
        Args:
            response_text: The original AI response
            
        Returns:
            The response with skill tags removed
        """
        # Remove skill blocks
        cleaned = re.sub(r'<skill\s+name="[^"]+">.*?</skill>', '', response_text, flags=re.DOTALL | re.IGNORECASE)
        return cleaned.strip()
    
    def get_available_skills(self) -> List[str]:
        """Return a list of available skill names."""
        return list(self._skills.keys())
    
    def get_skill_description(self, skill_name: str) -> str:
        """Get a description of what a skill does."""
        descriptions = {
            "add_lines": "Insert lines of code at a specific position in the editor",
            "delete_lines": "Delete lines from the editor",
            "create_file": "Create a new file with optional content",
            "delete_file": "Delete an existing file",
            "create_folder": "Create a new folder",
            "delete_folder": "Delete a folder and its contents",
        }
        return descriptions.get(skill_name, "No description available")
    
    def generate_skill_prompt(self) -> str:
        """
        Generate a concise prompt that explains available skills to the AI.
        This should be appended to the system prompt.
        """
        return """
You have skills to manipulate files/code. Use XML tags in responses:

<skill name="add_lines"><parameter name="line">N</parameter><parameter name="content">CODE</parameter></skill> - Insert code at line N
<skill name="delete_lines"><parameter name="line">N</parameter><parameter name="count">C</parameter></skill> - Delete C lines from N
<skill name="create_file"><parameter name="path">PATH</parameter><parameter name="content">CODE</parameter></skill> - Create file
<skill name="delete_file"><parameter name="path">PATH</parameter></skill> - Delete file
<skill name="create_folder"><parameter name="path">PATH</parameter></skill> - Create folder
<skill name="delete_folder"><parameter name="path">PATH</parameter></skill> - Delete folder

Example: <skill name="add_lines"><parameter name="line">1</parameter><parameter name="content">print("Hi")</parameter></skill>
"""


# Singleton instance for easy access
_default_executor = None


def get_executor(editor_getter=None, editor_setter=None, file_path_getter=None, 
                 project_folder_getter=None, status_callback=None):
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
            raise ValueError("First initialization of AI Skills Executor requires all callback functions")
        _default_executor = AISkillsExecutor(editor_getter, editor_setter, file_path_getter, 
                                             project_folder_getter, status_callback)
    
    return _default_executor


def reset_executor():
    """Reset the default executor (useful for testing)."""
    global _default_executor
    _default_executor = None