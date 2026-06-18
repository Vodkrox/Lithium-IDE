import json
import os
import sys


class SettingsManager:
    APP_NAME = "LithiumIDE"
    FILE_NAME = "settings.json"
    DEFAULTS = {
        "theme": "Graphite",
        "language": "Python",
        "last_file": None,
        "last_folder": None,
        "ai_level_mode": "auto",
        "ai_level": "Medium",
        "ai_skill_file_scope": "open_file",
        "ai_skill_web_search": False,
        "ai_skill_reasoning": False,
        "ai_skill_explain_actions": False,
        "ai_skill_auto_approve": False,
        "ai_skill_run_commands": False,
        "ai_skill_notify_on_complete": False,
    }

    def __init__(self):
        self.settings_path = self._get_settings_path()
        self.settings = dict(self.DEFAULTS)
        self.load()

    def _get_settings_path(self):
        if sys.platform == "win32":
            base_dir = os.getenv("LOCALAPPDATA") or os.path.expanduser(
                "~\\AppData\\Local"
            )
        elif sys.platform == "darwin":
            base_dir = os.path.join(
                os.path.expanduser("~"), "Library", "Application Support"
            )
        else:
            base_dir = os.getenv("XDG_CONFIG_HOME") or os.path.join(
                os.path.expanduser("~"), ".config"
            )

        app_dir = os.path.join(base_dir, self.APP_NAME)
        try:
            os.makedirs(app_dir, exist_ok=True)
        except Exception:
            app_dir = os.path.join(os.path.expanduser("~"), ".config", self.APP_NAME)
            os.makedirs(app_dir, exist_ok=True)

        return os.path.join(app_dir, self.FILE_NAME)

    def load(self):
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.settings.update(data)
        except Exception:
            pass

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self, key, default=None):
        if default is None:
            return self.settings.get(key, self.DEFAULTS.get(key))
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save()
