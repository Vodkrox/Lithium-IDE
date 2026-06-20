import json
import os
import tkinter as tk
from tkinter import filedialog

from .settings import SettingsManager


class LithiumEditorController:
    def __init__(
        self,
        root,
        editor,
        line_numbers,
        status_bar,
        selected_lang,
        editor_label,
        on_file_open_callback=None,
        require_explorer_open=False,
        settings_manager=None,
    ):
        self.root = root
        self.editor = editor
        self.line_numbers = line_numbers
        self.status_bar = status_bar
        self.selected_lang = selected_lang
        self.editor_label = editor_label
        self.file_path = None
        self.on_file_open_callback = on_file_open_callback
        self.on_dirty_state_changed_callback = None
        self.on_filesystem_change_callback = None
        self.require_explorer_open = require_explorer_open
        self.has_unsaved_changes = False
        self.settings_manager = settings_manager or SettingsManager()

    def update_line_numbers(self, event=None):
        self.line_numbers.config(state=tk.NORMAL)
        self.line_numbers.delete(1.0, tk.END)

        end_line_str = self.editor.index("end-1c").split(".")[0]
        end_line = int(end_line_str) if end_line_str else 1

        line_numbers_content = "\n".join(str(i) for i in range(1, end_line + 1))
        self.line_numbers.insert(1.0, line_numbers_content)
        self.line_numbers.config(state=tk.DISABLED)
        self.sync_line_number_scroll()

    def sync_line_number_scroll(self):
        self.line_numbers.yview_moveto(self.editor.yview()[0])

    def update_status(self, event=None):
        pos = self.editor.index(tk.INSERT)
        line, col = pos.split(".")
        lang = self.selected_lang.get()
        path = os.path.basename(self.file_path) if self.file_path else "Untitled"
        self.status_bar.config(text=f"{path}  |  Ln {line}, Col {col}  |  {lang}   ")

    def update_title(self):
        file_name = os.path.basename(self.file_path) if self.file_path else "Untitled"
        dirty_marker = "* " if self.has_unsaved_changes else ""
        self.root.title(f"{dirty_marker}{file_name} - Lithium IDE")

    def _notify_dirty_state(self):
        if self.on_dirty_state_changed_callback:
            self.on_dirty_state_changed_callback(
                self.file_path, self.has_unsaved_changes
            )

    def _notify_filesystem_change(self):
        if self.on_filesystem_change_callback:
            self.on_filesystem_change_callback()

    def mark_dirty(self):
        if not self.has_unsaved_changes:
            self.has_unsaved_changes = True
            self.update_title()
            self._notify_dirty_state()
        self.editor.edit_modified(False)

    def mark_clean(self):
        if self.has_unsaved_changes:
            self.has_unsaved_changes = False
            self.update_title()
            self._notify_dirty_state()
        self.editor.edit_modified(False)

    def new_file(self):
        if self.require_explorer_open:
            self.editor.delete(1.0, tk.END)
            self.file_path = None
            self.has_unsaved_changes = False
            self.editor.edit_modified(False)
            self.update_title()
            self.update_line_numbers()
            self.update_status()
            return

        self.editor.delete(1.0, tk.END)
        self.file_path = None
        self.has_unsaved_changes = False
        self.editor.edit_modified(False)
        self.update_title()
        self.update_line_numbers()
        self.update_status()
        if self.on_file_open_callback:
            self.on_file_open_callback()

    def open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("All Files", "*.*"), ("Python Files", "*.py")]
        )
        if path:
            self.file_path = path
            self.editor.config(state=tk.NORMAL)
            with open(path, "r", encoding="utf-8") as file:
                code = file.read()
                self.editor.delete(1.0, tk.END)
                self.editor.insert(1.0, code)
            self.has_unsaved_changes = False
            self.editor.edit_modified(False)
            self.root.title(f"{os.path.basename(path)} - Lithium IDE")
            self.update_line_numbers()
            self.update_status()
            if self.on_file_open_callback:
                self.on_file_open_callback()
            if (
                hasattr(self, "on_single_file_open_callback")
                and self.on_single_file_open_callback
            ):
                self.on_single_file_open_callback()

    def save_file(self):
        if self.file_path:
            try:
                with open(self.file_path, "w", encoding="utf-8") as file:
                    file.write(self.editor.get(1.0, tk.END))
                self._notify_filesystem_change()
                self.mark_clean()
                self.update_status()
                self.settings_manager.set("language", self.selected_lang.get())
                return True
            except Exception:
                return False
        else:
            return self.save_as_file()

    def save_as_file(self):
        if self.require_explorer_open and not self.file_path:
            from tkinter import messagebox

            messagebox.showinfo(
                "Info", "Please create a new file from the File Explorer panel first."
            )
            return False

        path = filedialog.asksaveasfilename(
            defaultextension=".py",
            filetypes=[("Python Files", "*.py"), ("All Files", "*.*")],
        )
        if path:
            self.file_path = path
            with open(self.file_path, "w", encoding="utf-8") as file:
                file.write(self.editor.get(1.0, tk.END))
            self._notify_filesystem_change()
            self.editor.edit_modified(False)
            self.update_line_numbers()
            self.settings_manager.set("language", self.selected_lang.get())
            if self.on_file_open_callback:
                self.on_file_open_callback()
            self.mark_clean()
            self.update_title()
            self.update_status()
            return True
        return False

    def _save_language_preference(self):
        try:
            self.settings_manager.set("language", self.selected_lang.get())
        except Exception:
            pass
