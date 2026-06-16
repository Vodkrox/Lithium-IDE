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
from src.ai_powered.ai_skills import get_executor as get_ai_skills_executor, reset_executor as reset_ai_skills_executor, AISkillResult
from src.ai_powered.conversation_manager import get_conversation_manager, Conversation
from src.file_explorer import FileExplorer

class LithiumIDE:
    def __init__(self, root):
        self.root = root
        self.root.title("Lithium IDE")
        self.root.geometry("900x650")

        self.root.after(100, self.check_and_setup_dependencies)

        self.selected_lang = tk.StringVar(value="Python")
        self.languages = ["Python", "JavaScript", "HTML", "CSS", "C++", "Java", "Rust", "Go"]

        # Create a modern Toolbar at the top
        self.toolbar = tk.Frame(root, bg=theme.COLORS["bg_header"], height=38)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)
        self.toolbar.pack_propagate(False)

        self.toolbar_divider = tk.Frame(root, bg=theme.COLORS["sash_color"], height=1)
        self.toolbar_divider.pack(side=tk.TOP, fill=tk.X)

        # Status bar at bottom (packed before main_paned to ensure visibility)
        self.status_bar = tk.Frame(root, bg=theme.COLORS["bg_header"], height=25)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_bar.pack_propagate(False)
        
        # Status label (left side)
        self.status_label = tk.Label(
            self.status_bar,
            text="",
            anchor="w",
            font=("Segoe UI", 9),
            fg=theme.COLORS["fg_dim"],
            bg=theme.COLORS["bg_header"]
        )
        self.status_label.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        # Conversation dropdown button
        self.conv_dropdown_btn = tk.Button(
            self.status_bar,
            text="💬 No conversation",
            font=("Segoe UI", 9),
            fg=theme.COLORS["fg_light"],
            bg=theme.COLORS["bg_header"],
            bd=0,
            activebackground=theme.COLORS["sash_color"],
            activeforeground=theme.COLORS["fg_light"],
            cursor="hand2",
            command=self.show_conversations_dropdown
        )
        self.conv_dropdown_btn.pack(side=tk.RIGHT, padx=10)

        # Main horizontal paned window
        self.main_paned = tk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=1)

        # Create center-right paned window (will contain editor/console + AI chat)
        self.center_right_paned = tk.PanedWindow(self.main_paned, orient=tk.HORIZONTAL)

        # Create vertical paned window for editor and console
        self.paned_window = tk.PanedWindow(self.center_right_paned, orient=tk.VERTICAL)
        self.center_right_paned.add(self.paned_window, minsize=400)

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

        self.controller = LithiumEditorController(
            self.root, 
            self.editor, 
            self.line_numbers, 
            self.status_label, 
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

        self.ai_model_link = ai_runner.MODEL_CANDIDATES[0][1] if ai_runner.MODEL_CANDIDATES else ""
        self.ai_system_prompt = ai_runner.DEFAULT_SYSTEM_PROMPT
        
        # Initialize AI Skills Executor
        self.ai_skills_executor = None
        self._init_ai_skills()
        
        if self.ai_model_link:
            self.status_label.config(text=f"AI: configured model {self.ai_model_link}")

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

        # Configure main_paned style
        self.main_paned.config(
            bg=theme.COLORS["bg_dark"],
            bd=0,
            sashwidth=4,
            sashpad=1,
            sashrelief=tk.FLAT
        )

        # Configure center_right_paned style
        self.center_right_paned.config(
            bg=theme.COLORS["bg_dark"],
            bd=0,
            sashwidth=4,
            sashpad=1,
            sashrelief=tk.FLAT
        )

        # File Explorer Sidebar Frame (left side)
        self.explorer_frame = tk.Frame(self.main_paned, bg=theme.COLORS["bg_dark"], width=250)
        self.explorer_frame.pack_propagate(False)
        
        # Initialize File Explorer
        self.file_explorer = FileExplorer(
            self.explorer_frame,
            self.controller,
            theme.COLORS,
            theme.FONTS
        )
        self.main_paned.add(self.explorer_frame, minsize=150, width=250)

        # Add center-right paned window (editor/console + AI chat) to main paned
        self.main_paned.add(self.center_right_paned, minsize=400)

        # Initialize conversation manager
        self.conversation_manager = get_conversation_manager()
        self._conversation_ids = []
        self.current_conversation_label = tk.StringVar(value="No conversation")
        
        # AI Chat Sidebar Frame (right side, initially hidden)
        self.chat_frame = tk.Frame(self.center_right_paned, bg=theme.COLORS["bg_dark"])
        
        # === Chat Panel ===
        self.chat_panel = tk.Frame(self.chat_frame, bg=theme.COLORS["bg_dark"])
        self.chat_panel.pack(fill=tk.BOTH, expand=True)
        
        # Header frame
        self.chat_header = tk.Frame(self.chat_panel, bg=theme.COLORS["bg_header"], height=35)
        self.chat_header.pack(fill=tk.X, side=tk.TOP)
        self.chat_header.pack_propagate(False)
        
        self.chat_header_label = tk.Label(
            self.chat_header, 
            text="AI CHAT ASSISTANT", 
            font=theme.FONTS["header"], 
            fg=theme.COLORS["fg_dim"], 
            bg=theme.COLORS["bg_header"]
        )
        self.chat_header_label.pack(side=tk.LEFT, padx=12, pady=8)
        
        self.chat_close_btn = tk.Button(
            self.chat_header, 
            text="✕", 
            font=("Segoe UI", 10), 
            fg=theme.COLORS["fg_dim"], 
            bg=theme.COLORS["bg_header"], 
            bd=0, 
            activebackground=theme.COLORS["sash_color"], 
            activeforeground=theme.COLORS["accent"], 
            command=self.toggle_ai_chat
        )
        self.chat_close_btn.pack(side=tk.RIGHT, padx=10)
        
        # Chat history scrollbar
        self.chat_scrollbar = ttk.Scrollbar(self.chat_panel)
        self.chat_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.chat_history = tk.Text(
            self.chat_panel, 
            wrap=tk.WORD, 
            yscrollcommand=self.chat_scrollbar.set,
            font=theme.FONTS["ui"],
            bg=theme.COLORS["bg_editor"],
            fg=theme.COLORS["fg_light"],
            bd=0,
            highlightthickness=0
        )
        self.chat_history.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))
        self.chat_scrollbar.config(command=self.chat_history.yview)
        self.chat_history.config(state=tk.DISABLED)
        # Dictionary to keep track of button frames for each code snippet
        self.button_frames = {}
        # Dictionary to keep track of start index of each code snippet in chat history
        self.code_indices = {}

        
        # Input container
        self.chat_input_container = tk.Frame(self.chat_panel, bg=theme.COLORS["bg_dark"])
        self.chat_input_container.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=(5, 10))
        
        self.chat_input = tk.Text(
            self.chat_input_container, 
            height=3, 
            wrap=tk.WORD,
            font=theme.FONTS["ui"],
            bg=theme.COLORS["bg_editor"],
            fg=theme.COLORS["fg_light"],
            insertbackground=theme.COLORS["accent"],
            bd=0,
            highlightthickness=1,
            highlightbackground=theme.COLORS["sash_color"],
            highlightcolor=theme.COLORS["accent"]
        )
        self.chat_input.pack(fill=tk.X, side=tk.TOP, pady=(0, 5))
        
        self.chat_button_frame = tk.Frame(self.chat_input_container, bg=theme.COLORS["bg_dark"])
        self.chat_button_frame.pack(fill=tk.X, side=tk.TOP)
        
        self.chat_send_btn = tk.Button(
            self.chat_button_frame, 
            text="Send", 
            command=self.send_chat_message
        )
        self.chat_send_btn.pack(side=tk.RIGHT)
        theme.style_toolbar_button(self.chat_send_btn)
        
        self.chat_clear_btn = tk.Button(
            self.chat_button_frame, 
            text="Clear", 
            command=self.clear_chat
        )
        self.chat_clear_btn.pack(side=tk.LEFT)
        theme.style_toolbar_button(self.chat_clear_btn)

        self.chat_visible = True
        self.center_right_paned.add(self.chat_frame, minsize=450, width=500)

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
        self.file_menu.add_command(label="Open Folder", command=self.open_folder)
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
        self.ai_menu.add_command(
            label="Toggle AI Chat Sidebar",
            command=self.toggle_ai_chat
        )
        self.ai_menu.add_separator()
        self.ai_menu.add_command(
            label="AI Skills Info",
            command=self.show_ai_skills_info
        )
        self.ai_menu.add_separator()
        self.ai_menu.add_command(
            label="About AI",
            command=lambda: messagebox.showinfo(
                "AI",
                "This menu lets you configure and run a local AI model with file and code manipulation capabilities."
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
        candidates = ai_runner.list_model_candidates()
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
                    self.ai_model_link = local_path
                    self.root.after(0, lambda: self.status_label.config(text=f"AI: configured model {self.ai_model_link}"))
                    self.root.after(0, lambda: self.status_label.config(text=f"AI: downloaded model to {local_path}"))
                    self.root.after(0, lambda: progress_label.config(text="Download complete"))
                except Exception as exc:
                    exc_text = str(exc)
                    def show_error():
                        messagebox.showerror("AI Download Error", exc_text)
                        self.status_label.config(text=f"AI: download error {exc_text}")
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
        self.root.after(0, lambda: self.status_label.config(text="AI: running local model..."))
        try:
            result = ai_runner.generate_text_from_model(self.ai_model_link, self.ai_system_prompt, prompt)

            def finish():
                self.console.config(state=tk.NORMAL)
                self.console.insert(tk.END, "\n=== AI OUTPUT ===\n")
                self.console.insert(tk.END, result + "\n")
                self.console.see(tk.END)
                self.console.config(state=tk.DISABLED)
                self.status_label.config(text="AI: response generated.")

            self.root.after(0, finish)
        except Exception as exc:
            exc_text = str(exc)
            def fail():
                messagebox.showerror("AI error", exc_text)
                self.status_label.config(text=f"AI: error {exc_text}")

            self.root.after(0, fail)

    def check_ai_status(self):
        runtime = ai_runner.get_runtime_status()
        if runtime:
            messagebox.showinfo("AI Status", f"AI backend available: {runtime}\nModel: {self.ai_model_link or 'Not configured'}")
            self.status_label.config(text=f"AI: backend {runtime} available")
        else:
            messagebox.showwarning(
                "AI Status",
                "No local AI backend was found. Install llama-cpp or transformers and torch in your Python environment."
            )
            self.status_label.config(text="AI: local backend not available")

    def show_ai_skills_info(self):
        """Show information about available AI Skills."""
        info_text = """AI Skills - File and Code Manipulation

The AI assistant can perform the following actions using special skill tags:

1. ADD LINES - Insert code at a specific position
   Example: "Add a function at line 5"

2. DELETE LINES - Remove lines from the editor
   Example: "Delete lines 10 to 15"

3. CREATE FILE - Create a new file with content
   Example: "Create a file called utils.py with helper functions"

4. DELETE FILE - Remove an existing file
   Example: "Delete the file old_module.py"

5. CREATE FOLDER - Create a new directory
   Example: "Create a folder called tests"

6. DELETE FOLDER - Remove a directory and its contents
   Example: "Delete the temp folder"

The AI will automatically use these skills when you ask it to modify
your code or create/delete files. Just use the AI Chat sidebar to
communicate with the assistant!

Example prompts:
• "Add a print statement at the beginning of the file"
• "Create a new Python file called helper.py with a greet function"
• "Delete line 5 from the current file"
• "Create a folder called src/components"
"""
        messagebox.showinfo("AI Skills Information", info_text)

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
        # Update sidebar styling for the new theme
        self.main_paned.config(bg=theme.COLORS["bg_dark"])
        self.chat_frame.config(bg=theme.COLORS["bg_dark"])
        self.chat_header.config(bg=theme.COLORS["bg_header"])
        self.chat_header_label.config(fg=theme.COLORS["fg_dim"], bg=theme.COLORS["bg_header"])
        self.chat_close_btn.config(fg=theme.COLORS["fg_dim"], bg=theme.COLORS["bg_header"], activebackground=theme.COLORS["sash_color"])
        self.chat_history.config(bg=theme.COLORS["bg_editor"], fg=theme.COLORS["fg_light"])
        self.chat_input_container.config(bg=theme.COLORS["bg_dark"])
        self.chat_input.config(bg=theme.COLORS["bg_editor"], fg=theme.COLORS["fg_light"], insertbackground=theme.COLORS["accent"], highlightbackground=theme.COLORS["sash_color"], highlightcolor=theme.COLORS["accent"])
        self.chat_button_frame.config(bg=theme.COLORS["bg_dark"])
        theme.style_toolbar_button(self.chat_send_btn)
        theme.style_toolbar_button(self.chat_clear_btn)

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


    def open_folder(self):
        """Open a folder in the file explorer."""
        folder = filedialog.askdirectory(title="Open Folder")
        if folder:
            self.file_explorer.load_folder(folder)

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

    def check_and_setup_dependencies(self):
        missing = []
        try:
            from huggingface_hub import HfApi, get_token
        except Exception:
            missing.append("huggingface_hub")

        if ai_runner.get_runtime_status() is None:
            missing.append("llama-cpp-python")

        if not missing:
            return True

        # Create Setup Assistant Window
        setup_win = tk.Toplevel(self.root)
        setup_win.title("Lithium IDE - Asistente de Configuración de IA")
        setup_win.geometry("500x320")
        setup_win.resizable(False, False)

        # Center the window
        setup_win.update_idletasks()
        width = setup_win.winfo_width()
        height = setup_win.winfo_height()
        x = (setup_win.winfo_screenwidth() // 2) - (width // 2)
        y = (setup_win.winfo_screenheight() // 2) - (height // 2)
        setup_win.geometry(f"+{x}+{y}")

        # Apply theme colors
        bg_color = theme.COLORS.get("bg_dark", "#1e1e1e")
        fg_color = theme.COLORS.get("fg_light", "#ffffff")
        fg_dim = theme.COLORS.get("fg_dim", "#888888")
        accent_color = theme.COLORS.get("accent", "#007acc")
        sash_color = theme.COLORS.get("sash_color", "#555555")

        setup_win.configure(bg=bg_color)

        title_label = tk.Label(
            setup_win,
            text="Configuración Inicial de Inteligencia Artificial",
            font=("Segoe UI", 13, "bold"),
            fg=accent_color,
            bg=bg_color
        )
        title_label.pack(pady=(20, 10))

        desc_text = "Para poder utilizar las herramientas de IA local, el sistema necesita instalar las siguientes dependencias:\n\n"
        for dep in missing:
            desc_text += f" • {dep}\n"
        desc_text += "\n¿Deseas instalarlas automáticamente ahora?"

        desc_label = tk.Label(
            setup_win,
            text=desc_text,
            font=("Segoe UI", 10),
            fg=fg_color,
            bg=bg_color,
            justify=tk.LEFT,
            wraplength=460
        )
        desc_label.pack(padx=20, pady=10, anchor="w")

        progress_label = tk.Label(
            setup_win,
            text="",
            font=("Segoe UI", 9, "italic"),
            fg=fg_dim,
            bg=bg_color
        )
        progress_label.pack(fill=tk.X, padx=20, pady=(5, 2))

        progress_bar = ttk.Progressbar(setup_win, orient="horizontal", mode="determinate", maximum=100)
        progress_bar.pack(fill=tk.X, padx=20, pady=(0, 20))

        button_frame = tk.Frame(setup_win, bg=bg_color)
        button_frame.pack(fill=tk.X, padx=20, pady=5)

        install_btn = tk.Button(
            button_frame,
            text="Instalar dependencias",
            font=("Segoe UI", 10, "bold"),
            bg=accent_color,
            fg=bg_color,
            activebackground=sash_color,
            activeforeground=fg_color,
            bd=0,
            padx=15,
            pady=5,
            command=lambda: start_installation()
        )
        install_btn.pack(side=tk.RIGHT)

        installation_in_progress = {"active": False}

        def on_close():
            if installation_in_progress["active"]:
                messagebox.showwarning("Instalación en curso", "Las dependencias se están instalando. Por favor, espera a que termine.")
                return
            if messagebox.askyesno("Salir", "¿Seguro que quieres salir? El editor requiere estas dependencias para continuar."):
                setup_win.destroy()
                self.root.destroy()
                sys.exit(0)

        setup_win.protocol("WM_DELETE_WINDOW", on_close)

        def start_installation():
            installation_in_progress["active"] = True
            install_btn.config(state="disabled")
            progress_bar.config(mode="indeterminate")
            progress_bar.start(10)
            progress_label.config(text="Instalando dependencias... Esto puede tardar un momento.")

            def install_thread():
                import subprocess
                import sys
                import importlib
                try:
                    import os
                    custom_env = os.environ.copy()
                    temp_dir = os.path.abspath(os.path.join(".cache", "t"))
                    os.makedirs(temp_dir, exist_ok=True)
                    custom_env["TEMP"] = temp_dir
                    custom_env["TMP"] = temp_dir

                    for dep in missing:
                        self.root.after(0, lambda d=dep: progress_label.config(text=f"Instalando {d}..."))
                        
                        process = subprocess.Popen(
                            [sys.executable, "-m", "pip", "install", dep],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            env=custom_env,
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                        )
                        
                        while True:
                            line = process.stdout.readline()
                            if not line:
                                break
                            if "Building wheel" in line or "pyproject.toml" in line or "Building wheels" in line:
                                self.root.after(0, lambda: progress_label.config(text="Building llama-cpp-python. Please wait..."))
                        
                        process.wait()
                        if process.returncode != 0:
                            raise subprocess.CalledProcessError(process.returncode, process.args)
                    
                    importlib.invalidate_caches()

                    # Verify
                    still_missing = []
                    try:
                        from huggingface_hub import HfApi, get_token
                    except Exception:
                        still_missing.append("huggingface_hub")
                    if ai_runner.get_runtime_status() is None:
                        still_missing.append("llama-cpp-python")

                    if still_missing:
                        raise RuntimeError(f"Las siguientes dependencias no pudieron cargarse: {', '.join(still_missing)}")

                    self.root.after(0, finish_success)
                except Exception as e:
                    err_msg = str(e)
                    self.root.after(0, lambda: finish_error(err_msg))

            threading.Thread(target=install_thread, daemon=True).start()

        def finish_success():
            installation_in_progress["active"] = False
            progress_bar.stop()
            progress_bar.config(mode="determinate", value=100)
            progress_label.config(text="¡Instalación completada con éxito!")
            messagebox.showinfo("Configuración completada", "Todas las dependencias han sido instaladas con éxito. Iniciando Lithium IDE.")
            setup_win.destroy()

        def is_long_paths_enabled():
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
                    value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
                    return value == 1
            except Exception:
                return False

        def enable_windows_long_paths():
            import ctypes
            try:
                ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    "powershell.exe",
                    '-Command "Set-ItemProperty -Path \'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem\' -Name \'LongPathsEnabled\' -Value 1"',
                    None,
                    1
                )
                return True
            except Exception:
                return False

        def finish_error(err_msg):
            installation_in_progress["active"] = False
            progress_bar.stop()
            progress_bar.config(mode="determinate", value=0)
            progress_label.config(text="Error durante la instalación.")
            
            import sys
            if sys.platform == "win32" and not is_long_paths_enabled():
                if messagebox.askyesno(
                    "Rutas Largas Requeridas",
                    "La instalación de llama-cpp-python falló debido al límite de caracteres de Windows (MAX_PATH).\n\n"
                    "¿Deseas que Lithium intente activar las rutas largas automáticamente? (Requiere permisos de administrador y se abrirá una ventana de confirmación)."
                ):
                    if enable_windows_long_paths():
                        messagebox.showinfo(
                            "Solicitud enviada",
                            "Se ha solicitado la activación. Una vez aceptado el permiso de Windows (UAC), reinicia el IDE y vuelve a intentar la instalación."
                        )
                        setup_win.destroy()
                        self.root.destroy()
                        sys.exit(0)
                    else:
                        messagebox.showerror("Error", "No se pudo solicitar la activación automática.")
            
            messagebox.showerror("Error de instalación", f"Ocurrió un error al instalar las dependencias:\n\n{err_msg}\n\nPor favor, inténtalo manualmente con: pip install {' '.join(missing)}")
            install_btn.config(state="normal")

        # Block interaction with other windows
        setup_win.transient(self.root)
        setup_win.grab_set()
        self.root.wait_window(setup_win)

    def _init_ai_skills(self):
        """Initialize the AI Skills Executor with editor callbacks."""
        def get_editor_content():
            return self.editor.get("1.0", tk.END)
        
        def set_editor_content(content):
            self.editor.delete("1.0", tk.END)
            self.editor.insert("1.0", content)
            self.controller.update_line_numbers()
            self.controller.update_status()
        
        def get_file_path():
            return self.controller.file_path
        
        def get_project_folder():
            # Get the project folder from the file explorer
            if hasattr(self, 'file_explorer') and self.file_explorer:
                return self.file_explorer.current_folder
            return None
        
        def status_update(message):
            self.root.after(0, lambda: self.status_label.config(text=f"AI Skills: {message}"))
        
        try:
            self.ai_skills_executor = get_ai_skills_executor(
                editor_getter=get_editor_content,
                editor_setter=set_editor_content,
                file_path_getter=get_file_path,
                project_folder_getter=get_project_folder,
                status_callback=status_update
            )
            # Append skills prompt to system prompt
            self.ai_system_prompt = self.ai_system_prompt + "\n" + self.ai_skills_executor.generate_skill_prompt()
        except Exception as e:
            print(f"Warning: Could not initialize AI Skills: {e}")
            self.ai_skills_executor = None

    def toggle_ai_chat(self):
        if self.chat_visible:
            self.center_right_paned.remove(self.chat_frame)
            self.chat_visible = False
        else:
            self.center_right_paned.add(self.chat_frame, minsize=250, width=300)
            self.chat_visible = True

    def clear_chat(self):
        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.delete("1.0", tk.END)
        self.chat_history.config(state=tk.DISABLED)

    def send_chat_message(self):
        message = self.chat_input.get("1.0", tk.END).strip()
        if not message:
            return
        
        self.chat_input.delete("1.0", tk.END)
        self.append_to_chat_history("You", message)
        
        # Auto-create conversation if none exists
        if not self.conversation_manager.current_conversation:
            self.conversation_manager.create_conversation("New Conversation")
            self.refresh_conversations_list()
        
        # Save user message to current conversation
        if self.conversation_manager.current_conversation:
            self.conversation_manager.current_conversation.add_message("user", message)
            self.conversation_manager.save_conversation()
        
        threading.Thread(target=self.run_chat_ai, args=(message,), daemon=True).start()

    def run_chat_ai(self, prompt):
        self.root.after(0, lambda: self.status_label.config(text="AI: Loading..."))
        
        # Show loading indicator with animated dots
        self._show_loading_indicator()
        
        try:
            response = ai_runner.generate_text_from_model(
                self.ai_model_link, 
                self.ai_system_prompt, 
                prompt
            )
            
            # Remove loading indicator
            self._remove_loading_indicator()
            
            # Process AI skills if executor is available - use preview mode for approval
            skill_results = []  # List of (skill_name, result) tuples
            pending_approvals = []
            clean_response = response
            if self.ai_skills_executor:
                try:
                    skill_results = self.ai_skills_executor.parse_for_preview(response)
                    clean_response = self.ai_skills_executor.get_clean_response(response)
                    
                    # Separate skills that need approval (skill_results is list of tuples: (skill_name, result))
                    for i, (skill_name, result) in enumerate(skill_results):
                        if result.requires_approval and result.success:
                            pending_approvals.append((i, skill_name, result))
                except Exception as skill_err:
                    print(f"Warning: Error processing AI skills: {skill_err}")
            
            # Display the response and handle approvals
            def show_response():
                # Save AI response to current conversation
                if self.conversation_manager.current_conversation and clean_response.strip():
                    self.conversation_manager.current_conversation.add_message("assistant", clean_response)
                    self.conversation_manager.save_conversation()
                
                # Show skill previews that need approval
                if pending_approvals:
                    self._show_approval_dialog(0, pending_approvals, skill_results, clean_response)
                else:
                    # No approvals needed, show results directly
                    for skill_name, result in skill_results:
                        status_icon = "✓" if result.success else "✗"
                        self.append_to_chat_history("Skill", f"{status_icon} {result.message}")
                    
                    if clean_response.strip():
                        self.append_to_chat_history("AI", clean_response)
                    
                    self.status_label.config(text="AI: Ready")
                    
                    # Refresh conversations list to update titles
                    self.refresh_conversations_list()
            
            self.root.after(0, show_response)
        except Exception as exc:
            self._remove_loading_indicator()
            err_msg = str(exc)
            self.root.after(0, lambda: self.append_to_chat_history("Error", f"Could not generate response: {err_msg}"))
            self.root.after(0, lambda: self.status_label.config(text="AI: Error"))

    def _show_loading_indicator(self):
        """Show simple loading indicator with fading dot in chat."""
        self.chat_history.config(state=tk.NORMAL)
        
        # Create a frame to hold the loader
        self._loading_frame = tk.Frame(self.chat_history, bg=theme.COLORS.get("bg_dark", "#181825"))
        
        # Add "AI is thinking" text
        tk.Label(
            self._loading_frame,
            text="AI is thinking",
            font=("Segoe UI", 9, "italic"),
            fg=theme.COLORS.get("fg_dim", "#a6adc8"),
            bg=theme.COLORS.get("bg_dark", "#181825")
        ).pack(side=tk.LEFT)
        
        # Create canvas for animated dot
        self._loader_canvas = tk.Canvas(
            self._loading_frame,
            width=12,
            height=12,
            bg=theme.COLORS.get("bg_dark", "#181825"),
            highlightthickness=0
        )
        self._loader_canvas.pack(side=tk.LEFT, padx=(2, 5))
        
        # Insert the frame into chat history
        self.chat_history.window_create(tk.END, window=self._loading_frame)
        self.chat_history.insert(tk.END, "\n")
        self.chat_history.see(tk.END)
        self.chat_history.config(state=tk.DISABLED)
        
        # Start dot animation
        self._fade_alpha = 0
        self._fade_increasing = True
        self._animate_loader()

    def _animate_loader(self):
        """Animate a single dot with fade in/out effect."""
        if not hasattr(self, '_loader_canvas'):
            return
        
        canvas = self._loader_canvas
        canvas.delete("all")
        
        # Get colors
        accent_color = theme.COLORS.get("accent", "#cba6f7")
        r = int(accent_color[1:3], 16)
        g = int(accent_color[3:5], 16)
        b = int(accent_color[5:7], 16)
        
        # Calculate opacity for fade effect
        opacity = self._fade_alpha / 100.0
        color = f"#{int(r * opacity):02x}{int(g * opacity):02x}{int(b * opacity):02x}"
        
        # Draw single dot in center
        dot_size = 3
        canvas.create_oval(
            6 - dot_size, 6 - dot_size,
            6 + dot_size, 6 + dot_size,
            fill=color, outline=""
        )
        
        # Update fade animation
        if self._fade_increasing:
            self._fade_alpha += 5
            if self._fade_alpha >= 100:
                self._fade_increasing = False
        else:
            self._fade_alpha -= 5
            if self._fade_alpha <= 0:
                self._fade_increasing = True
        
        # Schedule next frame
        if hasattr(self, '_loader_canvas'):
            self.root.after(50, self._animate_loader)

    def _remove_loading_indicator(self):
        """Remove the loading indicator from chat."""
        if hasattr(self, '_loading_frame'):
            try:
                self._loading_frame.destroy()
            except Exception:
                pass
            del self._loading_frame
        
        if hasattr(self, '_loader_canvas'):
            del self._loader_canvas

    def _show_approval_dialog(self, index, pending_approvals, all_results, clean_response):
        """Show approval dialog inline in the chat for pending skill changes."""
        if index >= len(pending_approvals):
            # All approvals processed, show final results
            for skill_name, result in all_results:
                status_icon = "✓" if result.success else "✗"
                self.append_to_chat_history("Skill", f"{status_icon} {result.message}")
            
            if clean_response.strip():
                self.append_to_chat_history("AI", clean_response)
            
            self.status_label.config(text="AI: Ready")
            return
        
        result_idx, skill_name, result = pending_approvals[index]
        data = result.data or {}
        
        # Build the approval message to show in chat
        approval_msg = f"⚡ **AI wants to: {result.message}**\n"
        
        if len(pending_approvals) > 1:
            approval_msg += f"_(Change {index + 1} of {len(pending_approvals)})_\n"
        
        # Add preview content based on skill type
        if skill_name in ("delete_lines", "remove_lines"):
            # For delete operations, show the original content that will be deleted
            if "original_content" in data and "new_content" in data:
                original = data.get("original_content", "")
                new = data.get("new_content", "")
                original_lines = original.splitlines()
                new_lines = new.splitlines()
                approval_msg += f"\n📝 Lines will be removed from the editor.\n"
                approval_msg += f"Current lines: {len(original_lines)} → After deletion: {len(new_lines)}\n"
        elif "new_content" in data:
            approval_msg += "\n```python\n" + data.get("new_content", "") + "\n```"
        elif "path" in data:
            approval_msg += f"\n📁 Path: {data.get('path', '')}\n"
            if "content" in data:
                approval_msg += "\n```python\n" + data.get("content", "") + "\n```"
        
        # Show the approval request in chat
        self._show_inline_approval(approval_msg, result, skill_name, result_idx, 
                                   all_results, pending_approvals, index, clean_response)
    
    def _show_inline_approval(self, message, result, skill_name, result_idx,
                              all_results, pending_approvals, index, clean_response):
        """Show an inline approval request in the chat with approve/reject buttons."""
        self.chat_history.config(state=tk.NORMAL)
        
        # Insert the message
        self.chat_history.insert(tk.END, "\n")
        self.chat_history.insert(tk.END, message + "\n", ("approval_msg",))
        self.chat_history.tag_config("approval_msg", foreground=theme.COLORS.get("accent", "#cba6f7"), 
                                     font=("Segoe UI", 10))
        
        # Create button frame
        btn_frame = tk.Frame(self.chat_history, bg=theme.COLORS.get("bg_dark", "#181825"))
        
        def approve():
            # Apply the skill
            apply_result = self.ai_skills_executor.apply_skill(skill_name, result)
            all_results[result_idx] = apply_result
            
            # Update the button frame to show result
            for widget in btn_frame.winfo_children():
                widget.destroy()
            
            status_icon = "✓" if apply_result.success else "✗"
            status_color = "#4ade80" if apply_result.success else "#f87171"
            
            tk.Label(
                btn_frame,
                text=f"{status_icon} {apply_result.message}",
                font=("Segoe UI", 9, "bold"),
                fg=status_color,
                bg=theme.COLORS.get("bg_dark", "#181825")
            ).pack(side=tk.LEFT, padx=5)
            
            # Process next approval
            self.root.after(500, lambda: self._show_approval_dialog(index + 1, pending_approvals, all_results, clean_response))
        
        def reject():
            # Mark as rejected
            all_results[result_idx] = AISkillResult(False, f"Rejected: {result.message}")
            
            # Update the button frame to show result
            for widget in btn_frame.winfo_children():
                widget.destroy()
            
            tk.Label(
                btn_frame,
                text=f"✗ Rejected: {result.message}",
                font=("Segoe UI", 9, "bold"),
                fg="#f87171",
                bg=theme.COLORS.get("bg_dark", "#181825")
            ).pack(side=tk.LEFT, padx=5)
            
            # Process next approval
            self.root.after(500, lambda: self._show_approval_dialog(index + 1, pending_approvals, all_results, clean_response))
        
        tk.Button(
            btn_frame,
            text="✓ Approve",
            font=("Segoe UI", 9, "bold"),
            bg=theme.COLORS.get("accent", "#cba6f7"),
            fg=theme.COLORS.get("bg_dark", "#181825"),
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            command=approve
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="✗ Reject",
            font=("Segoe UI", 9),
            bg=theme.COLORS.get("sash_color", "#313244"),
            fg=theme.COLORS.get("fg_light", "#cdd6f4"),
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            command=reject
        ).pack(side=tk.LEFT, padx=5)
        
        self.chat_history.window_create(tk.END, window=btn_frame)
        self.chat_history.insert(tk.END, "\n")
        self.chat_history.see(tk.END)
        self.chat_history.config(state=tk.DISABLED)

    def _get_skill_name_from_result(self, result_idx, all_results):
        """Get skill name from result index (simplified - in real impl would track names)."""
        # This is a simplified version - the actual implementation would track skill names
        # For now, we'll need to modify parse_for_preview to return skill names too
        return "unknown"

    def append_to_chat_history(self, sender, text):
        self.chat_history.config(state=tk.NORMAL)
        
        color = theme.COLORS.get("accent", "#cba6f7") if sender == "AI" else theme.COLORS.get("fg_dim", "#a6adc8")
        if sender == "Error":
            color = theme.COLORS.get("console_err", "#ff0000")
            
        self.chat_history.insert(tk.END, f"\n{sender}:\n", ("sender_tag_" + sender,))
        self.chat_history.tag_config("sender_tag_" + sender, foreground=color, font=("Segoe UI", 10, "bold"))
        
        parts = text.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 1:
                # Code block
                lines = part.split("\n")
                lang = ""
                code_content = part
                if lines and lines[0].strip() in ["python", "javascript", "html", "css", "c++", "java", "rust", "go", "json", "py", "js"]:
                    lang = lines[0].strip()
                    code_content = "\n".join(lines[1:])
                
                start_index = self.chat_history.index(tk.END)
                self.chat_history.insert(tk.END, code_content, ("code_block_tag",))
                self.chat_history.tag_config(
                    "code_block_tag", 
                    background=theme.COLORS.get("bg_dark", "#181825"), 
                    foreground=theme.COLORS.get("fg_light", "#cdd6f4"), 
                    font=theme.FONTS.get("editor", ("Consolas", 11))
                )
                self.chat_history.insert(tk.END, "\n")
                # Store start index for later removal
                self.code_indices[code_content] = start_index
                
                btn_frame = tk.Frame(self.chat_history, bg=theme.COLORS.get("bg_dark", "#181825"))

                apply_btn = tk.Button(
                    btn_frame, 
                    text="✓ Apply", 
                    font=("Segoe UI", 9, "bold"), 
                    bg=theme.COLORS.get("accent", "#cba6f7"), 
                    fg=theme.COLORS.get("bg_dark", "#181825"), 
                    bd=0,
                    padx=8,
                    pady=2,
                    command=lambda c=code_content: self.apply_suggested_code(c)
                )
                apply_btn.pack(side=tk.LEFT, padx=(5, 5))

                review_btn = tk.Button(
                    btn_frame, 
                    text="🔍 Review", 
                    font=("Segoe UI", 9), 
                    bg=theme.COLORS.get("sash_color", "#313244"), 
                    fg=theme.COLORS.get("fg_light", "#cdd6f4"), 
                    bd=0,
                    padx=8,
                    pady=2,
                    command=lambda c=code_content: self.open_review_window(c)
                )
                review_btn.pack(side=tk.LEFT)

                # Store the button frame for later removal on approval
                if not hasattr(self, 'button_frames'): self.button_frames = {}
                self.button_frames[code_content] = btn_frame

                self.chat_history.window_create(tk.END, window=btn_frame)
                self.chat_history.insert(tk.END, "\n")
            else:
                self.chat_history.insert(tk.END, part)
                
        self.chat_history.see(tk.END)
        self.chat_history.config(state=tk.DISABLED)

    def apply_suggested_code(self, code):
        try:
            if self.editor.tag_ranges(tk.SEL):
                self.editor.delete(tk.SEL_FIRST, tk.SEL_LAST)
            self.editor.insert(tk.INSERT, code)
            self.controller.update_line_numbers()
            self.controller.update_status()
            self.status_label.config(text="AI: Suggested code applied.")
            # Remove the button frame associated with this code snippet, if exists
            if code in getattr(self, 'button_frames', {}):
                btn_frame = self.button_frames.pop(code)
                btn_frame.destroy()
            # Remove the code snippet from chat history if present
            if code in getattr(self, 'code_indices', {}):
                start = self.code_indices.pop(code)
                end = f"{start} + {len(code)}c"
                self.chat_history.config(state=tk.NORMAL)
                self.chat_history.delete(start, end)
                self.chat_history.config(state=tk.DISABLED)
        except Exception as e:
            messagebox.showerror("Error", f"Could not apply code: {e}")

    def open_review_window(self, suggested_code):
        review_win = tk.Toplevel(self.root)
        review_win.title("Revisar Cambios Propuestos")
        review_win.geometry("800x500")
        review_win.transient(self.root)
        review_win.grab_set()
        
        review_win.update_idletasks()
        width = review_win.winfo_width()
        height = review_win.winfo_height()
        x = (review_win.winfo_screenwidth() // 2) - (width // 2)
        y = (review_win.winfo_screenheight() // 2) - (height // 2)
        review_win.geometry(f"+{x}+{y}")
        
        bg_color = theme.COLORS.get("bg_dark", "#181825")
        fg_color = theme.COLORS.get("fg_light", "#cdd6f4")
        review_win.configure(bg=bg_color)
        
        title_label = tk.Label(
            review_win,
            text="Revisión de Cambios de la IA",
            font=("Segoe UI", 12, "bold"),
            fg=theme.COLORS.get("accent", "#cba6f7"),
            bg=bg_color
        )
        title_label.pack(pady=(15, 10))
        
        paned = tk.PanedWindow(review_win, orient=tk.HORIZONTAL, bg=bg_color, bd=0, sashwidth=4, sashpad=1, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        original_code = ""
        has_selection = False
        try:
            if self.editor.tag_ranges(tk.SEL):
                original_code = self.editor.get(tk.SEL_FIRST, tk.SEL_LAST)
                has_selection = True
            else:
                original_code = self.editor.get("1.0", tk.END)
        except Exception:
            original_code = self.editor.get("1.0", tk.END)
            
        orig_frame = tk.Frame(paned, bg=bg_color)
        orig_label = tk.Label(orig_frame, text="Código Actual" + (" (Selección)" if has_selection else " (Todo el archivo)"), fg=theme.COLORS.get("fg_dim", "#a6adc8"), bg=bg_color, font=("Segoe UI", 9, "bold"))
        orig_label.pack(fill=tk.X, anchor="w", pady=(0, 2))
        
        orig_scroll = ttk.Scrollbar(orig_frame)
        orig_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        orig_text = tk.Text(orig_frame, wrap=tk.NONE, yscrollcommand=orig_scroll.set, font=theme.FONTS.get("editor", ("Consolas", 11)), bg=theme.COLORS.get("bg_editor", "#1e1e2e"), fg=theme.COLORS.get("fg_light", "#cdd6f4"), bd=0, highlightthickness=0)
        orig_text.pack(fill=tk.BOTH, expand=True)
        orig_scroll.config(command=orig_text.yview)
        orig_text.insert(tk.END, original_code)
        orig_text.config(state=tk.DISABLED)
        paned.add(orig_frame, minsize=200)
        
        sug_frame = tk.Frame(paned, bg=bg_color)
        sug_label = tk.Label(sug_frame, text="Código Sugerido", fg=theme.COLORS.get("accent", "#cba6f7"), bg=bg_color, font=("Segoe UI", 9, "bold"))
        sug_label.pack(fill=tk.X, anchor="w", pady=(0, 2))
        
        sug_scroll = ttk.Scrollbar(sug_frame)
        sug_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        sug_text = tk.Text(sug_frame, wrap=tk.NONE, yscrollcommand=sug_scroll.set, font=theme.FONTS.get("editor", ("Consolas", 11)), bg=theme.COLORS.get("bg_editor", "#1e1e2e"), fg=theme.COLORS.get("fg_light", "#cdd6f4"), bd=0, highlightthickness=0)
        sug_text.pack(fill=tk.BOTH, expand=True)
        sug_scroll.config(command=sug_text.yview)
        sug_text.insert(tk.END, suggested_code)
        sug_text.config(state=tk.DISABLED)
        paned.add(sug_frame, minsize=200)
        
        def sync_yview(*args):
            orig_text.yview(*args)
            sug_text.yview(*args)
            
        orig_scroll.config(command=sync_yview)
        sug_scroll.config(command=sync_yview)
        
        btn_frame = tk.Frame(review_win, bg=bg_color)
        btn_frame.pack(fill=tk.X, padx=15, pady=15)
        
        def approve_changes():
            try:
                if has_selection:
                    self.editor.delete(tk.SEL_FIRST, tk.SEL_LAST)
                    self.editor.insert(tk.INSERT, suggested_code)
                else:
                    self.editor.delete("1.0", tk.END)
                    self.editor.insert("1.0", suggested_code)
                self.controller.update_line_numbers()
                self.controller.update_status()
                self.status_label.config(text="AI: Changes approved and applied.")
                # Remove the button frame for this suggested code, if present
                if suggested_code in getattr(self, 'button_frames', {}):
                    btn = self.button_frames.pop(suggested_code)
                    btn.destroy()
                # Remove the code snippet from chat history if present
                if suggested_code in getattr(self, 'code_indices', {}):
                    start = self.code_indices.pop(suggested_code)
                    end = f"{start} + {len(suggested_code)}c"
                    self.chat_history.config(state=tk.NORMAL)
                    self.chat_history.delete(start, end)
                    self.chat_history.config(state=tk.DISABLED)
                review_win.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Could not apply changes: {e}")
                
        approve_btn = tk.Button(
            btn_frame,
            text="✓ Aprobar y Aplicar",
            font=("Segoe UI", 10, "bold"),
            bg=theme.COLORS.get("accent", "#cba6f7"),
            fg=theme.COLORS.get("bg_dark", "#181825"),
            bd=0,
            padx=15,
            pady=5,
            command=approve_changes
        )
        approve_btn.pack(side=tk.RIGHT, padx=5)
        
        reject_btn = tk.Button(
            btn_frame,
            text="✗ Rechazar",
            font=("Segoe UI", 10),
            bg=theme.COLORS.get("sash_color", "#313244"),
            fg=fg_color,
            bd=0,
            padx=15,
            pady=5,
            command=review_win.destroy
        )
        reject_btn.pack(side=tk.RIGHT, padx=5)
        
        review_win.wait_window(review_win)

    def show_conversations_dropdown(self):
        """Show conversations dropdown menu from status bar."""
        conversations = self.conversation_manager.list_conversations()
        self._conversation_ids = [conv["id"] for conv in conversations]
        
        menu = tk.Menu(self.root, tearoff=0, bg=theme.COLORS["bg_header"], fg=theme.COLORS["fg_light"])
        
        # New conversation option
        menu.add_command(label="＋ New Conversation", command=self.new_conversation)
        menu.add_separator()
        
        if conversations:
            # List existing conversations
            for i, conv in enumerate(conversations):
                display_text = conv["title"][:30] + ("..." if len(conv["title"]) > 30 else "")
                is_current = self.conversation_manager.current_conversation and \
                             self.conversation_manager.current_conversation.id == conv["id"]
                if is_current:
                    display_text = "✓ " + display_text
                menu.add_command(label=display_text, command=lambda cid=conv["id"]: self.load_conversation(cid))
            menu.add_separator()
            
            # Context menu for current conversation
            if self.conversation_manager.current_conversation:
                current_id = self.conversation_manager.current_conversation.id
                menu.add_command(label="Rename Conversation", command=lambda: self.rename_conversation(current_id))
                menu.add_command(label="Export Conversation", command=lambda: self.export_conversation(current_id))
                menu.add_separator()
                menu.add_command(label="Delete Conversation", command=lambda: self.delete_conversation(current_id))
        else:
            menu.add_command(label="No saved conversations", state=tk.DISABLED)
        
        # Show menu above the button
        x = self.conv_dropdown_btn.winfo_rootx()
        y = self.conv_dropdown_btn.winfo_rooty() - 200
        menu.post(x, y)
    
    def refresh_conversations_list(self):
        """Refresh the conversation dropdown button label."""
        if self.conversation_manager.current_conversation:
            title = self.conversation_manager.current_conversation.title[:20]
            self.conv_dropdown_btn.config(text=f"💬 {title}")
        else:
            self.conv_dropdown_btn.config(text="💬 No conversation")
    
    def new_conversation(self):
        """Create a new conversation."""
        # Save current conversation if exists
        if self.conversation_manager.current_conversation:
            self.save_current_conversation_to_history()
        
        # Create new conversation
        self.conversation_manager.create_conversation("New Conversation")
        
        # Clear chat display
        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.delete("1.0", tk.END)
        self.chat_history.config(state=tk.DISABLED)
        
        # Update button label
        self.refresh_conversations_list()
        
        # Welcome message
        self.append_to_chat_history("AI", "Hello! How can I help you today?")
    
    def load_conversation(self, conversation_id):
        """Load a conversation and display its messages."""
        # Save current conversation first
        if self.conversation_manager.current_conversation:
            self.save_current_conversation_to_history()
        
        # Load the selected conversation
        conversation = self.conversation_manager.load_conversation(conversation_id)
        if not conversation:
            return
        
        # Clear chat display
        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.delete("1.0", tk.END)
        
        # Display all messages
        for msg in conversation.messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            sender = role.capitalize()
            if role == "user":
                sender = "You"
            elif role == "assistant":
                sender = "AI"
            self.append_to_chat_history(sender, content)
        
        self.chat_history.config(state=tk.DISABLED)
        
        # Update button label
        self.refresh_conversations_list()
    
    def save_current_conversation_to_history(self):
        """Save the current chat history to the conversation."""
        if not self.conversation_manager.current_conversation:
            return
        
        # Save the conversation
        self.conversation_manager.save_conversation()
    
    def rename_conversation(self, conversation_id):
        """Rename a conversation."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Rename Conversation")
        dialog.geometry("300x120")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=theme.COLORS["bg_dark"])
        
        tk.Label(
            dialog,
            text="Enter new name:",
            font=theme.FONTS["ui"],
            fg=theme.COLORS["fg_light"],
            bg=theme.COLORS["bg_dark"]
        ).pack(pady=(15, 5))
        
        entry = tk.Entry(
            dialog,
            font=theme.FONTS["ui"],
            bg=theme.COLORS["bg_editor"],
            fg=theme.COLORS["fg_light"],
            insertbackground=theme.COLORS["accent"],
            bd=0,
            highlightthickness=1,
            highlightbackground=theme.COLORS["sash_color"]
        )
        entry.pack(fill=tk.X, padx=20, pady=5)
        entry.focus_set()
        
        def rename():
            new_name = entry.get().strip()
            if new_name:
                self.conversation_manager.rename_conversation(conversation_id, new_name)
                self.refresh_conversations_list()
                dialog.destroy()
        
        def on_enter(event):
            rename()
        
        entry.bind("<Return>", on_enter)
        
        btn_frame = tk.Frame(dialog, bg=theme.COLORS["bg_dark"])
        btn_frame.pack(pady=10)
        
        tk.Button(
            btn_frame,
            text="Rename",
            font=theme.FONTS["ui"],
            bg=theme.COLORS["accent"],
            fg=theme.COLORS["bg_dark"],
            bd=0,
            padx=15,
            pady=5,
            cursor="hand2",
            command=rename
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="Cancel",
            font=theme.FONTS["ui"],
            bg=theme.COLORS["sash_color"],
            fg=theme.COLORS["fg_light"],
            bd=0,
            padx=15,
            pady=5,
            cursor="hand2",
            command=dialog.destroy
        ).pack(side=tk.LEFT, padx=5)
    
    def delete_conversation(self, conversation_id):
        """Delete a conversation after confirmation."""
        if messagebox.askyesno("Delete Conversation", "Are you sure you want to delete this conversation?"):
            self.conversation_manager.delete_conversation(conversation_id)
            self.refresh_conversations_list()
            
            # Clear chat if this was the current conversation
            if not self.conversation_manager.current_conversation:
                self.chat_history.config(state=tk.NORMAL)
                self.chat_history.delete("1.0", tk.END)
                self.chat_history.config(state=tk.DISABLED)
    
    def export_conversation(self, conversation_id):
        """Export a conversation to a file."""
        filetypes = [
            ("Text files", "*.txt"),
            ("JSON files", "*.json"),
            ("Markdown files", "*.md"),
            ("All files", "*.*")
        ]
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=filetypes,
            title="Export Conversation"
        )
        
        if not filename:
            return
        
        # Determine format from extension
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".json":
            format_type = "json"
        elif ext == ".md":
            format_type = "md"
        else:
            format_type = "txt"
        
        content = self.conversation_manager.export_conversation(conversation_id, format_type)
        if content:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                messagebox.showinfo("Export", "Conversation exported successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export: {e}")
    
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
