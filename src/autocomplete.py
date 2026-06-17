import tkinter as tk
import re
from . import theme

class LithiumAutocompleteManager:
    def __init__(self, editor, selected_lang, check_callback=None):
        self.editor = editor
        self.selected_lang = selected_lang
        self.check_callback = check_callback

        self.autocomplete_win = None
        self.autocomplete_listbox = None

        self.editor.bind("<KeyPress>", self.on_editor_keypress)
        self.editor.bind("<Control-space>", lambda event: self.check_autocomplete(event))

    def on_editor_keypress(self, event):
        if self.autocomplete_win and self.autocomplete_win.winfo_exists():
            if event.keysym in ("Down", "Up", "Return", "Tab", "Escape"):
                if event.keysym == "Down":
                    current = self.autocomplete_listbox.curselection()
                    next_idx = (current[0] + 1) if current else 0
                    if next_idx < self.autocomplete_listbox.size():
                        self.autocomplete_listbox.selection_clear(0, tk.END)
                        self.autocomplete_listbox.selection_set(next_idx)
                        self.autocomplete_listbox.activate(next_idx)
                elif event.keysym == "Up":
                    current = self.autocomplete_listbox.curselection()
                    prev_idx = (current[0] - 1) if current else 0
                    if prev_idx >= 0:
                        self.autocomplete_listbox.selection_clear(0, tk.END)
                        self.autocomplete_listbox.selection_set(prev_idx)
                        self.autocomplete_listbox.activate(prev_idx)
                elif event.keysym in ("Return", "Tab"):
                    self.insert_autocomplete()
                    return "break"
                elif event.keysym == "Escape":
                    self.close_autocomplete()
                    return "break"
                return "break"

        pairs = {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'"}
        if event.char in pairs:
            self.editor.insert(tk.INSERT, event.char + pairs[event.char])
            self.editor.mark_set(tk.INSERT, f"{tk.INSERT} -1c")
            if self.check_callback:
                self.check_callback()
            return "break"

    def check_autocomplete(self, event=None):
        if event:
            if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                               "Up", "Down", "Left", "Right", "Return", "Tab", "Escape", "BackSpace"):
                if event.keysym == "BackSpace":
                    self.update_autocomplete_suggestions()
                return
        self.update_autocomplete_suggestions()

    def update_autocomplete_suggestions(self):
        try:
            idx = self.editor.index(tk.INSERT)
            word_start = self.editor.index(f"{idx} -1c wordstart")
            word = self.editor.get(word_start, idx).strip()
        except Exception:
            self.close_autocomplete()
            return

        if not word or not (word[0].isalnum() or word[0] == '_'):
            self.close_autocomplete()
            return

        content = self.editor.get(1.0, tk.END)
        all_words = set(re.findall(r'[a-zA-Z_]\w*', content))

        lang = self.selected_lang.get()
        keywords = {
            "Python": ["print", "def", "class", "import", "from", "return", "if", "else", "elif", "for", "while", "try", "except", "with", "as", "True", "False", "None", "self", "lambda", "yield", "pass", "break", "continue", "in", "is", "not", "and", "or", "range", "len", "list", "dict", "set", "str", "int", "float"],
            "JavaScript": ["console.log", "function", "const", "let", "var", "return", "if", "else", "for", "while", "try", "catch", "class", "import", "export", "from", "true", "false", "null", "undefined", "this", "new", "async", "await", "document", "window", "push", "pop", "length"],
            "TypeScript": ["console.log", "function", "const", "let", "var", "return", "if", "else", "for", "while", "try", "catch", "class", "import", "export", "from", "true", "false", "null", "undefined", "this", "new", "async", "await", "interface", "type", "string", "number", "boolean", "any", "void"]
        }
        lang_keywords = keywords.get(lang, [])

        suggestions = sorted(list((all_words | set(lang_keywords)) - {word}))
        matches = [s for s in suggestions if s.lower().startswith(word.lower())]

        if not matches:
            self.close_autocomplete()
            return

        if not self.autocomplete_win or not self.autocomplete_win.winfo_exists():
            self.autocomplete_win = tk.Toplevel(self.editor.winfo_toplevel())
            self.autocomplete_win.overrideredirect(True)
            self.autocomplete_listbox = tk.Listbox(self.autocomplete_win, bd=0, highlightthickness=1)
            self.autocomplete_listbox.pack(fill=tk.BOTH, expand=True)
            theme.style_autocomplete(self.autocomplete_win, self.autocomplete_listbox)

            self.autocomplete_listbox.bind("<Double-Button-1>", lambda e: self.insert_autocomplete())

        self.autocomplete_listbox.delete(0, tk.END)
        for m in matches:
            self.autocomplete_listbox.insert(tk.END, m)
        self.autocomplete_listbox.selection_set(0)

        try:
            bbox = self.editor.bbox(idx)
            if bbox:
                x, y, _, height = bbox
                root_x = self.editor.winfo_rootx() + x
                root_y = self.editor.winfo_rooty() + y + height + 2
                pop_w = 200
                pop_h = min(150, len(matches) * 20 + 4)
                self.autocomplete_win.geometry(f"{pop_w}x{pop_h}+{root_x}+{root_y}")
                self.autocomplete_win.lift()
            else:
                self.close_autocomplete()
        except Exception:
            self.close_autocomplete()

    def insert_autocomplete(self):
        if not self.autocomplete_listbox:
            return
        sel = self.autocomplete_listbox.curselection()
        if sel:
            chosen = self.autocomplete_listbox.get(sel[0])
            idx = self.editor.index(tk.INSERT)
            word_start = self.editor.index(f"{idx} -1c wordstart")
            self.editor.delete(word_start, idx)
            self.editor.insert(word_start, chosen)
            if self.check_callback:
                self.check_callback()
        self.close_autocomplete()

    def close_autocomplete(self):
        if self.autocomplete_win and self.autocomplete_win.winfo_exists():
            self.autocomplete_win.destroy()
        self.autocomplete_win = None
        self.autocomplete_listbox = None
