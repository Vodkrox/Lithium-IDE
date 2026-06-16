import sys
import tkinter as tk
from tkinter import messagebox, ttk
import urllib.request
import json
import threading
import os

from src import theme
from src import runner
from src.editor import LithiumEditorController
from src.autocomplete import LithiumAutocompleteManager

class LithiumIDE:
    def __init__(self, root):
        self.root = root
        self.root.title("Lithium IDE")
        self.root.geometry("900x650")

        self.selected_lang = tk.StringVar(value="Python")
        self.languages = ["Python", "JavaScript", "HTML", "CSS", "C++", "Java", "Rust", "Go"]

        # Create a modern Toolbar at the top
        self.toolbar = tk.Frame(root, bg=theme.COLORS["bg_header"], height=38)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)
        self.toolbar.pack_propagate(False)

        self.toolbar_divider = tk.Frame(root, bg=theme.COLORS["sash_color"], height=1)
        self.toolbar_divider.pack(side=tk.TOP, fill=tk.X)

        self.paned_window = tk.PanedWindow(root, orient=tk.VERTICAL)
        self.paned_window.pack(fill=tk.BOTH, expand=1)

        self.editor_frame = tk.Frame(self.paned_window)
        self.editor_label = tk.Label(self.editor_frame, text="EDITOR (PYTHON)")
        self.editor_label.pack(fill=tk.X)
        
        self.editor_scrollbar = ttk.Scrollbar(self.editor_frame)
        self.editor_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.line_numbers = tk.Text(
            self.editor_frame,
            width=4,
            wrap=tk.NONE,
            state=tk.DISABLED
        )
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
        
        self.editor = tk.Text(
            self.editor_frame, 
            wrap=tk.NONE, 
            undo=True
        )
        self.editor.pack(fill=tk.BOTH, expand=1)

        self.paned_window.add(self.editor_frame, minsize=150)

        self.console_frame = tk.Frame(self.paned_window)
        self.console_label = tk.Label(self.console_frame, text="CONSOLE OUTPUT")
        self.console_label.pack(fill=tk.X)

        self.console_scrollbar = ttk.Scrollbar(self.console_frame)
        self.console_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.console = tk.Text(
            self.console_frame, 
            wrap=tk.WORD, 
            yscrollcommand=self.console_scrollbar.set
        )
        self.console.pack(fill=tk.BOTH, expand=1)
        self.console_scrollbar.config(command=self.console.yview)
        self.console.config(state=tk.DISABLED)

        self.paned_window.add(self.console_frame, minsize=100)

        self.status_bar = tk.Label(root, text="", anchor="e")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.controller = LithiumEditorController(
            self.root, 
            self.editor, 
            self.line_numbers, 
            self.status_bar, 
            self.selected_lang, 
            self.editor_label
        )
        
        def sync_scroll(*args):
            self.editor.yview(*args)
            self.line_numbers.yview(*args)
        
        self.editor_scrollbar.config(command=sync_scroll)
        
        def on_editor_scroll(*args):
            self.editor_scrollbar.set(*args)
            self.line_numbers.yview_moveto(args[0])
            
        self.editor.config(yscrollcommand=on_editor_scroll)

        self.autocomplete = LithiumAutocompleteManager(
            self.editor, 
            self.selected_lang,
            check_callback=self.on_editor_change
        )

        theme.apply_theme(
            self.root, 
            self.editor, 
            self.console, 
            self.paned_window, 
            self.editor_label, 
            self.console_label,
            self.line_numbers,
            self.status_bar,
            self.toolbar,
            self.toolbar_divider
        )

        # Load Assets
        self.icons = {}
        try:
            self.icons["file"] = tk.PhotoImage(file="src/assets/file.png")
            self.icons["theme"] = tk.PhotoImage(file="src/assets/theme.png")
            self.icons["run"] = tk.PhotoImage(file="src/assets/run.png")
            self.icons["python"] = tk.PhotoImage(file="src/assets/python.png")
            self.icons["javascript"] = tk.PhotoImage(file="src/assets/javascript.png")
            self.icons["typescript"] = tk.PhotoImage(file="src/assets/typescript.png")
            self.icons["html"] = tk.PhotoImage(file="src/assets/html.png")
            self.icons["css"] = tk.PhotoImage(file="src/assets/css.png")
            self.icons["generic"] = tk.PhotoImage(file="src/assets/generic.png")
        except Exception:
            pass

        # Populate toolbar buttons
        self.btn_file = tk.Button(self.toolbar, text=" File ▾", image=self.icons.get("file"), compound=tk.LEFT, command=self.show_file_menu)
        self.btn_file.pack(side=tk.LEFT, padx=(10, 2), pady=3)
        theme.style_toolbar_button(self.btn_file)

        self.btn_lang = tk.Button(self.toolbar, text=" Language ▾", image=self.icons.get("generic"), compound=tk.LEFT, command=self.show_lang_menu)
        self.btn_lang.pack(side=tk.LEFT, padx=2, pady=3)
        theme.style_toolbar_button(self.btn_lang)

        self.btn_theme = tk.Button(self.toolbar, text=" Theme ▾", image=self.icons.get("theme"), compound=tk.LEFT, command=self.show_theme_menu)
        self.btn_theme.pack(side=tk.LEFT, padx=2, pady=3)
        theme.style_toolbar_button(self.btn_theme)

        self.btn_run = tk.Button(self.toolbar, text=" Run Script", image=self.icons.get("run"), compound=tk.LEFT, command=self.run_code)
        self.btn_run.pack(side=tk.LEFT, padx=(20, 2), pady=3)
        theme.style_toolbar_button(self.btn_run)

        self.editor.bind("<KeyRelease>", self.on_editor_change)
        self.editor.bind("<ButtonRelease-1>", lambda e: self.controller.update_status())
        self.editor.bind("<MouseWheel>", lambda e: self.root.after(10, self.controller.sync_line_number_scroll))

        self.create_menu()

        self.controller.load_cache()
        self.controller.update_line_numbers()
        self.controller.update_status()

        # Update language button icon after loading cache
        lang = self.selected_lang.get()
        icon_key = lang.lower()
        if icon_key not in self.icons:
            icon_key = "generic"
        self.btn_lang.config(text=f" {lang} ▾", image=self.icons.get(icon_key))

        threading.Thread(target=self.load_languages_async, daemon=True).start()

    def on_editor_change(self, event=None):
        self.controller.update_line_numbers()
        self.controller.update_status()
        self.autocomplete.check_autocomplete(event)

    def show_file_menu(self):
        x = self.btn_file.winfo_rootx()
        y = self.btn_file.winfo_rooty() + self.btn_file.winfo_height()
        self.file_menu.post(x, y)

    def show_lang_menu(self):
        x = self.btn_lang.winfo_rootx()
        y = self.btn_lang.winfo_rooty() + self.btn_lang.winfo_height()
        self.lang_menu.post(x, y)

    def show_theme_menu(self):
        x = self.btn_theme.winfo_rootx()
        y = self.btn_theme.winfo_rooty() + self.btn_theme.winfo_height()
        self.theme_menu.post(x, y)

    def create_menu(self):
        self.file_menu = tk.Menu(self.root, tearoff=0)
        theme.style_menu(self.file_menu)
        self.file_menu.add_command(label="New", command=self.controller.new_file, accelerator="Ctrl+N")
        self.file_menu.add_command(label="Open", command=self.controller.open_file, accelerator="Ctrl+O")
        self.file_menu.add_command(label="Save", command=self.controller.save_file, accelerator="Ctrl+S")
        self.file_menu.add_command(label="Save As", command=self.controller.save_as_file)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=self.root.quit)

        self.lang_menu = tk.Menu(self.root, tearoff=0)
        theme.style_menu(self.lang_menu)
        self.build_languages_menu()

        self.theme_menu = tk.Menu(self.root, tearoff=0)
        theme.style_menu(self.theme_menu)
        self.build_theme_menu()

        self.root.bind("<Control-n>", lambda event: self.controller.new_file())
        self.root.bind("<Control-o>", lambda event: self.controller.open_file())
        self.root.bind("<Control-s>", lambda event: self.controller.save_file())
        self.root.bind("<F5>", lambda event: self.run_code())
        self.root.bind("<Control-Shift-P>", lambda event: self.show_search_dialog())
        self.root.bind("<Control-Shift-p>", lambda event: self.show_search_dialog())

    def build_languages_menu(self):
        self.lang_menu.delete(0, tk.END)

        self.lang_menu.add_command(
            label="Search Language...", 
            command=self.show_search_dialog, 
            accelerator="Ctrl+Shift+P"
        )
        self.lang_menu.add_separator()

        most_used = ["Python", "JavaScript", "TypeScript", "HTML", "CSS", "C++", "C#", "Java", "PHP", "Go", "Rust", "SQL"]
        most_used_sub = tk.Menu(self.lang_menu, tearoff=0)
        theme.style_menu(most_used_sub)
        for lang in sorted(most_used):
            most_used_sub.add_radiobutton(
                label=lang,
                variable=self.selected_lang,
                value=lang,
                command=self.on_language_select
            )
        self.lang_menu.add_cascade(label="Most Used", menu=most_used_sub)
        self.lang_menu.add_separator()

        groups = {}
        for lang in sorted(self.languages, key=lambda s: s.lower()):
            first_char = lang[0].upper()
            if not first_char.isalpha():
                first_char = "#"
            
            if first_char in "ABC":
                group_name = "A - C"
            elif first_char in "DEF":
                group_name = "D - F"
            elif first_char in "GHI":
                group_name = "G - I"
            elif first_char in "JKL":
                group_name = "J - L"
            elif first_char in "MNO":
                group_name = "M - O"
            elif first_char in "PQR":
                group_name = "P - R"
            elif first_char in "STU":
                group_name = "S - U"
            elif first_char in "VWXYZ#":
                group_name = "V - Z"
            else:
                group_name = "Other"

            groups.setdefault(group_name, []).append(lang)

        for group_title in sorted(groups.keys()):
            sub = tk.Menu(self.lang_menu, tearoff=0)
            theme.style_menu(sub)
            for lang in groups[group_title]:
                sub.add_radiobutton(
                    label=lang, 
                    variable=self.selected_lang, 
                    value=lang,
                    command=self.on_language_select
                )
            self.lang_menu.add_cascade(label=group_title, menu=sub)

    def on_language_select(self):
        lang = self.selected_lang.get()
        self.editor_label.config(text=f"EDITOR ({lang.upper()})")
        self.controller.update_status()
        self.controller.save_cache()
        icon_key = lang.lower()
        if icon_key not in self.icons:
            icon_key = "generic"
        self.btn_lang.config(text=f" {lang} ▾", image=self.icons.get(icon_key))

    def build_theme_menu(self):
        self.theme_menu.delete(0, tk.END)
        for theme_name in theme.THEMES.keys():
            self.theme_menu.add_command(
                label=theme_name,
                command=lambda t=theme_name: self.change_theme(t)
            )

    def change_theme(self, theme_name):
        theme.set_theme(theme_name)
        theme.apply_theme(
            self.root, 
            self.editor, 
            self.console, 
            self.paned_window, 
            self.editor_label, 
            self.console_label,
            self.line_numbers,
            self.status_bar,
            self.toolbar,
            self.toolbar_divider
        )
        theme.style_toolbar_button(self.btn_file)
        theme.style_toolbar_button(self.btn_lang)
        theme.style_toolbar_button(self.btn_theme)
        theme.style_toolbar_button(self.btn_run)

        theme.style_menu(self.file_menu)
        theme.style_menu(self.lang_menu)
        theme.style_menu(self.theme_menu)

        self.build_languages_menu()
        self.build_theme_menu()


    def run_code(self, event=None):
        if not self.controller.file_path:
            self.controller.save_as_file()
            if not self.controller.file_path:
                return
        else:
            self.controller.save_file()
        
        runner.run_code(self.controller.file_path, self.console)

    def show_search_dialog(self):
        search_win = tk.Toplevel(self.root)
        search_win.title("Search Language")
        search_win.geometry("350x450")
        search_win.resizable(False, False)
        search_win.transient(self.root)
        search_win.grab_set()

        title_label = tk.Label(search_win, text="Search for a programming language:")
        title_label.pack(fill=tk.X, padx=15, pady=(15, 5), anchor="w")

        search_entry = tk.Entry(search_win)
        search_entry.pack(fill=tk.X, padx=15, pady=5)
        search_entry.focus_set()

        list_frame = tk.Frame(search_win)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 15))

        list_scrollbar = ttk.Scrollbar(list_frame)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        listbox = tk.Listbox(list_frame, yscrollcommand=list_scrollbar.set)
        listbox.pack(fill=tk.BOTH, expand=True)
        list_scrollbar.config(command=listbox.yview)

        theme.style_search_dialog(search_win, search_entry, listbox, title_label)

        def update_list(query=""):
            listbox.delete(0, tk.END)
            for lang in sorted(self.languages, key=lambda s: s.lower()):
                if query.lower() in lang.lower():
                    listbox.insert(tk.END, lang)

        update_list()

        def on_key_release(event):
            update_list(search_entry.get())

        def select_language(event=None):
            selection = listbox.curselection()
            if selection:
                chosen = listbox.get(selection[0])
                self.selected_lang.set(chosen)
                self.on_language_select()
                search_win.destroy()

        search_entry.bind("<KeyRelease>", on_key_release)
        search_entry.bind("<Return>", select_language)
        listbox.bind("<Double-Button-1>", select_language)
        listbox.bind("<Return>", select_language)

        def focus_listbox(event):
            listbox.focus_set()
            if listbox.size() > 0:
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(0)
                listbox.activate(0)

        search_entry.bind("<Down>", focus_listbox)

    def load_languages_async(self):
        try:
            url = "https://raw.githubusercontent.com/blakeembrey/language-map/master/languages.json"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                fetched_langs = []
                for name, info in data.items():
                    if info.get("type") == "programming":
                        fetched_langs.append(name)
                
                if fetched_langs:
                    self.languages = list(set(self.languages + fetched_langs))
                    self.root.after(0, self.build_languages_menu)
        except Exception:
            pass

if __name__ == "__main__":
    root = tk.Tk()
    app = LithiumIDE(root)
    root.mainloop()
