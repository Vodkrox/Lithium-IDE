import os
import json
import tkinter as tk
from tkinter import filedialog

class LithiumEditorController:
    def __init__(self, root, editor, line_numbers, status_bar, selected_lang, editor_label):
        self.root = root
        self.editor = editor
        self.line_numbers = line_numbers
        self.status_bar = status_bar
        self.selected_lang = selected_lang
        self.editor_label = editor_label
        self.file_path = None

    def update_line_numbers(self, event=None):
        self.line_numbers.config(state=tk.NORMAL)
        self.line_numbers.delete(1.0, tk.END)
        
        end_line_str = self.editor.index('end-1c').split('.')[0]
        end_line = int(end_line_str) if end_line_str else 1
        
        line_numbers_content = "\n".join(str(i) for i in range(1, end_line + 1))
        self.line_numbers.insert(1.0, line_numbers_content)
        self.line_numbers.config(state=tk.DISABLED)
        self.sync_line_number_scroll()

    def sync_line_number_scroll(self):
        self.line_numbers.yview_moveto(self.editor.yview()[0])

    def update_status(self, event=None):
        pos = self.editor.index(tk.INSERT)
        line, col = pos.split('.')
        lang = self.selected_lang.get()
        path = os.path.basename(self.file_path) if self.file_path else "Untitled"
        self.status_bar.config(text=f"{path}  |  Ln {line}, Col {col}  |  {lang}   ")

    def new_file(self):
        self.editor.delete(1.0, tk.END)
        self.file_path = None
        self.root.title("New File - Lithium IDE")
        self.update_line_numbers()
        self.update_status()
        self.save_cache()

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("Python Files", "*.py"), ("All Files", "*.*")])
        if path:
            self.file_path = path
            with open(path, "r", encoding="utf-8") as file:
                code = file.read()
                self.editor.delete(1.0, tk.END)
                self.editor.insert(1.0, code)
            self.root.title(f"{os.path.basename(path)} - Lithium IDE")
            self.update_line_numbers()
            self.update_status()
            self.save_cache()

    def save_file(self):
        if self.file_path:
            with open(self.file_path, "w", encoding="utf-8") as file:
                file.write(self.editor.get(1.0, tk.END))
            self.update_status()
            self.save_cache()
        else:
            self.save_as_file()

    def save_as_file(self):
        path = filedialog.asksaveasfilename(defaultextension=".py", filetypes=[("Python Files", "*.py"), ("All Files", "*.*")])
        if path:
            self.file_path = path
            with open(self.file_path, "w", encoding="utf-8") as file:
                file.write(self.editor.get(1.0, tk.END))
            self.root.title(f"{os.path.basename(path)} - Lithium IDE")
            self.update_line_numbers()
            self.update_status()
            self.save_cache()

    def save_cache(self):
        try:
            os.makedirs(".cache", exist_ok=True)
            cache_data = {
                "last_file": self.file_path,
                "language": self.selected_lang.get()
            }
            with open(".cache/cache.lthm", "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_cache(self):
        try:
            cache_path = ".cache/cache.lthm"
            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                
                last_file = cache_data.get("last_file")
                lang = cache_data.get("language")
                
                if lang:
                    self.selected_lang.set(lang)
                    self.editor_label.config(text=f"EDITOR ({lang.upper()})")
                
                if last_file and os.path.exists(last_file):
                    self.file_path = last_file
                    with open(last_file, "r", encoding="utf-8") as f_content:
                        code = f_content.read()
                        self.editor.delete(1.0, tk.END)
                        self.editor.insert(1.0, code)
                    self.root.title(f"{os.path.basename(last_file)} - Lithium IDE")
                    self.update_line_numbers()
                    self.update_status()
        except Exception:
            pass
