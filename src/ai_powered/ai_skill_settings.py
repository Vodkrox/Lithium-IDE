"""Persistent toggles for AI chat skills."""

SETTINGS_KEYS = {
    "file_scope": "ai_skill_file_scope",
    "web_search": "ai_skill_web_search",
    "reasoning": "ai_skill_reasoning",
    "explain_actions": "ai_skill_explain_actions",
    "auto_approve": "ai_skill_auto_approve",
    "run_commands": "ai_skill_run_commands",
    "notify_on_complete": "ai_skill_notify_on_complete",
    "code_review": "ai_skill_code_review",
    "refactor": "ai_skill_refactor",
    "optimize": "ai_skill_optimize",
    "document": "ai_skill_document",
    "test_gen": "ai_skill_test_gen",
}

DEFAULTS = {
    "file_scope": "open_file",
    "web_search": False,
    "reasoning": False,
    "explain_actions": False,
    "auto_approve": False,
    "run_commands": False,
    "notify_on_complete": False,
    "code_review": False,
    "refactor": False,
    "optimize": False,
    "document": False,
    "test_gen": False,
}

FILE_SCOPE_OPTIONS = (
    ("open_file", "Open file only"),
    ("workspace", "Folder and subfolders"),
)

SKILL_TOGGLE_LABELS = (
    ("web_search", "Search the web"),
    ("reasoning", "Reason"),
    ("explain_actions", "Explain actions"),
    ("auto_approve", "Auto-approve changes"),
    ("run_commands", "Run commands"),
    ("notify_on_complete", "Notify when done"),
    ("code_review", "Review & analyze code"),
    ("refactor", "Suggest refactoring"),
    ("optimize", "Optimize performance"),
    ("document", "Generate documentation"),
    ("test_gen", "Generate tests"),
)


class AISkillSettings:
    def __init__(self, settings_manager):
        self.settings_manager = settings_manager
        self._values = dict(DEFAULTS)

    def load(self):
        for key, setting_key in SETTINGS_KEYS.items():
            default = DEFAULTS[key]
            stored = self.settings_manager.get(setting_key, default)
            if key == "file_scope":
                if stored not in dict(FILE_SCOPE_OPTIONS):
                    stored = default
            else:
                stored = bool(stored)
            self._values[key] = stored
        return self

    def get(self, key, default=None):
        if default is None:
            return self._values.get(key, DEFAULTS.get(key))
        return self._values.get(key, default)

    def set(self, key, value):
        if key == "file_scope":
            if value not in dict(FILE_SCOPE_OPTIONS):
                value = DEFAULTS["file_scope"]
        else:
            value = bool(value)
        self._values[key] = value
        self.settings_manager.set(SETTINGS_KEYS[key], value)

    def is_workspace_scope(self):
        return self.get("file_scope") == "workspace"

    def active_count(self):
        count = sum(1 for key, _ in SKILL_TOGGLE_LABELS if self.get(key))
        if self.is_workspace_scope():
            count += 1
        return count

    def get_active_skills_list(self) -> list:
        """Return a list of (key, label) for all currently active skills."""
        active = []
        for key, label in SKILL_TOGGLE_LABELS:
            if self.get(key):
                active.append((key, label))
        if self.is_workspace_scope():
            active.append(("file_scope", "Folder and subfolders"))
        return active

    def build_system_prompt_addendum(self):
        parts = []

        if self.is_workspace_scope():
            parts.append(
                "You may read and modify any file under the opened project folder and its subfolders."
            )
        else:
            parts.append("You may only view and modify the currently open file.")

        if self.get("reasoning"):
            parts.append(
                "Reason step by step before proposing changes. You may include a short reasoning section."
            )

        if self.get("explain_actions"):
            parts.append("Briefly explain what you are doing when applying changes.")
        elif not self.get("reasoning"):
            parts.append(
                "When editing files, prefer skill XML tags over long prose unless the user asks for an explanation."
            )

        if self.get("web_search"):
            parts.append(
                "Web search is enabled. You may use it when local project context is not enough."
            )

        if self.get("run_commands"):
            parts.append(
                "Shell command execution is enabled for safe project commands when verification is needed."
            )

        if self.get("auto_approve"):
            parts.append(
                "Changes will be applied automatically without manual approval."
            )

        # --- New skills ---
        if self.get("code_review"):
            parts.append("Analyze code for bugs, security issues, and best practices.")

        if self.get("refactor"):
            parts.append("Suggest refactoring opportunities to improve code quality.")

        if self.get("optimize"):
            parts.append(
                "Identify performance bottlenecks and optimization opportunities."
            )

        if self.get("document"):
            parts.append("Generate comprehensive documentation for code.")

        if self.get("test_gen"):
            parts.append("Generate unit tests for the code.")

        return "\n".join(parts)

    def build_task_type_instruction(self, task_type: str) -> str:
        """Generate specific instructions based on the task type.

        Supported task types: "code", "chat", "debug", "explain", "refactor".
        Returns an empty string for unknown types.
        """
        instructions = {
            "code": (
                "You are writing production-quality code. "
                "Follow the project's existing style, use clear names, "
                "add appropriate error handling, and prefer simple solutions."
            ),
            "chat": (
                "Answer conversationally and concisely. "
                "Provide helpful explanations without unnecessary code unless asked."
            ),
            "debug": (
                "You are debugging an issue. First identify the root cause by "
                "examining relevant code and logs. Propose a minimal, targeted fix "
                "and explain why it resolves the problem."
            ),
            "explain": (
                "Explain the requested code or concept clearly and thoroughly. "
                "Use examples where helpful, and break down complex ideas into "
                "simple steps."
            ),
            "refactor": (
                "Suggest refactoring to improve code quality, readability, and "
                "maintainability without changing external behavior. "
                "Prioritize small, safe steps that can be validated independently."
            ),
        }
        return instructions.get(task_type, "")
