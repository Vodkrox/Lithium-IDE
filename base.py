import difflib
import json
import os
import sys
import tempfile
import threading
import tkinter as tk
import urllib.request
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse

from src import runner, theme
from src.ai_powered import ai_engine as ai_runner
from src.ai_powered import ai_level as ai_level_manager
from src.ai_powered.ai_skill_settings import (
    FILE_SCOPE_OPTIONS,
    SKILL_TOGGLE_LABELS,
    AISkillSettings,
)
from src.ai_powered.ai_skills import AISkillResult
from src.ai_powered.ai_skills import get_executor as get_ai_skills_executor
from src.ai_powered.ai_skills import reset_executor as reset_ai_skills_executor
from src.ai_powered.conversation_manager import Conversation, get_conversation_manager
from src.autocomplete import LithiumAutocompleteManager
from src.editor import LithiumEditorController
from src.file_explorer import FileExplorer
from src.settings import SettingsManager
from src.splash import SplashScreen
from src.utils import can_import_module, prepare_frozen_python_runtime, resource_path


class LithiumIDE:
    def __init__(self, root):
        self.root = root
        self.root.title("Lithium IDE")
        self.root.geometry("900x650")

        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Vodkrox.LithiumIDE"
            )
        except Exception:
            pass
        try:
            # Resize oversized icons to avoid X11 BadLength on X_PolySegment;
            # the 3000x3000 raw icon exceeds the X11 max request size (~16MB).
            from PIL import Image, ImageTk

            pil_img = Image.open(resource_path("src/assets/lithium_icon.png"))
            MAX_ICON = 256
            if max(pil_img.size) > MAX_ICON:
                ratio = MAX_ICON / max(pil_img.size)
                new_size = (int(pil_img.width * ratio), int(pil_img.height * ratio))
                pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
            icon = ImageTk.PhotoImage(pil_img)
            self.root.iconphoto(True, icon)
            self._app_icon = icon
        except Exception:
            pass
        try:
            import ctypes

            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            dwm = ctypes.windll.dwmapi
            value = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
            )
            black = ctypes.c_int(0x00000000)
            dwm.DwmSetWindowAttribute(
                hwnd, 35, ctypes.byref(black), ctypes.sizeof(black)
            )
            dwm.DwmSetWindowAttribute(
                hwnd, 34, ctypes.byref(black), ctypes.sizeof(black)
            )
        except Exception:
            pass

        self.file_or_folder_opened = False

        prepare_frozen_python_runtime()
        self.root.after(100, self.check_and_setup_dependencies)

        self.settings_manager = SettingsManager()
        theme_name = self.settings_manager.get("theme", "Graphite")
        theme.set_theme(theme_name)

        self.selected_lang = tk.StringVar(
            value=self.settings_manager.get("language", "Python")
        )
        self.languages = [
            "Python",
            "JavaScript",
            "HTML",
            "CSS",
            "C++",
            "Java",
            "Rust",
            "Go",
        ]

        self.toolbar = tk.Frame(root, bg=theme.COLORS["bg_header"], height=38)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)
        self.toolbar.pack_propagate(False)

        self.toolbar_divider = tk.Frame(root, bg=theme.COLORS["sash_color"], height=1)
        self.toolbar_divider.pack(side=tk.TOP, fill=tk.X)

        self.status_bar = tk.Frame(root, bg=theme.COLORS["bg_header"], height=25)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_bar.pack_propagate(False)

        self.status_label = tk.Label(
            self.status_bar,
            text="",
            anchor="w",
            font=theme.FONTS["ui"],
            fg=theme.COLORS["fg_dim"],
            bg=theme.COLORS["bg_header"],
        )
        self.status_label.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        self.ai_level_status_label = tk.Label(
            self.status_bar,
            text="AI Level: Medium",
            anchor="e",
            font=theme.FONTS["ui"],
            fg=theme.COLORS["fg_light"],
            bg=theme.COLORS["bg_header"],
        )
        self.ai_level_status_label.pack(side=tk.RIGHT, padx=(0, 10))

        self.main_paned = tk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=1)

        self.center_right_paned = tk.PanedWindow(self.main_paned, orient=tk.HORIZONTAL)

        self.paned_window = tk.PanedWindow(self.center_right_paned, orient=tk.VERTICAL)
        self.center_right_paned.add(self.paned_window, minsize=400)

        self.editor_frame = tk.Frame(self.paned_window)
        self.editor_label = tk.Label(self.editor_frame, text="EDITOR (PYTHON)")
        self.editor_label.pack(fill=tk.X)

        self.editor_scrollbar = ttk.Scrollbar(self.editor_frame)
        self.editor_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.line_numbers = tk.Text(
            self.editor_frame, width=4, wrap=tk.NONE, state=tk.DISABLED
        )
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)

        self.editor = tk.Text(self.editor_frame, wrap=tk.NONE, undo=True)
        self.editor.pack(fill=tk.BOTH, expand=1)

        self.paned_window.add(self.editor_frame, minsize=150)

        self.console_frame = tk.Frame(self.paned_window)
        self.console_label = tk.Label(self.console_frame, text="CONSOLE OUTPUT")
        self.console_label.pack(fill=tk.X)

        self.console_scrollbar = ttk.Scrollbar(self.console_frame)
        self.console_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.console = tk.Text(
            self.console_frame, wrap=tk.WORD, yscrollcommand=self.console_scrollbar.set
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
            self.editor_label,
            on_file_open_callback=self.update_editor_ai_state,
            require_explorer_open=True,
            settings_manager=self.settings_manager,
        )
        self.controller.on_dirty_state_changed_callback = self.on_dirty_state_changed
        self.controller.on_single_file_open_callback = self.hide_explorer

        def sync_scroll(*args):
            self.editor.yview(*args)
            self.line_numbers.yview(*args)

        self.editor_scrollbar.config(command=sync_scroll)

        def on_editor_scroll(*args):
            self.editor_scrollbar.set(*args)
            self.line_numbers.yview_moveto(args[0])

        self.editor.config(yscrollcommand=on_editor_scroll)

        # Bind to <<Modified>> BEFORE the syntax highlighter does,
        # so we capture dirty state before the highlighter resets edit_modified().
        self.editor.bind("<<Modified>>", self._on_editor_modified, add="+")

        self.autocomplete = LithiumAutocompleteManager(
            self.editor, self.selected_lang, check_callback=self.on_editor_change
        )

        from src.syntax import SyntaxHighlighter

        self.syntax_highlighter = SyntaxHighlighter(
            self.editor,
            language_getter=lambda: self.selected_lang.get(),
        )
        self.syntax_highlighter.highlight_all()
        self.editor.bind(
            "<KeyRelease>",
            lambda e: self.syntax_highlighter.schedule_highlight(),
            add="+",
        )
        self.editor.bind(
            "<MouseWheel>",
            lambda e: self.syntax_highlighter.schedule_highlight(),
            add="+",
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
            self.toolbar_divider,
        )

        self.icons = {}
        try:
            self.icons["file"] = tk.PhotoImage(
                file=resource_path("src/assets/file.png")
            )
            self.icons["theme"] = tk.PhotoImage(
                file=resource_path("src/assets/theme.png")
            )
            self.icons["run"] = tk.PhotoImage(file=resource_path("src/assets/run.png"))
            self.icons["python"] = tk.PhotoImage(
                file=resource_path("src/assets/python.png")
            )
            self.icons["javascript"] = tk.PhotoImage(
                file=resource_path("src/assets/javascript.png")
            )
            self.icons["typescript"] = tk.PhotoImage(
                file=resource_path("src/assets/typescript.png")
            )
            self.icons["html"] = tk.PhotoImage(
                file=resource_path("src/assets/html.png")
            )
            self.icons["css"] = tk.PhotoImage(file=resource_path("src/assets/css.png"))
            self.icons["generic"] = tk.PhotoImage(
                file=resource_path("src/assets/generic.png")
            )
        except Exception:
            pass

        self.btn_file = tk.Button(
            self.toolbar,
            text=" File ▾",
            image=self.icons.get("file", ""),
            compound=tk.LEFT,
            command=self.show_file_menu,
        )
        self.btn_file.pack(side=tk.LEFT, padx=(10, 2), pady=3)
        theme.style_toolbar_button(self.btn_file)

        self.btn_lang = tk.Button(
            self.toolbar,
            text=" Language ▾",
            image=self.icons.get("generic", ""),
            compound=tk.LEFT,
            command=self.show_lang_menu,
        )
        self.btn_lang.pack(side=tk.LEFT, padx=2, pady=3)
        theme.style_toolbar_button(self.btn_lang)

        self.btn_ai = tk.Button(
            self.toolbar,
            text=" AI ▾",
            image=self.icons.get("generic", ""),
            compound=tk.LEFT,
            command=self.show_ai_menu,
        )
        self.btn_ai.pack(side=tk.LEFT, padx=2, pady=3)
        theme.style_toolbar_button(self.btn_ai)

        self.system_ram_gb = ai_level_manager.get_system_ram_gb()
        self.ai_level_mode = self.settings_manager.get("ai_level_mode", "auto")
        self.ai_manual_level = self.settings_manager.get("ai_level", "Medium")
        self.effective_ai_level = ai_level_manager.get_effective_level(
            self.ai_level_mode,
            self.ai_manual_level,
            self.system_ram_gb,
        )
        self.ai_inference_params = ai_level_manager.get_inference_params(
            self.effective_ai_level
        )

        self.ai_skill_settings = AISkillSettings(self.settings_manager).load()
        self._init_ai_skill_vars()

        self.ai_model_link = self._resolve_ai_model_link()
        self.ai_system_prompt = ai_runner.DEFAULT_SYSTEM_PROMPT

        self.ai_skills_executor = None
        self._init_ai_skills()
        self._pending_retry_info = None  # (prompt, retry_count) for reject-and-retry
        self._original_content_before_ai = (
            None  # Original editor content before AI changes
        )
        self._approval_bar = None  # Approval bar frame widget

        if self.ai_model_link:
            self.status_label.config(text=f"AI: configured model {self.ai_model_link}")

        self._update_ai_level_display()

        try:
            stop_icon = tk.PhotoImage(width=12, height=12)
            stop_icon.put("red", to=(0, 0, 11, 11))
            self.icons["stop"] = stop_icon
        except Exception:
            self.icons["stop"] = self.icons.get("run", "")

        self.btn_theme = tk.Button(
            self.toolbar,
            text=" Theme ▾",
            image=self.icons.get("theme", ""),
            compound=tk.LEFT,
            command=self.show_theme_menu,
        )
        self.btn_theme.pack(side=tk.LEFT, padx=2, pady=3)
        theme.style_toolbar_button(self.btn_theme)

        self.btn_run = tk.Button(
            self.toolbar,
            text=" Run Script",
            image=self.icons.get("run", ""),
            compound=tk.LEFT,
            command=self.run_code,
        )
        self.btn_run.pack(side=tk.LEFT, padx=(20, 2), pady=3)
        theme.style_toolbar_button(self.btn_run)
        self.script_running = False

        self.active_menu = None

        self.editor.bind("<KeyRelease>", self.on_editor_change, add="+")
        self.editor.bind("<ButtonRelease-1>", lambda e: self.controller.update_status())
        self.editor.bind(
            "<MouseWheel>",
            lambda e: self.root.after(10, self.controller.sync_line_number_scroll),
        )

        self.create_menu()

        self.controller.update_line_numbers()
        self.controller.update_status()
        self.update_editor_ai_state()

        lang = self.selected_lang.get()
        icon_key = lang.lower()
        if icon_key not in self.icons:
            icon_key = "generic"
        self.btn_lang.config(text=f" {lang} ▾", image=self.icons.get(icon_key, ""))

        self.main_paned.config(
            bg=theme.COLORS["bg_dark"], bd=0, sashwidth=4, sashpad=1, sashrelief=tk.FLAT
        )

        self.center_right_paned.config(
            bg=theme.COLORS["bg_dark"], bd=0, sashwidth=4, sashpad=1, sashrelief=tk.FLAT
        )

        self.explorer_frame = tk.Frame(
            self.main_paned, bg=theme.COLORS["bg_dark"], width=320
        )
        self.explorer_frame.pack_propagate(False)

        self.file_explorer = FileExplorer(
            self.explorer_frame, self.controller, theme.COLORS, theme.FONTS
        )
        self.main_paned.add(self.explorer_frame, minsize=150, width=320)

        self.main_paned.add(self.center_right_paned, minsize=400)

        self.conversation_manager = get_conversation_manager()
        self._conversation_ids = []
        self.current_conversation_label = tk.StringVar(value="No conversation")

        self.chat_frame = tk.Frame(self.center_right_paned, bg=theme.COLORS["bg_dark"])

        self.chat_panel = tk.Frame(self.chat_frame, bg=theme.COLORS["bg_dark"])
        self.chat_panel.pack(fill=tk.BOTH, expand=True)

        self.chat_header = tk.Frame(
            self.chat_panel, bg=theme.COLORS["bg_header"], height=35
        )
        self.chat_header.pack(fill=tk.X, side=tk.TOP)
        self.chat_header.pack_propagate(False)

        self.chat_header_label = tk.Label(
            self.chat_header,
            text="AI CHAT",
            font=theme.FONTS["header"],
            fg=theme.COLORS["fg_dim"],
            bg=theme.COLORS["bg_header"],
        )
        self.chat_header_label.pack(side=tk.LEFT, padx=12, pady=8)

        self.ai_level_var = tk.StringVar(value=self._ai_level_dropdown_value())
        self.ai_level_dropdown = ttk.Combobox(
            self.chat_header,
            textvariable=self.ai_level_var,
            values=self._ai_level_dropdown_options(),
            state="readonly",
            width=18,
            font=theme.FONTS["ui"],
        )
        self.ai_level_dropdown.pack(side=tk.LEFT, padx=(0, 8), pady=6)
        self.ai_level_dropdown.bind("<<ComboboxSelected>>", self.on_ai_level_selected)

        self.chat_close_btn = tk.Button(
            self.chat_header,
            text="✕",
            font=theme.FONTS["ui"],
            fg=theme.COLORS["fg_dim"],
            bg=theme.COLORS["bg_header"],
            bd=0,
            activebackground=theme.COLORS["sash_color"],
            activeforeground=theme.COLORS["accent"],
            command=self.toggle_ai_chat,
        )
        self.chat_close_btn.pack(side=tk.RIGHT, padx=10)

        self.conv_dropdown_btn = tk.Button(
            self.chat_header,
            text="💬 No conversation ▾",
            font=theme.FONTS["ui"],
            fg=theme.COLORS["fg_light"],
            bg=theme.COLORS["bg_header"],
            bd=0,
            activebackground=theme.COLORS["sash_color"],
            activeforeground=theme.COLORS["fg_light"],
            cursor="hand2",
            command=self.show_conversations_dropdown,
        )
        self.conv_dropdown_btn.pack(side=tk.RIGHT, padx=(0, 4), pady=6)

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
            highlightthickness=0,
        )
        self.chat_history.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))
        self.chat_scrollbar.config(command=self.chat_history.yview)
        self.chat_history.config(state=tk.DISABLED)
        self.button_frames = {}
        self.code_indices = {}

        self.chat_input_container = tk.Frame(
            self.chat_panel, bg=theme.COLORS["bg_dark"]
        )
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
            highlightcolor=theme.COLORS["accent"],
        )
        self.chat_input.pack(fill=tk.X, side=tk.TOP, pady=(0, 5))

        self.chat_status_bar = tk.Frame(
            self.chat_input_container, bg=theme.COLORS["bg_dark"]
        )
        self.chat_status_bar.pack(fill=tk.X, side=tk.TOP, pady=(0, 4))

        self.skills_dropdown_btn = tk.Button(
            self.chat_status_bar,
            text="Skills ▾",
            font=theme.FONTS["ui"],
            fg=theme.COLORS["fg_light"],
            bg=theme.COLORS["bg_dark"],
            bd=0,
            activebackground=theme.COLORS["sash_color"],
            activeforeground=theme.COLORS["fg_light"],
            cursor="hand2",
            command=self.show_skills_dropdown,
        )
        self.skills_dropdown_btn.pack(side=tk.LEFT)
        theme.style_toolbar_button(self.skills_dropdown_btn)

        self.chat_task_status_label = tk.Label(
            self.chat_status_bar,
            text="",
            font=("DejaVu Sans", 8),
            fg=theme.COLORS["fg_dim"],
            bg=theme.COLORS["bg_dark"],
        )
        self.chat_task_status_label.pack(side=tk.RIGHT)

        self._update_skills_dropdown_label()

        self.chat_button_frame = tk.Frame(
            self.chat_input_container, bg=theme.COLORS["bg_dark"]
        )
        self.chat_button_frame.pack(fill=tk.X, side=tk.TOP)

        self.chat_send_btn = tk.Button(
            self.chat_button_frame, text="Send", command=self.send_chat_message
        )
        self.chat_send_btn.pack(side=tk.RIGHT)
        theme.style_toolbar_button(self.chat_send_btn)

        self.chat_clear_btn = tk.Button(
            self.chat_button_frame, text="Clear", command=self.clear_chat
        )
        self.chat_clear_btn.pack(side=tk.LEFT)
        theme.style_toolbar_button(self.chat_clear_btn)

        self.chat_visible = True
        self.center_right_paned.add(self.chat_frame, minsize=450, width=500)

        # Re-apply enabled/disabled state now that all chat widgets exist
        self.update_editor_ai_state()

        # Bind click events on disabled widgets to flash the File button
        self.editor.bind("<Button-1>", self._on_disabled_area_click, add="+")
        self.chat_input.bind("<Button-1>", self._on_disabled_area_click, add="+")
        self.chat_history.bind("<Button-1>", self._on_disabled_area_click, add="+")

        threading.Thread(target=self.load_languages_async, daemon=True).start()

    def _on_editor_modified(self, event=None):
        """Called on <<Modified>> — fires before the syntax highlighter resets edit_modified()."""
        if self.controller.editor.edit_modified():
            self.controller.mark_dirty()

    def on_editor_change(self, event=None):
        self.controller.update_line_numbers()
        self.controller.update_status()
        self.autocomplete.check_autocomplete(event)

    def on_dirty_state_changed(self, file_path, is_dirty):
        current_name = os.path.basename(file_path) if file_path else "Untitled"
        status_text = f"{current_name}{' *' if is_dirty else ''}"
        self.status_label.config(text=status_text)
        if hasattr(self, "file_explorer") and self.file_explorer:
            explorer_marker = " • Unsaved" if is_dirty else ""
            self.file_explorer.header_label.config(text=f"EXPLORER{explorer_marker}")
            try:
                self.file_explorer.mark_file_dirty(file_path, is_dirty)
            except Exception:
                pass

    def on_app_close(self):
        if self.controller.has_unsaved_changes:
            answer = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?",
            )
            if answer is None:
                return
            if answer:
                saved = self.controller.save_file()
                if not saved:
                    messagebox.showerror(
                        "Save Error", "Unable to save the file. Close canceled."
                    )
                    return
        self.root.destroy()

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
        self.file_menu.add_command(
            label="New", command=self.controller.new_file, accelerator="Ctrl+N"
        )
        self.file_menu.add_command(
            label="Open", command=self.controller.open_file, accelerator="Ctrl+O"
        )
        self.file_menu.add_command(label="Open Folder", command=self.open_folder)
        self.file_menu.add_command(
            label="Save", command=self.controller.save_file, accelerator="Ctrl+S"
        )
        self.file_menu.add_command(
            label="Save As", command=self.controller.save_as_file
        )
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=self.on_app_close)

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
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)

        self.update_editor_ai_state()

    def build_languages_menu(self):
        self.lang_menu.delete(0, tk.END)

        self.lang_menu.add_command(
            label="Search Language...",
            command=self.show_search_dialog,
            accelerator="Ctrl+Shift+P",
        )
        self.lang_menu.add_separator()

        most_used = [
            "Python",
            "JavaScript",
            "TypeScript",
            "HTML",
            "CSS",
            "C++",
            "C#",
            "Java",
            "PHP",
            "Go",
            "Rust",
            "SQL",
        ]
        most_used_sub = tk.Menu(self.lang_menu, tearoff=0)
        theme.style_menu(most_used_sub)
        for lang in sorted(most_used):
            most_used_sub.add_radiobutton(
                label=lang,
                variable=self.selected_lang,
                value=lang,
                command=self.on_language_select,
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
                    command=self.on_language_select,
                )
            self.lang_menu.add_cascade(label=group_title, menu=sub)

    def on_language_select(self):
        lang = self.selected_lang.get()
        self.editor_label.config(text=f"EDITOR ({lang.upper()})")
        self.controller.update_status()
        self.controller._save_language_preference()
        icon_key = lang.lower()
        if icon_key not in self.icons:
            icon_key = "generic"
        self.btn_lang.config(text=f" {lang} ▾", image=self.icons.get(icon_key, ""))
        if hasattr(self, "syntax_highlighter"):
            self.syntax_highlighter.highlight_all()

    def build_ai_menu(self):
        self.ai_menu.delete(0, tk.END)
        self.ai_menu.add_command(label="Check AI Status", command=self.check_ai_status)
        self.ai_menu.add_command(
            label="Toggle AI Chat Sidebar", command=self.toggle_ai_chat
        )
        self.ai_menu.add_separator()
        self.ai_menu.add_command(
            label="About Lithium",
            command=lambda: messagebox.showinfo(
                "Lithium IDE", "Developed by Vodkrox | 2026"
            ),
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
            text="A built-in model is required. Click 'Download' to install it locally.",
            wraplength=480,
            justify=tk.LEFT,
        ).pack(fill=tk.X, padx=12, pady=(12, 8), anchor="w")

        candidates = ai_runner.list_model_candidates()
        if not candidates:
            tk.Label(config_win, text="No downloadable model available.").pack(
                fill=tk.X, padx=12, pady=12
            )
            tk.Button(config_win, text="Close", command=config_win.destroy).pack(
                pady=10
            )
            return

        model_name, model_url = candidates[0]
        tk.Label(config_win, text=f"Model: {model_name}").pack(
            fill=tk.X, padx=12, pady=(6, 8), anchor="w"
        )

        progress_label = tk.Label(config_win, text="", anchor="w")
        progress_label.pack(fill=tk.X, padx=12, pady=(0, 4))

        progress_bar = ttk.Progressbar(
            config_win, orient="horizontal", mode="determinate", maximum=100
        )
        progress_bar.pack(fill=tk.X, padx=12, pady=(0, 10))

        download_in_progress = {"active": False}

        def on_close():
            if download_in_progress["active"]:
                messagebox.showwarning(
                    "AI", "The model is downloading. Please wait until it finishes."
                )
                return
            config_win.destroy()
            self.root.destroy()

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
                    local_path = ai_runner.download_model_url(
                        url, progress_callback=update_progress
                    )
                    self.ai_model_link = local_path
                    self.settings_manager.set("ai_model_path", local_path)

                    def on_download_complete():
                        progress_label.config(text="Download complete")
                        messagebox.showinfo(
                            "AI", "Download Finished! Lithium will close."
                        )
                        config_win.destroy()
                        self.root.destroy()

                    self.root.after(0, on_download_complete)
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

        tk.Label(config_win, text="Wait until download finishes").pack(
            fill=tk.X, padx=12, pady=(6, 6)
        )
        close_button = tk.Button(config_win, text="Close", command=on_close)
        close_button.pack(pady=6)
        config_win.protocol("WM_DELETE_WINDOW", on_close)

    def ask_ai_prompt(self):
        has_file_opened = self.controller.file_path is not None
        if not has_file_opened:
            messagebox.showwarning(
                "AI", "You must open a file from the explorer before using AI features."
            )
            return

        if not self.ai_model_link:
            messagebox.showwarning(
                "AI", "No AI model is configured. Please configure the model first."
            )
            return

        prompt_win = tk.Toplevel(self.root)
        prompt_win.title("Run AI Prompt")
        prompt_win.geometry("520x360")
        prompt_win.resizable(False, False)
        prompt_win.transient(self.root)
        prompt_win.grab_set()

        tk.Label(prompt_win, text="Enter your question or instruction:").pack(
            fill=tk.X, padx=15, pady=(15, 5), anchor="w"
        )
        prompt_box = tk.Text(prompt_win, height=12, wrap=tk.WORD)
        prompt_box.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))

        def submit_prompt():
            prompt_text = prompt_box.get("1.0", tk.END).strip()
            if not prompt_text:
                messagebox.showwarning("AI", "Prompt cannot be empty.")
                return
            prompt_win.destroy()
            threading.Thread(
                target=self.run_ai_prompt, args=(prompt_text,), daemon=True
            ).start()

        tk.Button(prompt_win, text="Generate response", command=submit_prompt).pack(
            pady=10
        )

    def run_ai_prompt(self, prompt):
        self.root.after(
            0, lambda: self.status_label.config(text="AI: running local model...")
        )
        try:
            editor_prompt = self._build_ai_editor_prompt(prompt)
            result = ai_runner.generate_text_from_model(
                self.ai_model_link,
                self.ai_system_prompt,
                editor_prompt,
                **self.ai_inference_params,
            )
            result = self._retry_if_broken_ai_edit_response(
                prompt, editor_prompt, result
            )

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
        level = self.effective_ai_level
        billions = ai_level_manager.format_billions_label(level)
        mode = "Auto" if (self.ai_level_mode or "auto").lower() == "auto" else "Manual"
        ram_info = f"{self.system_ram_gb:.1f} GB" if self.system_ram_gb else "Unknown"
        if runtime:
            messagebox.showinfo(
                "AI Status",
                (
                    f"AI backend available: {runtime}\n"
                    f"AI Level: {level} ({billions} de 7B)\n"
                    f"Modo: {mode} | RAM: {ram_info}\n"
                    f"Model: {self.ai_model_link or 'Not configured'}"
                ),
            )
            self.status_label.config(text=f"AI: backend {runtime} available")
        else:
            messagebox.showwarning(
                "AI Status",
                "No local AI backend was found. Install llama-cpp or transformers and torch in your Python environment.",
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
                label=theme_name, command=lambda t=theme_name: self.change_theme(t)
            )

    def change_theme(self, theme_name):
        theme.set_theme(theme_name)
        self.settings_manager.set("theme", theme_name)
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
            self.toolbar_divider,
        )
        self._apply_window_theme()

    def _apply_window_theme(self):
        """Re-apply the active theme to every persistent UI region."""
        for paned in (self.main_paned, self.center_right_paned):
            paned.config(
                bg=theme.COLORS["bg_dark"],
                bd=0,
                sashwidth=4,
                sashpad=1,
                sashrelief=tk.FLAT,
            )

        for frame_attr in ("editor_frame", "console_frame", "explorer_frame"):
            if hasattr(self, frame_attr):
                getattr(self, frame_attr).config(bg=theme.COLORS["bg_dark"])

        self._apply_status_bar_theme()
        self._apply_chat_theme()

        if hasattr(self, "file_explorer") and self.file_explorer:
            self.file_explorer.apply_theme()

        for button in (
            self.btn_file,
            self.btn_lang,
            self.btn_ai,
            self.btn_theme,
            self.btn_run,
            self.chat_send_btn,
            self.chat_clear_btn,
        ):
            theme.style_toolbar_button(button)

        self.conv_dropdown_btn.config(
            bg=theme.COLORS["bg_header"],
            fg=theme.COLORS["fg_light"],
            activebackground=theme.COLORS["sash_color"],
            activeforeground=theme.COLORS["fg_light"],
        )

        for menu in (self.file_menu, self.lang_menu, self.ai_menu, self.theme_menu):
            theme.style_menu(menu)

        self.build_languages_menu()
        self.build_theme_menu()

    def _apply_status_bar_theme(self):
        self.status_bar.config(bg=theme.COLORS["bg_header"])
        self.status_label.config(
            bg=theme.COLORS["bg_header"], fg=theme.COLORS["fg_dim"]
        )
        self.ai_level_status_label.config(
            bg=theme.COLORS["bg_header"], fg=theme.COLORS["fg_light"]
        )

    def _apply_chat_theme(self):
        self.chat_frame.config(bg=theme.COLORS["bg_dark"])
        self.chat_panel.config(bg=theme.COLORS["bg_dark"])
        self.chat_header.config(bg=theme.COLORS["bg_header"])
        self.chat_header_label.config(
            fg=theme.COLORS["fg_dim"], bg=theme.COLORS["bg_header"]
        )
        if hasattr(self, "ai_level_dropdown"):
            self.ai_level_dropdown.configure(
                foreground=theme.COLORS["fg_light"],
                background=theme.COLORS["bg_header"],
            )
        if hasattr(self, "conv_dropdown_btn"):
            self.conv_dropdown_btn.config(
                fg=theme.COLORS["fg_light"],
                bg=theme.COLORS["bg_header"],
                activebackground=theme.COLORS["sash_color"],
                activeforeground=theme.COLORS["fg_light"],
            )
        self.chat_close_btn.config(
            fg=theme.COLORS["fg_dim"],
            bg=theme.COLORS["bg_header"],
            activebackground=theme.COLORS["sash_color"],
            activeforeground=theme.COLORS["accent"],
        )
        self.chat_history.config(
            bg=theme.COLORS["bg_editor"],
            fg=theme.COLORS["fg_light"],
            insertbackground=theme.COLORS["accent"],
            selectbackground=theme.COLORS["selection_bg"],
            selectforeground=theme.COLORS["fg_light"],
        )
        self.chat_input_container.config(bg=theme.COLORS["bg_dark"])
        if hasattr(self, "chat_status_bar"):
            self.chat_status_bar.config(bg=theme.COLORS["bg_dark"])
            self.skills_dropdown_btn.config(
                fg=theme.COLORS["fg_light"],
                bg=theme.COLORS["bg_dark"],
                activebackground=theme.COLORS["sash_color"],
                activeforeground=theme.COLORS["fg_light"],
            )
            self.chat_task_status_label.config(
                fg=theme.COLORS["fg_dim"],
                bg=theme.COLORS["bg_dark"],
            )
        self.chat_input.config(
            bg=theme.COLORS["bg_editor"],
            fg=theme.COLORS["fg_light"],
            insertbackground=theme.COLORS["accent"],
            selectbackground=theme.COLORS["selection_bg"],
            selectforeground=theme.COLORS["fg_light"],
            highlightbackground=theme.COLORS["sash_color"],
            highlightcolor=theme.COLORS["accent"],
        )
        self.chat_button_frame.config(bg=theme.COLORS["bg_dark"])
        self._restyle_chat_tags()
        self._restyle_embedded_chat_widgets()

    def _restyle_chat_tags(self):
        self.chat_history.tag_config(
            "approval_msg", foreground=theme.COLORS["accent"], font=theme.FONTS["ui"]
        )
        self.chat_history.tag_config(
            "code_block_tag",
            background=theme.COLORS["bg_dark"],
            foreground=theme.COLORS["fg_light"],
            font=theme.FONTS.get("editor", ("Consolas", 11)),
        )
        for tag_name in self.chat_history.tag_names():
            if not tag_name.startswith("sender_tag_"):
                continue
            sender = tag_name.removeprefix("sender_tag_")
            if sender == "AI":
                color = theme.COLORS["accent"]
            elif sender == "Error":
                color = theme.COLORS["console_err"]
            else:
                color = theme.COLORS["fg_dim"]
            self.chat_history.tag_config(
                tag_name, foreground=color, font=("DejaVu Sans", 10, "bold")
            )

    def _restyle_embedded_chat_widgets(self):
        for widget in self.chat_history.winfo_children():
            self._restyle_embedded_widget(widget)

    def _restyle_embedded_widget(self, widget):
        try:
            if isinstance(widget, tk.Frame):
                widget.config(bg=theme.COLORS["bg_dark"])
            elif isinstance(widget, tk.Label):
                widget.config(bg=theme.COLORS["bg_dark"])
                if widget.cget("fg") not in (
                    theme.COLORS["success"],
                    theme.COLORS["error"],
                ):
                    widget.config(fg=theme.COLORS["fg_dim"])
            elif isinstance(widget, tk.Text):
                widget.config(
                    bg=theme.COLORS["bg_editor"],
                    fg=theme.COLORS["fg_dim"],
                )
            elif isinstance(widget, tk.Button):
                text = widget.cget("text")
                if "Approve" in text or "Apply" in text or "Aprobar" in text:
                    widget.config(bg=theme.COLORS["accent"], fg=theme.COLORS["bg_dark"])
                elif "reasoning" in text.lower():
                    widget.config(
                        bg=theme.COLORS["bg_editor"],
                        fg=theme.COLORS["fg_dim"],
                        activebackground=theme.COLORS["bg_dark"],
                        activeforeground=theme.COLORS["accent"],
                    )
                else:
                    widget.config(
                        bg=theme.COLORS["sash_color"], fg=theme.COLORS["fg_light"]
                    )
        except Exception:
            pass

        for child in widget.winfo_children():
            self._restyle_embedded_widget(child)

    def open_folder(self):
        """Open a folder in the file explorer."""
        folder = filedialog.askdirectory(title="Open Folder")
        if folder:
            self.show_explorer()
            self.file_explorer.load_folder(folder)
            self.file_or_folder_opened = True
            self.update_editor_ai_state()

    def hide_explorer(self):
        """Hide the file explorer sidebar."""
        try:
            self.main_paned.forget(self.explorer_frame)
        except Exception:
            pass

    def show_explorer(self):
        """Show the file explorer sidebar."""
        try:
            panes = self.main_paned.panes()
            if str(self.explorer_frame) not in panes:
                self.main_paned.add(
                    self.explorer_frame,
                    before=self.center_right_paned,
                    minsize=150,
                    width=320,
                )
        except Exception:
            pass

    def run_code(self, event=None):
        if runner.is_running():
            self._stop_script()
            return

        if not self.controller.file_path:
            self.controller.save_as_file()
            if not self.controller.file_path:
                return
        else:
            self.controller.save_file()

        self._script_started()
        runner.run_code(
            self.controller.file_path, self.console, on_complete=self._script_complete
        )

    def _stop_script(self):
        stopped = runner.stop_code()
        if stopped:
            self.status_label.config(text="Script stopped")
            self.console.config(state=tk.NORMAL)
            self.console.insert(tk.END, "\n[Script stopped by user]\n")
            self.console.config(state=tk.DISABLED)
        else:
            self.status_label.config(text="Stop request failed")

    def _script_started(self):
        self.script_running = True
        self.btn_run.config(text=" Stop Script", image=self.icons.get("stop", ""))
        self.status_label.config(text="Running script...")

    def _script_complete(self):
        self.script_running = False
        self.btn_run.config(text=" Run Script", image=self.icons.get("run", ""))
        self.status_label.config(text="Ready")

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

    def _ai_level_dropdown_options(self):
        return ["Auto"] + ai_level_manager.AI_LEVELS

    def _ai_level_dropdown_value(self):
        if (self.ai_level_mode or "auto").lower() == "auto":
            return "Auto"
        return ai_level_manager.normalize_level(self.ai_manual_level)

    def _get_effective_ai_level(self):
        return ai_level_manager.get_effective_level(
            self.ai_level_mode,
            self.ai_manual_level,
            self.system_ram_gb,
        )

    def _apply_ai_level(self):
        previous_params = getattr(self, "ai_inference_params", None)
        self.effective_ai_level = self._get_effective_ai_level()
        self.ai_inference_params = ai_level_manager.get_inference_params(
            self.effective_ai_level
        )

        if previous_params != self.ai_inference_params:
            ai_runner.clear_model_cache()

        self._update_ai_level_display()

    def _update_ai_level_display(self):
        level = self.effective_ai_level
        self.ai_level_status_label.config(text=f"AI Level: {level}")

        if hasattr(self, "ai_level_var"):
            self.ai_level_var.set(self._ai_level_dropdown_value())

    def on_ai_level_selected(self, event=None):
        selected = self.ai_level_var.get().strip()
        if selected == "Auto":
            self.ai_level_mode = "auto"
            self.settings_manager.set("ai_level_mode", "auto")
        else:
            self.ai_level_mode = "manual"
            self.ai_manual_level = ai_level_manager.normalize_level(selected)
            self.settings_manager.set("ai_level_mode", "manual")
            self.settings_manager.set("ai_level", self.ai_manual_level)

        self._apply_ai_level()

    def _init_ai_skill_vars(self):
        self._ai_skill_file_scope_var = tk.StringVar(
            value=self.ai_skill_settings.get("file_scope")
        )
        self._ai_skill_toggle_vars = {}
        for key, _label in SKILL_TOGGLE_LABELS:
            self._ai_skill_toggle_vars[key] = tk.BooleanVar(
                value=self.ai_skill_settings.get(key)
            )

    def _refresh_ai_system_prompt(self):
        self.ai_system_prompt = ai_runner.DEFAULT_SYSTEM_PROMPT
        if not self.ai_skills_executor:
            return

        scope = self.ai_skill_settings.get("file_scope")
        self.ai_skills_executor.configure_capabilities(
            file_scope=scope,
            allow_run_commands=self.ai_skill_settings.get("run_commands"),
        )
        self.ai_system_prompt += "\n" + self.ai_skills_executor.generate_skill_prompt(
            file_scope=scope
        )
        addendum = self.ai_skill_settings.build_system_prompt_addendum()
        if addendum:
            self.ai_system_prompt += "\n" + addendum

    def _set_ai_skill(self, key, value):
        self.ai_skill_settings.set(key, value)
        self._refresh_ai_system_prompt()
        self._update_skills_dropdown_label()

    def _update_skills_dropdown_label(self):
        if not hasattr(self, "skills_dropdown_btn"):
            return
        count = self.ai_skill_settings.active_count()
        label = f"Skills ({count}) ▾" if count else "Skills ▾"
        self.skills_dropdown_btn.config(text=label)

    def show_skills_dropdown(self):
        menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=theme.COLORS["bg_header"],
            fg=theme.COLORS["fg_light"],
        )
        theme.style_menu(menu)

        for scope_value, scope_label in FILE_SCOPE_OPTIONS:
            menu.add_radiobutton(
                label=scope_label,
                variable=self._ai_skill_file_scope_var,
                value=scope_value,
                command=lambda value=scope_value: self._set_ai_skill(
                    "file_scope", value
                ),
            )

        menu.add_separator()

        for key, label in SKILL_TOGGLE_LABELS:
            menu.add_checkbutton(
                label=label,
                variable=self._ai_skill_toggle_vars[key],
                command=lambda skill_key=key: self._set_ai_skill(
                    skill_key,
                    self._ai_skill_toggle_vars[skill_key].get(),
                ),
            )

        x = self.skills_dropdown_btn.winfo_rootx()
        y = (
            self.skills_dropdown_btn.winfo_rooty()
            + self.skills_dropdown_btn.winfo_height()
        )
        menu.post(x, y)

    def _collect_workspace_files(self, max_files=150):
        folder = None
        if hasattr(self, "file_explorer") and self.file_explorer:
            folder = self.file_explorer.current_folder
        if not folder or not os.path.isdir(folder):
            return []

        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", ".models"}
        collected = []
        for root, dirs, files in os.walk(folder):
            dirs[:] = [
                name
                for name in dirs
                if not name.startswith(".") and name not in skip_dirs
            ]
            for filename in files:
                if filename.startswith("."):
                    continue
                rel_path = os.path.relpath(os.path.join(root, filename), folder)
                collected.append(rel_path.replace("\\", "/"))
                if len(collected) >= max_files:
                    return collected
        return collected

    def _notify_ai_task_complete(self):
        if not self.ai_skill_settings.get("notify_on_complete"):
            return
        self.root.bell()
        if hasattr(self, "chat_task_status_label"):
            self.chat_task_status_label.config(text="Task complete")
            self.root.after(4000, lambda: self.chat_task_status_label.config(text=""))

    def _resolve_ai_model_link(self):
        saved_model = self.settings_manager.get("ai_model_path")
        if saved_model and (os.path.isfile(saved_model) or os.path.isdir(saved_model)):
            return saved_model

        local_model = ai_runner.find_local_model()
        if local_model:
            return local_model

        return ai_runner.MODEL_CANDIDATES[0][1] if ai_runner.MODEL_CANDIDATES else ""

    def _get_missing_dependencies(self):
        missing = []
        if not can_import_module("huggingface_hub"):
            missing.append("huggingface_hub")
        if ai_runner.get_runtime_status() is None:
            missing.append("llama-cpp-python")
        return missing

    def _is_ai_model_ready(self):
        if self.ai_model_link and os.path.isfile(self.ai_model_link):
            return True
        if self.ai_model_link and os.path.isdir(self.ai_model_link):
            return True

        local_model = ai_runner.find_local_model()
        if local_model:
            self.ai_model_link = local_model
            self.settings_manager.set("ai_model_path", local_model)
            return True

        return False

    def _finish_dependency_setup(self):
        if self._is_ai_model_ready():
            self._enable_root()
            return True
        self.configure_ai_model()
        return False

    def _disable_root(self):
        """Disable the root window (Windows-only, safe to ignore on other platforms)."""
        try:
            self.root.attributes("-disabled", True)
        except Exception:
            pass

    def _enable_root(self):
        """Re-enable the root window (Windows-only, safe to ignore on other platforms)."""
        try:
            self.root.attributes("-disabled", False)
        except Exception:
            pass

    def check_and_setup_dependencies(self):
        self._disable_root()
        missing = self._get_missing_dependencies()
        if not missing:
            return self._finish_dependency_setup()

        self._disable_root()
        setup_win = tk.Toplevel(self.root)
        setup_win.title("Lithium IDE - AI Setup Assistant")
        setup_win.geometry("500x320")
        setup_win.resizable(False, False)

        setup_win.update_idletasks()
        width = setup_win.winfo_width()
        height = setup_win.winfo_height()
        x = (setup_win.winfo_screenwidth() // 2) - (width // 2)
        y = (setup_win.winfo_screenheight() // 2) - (height // 2)
        setup_win.geometry(f"+{x}+{y}")

        bg_color = theme.COLORS.get("bg_dark", "#1e1e1e")
        fg_color = theme.COLORS.get("fg_light", "#ffffff")
        fg_dim = theme.COLORS.get("fg_dim", "#888888")
        accent_color = theme.COLORS.get("accent", "#007acc")
        sash_color = theme.COLORS.get("sash_color", "#555555")

        setup_win.configure(bg=bg_color)

        title_label = tk.Label(
            setup_win,
            text="Initial AI Configuration",
            font=("DejaVu Sans", 13, "bold"),
            fg=accent_color,
            bg=bg_color,
        )
        title_label.pack(pady=(20, 10))

        desc_text = "To use the local AI tools, the following dependencies need to be installed:\n\n"
        for dep in missing:
            desc_text += f" • {dep}\n"
        desc_text += "\nWould you like to install them automatically now?"

        desc_label = tk.Label(
            setup_win,
            text=desc_text,
            font=("DejaVu Sans", 10),
            fg=fg_color,
            bg=bg_color,
            justify=tk.LEFT,
            wraplength=460,
        )
        desc_label.pack(padx=20, pady=10, anchor="w")

        progress_label = tk.Label(
            setup_win,
            text="",
            font=("DejaVu Sans", 9, "italic"),
            fg=fg_dim,
            bg=bg_color,
        )
        progress_label.pack(fill=tk.X, padx=20, pady=(5, 2))

        progress_bar = ttk.Progressbar(
            setup_win, orient="horizontal", mode="determinate", maximum=100
        )
        progress_bar.pack(fill=tk.X, padx=20, pady=(0, 20))

        button_frame = tk.Frame(setup_win, bg=bg_color)
        button_frame.pack(fill=tk.X, padx=20, pady=5)

        install_btn = tk.Button(
            button_frame,
            text="Install Dependencies",
            font=("DejaVu Sans", 10, "bold"),
            bg=accent_color,
            fg=bg_color,
            activebackground=sash_color,
            activeforeground=fg_color,
            bd=0,
            padx=15,
            pady=5,
            command=lambda: start_installation(),
        )
        install_btn.pack(side=tk.RIGHT)

        installation_in_progress = {"active": False}

        def on_close():
            if installation_in_progress["active"]:
                messagebox.showwarning(
                    "Installation in Progress",
                    "Dependencies are being installed. Please wait until the process finishes.",
                )
                return
            if messagebox.askyesno(
                "Exit",
                "Are you sure you want to exit? The editor requires these dependencies to continue.",
            ):
                setup_win.destroy()
                self.root.destroy()
                sys.exit(0)

        setup_win.protocol("WM_DELETE_WINDOW", on_close)

        def start_installation():
            import tempfile
            import threading

            installation_in_progress["active"] = True
            install_btn.config(state="disabled")
            progress_bar.config(mode="indeterminate")
            progress_bar.start(10)
            progress_label.config(
                text="Installing dependencies... This may take a moment."
            )

            def install_thread():
                import importlib
                import os
                import subprocess
                import sys

                from src.utils import get_python_executable

                python_exe = get_python_executable()
                try:
                    custom_env = os.environ.copy()
                    temp_dir = tempfile.mkdtemp(prefix="lithium_pip_")
                    custom_env["TEMP"] = temp_dir
                    custom_env["TMP"] = temp_dir

                    for dep in missing:
                        self.root.after(
                            0,
                            lambda d=dep: progress_label.config(
                                text=f"Installing {d}..."
                            ),
                        )

                        process = subprocess.Popen(
                            [python_exe, "-m", "pip", "install", dep],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            env=custom_env,
                            creationflags=subprocess.CREATE_NO_WINDOW
                            if sys.platform == "win32"
                            else 0,
                        )

                        while True:
                            line = process.stdout.readline()
                            if not line:
                                break
                            if (
                                "Building wheel" in line
                                or "pyproject.toml" in line
                                or "Building wheels" in line
                            ):
                                self.root.after(
                                    0,
                                    lambda: progress_label.config(
                                        text="Building llama-cpp-python. Please wait..."
                                    ),
                                )

                        process.wait()
                        if process.returncode != 0:
                            raise subprocess.CalledProcessError(
                                process.returncode, process.args
                            )

                    importlib.invalidate_caches()
                    self.root.after(0, finish_success)
                except Exception as e:
                    err_msg = str(e)
                    self.root.after(0, lambda: finish_error(err_msg))

            threading.Thread(target=install_thread, daemon=True).start()

        def finish_success():
            installation_in_progress["active"] = False
            progress_bar.stop()
            progress_bar.config(mode="determinate", value=100)
            progress_label.config(text="Installation completed successfully!")
            prepare_frozen_python_runtime()
            messagebox.showinfo(
                "Setup Complete",
                "All dependencies have been installed successfully. Starting Lithium IDE.",
            )
            setup_win.destroy()

        def is_long_paths_enabled():
            import winreg

            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\FileSystem",
                ) as key:
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
                    "-Command \"Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem' -Name 'LongPathsEnabled' -Value 1\"",
                    None,
                    1,
                )
                return True
            except Exception:
                return False

        def finish_error(err_msg):
            installation_in_progress["active"] = False
            progress_bar.stop()
            progress_bar.config(mode="determinate", value=0)
            progress_label.config(text="Error during installation.")

            import sys

            if sys.platform == "win32" and not is_long_paths_enabled():
                if messagebox.askyesno(
                    "Long Paths Required",
                    "The installation of llama-cpp-python failed due to the Windows character limit (MAX_PATH).\n\n"
                    "Would you like Lithium to try enabling long paths automatically? (Requires administrator permissions and a confirmation prompt will appear).",
                ):
                    if enable_windows_long_paths():
                        messagebox.showinfo(
                            "Request Sent",
                            "The activation has been requested. Once the Windows permission (UAC) is accepted, restart the IDE and try the installation again.",
                        )
                        setup_win.destroy()
                        self.root.destroy()
                        sys.exit(0)
                    else:
                        messagebox.showerror(
                            "Error", "Could not request automatic activation."
                        )

            messagebox.showerror(
                "Installation Error",
                f"An error occurred while installing dependencies:\n\n{err_msg}\n\nPlease try manually with: pip install {' '.join(missing)}",
            )
            install_btn.config(state="normal")

        setup_win.transient(self.root)
        setup_win.grab_set()
        self.root.wait_window(setup_win)
        self._enable_root()
        if not self._get_missing_dependencies():
            self._finish_dependency_setup()

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
            if hasattr(self, "file_explorer") and self.file_explorer:
                return self.file_explorer.current_folder
            return None

        def status_update(message):
            self.root.after(
                0, lambda: self.status_label.config(text=f"AI Skills: {message}")
            )

        try:
            self.ai_skills_executor = get_ai_skills_executor(
                editor_getter=get_editor_content,
                editor_setter=set_editor_content,
                file_path_getter=get_file_path,
                project_folder_getter=get_project_folder,
                status_callback=status_update,
            )
            self._refresh_ai_system_prompt()
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
        has_file_opened = self.controller.file_path is not None
        if not has_file_opened:
            messagebox.showwarning(
                "AI", "You must open a file from the explorer before using AI features."
            )
            return

        message = self.chat_input.get("1.0", tk.END).strip()
        if not message:
            return

        # Hide any pending approval bar when starting a new request
        self._hide_approval_bar()

        self.chat_input.delete("1.0", tk.END)
        self.append_to_chat_history("You", message)

        if not self.conversation_manager.current_conversation:
            self.conversation_manager.create_conversation("New Conversation")
            self.refresh_conversations_list()

        if self.conversation_manager.current_conversation:
            self.conversation_manager.current_conversation.add_message("user", message)
            self.conversation_manager.save_conversation()

        threading.Thread(target=self.run_chat_ai, args=(message,), daemon=True).start()

    def _build_ai_editor_prompt(self, user_message):
        """Build an AI prompt that includes the current file content with line numbers.

        The AI needs this context so it can decide whether it must delete, replace,
        or add lines before proposing changes. Without the numbered file snapshot,
        the model tends to append code blindly instead of repairing invalid code.
        """
        file_path = self.controller.file_path or "Untitled"
        language = self.selected_lang.get()
        content = self.editor.get("1.0", "end-1c")
        numbered_lines = content.splitlines()

        if numbered_lines:
            numbered_content = "\n".join(
                f"{line_number}: {line}"
                for line_number, line in enumerate(numbered_lines, start=1)
            )
        else:
            numbered_content = "(empty file)"

        workspace_section = ""
        if self.ai_skill_settings.is_workspace_scope():
            project_files = self._collect_workspace_files()
            if project_files:
                file_list = "\n".join(f"- {path}" for path in project_files)
                workspace_section = f"""
Project scope: you may modify files anywhere under the opened folder tree.
Project files (relative paths):
{file_list}
"""
            else:
                workspace_section = """
Project scope: you may modify files anywhere under the opened folder tree.
"""

        reasoning_instruction = ""
        if self.ai_skill_settings.get("reasoning"):
            reasoning_instruction = (
                "IMPORTANT: You MUST reason step by step about what the user needs "
                "BEFORE emitting any skill XML. Put your reasoning inside <think>...</think> "
                "XML tags, and keep them BEFORE any <skill> blocks.\n"
                "Example:\n"
                "<think>The user wants to add error handling. I need to wrap the main logic in a try/except block.</think>\n"
                '<skill name="edit_lines">...</skill>\n'
                "This is REQUIRED - you MUST include a <think> section before the <skill> blocks.\n"
            )

        if self.ai_skill_settings.get("explain_actions"):
            edit_output_rule = (
                "- If the user request requires editing, use one or more <skill ...> XML blocks.\n"
                "- You may include a brief explanation of what you are doing."
            )
        else:
            if self.ai_skill_settings.get("reasoning"):
                # When reasoning is active, explicitly allow <think> tags before skill blocks
                edit_output_rule = (
                    "- If the user request requires editing the file, you MUST respond with "
                    "one or more <skill ...> XML blocks.\n"
                    "- CRITICAL: You MUST include a <think>...</think> section with your "
                    "step-by-step reasoning BEFORE the <skill> blocks.\n"
                    "- Do NOT explain what XML tags are.\n"
                    '- Do NOT say "propose the changes".\n'
                    "- Do NOT describe the changes in prose instead of using skills."
                )
            else:
                edit_output_rule = (
                    "- If the user request requires editing the file, respond ONLY with one or more <skill ...> XML blocks.\n"
                    "- Do NOT explain what XML tags are.\n"
                    '- Do NOT say "propose the changes".\n'
                    "- Do NOT describe the changes in prose instead of using skills."
                )

        scope_rule = (
            "- All modifications must target only the currently open file and must be expressed with skill XML tags so the user can approve them."
            if not self.ai_skill_settings.is_workspace_scope()
            else "- Modifications may target the open file or other files under the opened project folder using the appropriate skill XML tags."
        )

        return f"""TASK
User request:
{user_message}

Current file path: {file_path}
Current language: {language}

Current open file content with line numbers:
```text
{numbered_content}
```
{workspace_section}
OUTPUT CONTRACT
{reasoning_instruction}{edit_output_rule}
- If the current content would make the final file invalid, first emit delete_lines for the invalid/unrelated lines, then emit add_lines with the corrected code.
- If the whole file is invalid or contains unrelated text, use replace_file to replace the entire file content.
- Do not just append code if existing text/code would prevent compilation.
{scope_rule}

For example, if line 1 is invalid plain text and the user asks for Python hello world, respond exactly like this:
<skill name="delete_lines"><parameter name="line">1</parameter><parameter name="count">1</parameter></skill>
<skill name="add_lines"><parameter name="line">1</parameter><parameter name="content">print("Hello, world!")</parameter></skill>
"""

    def _looks_like_broken_ai_edit_response(self, response):
        """Detect meta/prompt-leak responses that cannot drive Lithium skills."""
        if not response or "<skill" in response.lower():
            return False
        broken_markers = (
            "xml tags must be well-formed",
            "contain all necessary parameters",
            "propose the changes",
            "current file content is invalid",
            "output contract",
            "respond only with one or more",
        )
        lowered = response.lower()
        return any(marker in lowered for marker in broken_markers)

    def _retry_if_broken_ai_edit_response(
        self, original_user_message, editor_prompt, response
    ):
        """Retry once when the model echoes instructions instead of emitting skills."""
        if not self._looks_like_broken_ai_edit_response(response):
            return response

        repair_prompt = f"""The previous answer was invalid because it was meta-instruction text, not executable Lithium skill XML.

Previous invalid answer:
```text
{response}
```

Original user request:
{original_user_message}

Return ONLY the corrected <skill> blocks needed for the current open file. No prose, no explanation.

{editor_prompt}
"""
        try:
            repaired = ai_runner.generate_text_from_model(
                self.ai_model_link,
                self.ai_system_prompt
                + "\nYour next answer must be only valid <skill> XML blocks for Lithium.",
                repair_prompt,
                **self.ai_inference_params,
            )
            if repaired and not self._looks_like_broken_ai_edit_response(repaired):
                return repaired
        except Exception:
            pass

        return response

    def _retry_rejected_ai(self):
        """Re-run the AI when the user rejects its proposed changes."""
        if not self._pending_retry_info:
            return

        original_prompt, retry_count = self._pending_retry_info
        max_retries = 3

        if retry_count >= max_retries:
            self.append_to_chat_history(
                "System",
                f"Rejected {max_retries} times. Please rephrase your request.",
            )
            self._pending_retry_info = None
            return

        self._pending_retry_info = (original_prompt, retry_count + 1)

        retry_hints = {
            0: "The user rejected your answer. Write COMPLETE, production-ready code — no skeletons, no placeholders, no stubs. Build it fully.",
            1: "Still rejected. Your approach was probably too simplistic. Implement the full feature with proper error handling, all callbacks, and a polished UI.",
            2: "Last attempt. Be thorough — write the entire implementation end-to-end. Include every button, every handler, every layout detail.",
        }
        hint = retry_hints.get(
            retry_count,
            "The user rejected your suggestion. Try a completely different approach.",
        )

        retry_instruction = f"""

IMPORTANT: The user REJECTED your previous suggestion. Do NOT repeat what you just proposed.
{hint}
"""
        retry_prompt = original_prompt + retry_instruction
        threading.Thread(
            target=self.run_chat_ai,
            args=(retry_prompt,),
            kwargs={"is_retry": True},
            daemon=True,
        ).start()

    @staticmethod
    def _extract_reasoning(response: str):
        """Extract reasoning content from a model response.

        Looks for <think>...</think> or <reasoning>...</reasoning> tags
        and returns (reasoning_text, cleaned_response).
        If the entire response is reasoning, both values hold the content.

        As a fallback, if the response starts with narrative text before any
        skill XML tag, that narrative is treated as implicit reasoning.
        """
        import re

        def _try_extract(pattern, text):
            match = pattern.search(text)
            if match:
                reasoning = match.group(1).strip()
                cleaned = pattern.sub("", text).strip()
                if not cleaned and reasoning:
                    return reasoning, reasoning
                return reasoning, cleaned
            return None, text

        # Try <think>...</think> (used by DeepSeek R1, QwQ, etc.)
        pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
        reasoning, cleaned = _try_extract(pattern, response)
        if reasoning is not None:
            return reasoning, cleaned

        # Try <reasoning>...</reasoning> (generic fallback)
        pattern2 = re.compile(
            r"<reasoning>(.*?)</reasoning>", re.DOTALL | re.IGNORECASE
        )
        reasoning, cleaned = _try_extract(pattern2, response)
        if reasoning is not None:
            return reasoning, cleaned

        # Fallback 1: narrative text before the first <skill tag is implicit reasoning
        skill_start = re.search(r"\<skill\b", response, re.IGNORECASE)
        if skill_start and skill_start.start() > 0:
            before_skill = response[: skill_start.start()].strip()
            if before_skill:
                # Only treat as reasoning if it looks analytical (multiple sentences/thoughts)
                word_count = len(before_skill.split())
                if word_count >= 5 and (
                    before_skill.count(".") >= 1 or "\n" in before_skill
                ):
                    return before_skill, response[skill_start.start() :].strip()

        # Fallback 2: narrative text before the first markdown code block
        code_block_start = re.search(r"```\w*", response)
        if code_block_start and code_block_start.start() > 0:
            before_code = response[: code_block_start.start()].strip()
            if before_code:
                word_count = len(before_code.split())
                if word_count >= 5 and (
                    before_code.count(".") >= 1 or "\n" in before_code
                ):
                    return before_code, response[code_block_start.start() :].strip()

        # Fallback 3: if the entire response is just one line of short text, it's not reasoning
        return None, response

    def _can_stream(self):
        """Check if streaming generation is possible with current setup."""
        if not getattr(self, "ai_model_link", None):
            return False
        if not self.ai_skill_settings.get("reasoning"):
            return False
        # Check if it's a GGUF model (llama.cpp supports streaming)
        try:
            resolved = ai_runner.resolve_model_source(self.ai_model_link)
            if not resolved:
                return False
            gguf_path = ai_runner._find_gguf_path(resolved)
            if not gguf_path:
                return False
            # Verify llama-cpp is available
            Llama = ai_runner._safe_import_llama_cpp()
            return Llama is not None
        except Exception:
            return False

    def _stream_ai_response(self, prompt):
        """Run AI with streaming, showing reasoning tokens in real-time."""
        self.root.after(0, lambda: self.status_label.config(text="AI: Reasoning..."))

        # Show the standard loading indicator immediately so there's visual feedback
        # NOTE: Must use root.after() because we're in a worker thread
        self.root.after(0, self._show_loading_indicator)

        editor_prompt = self._build_ai_editor_prompt(prompt)
        inference_params = dict(self.ai_inference_params)
        base_tokens = inference_params.get("max_tokens", 768)
        inference_params["max_tokens"] = int(base_tokens * 1.35)

        # Shared state between threads
        state = {
            "full_buffer": "",
            "reasoning": "",
            "response": "",
            "has_think_tag": False,
            "reasoning_done": False,
            "done": False,
            "error": None,
        }
        state_lock = threading.Lock()

        # --- Create reasoning widget only when <think> is first detected ---
        reasoning_created = [False]

        def create_reasoning_widget():
            """Create the collapsible '💭 Show reasoning' live widget (main thread)."""
            if reasoning_created[0]:
                return
            reasoning_created[0] = True

            self.chat_history.config(state=tk.NORMAL)
            bg = theme.COLORS.get("bg_editor", "#080808")
            bg_dark = theme.COLORS.get("bg_dark", "#000000")
            fg_dim = theme.COLORS.get("fg_dim", "#7D8794")
            accent = theme.COLORS.get("accent", "#cba6f7")

            frame = tk.Frame(self.chat_history, bg=bg)

            # Toggle state: collapsed by default
            visible = [False]

            widget = tk.Text(
                frame,
                wrap=tk.WORD,
                font=("DejaVu Sans", 9),
                fg=fg_dim,
                bg=bg_dark,
                bd=0,
                highlightthickness=0,
                height=3,
                padx=8,
                pady=4,
                relief=tk.FLAT,
            )
            # Start hidden

            def toggle_reasoning():
                if visible[0]:
                    widget.pack_forget()
                    toggle_btn.config(text="💭 Show reasoning")
                else:
                    widget.pack(fill=tk.X, padx=2, pady=(2, 6))
                    toggle_btn.config(text="💭 Hide reasoning")
                    # Auto-scroll to show latest tokens
                    try:
                        widget.see(tk.END)
                    except Exception:
                        pass
                visible[0] = not visible[0]

            toggle_btn = tk.Button(
                frame,
                text="💭 Show reasoning",
                font=("DejaVu Sans", 9),
                fg=fg_dim,
                bg=bg,
                bd=0,
                activebackground=bg_dark,
                activeforeground=accent,
                cursor="hand2",
                command=toggle_reasoning,
                anchor=tk.W,
                padx=4,
                pady=2,
            )
            toggle_btn.pack(fill=tk.X)

            self.chat_history.window_create(tk.END, window=frame)
            self.chat_history.insert(tk.END, "\n")
            self.chat_history.see(tk.END)
            self.chat_history.config(state=tk.DISABLED)

            self._stream_reasoning_widget = widget
            self._stream_reasoning_frame = frame
            self._stream_reasoning_visible = visible
            self._stream_reasoning_toggle = toggle_btn

        auto_expanded = [False]

        def update_reasoning_widget(text):
            """Update the reasoning widget content (main thread)."""
            if not reasoning_created[0]:
                return
            try:
                w = self._stream_reasoning_widget
                # Auto-expand the first time reasoning content arrives
                if (
                    not auto_expanded[0]
                    and hasattr(self, "_stream_reasoning_visible")
                    and self._stream_reasoning_visible
                ):
                    visible = self._stream_reasoning_visible
                    if not visible[0]:
                        # Programmatically expand
                        if hasattr(self, "_stream_reasoning_toggle"):
                            self._stream_reasoning_toggle.invoke()
                    auto_expanded[0] = True

                w.config(state=tk.NORMAL)
                w.delete("1.0", tk.END)
                w.insert("1.0", text)
                w.config(state=tk.DISABLED)
                w.see(tk.END)
                lines = text.count("\n") + 1
                w.config(height=min(max(lines, 3), 15))
            except Exception:
                pass

        # --- Periodic UI update (main thread) ---
        def poll_ui():
            with state_lock:
                if state["error"]:
                    self._remove_loading_indicator()
                    self._cleanup_stream_ui()
                    self.status_label.config(text="AI: Error")
                    self.append_to_chat_history(
                        "Error", f"Could not generate response: {state['error']}"
                    )
                    return

                reasoning = state["reasoning"]
                done = state["done"]

            # Create reasoning widget on first detection of <think>
            if reasoning and not reasoning_created[0]:
                self.root.after(0, create_reasoning_widget)

            # Live-update reasoning widget
            if reasoning and reasoning_created[0]:
                update_reasoning_widget(reasoning)

            if not done:
                self.root.after(100, poll_ui)
            else:
                self._finalize_stream_response(state, state_lock)

        # --- Streaming thread ---
        def streaming_worker():
            try:
                gen = ai_runner.stream_generate_text(
                    self.ai_model_link,
                    self.ai_system_prompt,
                    editor_prompt,
                    **inference_params,
                )
                for token in gen:
                    with state_lock:
                        state["full_buffer"] += token
                        self._update_stream_state_from_buffer(state)

                with state_lock:
                    state["done"] = True
            except Exception as e:
                with state_lock:
                    state["error"] = str(e)
                    state["done"] = True

        # Start polling & streaming
        self.root.after(100, poll_ui)
        threading.Thread(target=streaming_worker, daemon=True).start()

    def _update_stream_state_from_buffer(self, state):
        """Parse the full buffer to extract reasoning/response state.

        Called with state_lock held.
        """
        buf = state["full_buffer"]

        if "</think>" in buf:
            # Reasoning complete
            parts = buf.split("</think>", 1)
            before_close = parts[0]
            state["response"] = parts[1]
            state["reasoning_done"] = True
            # Extract reasoning content
            if "<think>" in before_close:
                _, reasoning = before_close.split("<think>", 1)
                state["reasoning"] = reasoning
            else:
                state["reasoning"] = before_close
            state["has_think_tag"] = True
        elif "<think>" in buf:
            # Inside reasoning
            parts = buf.split("<think>", 1)
            state["reasoning"] = parts[1]
            state["has_think_tag"] = True
            # Text before <think> is pre-reasoning response
            before = parts[0].strip()
            if before:
                state["response"] = before
        else:
            # No reasoning tags yet
            state["reasoning_done"] = False
            state["reasoning"] = ""
            state["response"] = buf

    def _finalize_stream_response(self, state, state_lock):
        """Called when streaming is done — process skills and finalize UI."""
        with state_lock:
            reasoning_text = state["reasoning"]
            full_response = state["response"]
            full_buffer = state["full_buffer"]
            error = state["error"]

        self._remove_loading_indicator()
        self._cleanup_stream_ui()

        if error:
            self.status_label.config(text="AI: Error")
            self.append_to_chat_history(
                "Error", f"Could not generate response: {error}"
            )
            return

        # Post-processing fallback: if streaming didn't detect <think> tags,
        # try the same extraction logic used by the non-streaming path
        if not reasoning_text:
            reasoning_text, full_response = self._extract_reasoning(full_buffer)

        # If response is empty but reasoning has content, show reasoning as response
        if not full_response.strip() and reasoning_text:
            full_response = reasoning_text
            reasoning_text = ""

        # Process skills (same as non-streaming path)
        skill_results = []
        pending_approvals = []
        clean_response = full_response
        if self.ai_skills_executor:
            try:
                skill_results = self.ai_skills_executor.parse_for_preview(full_response)
                clean_response = self.ai_skills_executor.get_clean_response(
                    full_response
                )
                for i, (sn, result) in enumerate(skill_results):
                    if result.requires_approval and result.success:
                        pending_approvals.append((i, sn, result))
            except Exception as skill_err:
                print(f"Warning: Error processing AI skills: {skill_err}")

        # Save original content before applying any changes
        original_content = self.editor.get("1.0", tk.END) if pending_approvals else None

        # Apply ALL pending skills immediately (no per-skill approval)
        if pending_approvals and self.ai_skills_executor:
            for idx, sn, result in pending_approvals:
                apply_result = self.ai_skills_executor.apply_skill(sn, result)
                skill_results[idx] = (sn, apply_result)

        # Save to conversation
        if self.conversation_manager.current_conversation and clean_response.strip():
            metadata = {}
            if reasoning_text:
                metadata["reasoning"] = reasoning_text
            self.conversation_manager.current_conversation.add_message(
                "assistant", clean_response, metadata=metadata
            )
            self.conversation_manager.save_conversation()

        # Show skill results in chat
        for sn, result in skill_results:
            icon = "✓" if result.success else "✗"
            self.append_to_chat_history("Skill", f"{icon} {result.message}")

        if clean_response.strip():
            self.append_to_chat_history("AI", clean_response, reasoning=reasoning_text)

        # Show unified approval bar if there were editor changes
        if original_content is not None:
            new_content = self.editor.get("1.0", tk.END)
            added, removed = self._compute_diff_stats(original_content, new_content)
            if added > 0 or removed > 0:
                self._show_approval_bar(original_content, new_content, added, removed)
            else:
                # No actual changes detected, clean up
                self._original_content_before_ai = None

        self.status_label.config(text="AI: Ready")
        self._notify_ai_task_complete()
        self.refresh_conversations_list()

    def _cleanup_stream_ui(self):
        """Remove streaming UI widgets."""
        for attr in (
            "_stream_reasoning_widget",
            "_stream_reasoning_frame",
            "_stream_reasoning_toggle",
        ):
            if hasattr(self, attr):
                try:
                    obj = getattr(self, attr)
                    if obj and obj.winfo_exists():
                        obj.destroy()
                except Exception:
                    pass
                delattr(self, attr)
        for attr in ("_stream_reasoning_visible",):
            if hasattr(self, attr):
                delattr(self, attr)

    def run_chat_ai(self, prompt, is_retry=False):
        # Use streaming path when reasoning skill is active and possible
        if not is_retry and self._can_stream():
            try:
                self._stream_ai_response(prompt)
                return
            except Exception as stream_err:
                print(f"Streaming failed, falling back to normal mode: {stream_err}")
                self._cleanup_stream_ui()
                # Fall through to non-streaming path

        self.root.after(0, lambda: self.status_label.config(text="AI: Loading..."))

        # NOTE: Must use root.after() because we're in a worker thread
        self.root.after(0, self._show_loading_indicator)

        if not is_retry:
            self._pending_retry_info = (prompt, 0)

        try:
            editor_prompt = self._build_ai_editor_prompt(prompt)
            inference_params = dict(self.ai_inference_params)
            if self.ai_skill_settings.get("reasoning"):
                base_tokens = inference_params.get("max_tokens", 768)
                inference_params["max_tokens"] = int(base_tokens * 1.35)

            max_attempts = 2
            last_error = None
            response = ""
            for attempt in range(max_attempts):
                try:
                    response = ai_runner.generate_text_from_model(
                        self.ai_model_link,
                        self.ai_system_prompt,
                        editor_prompt,
                        **inference_params,
                    )
                    if response and response.strip():
                        break
                except Exception as e:
                    last_error = e
                    print(
                        f"AI generation attempt {attempt + 1}/{max_attempts} failed: {e}"
                    )
                    # Reduce temperature on retry for better chance
                    inference_params["temperature"] = max(
                        0.1, inference_params.get("temperature", 0.5) - 0.2
                    )

            if not response or not response.strip():
                if last_error:
                    raise RuntimeError(
                        f"Model returned no valid response after {max_attempts} attempts: {last_error}"
                    )
                raise RuntimeError(
                    f"Model returned empty response after {max_attempts} attempts"
                )

            response = self._retry_if_broken_ai_edit_response(
                prompt, editor_prompt, response
            )

            # Extract reasoning before skill processing
            reasoning_text, response_no_reasoning = self._extract_reasoning(response)

            # Schedule removal on main thread (we're in a worker thread)
            self.root.after(0, self._remove_loading_indicator)

            skill_results = []
            pending_approvals = []
            clean_response = response_no_reasoning
            if self.ai_skills_executor:
                try:
                    skill_results = self.ai_skills_executor.parse_for_preview(
                        response_no_reasoning
                    )
                    clean_response = self.ai_skills_executor.get_clean_response(
                        response_no_reasoning
                    )

                    for i, (skill_name, result) in enumerate(skill_results):
                        if result.requires_approval and result.success:
                            pending_approvals.append((i, skill_name, result))
                except Exception as skill_err:
                    print(f"Warning: Error processing AI skills: {skill_err}")

            # Save original content before applying any changes
            original_content = (
                self.editor.get("1.0", tk.END) if pending_approvals else None
            )

            # Apply ALL pending skills immediately (no per-skill approval)
            if pending_approvals and self.ai_skills_executor:
                for result_idx, skill_name, result in pending_approvals:
                    apply_result = self.ai_skills_executor.apply_skill(
                        skill_name, result
                    )
                    skill_results[result_idx] = (skill_name, apply_result)

            def show_response():
                if (
                    self.conversation_manager.current_conversation
                    and clean_response.strip()
                ):
                    metadata = {}
                    if reasoning_text:
                        metadata["reasoning"] = reasoning_text
                    self.conversation_manager.current_conversation.add_message(
                        "assistant", clean_response, metadata=metadata
                    )
                    self.conversation_manager.save_conversation()

                for skill_name, result in skill_results:
                    status_icon = "✓" if result.success else "✗"
                    self.append_to_chat_history(
                        "Skill", f"{status_icon} {result.message}"
                    )

                if clean_response.strip():
                    self.append_to_chat_history(
                        "AI", clean_response, reasoning=reasoning_text
                    )

                # Show unified approval bar if there were editor changes
                if original_content is not None:
                    new_content = self.editor.get("1.0", tk.END)
                    added, removed = self._compute_diff_stats(
                        original_content, new_content
                    )
                    if added > 0 or removed > 0:
                        self._show_approval_bar(
                            original_content, new_content, added, removed
                        )
                    else:
                        self._original_content_before_ai = None

                self.status_label.config(text="AI: Ready")
                self._notify_ai_task_complete()
                self.refresh_conversations_list()

            self.root.after(0, show_response)
        except Exception as exc:
            # Schedule removal on main thread (we're in a worker thread)
            self.root.after(0, self._remove_loading_indicator)
            err_msg = str(exc)
            self.root.after(
                0,
                lambda: self.append_to_chat_history(
                    "Error", f"Could not generate response: {err_msg}"
                ),
            )
            self.root.after(0, lambda: self.status_label.config(text="AI: Error"))

    def _show_loading_indicator(self):
        """Show a minimal monochrome loader while the AI generates a response."""
        self.chat_history.config(state=tk.NORMAL)

        bg = theme.COLORS.get("bg_editor", "#080808")
        fg_dim = theme.COLORS.get("fg_dim", "#7D8794")

        self._loading_frame = tk.Frame(self.chat_history, bg=bg)
        row = tk.Frame(self._loading_frame, bg=bg, padx=8, pady=6)
        row.pack(anchor=tk.W, padx=6, pady=4)

        self._loader_status_label = tk.Label(
            row,
            text="Thinking",
            font=("DejaVu Sans", 9),
            fg=fg_dim,
            bg=bg,
        )
        self._loader_status_label.pack(side=tk.LEFT)

        self._loader_canvas = tk.Canvas(
            row,
            width=28,
            height=14,
            bg=bg,
            highlightthickness=0,
            bd=0,
        )
        self._loader_canvas.pack(side=tk.LEFT, padx=(4, 0))

        self.chat_history.window_create(tk.END, window=self._loading_frame)
        self.chat_history.insert(tk.END, "\n")
        self.chat_history.see(tk.END)
        self.chat_history.config(state=tk.DISABLED)

        self._loader_tick = 0
        self._loader_animating = True
        self._loader_after_id = None
        self._animate_loader()

    def _animate_loader(self):
        if not getattr(self, "_loader_animating", False):
            return
        if not hasattr(self, "_loader_canvas"):
            return

        fg_dim = theme.COLORS.get("fg_dim", "#7D8794")
        fg = theme.COLORS.get("fg_light", "#FFFFFF")
        active = (self._loader_tick // 6) % 3

        canvas = self._loader_canvas
        canvas.delete("all")
        for index in range(3):
            x = 6 + index * 9
            color = fg if index == active else fg_dim
            canvas.create_oval(x - 2, 5, x + 2, 9, fill=color, outline="")

        self._loader_tick += 1
        self._loader_after_id = self.root.after(120, self._animate_loader)

    def _remove_loading_indicator(self):
        """Remove the loading indicator from chat."""
        self._loader_animating = False

        if getattr(self, "_loader_after_id", None):
            try:
                self.root.after_cancel(self._loader_after_id)
            except Exception:
                pass
            self._loader_after_id = None

        if hasattr(self, "_loading_frame"):
            try:
                self._loading_frame.destroy()
            except Exception:
                pass
            del self._loading_frame

        for attr in ("_loader_canvas", "_loader_status_label"):
            if hasattr(self, attr):
                delattr(self, attr)

    def _show_approval_dialog(
        self, index, pending_approvals, all_results, clean_response, reasoning=None
    ):
        """Show approval dialog inline in the chat for pending skill changes."""
        if index >= len(pending_approvals):
            self.chat_history.config(state=tk.NORMAL)
            self.chat_history.insert(tk.END, "\n" + "=" * 50 + "\n")
            for skill_name, result in all_results:
                status_icon = "✓" if result.success else "✗"
                color = (
                    theme.COLORS.get("success", "#4ade80")
                    if result.success
                    else theme.COLORS.get("error", "#f87171")
                )
                self.chat_history.insert(
                    tk.END,
                    f"Skill:  {status_icon} Changes applied\n",
                    ("skill_result",),
                )
                self.chat_history.tag_config(
                    "skill_result", foreground=color, font=("DejaVu Sans", 9, "bold")
                )

            if clean_response.strip():
                self.chat_history.insert(tk.END, "\n")
                self.append_to_chat_history("AI", clean_response, reasoning=reasoning)

            self.chat_history.see(tk.END)
            self.chat_history.config(state=tk.DISABLED)
            self.status_label.config(text="AI: Ready")
            self._notify_ai_task_complete()
            return

        result_idx, skill_name, result = pending_approvals[index]
        data = result.data or {}

        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.insert(tk.END, "\n")

        title = f"⚡ **AI wants to: {result.message}**"
        if len(pending_approvals) > 1:
            title += f" _(Change {index + 1} of {len(pending_approvals)})_"

        self.chat_history.insert(tk.END, title + "\n\n", ("approval_title",))
        self.chat_history.tag_config(
            "approval_title",
            foreground=theme.COLORS.get("accent", "#7C9EFF"),
            font=("DejaVu Sans", 10, "bold"),
        )

        if skill_name in ("delete_lines", "remove_lines"):
            if "original_content" in data and "new_content" in data:
                original = data.get("original_content", "")
                new = data.get("new_content", "")
                original_lines = original.splitlines()
                new_lines = new.splitlines()

                self.chat_history.insert(
                    tk.END, "📝 Lines will be removed from the editor.\n"
                )
                self.chat_history.insert(
                    tk.END,
                    f"Current lines: {len(original_lines)} → After deletion: {len(new_lines)}\n\n",
                    ("preview_info",),
                )
                self.chat_history.tag_config(
                    "preview_info",
                    foreground=theme.COLORS.get("fg_dim", "#8F99A6"),
                    font=("DejaVu Sans", 9),
                )
        elif skill_name in ("add_lines", "insert_lines"):
            if "new_content" in data:
                content = data.get("new_content", "").strip()
                if content:
                    lines = content.splitlines()
                    line_count = len(lines)
                    self.chat_history.insert(
                        tk.END,
                        f"➕ Will add {line_count} line(s).\n\n",
                        ("preview_info",),
                    )
                    self.chat_history.tag_config(
                        "preview_info",
                        foreground=theme.COLORS.get("fg_dim", "#8F99A6"),
                        font=("DejaVu Sans", 9),
                    )

                    self.chat_history.insert(tk.END, "```python\n", ("code_header",))
                    self.chat_history.insert(
                        tk.END, content + "\n", ("code_block_tag",)
                    )
                    self.chat_history.insert(tk.END, "```\n\n", ("code_header",))
                    self.chat_history.tag_config(
                        "code_header", foreground=theme.COLORS.get("fg_dim", "#8F99A6")
                    )
                    self.chat_history.tag_config(
                        "code_block_tag",
                        background=theme.COLORS.get("bg_header", "#111519"),
                        foreground=theme.COLORS.get("console_fg", "#D8DEE9"),
                        font=("DejaVu Sans Mono", 10),
                    )
        elif skill_name == "replace_file":
            if "content" in data:
                self.chat_history.insert(
                    tk.END,
                    "🔄 Will replace entire file content.\n\n",
                    ("preview_info",),
                )
                self.chat_history.tag_config(
                    "preview_info",
                    foreground=theme.COLORS.get("fg_dim", "#8F99A6"),
                    font=("DejaVu Sans", 9),
                )

        self._show_inline_approval(
            result,
            skill_name,
            result_idx,
            all_results,
            pending_approvals,
            index,
            clean_response,
        )

    def _show_inline_approval(
        self,
        result,
        skill_name,
        result_idx,
        all_results,
        pending_approvals,
        index,
        clean_response,
    ):
        """Show an inline approval request in the chat with approve/reject buttons."""

        btn_frame = tk.Frame(
            self.chat_history, bg=theme.COLORS.get("bg_dark", "#0B0D10")
        )

        def approve():
            apply_result = self.ai_skills_executor.apply_skill(skill_name, result)
            all_results[result_idx] = (skill_name, apply_result)

            for widget in btn_frame.winfo_children():
                widget.destroy()

            status_color = theme.COLORS.get("success", "#A3BE8C")
            tk.Label(
                btn_frame,
                text="✓ Changes applied",
                font=("DejaVu Sans", 9, "bold"),
                fg=status_color,
                bg=theme.COLORS.get("bg_dark", "#0B0D10"),
            ).pack(side=tk.LEFT, padx=5)

            self.root.after(
                500,
                lambda: self._show_approval_dialog(
                    index + 1, pending_approvals, all_results, clean_response
                ),
            )

        def reject():
            all_results[result_idx] = (
                skill_name,
                AISkillResult(False, f"Rejected: {result.message}"),
            )

            for widget in btn_frame.winfo_children():
                widget.destroy()

            tk.Label(
                btn_frame,
                text="✗ Rejected — retrying...",
                font=("DejaVu Sans", 9, "bold"),
                fg=theme.COLORS.get("error", "#F07178"),
                bg=theme.COLORS.get("bg_dark", "#0B0D10"),
            ).pack(side=tk.LEFT, padx=5)

            self._retry_rejected_ai()

        approve_btn = tk.Button(
            btn_frame,
            text="✓ Approve",
            font=("DejaVu Sans", 9, "bold"),
            bg=theme.COLORS.get("accent", "#7C9EFF"),
            fg=theme.COLORS.get("bg_dark", "#0B0D10"),
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=approve,
            activebackground=theme.COLORS.get("accent_hover", "#5B82D1"),
            activeforeground=theme.COLORS.get("bg_dark", "#0B0D10"),
            relief=tk.FLAT,
        )
        approve_btn.pack(side=tk.LEFT, padx=5, pady=(10, 0))

        reject_btn = tk.Button(
            btn_frame,
            text="✗ Reject",
            font=("DejaVu Sans", 9),
            bg=theme.COLORS.get("sash_color", "#1F2833"),
            fg=theme.COLORS.get("fg_light", "#E5E9F0"),
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=reject,
            activebackground=theme.COLORS.get("sash_color", "#1F2833"),
            activeforeground=theme.COLORS.get("accent", "#7C9EFF"),
            relief=tk.FLAT,
        )
        reject_btn.pack(side=tk.LEFT, padx=5, pady=(10, 0))

        self.chat_history.window_create(tk.END, window=btn_frame)
        self.chat_history.insert(tk.END, "\n")
        self.chat_history.see(tk.END)
        self.chat_history.config(state=tk.DISABLED)

    def _compute_diff_stats(self, original, new):
        """Compute added and removed line counts between two texts."""
        orig_lines = original.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)

        matcher = difflib.SequenceMatcher(None, orig_lines, new_lines)
        added = 0
        removed = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                removed += i2 - i1
                added += j2 - j1
            elif tag == "delete":
                removed += i2 - i1
            elif tag == "insert":
                added += j2 - j1
        return added, removed

    def _show_approval_bar(self, original_content, new_content, added, removed):
        """Show a unified approve/reject bar above the chat input with line diff stats."""
        if self._approval_bar is not None:
            try:
                self._approval_bar.destroy()
            except Exception:
                pass
            self._approval_bar = None

        self._original_content_before_ai = original_content

        bg = theme.COLORS.get("bg_dark", "#0B0D10")
        accent = theme.COLORS.get("accent", "#7C9EFF")
        success = theme.COLORS.get("success", "#A3BE8C")
        error = theme.COLORS.get("error", "#F07178")
        fg = theme.COLORS.get("fg_light", "#E5E9F0")
        fg_dim = theme.COLORS.get("fg_dim", "#8F99A6")

        bar = tk.Frame(
            self.chat_input_container,
            bg=bg,
            bd=1,
            relief=tk.FLAT,
            highlightbackground=theme.COLORS.get("sash_color", "#1F2833"),
            highlightthickness=1,
        )

        # Diff stats label: +N -M
        diff_label = tk.Label(
            bar,
            text=f"+{added}  −{removed}",
            font=("DejaVu Sans Mono", 11, "bold"),
            fg=success if added > 0 else error,
            bg=bg,
            padx=10,
        )
        diff_label.pack(side=tk.LEFT, padx=(10, 5), pady=6)

        # Separator
        sep = tk.Frame(bar, bg=theme.COLORS.get("sash_color", "#1F2833"), width=1)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=4)

        # Description
        desc_label = tk.Label(
            bar,
            text="AI changes:",
            font=("DejaVu Sans", 9),
            fg=fg_dim,
            bg=bg,
        )
        desc_label.pack(side=tk.LEFT, padx=(5, 5), pady=6)

        # Approve button
        approve_btn = tk.Button(
            bar,
            text="✓ Approve",
            font=("DejaVu Sans", 9, "bold"),
            bg=success,
            fg=theme.COLORS.get("bg_dark", "#0B0D10"),
            bd=0,
            padx=14,
            pady=3,
            cursor="hand2",
            command=lambda: self._on_approve_bar_approve(),
            activebackground=theme.COLORS.get("success_hover", "#8FBC7A"),
            activeforeground=theme.COLORS.get("bg_dark", "#0B0D10"),
            relief=tk.FLAT,
        )
        approve_btn.pack(side=tk.RIGHT, padx=(5, 5), pady=4)

        # Reject button
        reject_btn = tk.Button(
            bar,
            text="✗ Reject",
            font=("DejaVu Sans", 9),
            bg=theme.COLORS.get("sash_color", "#1F2833"),
            fg=fg,
            bd=0,
            padx=14,
            pady=3,
            cursor="hand2",
            command=lambda: self._on_approve_bar_reject(),
            activebackground=theme.COLORS.get("sash_color", "#1F2833"),
            activeforeground=accent,
            relief=tk.FLAT,
        )
        reject_btn.pack(side=tk.RIGHT, padx=(0, 5), pady=4)

        # Pack at the TOP of chat_input_container so it appears above everything else
        bar.pack(side=tk.TOP, fill=tk.X, padx=0, pady=(0, 5))
        bar.pack_propagate(False)
        bar.configure(height=34)

        self._approval_bar = bar

    def _hide_approval_bar(self):
        """Remove the approval bar from the chat input area."""
        if self._approval_bar is not None:
            try:
                self._approval_bar.destroy()
            except Exception:
                pass
            self._approval_bar = None
        self._original_content_before_ai = None

    def _on_approve_bar_approve(self):
        """User approved the AI changes — keep them and hide the bar."""
        self._hide_approval_bar()
        self.status_label.config(text="AI: Changes approved")

    def _on_approve_bar_reject(self):
        """User rejected the AI changes — restore original editor content."""
        if self._original_content_before_ai is not None:
            try:
                self.editor.delete("1.0", tk.END)
                self.editor.insert("1.0", self._original_content_before_ai)
                self.controller.update_line_numbers()
                self.controller.update_status()
                self.status_label.config(text="AI: Changes reverted")
            except Exception as e:
                print(f"Error reverting AI changes: {e}")
        self._hide_approval_bar()

    def _get_skill_name_from_result(self, result_idx, all_results):
        """Get skill name from result index (simplified - in real impl would track names)."""
        return "unknown"

    def append_to_chat_history(self, sender, text, reasoning=None):
        self.chat_history.config(state=tk.NORMAL)

        color = (
            theme.COLORS.get("accent", "#cba6f7")
            if sender == "AI"
            else theme.COLORS.get("fg_dim", "#a6adc8")
        )
        if sender == "Error":
            color = theme.COLORS.get("console_err", "#ff0000")

        self.chat_history.insert(tk.END, f"\n{sender}:\n", ("sender_tag_" + sender,))
        self.chat_history.tag_config(
            "sender_tag_" + sender, foreground=color, font=("DejaVu Sans", 10, "bold")
        )

        # Insert collapsible reasoning section if present
        if reasoning:
            self._insert_reasoning_section(reasoning)

        parts = text.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 1:
                lines = part.split("\n")
                lang = ""
                code_content = part
                if lines and lines[0].strip() in [
                    "python",
                    "javascript",
                    "html",
                    "css",
                    "c++",
                    "java",
                    "rust",
                    "go",
                    "json",
                    "py",
                    "js",
                ]:
                    lang = lines[0].strip()
                    code_content = "\n".join(lines[1:])

                start_index = self.chat_history.index(tk.END)
                self.chat_history.insert(tk.END, code_content, ("code_block_tag",))
                self.chat_history.tag_config(
                    "code_block_tag",
                    background=theme.COLORS.get("bg_dark", "#181825"),
                    foreground=theme.COLORS.get("fg_light", "#cdd6f4"),
                    font=theme.FONTS.get("editor", ("Consolas", 11)),
                )
                self.chat_history.insert(tk.END, "\n")
                self.code_indices[code_content] = start_index

                btn_frame = tk.Frame(
                    self.chat_history, bg=theme.COLORS.get("bg_dark", "#181825")
                )

                apply_btn = tk.Button(
                    btn_frame,
                    text="✓ Apply",
                    font=("DejaVu Sans", 9, "bold"),
                    bg=theme.COLORS.get("accent", "#cba6f7"),
                    fg=theme.COLORS.get("bg_dark", "#181825"),
                    bd=0,
                    padx=8,
                    pady=2,
                    command=lambda c=code_content: self.apply_suggested_code(c),
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
                    command=lambda c=code_content: self.open_review_window(c),
                )
                review_btn.pack(side=tk.LEFT)

                if not hasattr(self, "button_frames"):
                    self.button_frames = {}
                self.button_frames[code_content] = btn_frame

                self.chat_history.window_create(tk.END, window=btn_frame)
                self.chat_history.insert(tk.END, "\n")
            else:
                self.chat_history.insert(tk.END, part)

        # Add Reject button after AI responses (not errors, skills, or system msgs)
        if sender == "AI" and self._pending_retry_info:
            reject_frame = tk.Frame(
                self.chat_history, bg=theme.COLORS.get("bg_dark", "#0B0D10")
            )

            def reject_response():
                for widget in reject_frame.winfo_children():
                    widget.destroy()
                tk.Label(
                    reject_frame,
                    text="✗ Rejected — retrying...",
                    font=("DejaVu Sans", 9, "bold"),
                    fg=theme.COLORS.get("error", "#F07178"),
                    bg=theme.COLORS.get("bg_dark", "#0B0D10"),
                ).pack(side=tk.LEFT, padx=5)
                self._retry_rejected_ai()

            reject_btn = tk.Button(
                reject_frame,
                text="✗ Reject",
                font=("DejaVu Sans", 9),
                bd=0,
                padx=14,
                pady=4,
                cursor="hand2",
                command=reject_response,
                bg=theme.COLORS.get("sash_color", "#1F2833"),
                fg=theme.COLORS.get("fg_light", "#E5E9F0"),
                activebackground=theme.COLORS.get("sash_color", "#1F2833"),
                activeforeground=theme.COLORS.get("accent", "#7C9EFF"),
                relief=tk.FLAT,
            )
            reject_btn.pack(side=tk.LEFT, padx=5, pady=(4, 0))

            self.chat_history.window_create(tk.END, window=reject_frame)
            self.chat_history.insert(tk.END, "\n")

        self.chat_history.see(tk.END)
        self.chat_history.config(state=tk.DISABLED)

    def _insert_reasoning_section(self, reasoning_text):
        """Insert a collapsible reasoning section into the chat history."""
        bg = theme.COLORS.get("bg_editor", "#080808")
        bg_dark = theme.COLORS.get("bg_dark", "#000000")
        fg_dim = theme.COLORS.get("fg_dim", "#7D8794")
        accent = theme.COLORS.get("accent", "#cba6f7")

        frame = tk.Frame(self.chat_history, bg=bg)

        # Toggle state
        visible = [False]

        # Reasoning text widget (hidden initially)
        reasoning_widget = tk.Text(
            frame,
            wrap=tk.WORD,
            font=("DejaVu Sans", 9),
            fg=fg_dim,
            bg=bg_dark,
            bd=0,
            highlightthickness=0,
            height=min(len(reasoning_text.splitlines()) + 1, 12),
            padx=8,
            pady=6,
            relief=tk.FLAT,
        )
        reasoning_widget.insert("1.0", reasoning_text)
        reasoning_widget.config(state=tk.DISABLED)

        def toggle_reasoning():
            if visible[0]:
                reasoning_widget.pack_forget()
                toggle_btn.config(text="💭 Show reasoning")
            else:
                reasoning_widget.pack(fill=tk.X, padx=2, pady=(2, 4))
                toggle_btn.config(text="💭 Hide reasoning")
            visible[0] = not visible[0]

        toggle_btn = tk.Button(
            frame,
            text="💭 Show reasoning",
            font=("DejaVu Sans", 9),
            fg=fg_dim,
            bg=bg,
            bd=0,
            activebackground=bg_dark,
            activeforeground=accent,
            cursor="hand2",
            command=toggle_reasoning,
            anchor=tk.W,
            padx=4,
            pady=2,
        )
        toggle_btn.pack(fill=tk.X)

        self.chat_history.window_create(tk.END, window=frame)
        self.chat_history.insert(tk.END, "\n")

    def apply_suggested_code(self, code):
        try:
            if self.editor.tag_ranges(tk.SEL):
                self.editor.delete(tk.SEL_FIRST, tk.SEL_LAST)
            self.editor.insert(tk.INSERT, code)
            self.controller.update_line_numbers()
            self.controller.update_status()
            self.status_label.config(text="AI: Suggested code applied.")
            if code in getattr(self, "button_frames", {}):
                btn_frame = self.button_frames.pop(code)
                btn_frame.destroy()
            if code in getattr(self, "code_indices", {}):
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
            bg=bg_color,
        )
        title_label.pack(pady=(15, 10))

        paned = tk.PanedWindow(
            review_win,
            orient=tk.HORIZONTAL,
            bg=bg_color,
            bd=0,
            sashwidth=4,
            sashpad=1,
            sashrelief=tk.FLAT,
        )
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
        orig_label = tk.Label(
            orig_frame,
            text="Código Actual"
            + (" (Selección)" if has_selection else " (Todo el archivo)"),
            fg=theme.COLORS.get("fg_dim", "#a6adc8"),
            bg=bg_color,
            font=("Segoe UI", 9, "bold"),
        )
        orig_label.pack(fill=tk.X, anchor="w", pady=(0, 2))

        orig_scroll = ttk.Scrollbar(orig_frame)
        orig_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        orig_text = tk.Text(
            orig_frame,
            wrap=tk.NONE,
            yscrollcommand=orig_scroll.set,
            font=theme.FONTS.get("editor", ("Consolas", 11)),
            bg=theme.COLORS.get("bg_editor", "#1e1e2e"),
            fg=theme.COLORS.get("fg_light", "#cdd6f4"),
            bd=0,
            highlightthickness=0,
        )
        orig_text.pack(fill=tk.BOTH, expand=True)
        orig_scroll.config(command=orig_text.yview)
        orig_text.insert(tk.END, original_code)
        orig_text.config(state=tk.DISABLED)
        paned.add(orig_frame, minsize=200)

        sug_frame = tk.Frame(paned, bg=bg_color)
        sug_label = tk.Label(
            sug_frame,
            text="Código Sugerido",
            fg=theme.COLORS.get("accent", "#cba6f7"),
            bg=bg_color,
            font=("Segoe UI", 9, "bold"),
        )
        sug_label.pack(fill=tk.X, anchor="w", pady=(0, 2))

        sug_scroll = ttk.Scrollbar(sug_frame)
        sug_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        sug_text = tk.Text(
            sug_frame,
            wrap=tk.NONE,
            yscrollcommand=sug_scroll.set,
            font=theme.FONTS.get("editor", ("Consolas", 11)),
            bg=theme.COLORS.get("bg_editor", "#1e1e2e"),
            fg=theme.COLORS.get("fg_light", "#cdd6f4"),
            bd=0,
            highlightthickness=0,
        )
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
                if suggested_code in getattr(self, "button_frames", {}):
                    btn = self.button_frames.pop(suggested_code)
                    btn.destroy()
                if suggested_code in getattr(self, "code_indices", {}):
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
            command=approve_changes,
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
            command=review_win.destroy,
        )
        reject_btn.pack(side=tk.RIGHT, padx=5)

        review_win.wait_window(review_win)

    def show_conversations_dropdown(self):
        """Show conversations dropdown menu from the AI chat header."""
        conversations = self.conversation_manager.list_conversations()
        self._conversation_ids = [conv["id"] for conv in conversations]

        menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=theme.COLORS["bg_header"],
            fg=theme.COLORS["fg_light"],
        )

        menu.add_command(label="＋ New Conversation", command=self.new_conversation)
        menu.add_separator()

        if conversations:
            for i, conv in enumerate(conversations):
                display_text = conv["title"][:30] + (
                    "..." if len(conv["title"]) > 30 else ""
                )
                is_current = (
                    self.conversation_manager.current_conversation
                    and self.conversation_manager.current_conversation.id == conv["id"]
                )
                if is_current:
                    display_text = "✓ " + display_text
                menu.add_command(
                    label=display_text,
                    command=lambda cid=conv["id"]: self.load_conversation(cid),
                )
            menu.add_separator()

            if self.conversation_manager.current_conversation:
                current_id = self.conversation_manager.current_conversation.id
                menu.add_command(
                    label="Rename Conversation",
                    command=lambda: self.rename_conversation(current_id),
                )
                menu.add_command(
                    label="Export Conversation",
                    command=lambda: self.export_conversation(current_id),
                )
                menu.add_separator()
                menu.add_command(
                    label="Delete Conversation",
                    command=lambda: self.delete_conversation(current_id),
                )
        else:
            menu.add_command(label="No saved conversations", state=tk.DISABLED)

        x = self.conv_dropdown_btn.winfo_rootx()
        y = self.conv_dropdown_btn.winfo_rooty() + self.conv_dropdown_btn.winfo_height()
        menu.post(x, y)

    def refresh_conversations_list(self):
        """Refresh the conversation dropdown button label."""
        if self.conversation_manager.current_conversation:
            title = self.conversation_manager.current_conversation.title[:20]
            self.conv_dropdown_btn.config(text=f"💬 {title} ▾")
        else:
            self.conv_dropdown_btn.config(text="💬 No conversation ▾")

    def new_conversation(self):
        """Create a new conversation."""
        if self.conversation_manager.current_conversation:
            self.save_current_conversation_to_history()

        self.conversation_manager.create_conversation("New Conversation")

        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.delete("1.0", tk.END)
        self.chat_history.config(state=tk.DISABLED)

        self.refresh_conversations_list()

        self.append_to_chat_history("AI", "Hello! How can I help you today?")

    def load_conversation(self, conversation_id):
        """Load a conversation and display its messages."""
        if self.conversation_manager.current_conversation:
            self.save_current_conversation_to_history()

        conversation = self.conversation_manager.load_conversation(conversation_id)
        if not conversation:
            return

        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.delete("1.0", tk.END)

        for msg in conversation.messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            sender = role.capitalize()
            if role == "user":
                sender = "You"
            elif role == "assistant":
                sender = "AI"
            metadata = msg.get("metadata", {}) or {}
            reasoning = (
                metadata.get("reasoning") if isinstance(metadata, dict) else None
            )
            self.append_to_chat_history(sender, content, reasoning=reasoning)

        self.chat_history.config(state=tk.DISABLED)

        self.refresh_conversations_list()

    def save_current_conversation_to_history(self):
        """Save the current chat history to the conversation."""
        if not self.conversation_manager.current_conversation:
            return

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
            bg=theme.COLORS["bg_dark"],
        ).pack(pady=(15, 5))

        entry = tk.Entry(
            dialog,
            font=theme.FONTS["ui"],
            bg=theme.COLORS["bg_editor"],
            fg=theme.COLORS["fg_light"],
            insertbackground=theme.COLORS["accent"],
            bd=0,
            highlightthickness=1,
            highlightbackground=theme.COLORS["sash_color"],
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
            command=rename,
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
            command=dialog.destroy,
        ).pack(side=tk.LEFT, padx=5)

    def delete_conversation(self, conversation_id):
        """Delete a conversation after confirmation."""
        if messagebox.askyesno(
            "Delete Conversation", "Are you sure you want to delete this conversation?"
        ):
            self.conversation_manager.delete_conversation(conversation_id)
            self.refresh_conversations_list()

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
            ("All files", "*.*"),
        ]

        filename = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=filetypes, title="Export Conversation"
        )

        if not filename:
            return

        ext = os.path.splitext(filename)[1].lower()
        if ext == ".json":
            format_type = "json"
        elif ext == ".md":
            format_type = "md"
        else:
            format_type = "txt"

        content = self.conversation_manager.export_conversation(
            conversation_id, format_type
        )
        if content:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                messagebox.showinfo("Export", "Conversation exported successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export: {e}")

    def _on_disabled_area_click(self, event):
        """Flash the File button when user clicks on a disabled area."""
        if self.controller.file_path is None and not self.file_or_folder_opened:
            self._flash_file_button()

    def _flash_file_button(self):
        """Blink the File button to suggest opening a file.
        Only one animation runs at a time.
        """
        if not hasattr(self, "btn_file"):
            return
        # Cancel any previous animation
        if hasattr(self, "_flash_after_id"):
            try:
                self.root.after_cancel(self._flash_after_id)
            except Exception:
                pass
        self._flash_after_id = None

        # Restore original colors immediately
        original_bg = theme.COLORS["bg_header"]
        original_fg = theme.COLORS["fg_light"]
        highlight_bg = theme.COLORS["accent"]
        highlight_fg = theme.COLORS["bg_dark"]

        def blink(count=0):
            if count >= 8:  # 4 on/off cycles
                self.btn_file.config(bg=original_bg, fg=original_fg)
                self._flash_after_id = None
                return
            if count % 2 == 0:
                self.btn_file.config(bg=highlight_bg, fg=highlight_fg)
            else:
                self.btn_file.config(bg=original_bg, fg=original_fg)
            self._flash_after_id = self.root.after(180, lambda: blink(count + 1))

        blink()

    def update_editor_ai_state(self):
        """Update the enabled/disabled state of editor and AI features based on whether a file is opened."""
        has_file_opened = self.controller.file_path is not None

        if has_file_opened:
            self.editor.config(state=tk.NORMAL)
            self.line_numbers.config(state=tk.NORMAL)
            self.btn_run.config(state=tk.NORMAL)

            if hasattr(self, "chat_input"):
                self.chat_input.config(state=tk.NORMAL)
            if hasattr(self, "chat_send_btn"):
                self.chat_send_btn.config(state=tk.NORMAL)
            if hasattr(self, "chat_clear_btn"):
                self.chat_clear_btn.config(state=tk.NORMAL)

            if not self.status_label.cget("text").startswith("AI:"):
                self.status_label.config(text="Ready")
        else:
            self.editor.config(state=tk.DISABLED)
            self.line_numbers.config(state=tk.DISABLED)
            self.btn_run.config(state=tk.DISABLED)

            if hasattr(self, "chat_input"):
                self.chat_input.config(state=tk.DISABLED)
            if hasattr(self, "chat_send_btn"):
                self.chat_send_btn.config(state=tk.DISABLED)
            if hasattr(self, "chat_clear_btn"):
                self.chat_clear_btn.config(state=tk.DISABLED)

            self.status_label.config(
                text="Open a file from the explorer to start coding"
            )

    def load_languages_async(self):
        try:
            url = "https://raw.githubusercontent.com/blakeembrey/language-map/master/languages.json"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))

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
    root.withdraw()

    splash = SplashScreen(root)

    app = LithiumIDE(root)

    root.after(2000, lambda: (splash.close(), root.deiconify()))
    root.mainloop()
