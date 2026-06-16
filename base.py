import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import urllib.request
from urllib.parse import urlparse
import json
import threading
import os

from src import theme
from src import runner
from src.editor import LithiumEditorController
from src.autocomplete import LithiumAutocompleteManager
from src.ai_powered import ai_engine as ai_runner

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
        self.btn_file = tk.Button(self.toolbar, text=" File ▾", image=self.icons.get("file", ""), compound=tk.LEFT, command=self.show_file_menu)
        self.btn_file.pack(side=tk.LEFT, padx=(10, 2), pady=3)
        theme.style_toolbar_button(self.btn_file)

        self.btn_lang = tk.Button(self.toolbar, text=" Language ▾", image=self.icons.get("generic", ""), compound=tk.LEFT, command=self.show_lang_menu)
        self.btn_lang.pack(side=tk.LEFT, padx=2, pady=3)
        theme.style_toolbar_button(self.btn_lang)

        self.btn_ai = tk.Button(self.toolbar, text=" AI ▾", image=self.icons.get("generic", ""), compound=tk.LEFT, command=self.show_ai_menu)
        self.btn_ai.pack(side=tk.LEFT, padx=2, pady=3)
        theme.style_toolbar_button(self.btn_ai)

        self.ai_link_file = os.path.join("src", "ai_powered", "ll_models.lthm")
        self.ai_prompt_file = os.path.join("src", "ai_powered", "parameters.ltai")
        self.ai_model_link = ""
        self.ai_system_prompt = ""
        self.load_ai_settings()

        self.btn_theme = tk.Button(self.toolbar, text=" Theme ▾", image=self.icons.get("theme", ""), compound=tk.LEFT, command=self.show_theme_menu)
        self.btn_theme.pack(side=tk.LEFT, padx=2, pady=3)
        theme.style_toolbar_button(self.btn_theme)

        self.btn_run = tk.Button(self.toolbar, text=" Run Script", image=self.icons.get("run", ""), compound=tk.LEFT, command=self.run_code)
        self.btn_run.pack(side=tk.LEFT, padx=(20, 2), pady=3)
        theme.style_toolbar_button(self.btn_run)

        self.active_menu = None

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
        self.btn_lang.config(text=f" {lang} ▾", image=self.icons.get(icon_key, ""))

        threading.Thread(target=self.load_languages_async, daemon=True).start()

    def on_editor_change(self, event=None):
        self.controller.update_line_numbers()
        self.controller.update_status()
        self.autocomplete.check_autocomplete(event)

    def show_file_menu(self):
        self.close_menus()
        x = self.btn_file.winfo_rootx()
        y = self.btn_file.winfo_rooty() + self.btn_file.winfo_height()
        self.file_menu.post(x, y)
        self.active_menu = self.file_menu

    def show_lang_menu(self):
        self.close_menus()
        x = self.btn_lang.winfo_rootx()
        y = self.btn_lang.winfo_rooty() + self.btn_lang.winfo_height()
        self.lang_menu.post(x, y)
        self.active_menu = self.lang_menu

    def show_ai_menu(self):
        self.close_menus()
        x = self.btn_ai.winfo_rootx()
        y = self.btn_ai.winfo_rooty() + self.btn_ai.winfo_height()
        self.ai_menu.post(x, y)
        self.active_menu = self.ai_menu

    def show_theme_menu(self):
        self.close_menus()
        x = self.btn_theme.winfo_rootx()
        y = self.btn_theme.winfo_rooty() + self.btn_theme.winfo_height()
        self.theme_menu.post(x, y)
        self.active_menu = self.theme_menu

    def close_menus(self):
        try:
            self.file_menu.unpost()
            self.lang_menu.unpost()
            self.ai_menu.unpost()
            self.theme_menu.unpost()
        except Exception:
            pass
        self.active_menu = None

    def on_root_click(self, event):
        if not self.active_menu:
            return

        widget = event.widget
        if widget in (self.btn_file, self.btn_lang, self.btn_ai, self.btn_theme):
            return
        if isinstance(widget, tk.Menu):
            return

        self.close_menus()

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

        self.ai_menu = tk.Menu(self.root, tearoff=0)
        theme.style_menu(self.ai_menu)
        self.build_ai_menu()

        self.theme_menu = tk.Menu(self.root, tearoff=0)
        theme.style_menu(self.theme_menu)
        self.build_theme_menu()

        self.root.bind_all("<Button-1>", self.on_root_click, add="+")
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
        self.btn_lang.config(text=f" {lang} ▾", image=self.icons.get(icon_key, ""))

    def load_ai_settings(self):
        self.ai_model_link = ai_runner.load_model_source(self.ai_link_file) or ""
        self.ai_system_prompt = ai_runner.load_system_prompt(self.ai_prompt_file)
        if self.ai_model_link:
            self.status_bar.config(text=f"AI: configured model {self.ai_model_link}")

    def build_ai_menu(self):
        self.ai_menu.delete(0, tk.END)
        self.ai_menu.add_command(
            label="Configure AI Model",
            command=self.configure_ai_model
        )
        self.ai_menu.add_command(
            label="Run AI Prompt",
            command=self.ask_ai_prompt
        )
        self.ai_menu.add_command(
            label="Check AI Status",
            command=self.check_ai_status
        )
        self.ai_menu.add_separator()
        self.ai_menu.add_command(
            label="About AI",
            command=lambda: messagebox.showinfo(
                "AI",
                "This menu lets you configure and run a local AI model."
            )
        )

    def configure_ai_model(self):
        config_win = tk.Toplevel(self.root)
        config_win.title("Configure AI Model")
        config_win.geometry("520x320")
        config_win.resizable(False, False)
        config_win.transient(self.root)
        config_win.grab_set()

        tk.Label(
            config_win,
            text="AI assistant: a single built-in model is available. Click 'Download' to install it locally.",
            wraplength=480,
            justify=tk.LEFT
        ).pack(fill=tk.X, padx=12, pady=(12, 8), anchor="w")

        # Load the single available candidate (ai_engine enforces a single candidate)
        candidates = ai_runner.list_model_candidates(self.ai_link_file)
        if not candidates:
            tk.Label(config_win, text="No downloadable model available.").pack(fill=tk.X, padx=12, pady=12)
            tk.Button(config_win, text="Close", command=config_win.destroy).pack(pady=10)
            return

        model_name, model_url = candidates[0]
        tk.Label(config_win, text=f"Model: {model_name}").pack(fill=tk.X, padx=12, pady=(6, 8), anchor="w")

        progress_label = tk.Label(config_win, text="", anchor="w")
        progress_label.pack(fill=tk.X, padx=12, pady=(0, 4))

        progress_bar = ttk.Progressbar(config_win, orient="horizontal", mode="determinate", maximum=100)
        progress_bar.pack(fill=tk.X, padx=12, pady=(0, 10))

        download_in_progress = {"active": False}

        def on_close():
            if download_in_progress["active"]:
                messagebox.showwarning("AI", "The model is downloading. Please wait until it finishes.")
                return
            config_win.destroy()

        def _update_progress(downloaded, total):
            if total and total > 0:
                percentage = int(downloaded * 100 / total)
                progress_bar.config(mode="determinate", maximum=100)
                progress_bar["value"] = percentage
                progress_label.config(text=f"Downloading... {percentage}%")
            else:
                progress_bar.config(mode="indeterminate")
                try:
                    progress_bar.start(10)
                except Exception:
                    pass
                progress_label.config(text="Downloading...")

        def update_progress(downloaded, total):
            self.root.after(0, lambda: _update_progress(downloaded, total))

        def reset_progress():
            try:
                progress_bar.stop()
            except Exception:
                pass
            progress_bar.config(mode="determinate", value=0)
            progress_label.config(text="")
            download_button.config(state="normal")
            close_button.config(state="normal")
            download_in_progress["active"] = False

        def start_download():
            url = model_url
            if not url:
                messagebox.showerror("AI", "No model URL available to download.")
                return

            if download_in_progress["active"]:
                return

            download_in_progress["active"] = True
            download_button.config(state="disabled")
            close_button.config(state="disabled")
            progress_bar.config(mode="indeterminate")
            progress_bar.start(10)
            progress_label.config(text="Downloading...")

            def download_job():
                try:
                    local_path = ai_runner.download_model_url(url, progress_callback=update_progress)
                    # save model path to settings (system prompt remains unchanged)
                    ai_runner.save_model_settings(self.ai_link_file, self.ai_prompt_file, local_path, self.ai_system_prompt)
                    self.root.after(0, lambda: self.load_ai_settings())
                    self.root.after(0, lambda: self.status_bar.config(text=f"AI: downloaded model to {local_path}"))
                    self.root.after(0, lambda: progress_label.config(text="Download complete"))
                except Exception as exc:
                    exc_text = str(exc)
                    def show_error():
                        messagebox.showerror("AI Download Error", exc_text)
                        self.status_bar.config(text=f"AI: download error {exc_text}")
                    self.root.after(0, show_error)
                finally:
                    self.root.after(0, reset_progress)

            threading.Thread(target=download_job, daemon=True).start()

        download_button = tk.Button(config_win, text="Download", command=start_download)
        download_button.pack(pady=(4, 8))

        tk.Label(config_win, text="The system prompt is managed in src/ai_powered/parameters.ltai and is not editable here.").pack(fill=tk.X, padx=12, pady=(6, 6))
        close_button = tk.Button(config_win, text="Close", command=on_close)
        close_button.pack(pady=6)
        config_win.protocol("WM_DELETE_WINDOW", on_close)

    def ask_ai_prompt(self):
        if not self.ai_model_link:
            messagebox.showwarning("AI", "No AI model is configured. Please configure the model first.")
            return

        prompt_win = tk.Toplevel(self.root)
        prompt_win.title("Run AI Prompt")
        prompt_win.geometry("520x360")
        prompt_win.resizable(False, False)
        prompt_win.transient(self.root)
        prompt_win.grab_set()

        tk.Label(prompt_win, text="Enter your question or instruction:").pack(fill=tk.X, padx=15, pady=(15, 5), anchor="w")
        prompt_box = tk.Text(prompt_win, height=12, wrap=tk.WORD)
        prompt_box.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))

        def submit_prompt():
            prompt_text = prompt_box.get("1.0", tk.END).strip()
            if not prompt_text:
                messagebox.showwarning("AI", "Prompt cannot be empty.")
                return
            prompt_win.destroy()
            threading.Thread(target=self.run_ai_prompt, args=(prompt_text,), daemon=True).start()

        tk.Button(prompt_win, text="Generate response", command=submit_prompt).pack(pady=10)

    def run_ai_prompt(self, prompt):
        self.root.after(0, lambda: self.status_bar.config(text="AI: running local model..."))
        try:
            result = ai_runner.generate_text_from_model(self.ai_model_link, self.ai_system_prompt, prompt)

            def finish():
                self.console.config(state=tk.NORMAL)
                self.console.insert(tk.END, "\n=== AI OUTPUT ===\n")
                self.console.insert(tk.END, result + "\n")
                self.console.see(tk.END)
                self.console.config(state=tk.DISABLED)
                self.status_bar.config(text="AI: response generated.")

            self.root.after(0, finish)
        except Exception as exc:
            def fail():
                messagebox.showerror("AI error", str(exc))
                self.status_bar.config(text=f"AI: error {exc}")

            self.root.after(0, fail)

    def check_ai_status(self):
        runtime = ai_runner.get_runtime_status()
        if runtime:
            messagebox.showinfo("AI Status", f"AI backend available: {runtime}\nModel: {self.ai_model_link or 'Not configured'}")
            self.status_bar.config(text=f"AI: backend {runtime} available")
        else:
            messagebox.showwarning(
                "AI Status",
                "No local AI backend was found. Install llama-cpp or transformers and torch in your Python environment."
            )
            self.status_bar.config(text="AI: local backend not available")

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
        theme.style_toolbar_button(self.btn_ai)
        theme.style_toolbar_button(self.btn_theme)
        theme.style_toolbar_button(self.btn_run)

        theme.style_menu(self.file_menu)
        theme.style_menu(self.lang_menu)
        theme.style_menu(self.ai_menu)
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
