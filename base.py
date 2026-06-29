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

from src import theme
from src.ai_powered import ai_engine as ai_runner
from src.ai_powered import ai_level as ai_level_manager
from src.ai_powered.ai_skill_settings import (
    SKILL_TOGGLE_LABELS,
    AISkillSettings,
)
from src.ai_powered.ai_skills import AISkillResult
from src.ai_powered.ai_skills import get_executor as get_ai_skills_executor
from src.ai_powered.ai_skills import reset_executor as reset_ai_skills_executor
from src.ai_powered.conversation_manager import Conversation, get_conversation_manager
from src.ai_powered.rag_engine import ProjectRAG
from src.autocomplete import LithiumAutocompleteManager
from src.agentic_ui import AgenticChangeBar, DiffViewer
from src.console import Console
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
        self.editor_header = tk.Frame(self.editor_frame, bg=theme.COLORS["bg_header"])
        self.editor_label = tk.Label(
            self.editor_header,
            text="EDITOR (PYTHON)",
            bg=theme.COLORS["bg_header"],
            fg=theme.COLORS["fg_dim"],
            font=theme.FONTS["header"],
            anchor="w",
            padx=12,
            pady=8,
        )
        self.editor_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.console_toggle_btn = tk.Button(
            self.editor_header,
            text="⬚ Terminal",
            font=theme.FONTS["ui"],
            fg=theme.COLORS["fg_dim"],
            bg=theme.COLORS["bg_header"],
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            activebackground=theme.COLORS["sash_color"],
            activeforeground=theme.COLORS["accent"],
            command=self.toggle_console,
        )
        self.console_toggle_btn.pack(side=tk.RIGHT, padx=(0, 4))
        self.editor_header.pack(fill=tk.X)

        self.editor_scrollbar = ttk.Scrollbar(self.editor_frame)
        self.editor_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.line_numbers = tk.Text(
            self.editor_frame, width=4, wrap=tk.NONE, state=tk.DISABLED
        )
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)

        self.editor = tk.Text(self.editor_frame, wrap=tk.NONE, undo=True)
        self.editor.pack(fill=tk.BOTH, expand=1)

        self.paned_window.add(self.editor_frame, minsize=150)

        # ── Console panel (integrated terminal below editor) ──
        self.console_frame = tk.Frame(self.paned_window, bg=theme.COLORS["bg_dark"])
        self.console_header = tk.Label(
            self.console_frame,
            text=" TERMINAL",
            font=theme.FONTS["header"],
            fg=theme.COLORS["fg_dim"],
            bg=theme.COLORS["bg_header"],
            anchor="w",
            padx=12,
            pady=4,
        )
        self.console_header.pack(fill=tk.X)

        self.console = Console(self.console_frame)
        self.console.pack(fill=tk.BOTH, expand=True)
        self.console.apply_theme(theme.COLORS)

        self.paned_window.add(self.console_frame, minsize=100, height=200)

        self.controller = LithiumEditorController(
            self.root,
            self.editor,
            self.line_numbers,
            self.status_label,
            self.selected_lang,
            self.editor_label,
            on_file_open_callback=self._on_file_opened,
            require_explorer_open=True,
            settings_manager=self.settings_manager,
        )
        self.controller.on_dirty_state_changed_callback = self.on_dirty_state_changed
        self.controller.on_filesystem_change_callback = self._on_filesystem_changed
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

        theme.apply_theme(
            self.root,
            self.editor,
            self.paned_window,
            self.editor_label,
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
         
        # Preload model in background for faster first query
        if self.ai_model_link:
            self.root.after(1500, self._preload_model_in_background)

        self.btn_theme = tk.Button(
            self.toolbar,
            text=" Theme ▾",
            image=self.icons.get("theme", ""),
            compound=tk.LEFT,
            command=self.show_theme_menu,
        )
        self.btn_theme.pack(side=tk.LEFT, padx=2, pady=3)
        theme.style_toolbar_button(self.btn_theme)

        self._ai_generating = False
        self._ai_stop_event = threading.Event()

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
            self.explorer_frame,
            self.controller,
            theme.COLORS,
            theme.FONTS,
            on_folder_open_callback=self._on_folder_opened,
        )
        self.main_paned.add(self.explorer_frame, minsize=150, width=320)

        self.main_paned.add(self.center_right_paned, minsize=400)

        self.conversation_manager = get_conversation_manager()
        self._conversation_ids = []
        self._rag = ProjectRAG()
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

        # Keyboard shortcuts for agentic AI approval workflow (GitHub Copilot-style)
        # Ctrl+Enter to approve pending AI changes
        self.root.bind("<Control-Return>", self._on_approve_shortcut, add="+")
        # Escape to reject pending AI changes
        self.root.bind("<Escape>", self._on_reject_shortcut, add="+")

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
        has_folder_opened = bool(
            hasattr(self, "file_explorer")
            and self.file_explorer
            and self.file_explorer.current_folder
        )
        if not self.controller.file_path and not has_folder_opened:
            messagebox.showwarning(
                "AI", "Open a folder from the explorer before using AI features."
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
            self.paned_window,
            self.editor_label,
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

        for frame_attr in ("editor_frame", "explorer_frame", "console_frame"):
            if hasattr(self, frame_attr):
                getattr(self, frame_attr).config(bg=theme.COLORS["bg_dark"])

        self._apply_status_bar_theme()
        self._apply_chat_theme()

        # Apply theme to console
        if hasattr(self, "console"):
            self.console.apply_theme(theme.COLORS)
        for header_attr in ("console_header", "editor_header"):
            if hasattr(self, header_attr):
                getattr(self, header_attr).config(
                    bg=theme.COLORS["bg_header"],
                )
        if hasattr(self, "console_toggle_btn"):
            theme.style_toolbar_button(self.console_toggle_btn)

        if hasattr(self, "file_explorer") and self.file_explorer:
            self.file_explorer.apply_theme()

        for button in (
            self.btn_file,
            self.btn_lang,
            self.btn_ai,
            self.btn_theme,
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

    def _collect_workspace_files(self, max_files=40):
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

    def _collect_workspace_tree_summary(self, max_depth=2, max_items=120):
        folder = None
        if hasattr(self, "file_explorer") and self.file_explorer:
            folder = self.file_explorer.current_folder
        if not folder or not os.path.isdir(folder):
            return ""

        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", ".models"}
        lines = []
        item_count = 0
        truncated = False

        def visible_entries(path):
            try:
                entries = sorted(
                    os.listdir(path),
                    key=lambda name: (not os.path.isdir(os.path.join(path, name)), name.lower()),
                )
            except PermissionError:
                return [], []

            dirs = []
            files = []
            for name in entries:
                if name.startswith(".") or name in skip_dirs:
                    continue
                full_path = os.path.join(path, name)
                if os.path.isdir(full_path):
                    dirs.append(name)
                else:
                    files.append(name)
            return dirs, files

        def walk(path, depth=0, label=None):
            nonlocal item_count, truncated

            dirs, files = visible_entries(path)
            indent = "  " * depth
            name = label or os.path.basename(path.rstrip(os.sep)) or path

            if depth == 0:
                lines.append(f"{name}/")
            else:
                lines.append(
                    f"{indent}- {name}/ ({len(files)} files, {len(dirs)} folders)"
                )

            item_count += 1
            if item_count >= max_items:
                truncated = True
                return

            if files:
                preview = ", ".join(files[:8])
                if len(files) > 8:
                    preview += f", ... (+{len(files) - 8} more)"
                lines.append(f"{indent}  files: {preview}")
                item_count += 1
                if item_count >= max_items:
                    truncated = True
                    return

            if depth + 1 >= max_depth:
                return

            for child in dirs:
                if item_count >= max_items:
                    truncated = True
                    return
                walk(os.path.join(path, child), depth + 1, child)

        walk(folder)
        if truncated:
            lines.append("... (summary truncated)")
        return "\n".join(lines)

    def _should_use_workspace_tree_summary(self, user_message):
        text = (user_message or "").lower()
        return any(
            phrase in text
            for phrase in (
                "explain this folder",
                "explain folder",
                "carpeta",
                "folder overview",
                "folder structure",
                "directory structure",
                "project structure",
                "tree",
                "estructura",
            )
        )

    def _set_ai_reading_status(self, file_label, start_line, end_line):
        message = f"Reading {file_label} >> L{start_line} - L{end_line}"
        status_label = getattr(self, "status_label", None)
        root = getattr(self, "root", None)
        if root and hasattr(root, "after"):
            root.after(0, lambda: status_label.config(text=message))
        elif status_label is not None:
            status_label.config(text=message)

    def _read_file_excerpt(self, absolute_path, start_line=1, end_line=40):
        if not absolute_path or not os.path.isfile(absolute_path):
            return "", start_line, start_line

        try:
            with open(absolute_path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
        except UnicodeDecodeError:
            with open(absolute_path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
        except Exception:
            return "", start_line, start_line

        total_lines = len(lines)
        if total_lines == 0:
            return "", start_line, start_line

        start_index = max(0, start_line - 1)
        end_index = min(end_line, total_lines)
        excerpt = "".join(lines[start_index:end_index]).rstrip()
        return excerpt, start_index + 1, end_index

    def _collect_workspace_excerpts(self, max_files=8):
        folder = None
        if hasattr(self, "file_explorer") and self.file_explorer:
            folder = self.file_explorer.current_folder
        if not folder or not os.path.isdir(folder):
            return []

        preferred_names = (
            "README.md",
            "README.txt",
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "base.py",
            "strip_comments.py",
        )
        preferred_paths = []
        for name in preferred_names:
            candidate = os.path.join(folder, name)
            if os.path.isfile(candidate):
                preferred_paths.append(candidate)

        discovered = []
        for rel_path in self._collect_workspace_files(max_files=max_files * 2):
            abs_path = os.path.join(folder, rel_path)
            if os.path.isfile(abs_path):
                discovered.append(abs_path)

        chosen = []
        seen = set()
        for path in preferred_paths + discovered:
            normalized = os.path.normpath(path)
            if normalized in seen:
                continue
            seen.add(normalized)
            chosen.append(path)
            if len(chosen) >= max_files:
                break

        excerpts = []
        for absolute_path in chosen:
            rel_path = os.path.relpath(absolute_path, folder).replace("\\", "/")
            ext = os.path.splitext(rel_path)[1].lower()
            max_line = 80 if ext in {".md", ".txt", ".toml", ".json", ".yml", ".yaml"} else 60
            self._set_ai_reading_status(rel_path, 1, max_line)
            text, start_line, end_line = self._read_file_excerpt(
                absolute_path, 1, max_line
            )
            if text:
                excerpts.append(
                    {
                        "path": rel_path,
                        "start_line": start_line,
                        "end_line": end_line,
                        "content": text,
                    }
                )

        return excerpts

    def _build_ai_folder_explanation_prompt(self, user_message):
        folder = None
        if hasattr(self, "file_explorer") and self.file_explorer:
            folder = self.file_explorer.current_folder

        tree_summary = self._collect_workspace_tree_summary(max_depth=3, max_items=120)
        if not tree_summary:
            tree_summary = "(No folder tree is available.)"

        excerpts = self._collect_workspace_excerpts(max_files=8)
        excerpt_block = ""
        if excerpts:
            formatted = []
            for item in excerpts:
                formatted.append(
                    f"{item['path']} (L{item['start_line']}-L{item['end_line']})\n{item['content']}"
                )
            excerpt_block = "\n\nSelective file excerpts:\n" + "\n\n".join(formatted)

        return f"""TASK
User request:
{user_message}

Current folder:
{folder or 'No folder open'}

Folder tree summary:
{tree_summary}
{excerpt_block}

OUTPUT CONTRACT
- Answer in plain language only.
- Do not use code-edit XML or skill tags.
- Do not describe files as code edits.
- Explain the folder structure clearly and concisely.
- Mention the main purpose of each top-level folder and the most relevant files you can see.
- If the folder is large, summarize the structure instead of listing every file.
"""

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

    def check_and_setup_dependencies(self):
        missing = self._get_missing_dependencies()
        if missing:
            print("Dependencies missing, run pip install -r requirements.txt")
            msg = (
                "Missing required dependencies:\n"
                + "\n".join(f"  \u2022 {m}" for m in missing)
                + "\n\nPlease run the following command and restart the IDE:\n"
                "  pip install -r requirements.txt"
            )
            try:
                messagebox.showerror("Lithium IDE - Missing Dependencies", msg)
            except Exception:
                pass
            # Force exit — don't let the IDE start
            try:
                self.root.destroy()
            except Exception:
                pass
            os._exit(1)

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

        def on_filesystem_change(_changed_path=None):
            """Refresh the file explorer when AI creates or deletes files."""
            self._on_filesystem_changed()

        try:
            self.ai_skills_executor = get_ai_skills_executor(
                editor_getter=get_editor_content,
                editor_setter=set_editor_content,
                file_path_getter=get_file_path,
                project_folder_getter=get_project_folder,
                status_callback=status_update,
                on_filesystem_change=on_filesystem_change,
            )
            self._refresh_ai_system_prompt()
        except Exception as e:
            print(f"Warning: Could not initialize AI Skills: {e}")
            self.ai_skills_executor = None

    def _preload_model_in_background(self):
        """Preload the AI model in a background thread to speed up first query."""
        if not self.ai_model_link or not self._is_ai_model_ready():
            return
         
        def preload():
            try:
                self.root.after(
                    0,
                    lambda: self.status_label.config(text="AI: Preloading model..."),
                )
                 
                # Preload model using optimized preload function
                ai_runner.preload_model(
                    self.ai_model_link,
                    n_ctx=self.ai_inference_params.get("n_ctx", 8192),
                    n_batch=self.ai_inference_params.get("n_batch", 512),
                    n_threads=self.ai_inference_params.get("n_threads"),
                )
                 
                self.root.after(
                    0,
                    lambda: self.status_label.config(text="AI: Ready"),
                )
            except Exception as e:
                print(f"[AI Engine] Background model preload failed: {e}")
                # Don't show error to user, just continue normally
                self.root.after(
                    0,
                    lambda: self.status_label.config(text="AI: Ready"),
                )
         
        preload_thread = threading.Thread(target=preload, daemon=True)
        preload_thread.start()


    def toggle_ai_chat(self):
        if self.chat_visible:
            self.center_right_paned.remove(self.chat_frame)
            self.chat_visible = False
        else:
            self.center_right_paned.add(self.chat_frame, minsize=250, width=300)
            self.chat_visible = True

    def toggle_console(self):
        """Show or hide the integrated terminal panel."""
        if self.console_frame.winfo_ismapped():
            self.paned_window.remove(self.console_frame)
            self.console_toggle_btn.config(text="⬚ Terminal")
        else:
            self.paned_window.add(self.console_frame, minsize=100, height=200)
            self.console_toggle_btn.config(text="✕ Terminal")
        self.paned_window.update_idletasks()

    def clear_chat(self):
        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.delete("1.0", tk.END)
        self.chat_history.config(state=tk.DISABLED)

    def send_chat_message(self):
        has_folder_opened = bool(
            hasattr(self, "file_explorer")
            and self.file_explorer
            and self.file_explorer.current_folder
        )
        if not self.controller.file_path and not has_folder_opened:
            messagebox.showwarning(
                "AI", "Open a folder from the explorer before using the AI chat."
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

        # Toggle button to Stop mode while AI generates
        self._ai_stop_event.clear()
        self._ai_generating = True
        self.chat_send_btn.config(
            text=" Stop",
            image=self.icons.get("stop", ""),
            compound=tk.LEFT,
            command=self._stop_ai_generation,
        )

    def _restore_send_button(self):
        """Restore the chat send button to its default state."""
        self._ai_generating = False
        self.chat_send_btn.config(
            text="Send",
            image="",
            command=self.send_chat_message,
        )

    def _stop_ai_generation(self):
        """Stop the current AI generation and restore the send button."""
        self._ai_stop_event.set()
        self._restore_send_button()
        self._remove_loading_indicator()
        self._cleanup_stream_ui()
        self.status_label.config(text="AI: Stopped")
        self.append_to_chat_history("System", "Response stopped by user")

    def _build_ai_editor_prompt(self, user_message, chat_only=False):
        """Build an AI prompt that includes the current file content with line numbers.

        The AI needs this context so it can decide whether it must delete, replace,
        or add lines before proposing changes. Without the numbered file snapshot,
        the model tends to append code blindly instead of repairing invalid code.
        """
        if self._should_use_workspace_tree_summary(user_message):
            return self._build_ai_folder_explanation_prompt(user_message)

        file_path = self.controller.file_path
        language = self.selected_lang.get()

        if file_path:
            content = self.editor.get("1.0", "end-1c")
            numbered_content, context_notice = self._build_compact_numbered_content(content)
            file_section = f"""Current file path: {file_path}
Current language: {language}

Current open file content with line numbers:
```text
{numbered_content}
```
{context_notice}"""
        else:
            file_section = "(No file is currently open — respond based on the project context and the user's request.)"

        workspace_section = ""
        if self._should_use_workspace_tree_summary(user_message):
            tree_summary = self._collect_workspace_tree_summary()
            if tree_summary:
                workspace_section = f"""
Project scope: you may modify files anywhere under the opened folder tree.
Workspace tree summary:
{tree_summary}
"""
            else:
                workspace_section = """
Project scope: you may modify files anywhere under the opened folder tree.
"""
        else:
            project_files = self._collect_workspace_files(max_files=20)
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

        if chat_only:
            return f"""TASK
User request:
{user_message}

{file_section}
{workspace_section}
OUTPUT CONTRACT
- Answer in plain language directly in chat.
- Do NOT use <skill> XML tags.
- Do NOT modify files.
- Explain clearly what the file does, its structure, and key functions relevant to the user's question.
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

        scope_rule = "- Modifications may target the open file or other files under the opened project folder using the appropriate skill XML tags."

        # When no file is open the model must create one before writing anything
        no_file_contract = ""
        file_editing_hints = """- If the current content would make the final file invalid, first emit delete_lines for the invalid/unrelated lines, then emit add_lines with the corrected code.
- If the whole file is invalid or contains unrelated text, use replace_file to replace the entire file content.
- Do not just append code if existing text/code would prevent compilation.

For example, if line 1 is invalid plain text and the user asks for Python hello world, respond exactly like this:
<skill name="delete_lines"><parameter name="line">1</parameter><parameter name="count">1</parameter></skill>
<skill name="add_lines"><parameter name="line">1</parameter><parameter name="content">print("Hello, world!")</parameter></skill>"""
        if not self.controller.file_path:
            no_file_contract = (
                "IMPORTANT: No file is currently open.\n"
                "You MUST use the create_file skill to create a new file before writing any code.\n"
                "Choose an appropriate filename and path relative to the project root.\n"
                "Put ALL the code inside that single create_file skill — do NOT use add_lines or edit_lines on a non-existent file.\n"
            )
            file_editing_hints = ""

        # --- RAG: inject relevant project context ---
        rag_section = ""
        self._last_rag_hits = []
        if hasattr(self, "_rag") and self._rag.is_indexed:
            current_file_abs = self.controller.file_path
            hits = self._rag.retrieve(
                user_message, top_k=6, exclude_file=current_file_abs
            )
            self._last_rag_hits = hits
            if hits:
                rag_context = self._rag.get_context_for_prompt(
                    user_message, max_chars=3000, top_k=6, exclude_file=current_file_abs
                )
                if rag_context:
                    rag_section = f"\n{rag_context}\n"

        return f"""TASK
User request:
{user_message}

{file_section}
{workspace_section}{rag_section}
OUTPUT CONTRACT
{no_file_contract}{reasoning_instruction}{edit_output_rule}
{file_editing_hints}
{scope_rule}
"""

    def _is_chat_only_request(self, user_message):
        """Return True when the request is explanatory/chat-only and should not edit files."""
        text = (user_message or "").strip().lower()
        if not text:
            return False

        chat_markers = (
            "que hace este archivo",
            "qué hace este archivo",
            "explica este archivo",
            "explain this file",
            "what does this file do",
            "solo explica",
            "solo explicar",
            "only explain",
            "just explain",
            "resumen",
            "summary",
        )

        edit_markers = (
            "agrega",
            "añade",
            "modifica",
            "edita",
            "cambia",
            "borra",
            "elimina",
            "create",
            "add ",
            "edit ",
            "modify",
            "delete",
            "replace",
            "refactor",
            "implement",
            "fix",
        )

        if any(marker in text for marker in chat_markers):
            return True
        if any(marker in text for marker in edit_markers):
            return False
        return text.endswith("?") or text.startswith("¿")

    def _build_compact_numbered_content(self, content, max_lines=240, max_chars=22000):
        """Return a bounded, line-numbered file snapshot for fast prompt evaluation."""
        lines = content.splitlines()
        if not lines:
            return "(empty file)", ""

        if len(lines) <= max_lines:
            numbered = "\n".join(
                f"{line_number}: {line}"
                for line_number, line in enumerate(lines, start=1)
            )
            if len(numbered) <= max_chars:
                return numbered, ""

        head_count = max(1, max_lines // 2)
        tail_count = max(1, max_lines - head_count)

        head_lines = [
            f"{line_number}: {line}"
            for line_number, line in enumerate(lines[:head_count], start=1)
        ]
        tail_start = max(head_count, len(lines) - tail_count)
        tail_lines = [
            f"{line_number}: {line}"
            for line_number, line in enumerate(lines[tail_start:], start=tail_start + 1)
        ]

        omitted_lines = max(0, len(lines) - head_count - len(tail_lines))
        sections = list(head_lines)
        if omitted_lines > 0:
            sections.append(f"... [{omitted_lines} lines omitted to speed up response] ...")
        sections.extend(tail_lines)

        numbered = "\n".join(sections)
        if len(numbered) > max_chars:
            half = max_chars // 2
            numbered = (
                numbered[:half]
                + "\n... [middle content omitted to fit prompt budget] ...\n"
                + numbered[-half:]
            )

        notice = (
            "Note: file context was trimmed for lower latency. "
            "Use visible line numbers for edits and avoid changing omitted regions unless needed."
        )
        return numbered, notice

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

    def _show_rag_sources_widget(self, hits):
        """Insert a compact collapsible RAG-sources pill into the chat (main thread)."""
        if not hits:
            return
        self.chat_history.config(state=tk.NORMAL)

        bg = theme.COLORS.get("bg_editor", "#080808")
        bg_dark = theme.COLORS.get("bg_dark", "#000000")
        fg_dim = theme.COLORS.get("fg_dim", "#7D8794")
        accent = theme.COLORS.get("accent", "#cba6f7")

        frame = tk.Frame(self.chat_history, bg=bg)
        visible = [False]

        # Deduplicate file paths, preserve score order
        seen = set()
        unique_files = []
        for chunk, score in hits:
            if chunk.rel_path not in seen:
                seen.add(chunk.rel_path)
                unique_files.append((chunk.rel_path, score))

        n = len(unique_files)
        label_plural = "s" if n != 1 else ""
        pill_text = f"\U0001f50d RAG \u00b7 {n} archivo{label_plural} consultado{label_plural}"

        list_frame = tk.Frame(frame, bg=bg_dark)

        for rel_path, score in unique_files:
            row = tk.Frame(list_frame, bg=bg_dark)
            row.pack(fill=tk.X, padx=4, pady=1)
            tk.Label(
                row,
                text=f"  \u2022 {rel_path}",
                font=("DejaVu Sans Mono", 8),
                fg=fg_dim,
                bg=bg_dark,
                anchor="w",
            ).pack(side=tk.LEFT)
            tk.Label(
                row,
                text=f"{score:.2f}",
                font=("DejaVu Sans Mono", 8),
                fg=accent,
                bg=bg_dark,
                anchor="e",
            ).pack(side=tk.RIGHT, padx=(0, 6))

        def toggle():
            if visible[0]:
                list_frame.pack_forget()
                toggle_btn.config(text=pill_text)
            else:
                list_frame.pack(fill=tk.X, padx=2, pady=(0, 4))
                toggle_btn.config(text=pill_text + " \u25be")
            visible[0] = not visible[0]

        toggle_btn = tk.Button(
            frame,
            text=pill_text,
            font=("DejaVu Sans", 8),
            fg=fg_dim,
            bg=bg,
            bd=0,
            activebackground=bg_dark,
            activeforeground=accent,
            cursor="hand2",
            command=toggle,
            anchor=tk.W,
            padx=6,
            pady=2,
        )
        toggle_btn.pack(fill=tk.X)

        self.chat_history.window_create(tk.END, window=frame)
        self.chat_history.insert(tk.END, "\n")
        self.chat_history.see(tk.END)
        self.chat_history.config(state=tk.DISABLED)

    def _stream_ai_response(self, prompt, chat_only=False):
        """Run AI with streaming, showing response tokens in real-time."""
        self.root.after(0, lambda: self.status_label.config(text="AI: Generating..."))

        # Show the standard loading indicator immediately so there's visual feedback
        # NOTE: Must use root.after() because we're in a worker thread
        self.root.after(0, self._show_loading_indicator)

        editor_prompt = self._build_ai_editor_prompt(prompt, chat_only=chat_only)
        # Show RAG sources pill in chat if any files were retrieved
        rag_hits = list(getattr(self, "_last_rag_hits", []))
        if rag_hits:
            self.root.after(0, lambda h=rag_hits: self._show_rag_sources_widget(h))
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
            "chat_only": chat_only,
            "done": False,
            "error": None,
        }
        state_lock = threading.Lock()

        # --- Create reasoning widget only when <think> is first detected ---
        reasoning_created = [False]
        response_created = [False]

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

        def create_response_widget():
            """Create a live-updating response widget while tokens stream in."""
            if response_created[0]:
                return
            response_created[0] = True

            self.chat_history.config(state=tk.NORMAL)
            bg = theme.COLORS.get("bg_editor", "#080808")
            bg_dark = theme.COLORS.get("bg_dark", "#000000")
            fg = theme.COLORS.get("fg_light", "#D8DEE9")
            accent = theme.COLORS.get("accent", "#cba6f7")

            frame = tk.Frame(self.chat_history, bg=bg)
            header = tk.Label(
                frame,
                text="AI (live):",
                font=("DejaVu Sans", 10, "bold"),
                fg=accent,
                bg=bg,
                anchor="w",
            )
            header.pack(fill=tk.X, padx=2, pady=(0, 2))

            widget = tk.Text(
                frame,
                wrap=tk.WORD,
                font=theme.FONTS.get("ui", ("DejaVu Sans", 10)),
                fg=fg,
                bg=bg_dark,
                bd=0,
                highlightthickness=0,
                height=3,
                padx=8,
                pady=6,
                relief=tk.FLAT,
            )
            widget.pack(fill=tk.X, padx=2, pady=(0, 6))
            widget.config(state=tk.DISABLED)

            self.chat_history.window_create(tk.END, window=frame)
            self.chat_history.insert(tk.END, "\n")
            self.chat_history.see(tk.END)
            self.chat_history.config(state=tk.DISABLED)

            self._stream_response_widget = widget
            self._stream_response_frame = frame

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

        def update_response_widget(text):
            """Update the live response widget as tokens arrive."""
            if not response_created[0]:
                return
            try:
                w = self._stream_response_widget
                w.config(state=tk.NORMAL)
                w.delete("1.0", tk.END)
                w.insert("1.0", text)
                w.config(state=tk.DISABLED)
                w.see(tk.END)
                lines = text.count("\n") + 1
                w.config(height=min(max(lines, 3), 20))
            except Exception:
                pass

        # --- Periodic UI update (main thread) ---
        def poll_ui():
            with state_lock:
                if state["error"]:
                    self._remove_loading_indicator()
                    self._cleanup_stream_ui()
                    self.status_label.config(text="AI: Error")
                    self._restore_send_button()
                    self.append_to_chat_history(
                        "Error", f"Could not generate response: {state['error']}"
                    )
                    return

                reasoning = state["reasoning"]
                response = state["response"]
                done = state["done"]

            # Create reasoning widget on first detection of <think>
            if reasoning and not reasoning_created[0]:
                self.root.after(0, create_reasoning_widget)

            # Live-update reasoning widget
            if reasoning and reasoning_created[0]:
                update_reasoning_widget(reasoning)

            # Live-update assistant output widget
            if response and not response_created[0]:
                self.root.after(0, create_response_widget)
            if response and response_created[0]:
                update_response_widget(response)

            if not done:
                self.root.after(50, poll_ui)
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
                    # Check if user requested stop
                    if self._ai_stop_event.is_set():
                        with state_lock:
                            state["done"] = True
                        return
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
            chat_only = state.get("chat_only", False)
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
        if self.ai_skills_executor and not chat_only:
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
        elif self.ai_skills_executor and chat_only:
            try:
                clean_response = self.ai_skills_executor.get_clean_response(full_response)
            except Exception:
                clean_response = full_response

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
            if sn == "respond_in_chat":
                continue
            icon = "✓" if result.success else "✗"
            self.append_to_chat_history("Skill", f"{icon} {result.message}")

        if clean_response.strip():
            self.append_to_chat_history("AI", clean_response, reasoning=reasoning_text)

        # Show unified approval bar if there were editor changes
        if original_content is not None:
            new_content = self.editor.get("1.0", tk.END)
            added, removed = self._compute_diff_stats(original_content, new_content)
            if added > 0 or removed > 0:
                # Show system message with agentic hint
                self.append_to_chat_history(
                    "⚡ System",
                    f"AI has made {added + removed} changes. Use Ctrl+Enter to approve or Esc to reject.",
                )
                self._show_approval_bar(original_content, new_content, added, removed)
            else:
                # No actual changes detected, clean up
                self._original_content_before_ai = None

        self.status_label.config(text="AI: Ready")
        self._restore_send_button()
        self._notify_ai_task_complete()
        self.refresh_conversations_list()

    def _cleanup_stream_ui(self):
        """Remove streaming UI widgets."""
        for attr in (
            "_stream_reasoning_widget",
            "_stream_reasoning_frame",
            "_stream_reasoning_toggle",
            "_stream_response_widget",
            "_stream_response_frame",
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
        chat_only = self._is_chat_only_request(prompt)

        # Use streaming path whenever the runtime supports it
        if not is_retry and self._can_stream():
            try:
                self._stream_ai_response(prompt, chat_only=chat_only)
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
            editor_prompt = self._build_ai_editor_prompt(prompt, chat_only=chat_only)
            rag_hits = list(getattr(self, "_last_rag_hits", []))
            if rag_hits:
                self.root.after(0, lambda h=rag_hits: self._show_rag_sources_widget(h))
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

            # Check if user requested stop during generation
            if self._ai_stop_event.is_set():
                self.root.after(0, self._remove_loading_indicator)
                self.root.after(0, self._restore_send_button)
                self.root.after(0, lambda: self.status_label.config(text="AI: Stopped"))
                return

            if not chat_only:
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
            if self.ai_skills_executor and not chat_only:
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
            elif self.ai_skills_executor and chat_only:
                try:
                    clean_response = self.ai_skills_executor.get_clean_response(
                        response_no_reasoning
                    )
                except Exception:
                    clean_response = response_no_reasoning

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
                    if skill_name == "respond_in_chat":
                        continue
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
                self._restore_send_button()
                self._notify_ai_task_complete()
                self.refresh_conversations_list()

            self.root.after(0, show_response)
        except Exception as exc:
            # Schedule removal on main thread (we're in a worker thread)
            self.root.after(0, self._remove_loading_indicator)
            err_msg = str(exc)
            self.root.after(0, self._restore_send_button)
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
            self._restore_send_button()
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
        """Show a unified approve/reject bar using agentic UI (GitHub Copilot-style)."""
        if self._approval_bar is not None:
            try:
                if hasattr(self._approval_bar, "destroy"):
                    self._approval_bar.destroy()
            except Exception:
                pass
            self._approval_bar = None

        self._original_content_before_ai = original_content

        # Use the new AgenticChangeBar for a more modern, agentic UI
        change_bar = AgenticChangeBar(
            parent=self.chat_input_container,
            theme_colors=theme.COLORS,
            original_content=original_content,
            new_content=new_content,
            on_approve=self._on_approve_bar_approve,
            on_reject=self._on_approve_bar_reject,
        )
        
        bar_frame = change_bar.create()
        # Pack at TOP so it appears above chat input
        bar_frame.pack(side=tk.TOP, fill=tk.X, padx=0, pady=(0, 5))

        self._approval_bar = bar_frame
        self._approval_bar_controller = change_bar  # Keep reference to controller

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

    def _on_approve_shortcut(self, event=None):
        """Handle Ctrl+Enter keyboard shortcut to approve pending AI changes."""
        if self._approval_bar is not None and self._approval_bar.winfo_exists():
            self._on_approve_bar_approve()
            return "break"  # Prevent default behavior
        return None

    def _on_reject_shortcut(self, event=None):
        """Handle Escape keyboard shortcut to reject pending AI changes."""
        if self._approval_bar is not None and self._approval_bar.winfo_exists():
            self._on_approve_bar_reject()
            return "break"  # Prevent default behavior
        return None

    def _get_skill_name_from_result(self, result_idx, all_results):
        """Get skill name from result index (simplified - in real impl would track names)."""
        return "unknown"

    def insert_colored_diff(self, original: str, new: str, context_lines: int = 2):
        """
        Insert a colored diff visualization into the chat history.
        Uses green for additions and red for deletions (GitHub-style).
        """
        self.chat_history.config(state=tk.NORMAL)
        
        # Setup tags for diff colors if not already done
        try:
            self.chat_history.tag_config(
                "diff_added",
                background="#1a3a1a",
                foreground=theme.COLORS.get("success", "#90ee90"),
            )
            self.chat_history.tag_config(
                "diff_removed",
                background="#3a1a1a",
                foreground=theme.COLORS.get("error", "#ff6b6b"),
            )
            self.chat_history.tag_config(
                "diff_info",
                foreground=theme.COLORS.get("fg_dim", "#a6adc8"),
                font=("DejaVu Sans Mono", 9),
            )
        except Exception:
            pass
        
        orig_lines = original.splitlines()
        new_lines = new.splitlines()
        
        differ = difflib.unified_diff(
            orig_lines,
            new_lines,
            fromfile="original",
            tofile="modified",
            lineterm="",
            n=context_lines,
        )
        
        for line in differ:
            if line.startswith("+++") or line.startswith("---"):
                self.chat_history.insert(tk.END, line + "\n", "diff_info")
            elif line.startswith("@@"):
                self.chat_history.insert(tk.END, line + "\n", "diff_info")
            elif line.startswith("+"):
                self.chat_history.insert(tk.END, line + "\n", "diff_added")
            elif line.startswith("-"):
                self.chat_history.insert(tk.END, line + "\n", "diff_removed")
            else:
                self.chat_history.insert(tk.END, line + "\n")
        
        self.chat_history.config(state=tk.DISABLED)

    def append_to_chat_history(self, sender, text, reasoning=None):
        """Add message to chat history with optional reasoning section."""
        self.chat_history.config(state=tk.NORMAL)

        # Determine sender color
        color = (
            theme.COLORS.get("accent", "#cba6f7")
            if sender == "AI"
            else theme.COLORS.get("fg_dim", "#a6adc8")
        )
        if sender == "Error":
            color = theme.COLORS.get("console_err", "#ff0000")
        elif sender == "⚡ AI":  # Agentic AI message
            color = theme.COLORS.get("accent", "#cba6f7")

        # Insert sender label with styling
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
                if sender == "AI":
                    self._insert_markdown_text(part)
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

    def _insert_markdown_text(self, text):
        """Render basic Markdown formatting into the chat Text widget."""
        import re

        self.chat_history.tag_config(
            "md_h1", font=("DejaVu Sans", 14, "bold"), foreground=theme.COLORS.get("accent", "#cba6f7")
        )
        self.chat_history.tag_config(
            "md_h2", font=("DejaVu Sans", 13, "bold"), foreground=theme.COLORS.get("accent", "#cba6f7")
        )
        self.chat_history.tag_config(
            "md_h3", font=("DejaVu Sans", 12, "bold"), foreground=theme.COLORS.get("accent", "#cba6f7")
        )
        self.chat_history.tag_config(
            "md_bold", font=("DejaVu Sans", 10, "bold")
        )
        self.chat_history.tag_config(
            "md_italic", font=("DejaVu Sans", 10, "italic")
        )
        self.chat_history.tag_config(
            "md_inline_code",
            background=theme.COLORS.get("bg_dark", "#181825"),
            foreground=theme.COLORS.get("fg_light", "#cdd6f4"),
            font=("Consolas", 10),
        )
        self.chat_history.tag_config(
            "md_link",
            foreground=theme.COLORS.get("accent", "#89b4fa"),
            underline=True,
        )

        lines = text.split("\n")
        for idx, line in enumerate(lines):
            heading_match = re.match(r"^(#{1,3})\s+(.*)$", line)
            bullet_match = re.match(r"^\s*[-*]\s+(.*)$", line)

            if heading_match:
                level = len(heading_match.group(1))
                content = heading_match.group(2)
                self.chat_history.insert(tk.END, content, (f"md_h{level}",))
            elif bullet_match:
                self.chat_history.insert(tk.END, "• ")
                self._insert_markdown_inline(bullet_match.group(1))
            else:
                self._insert_markdown_inline(line)

            if idx < len(lines) - 1:
                self.chat_history.insert(tk.END, "\n")

    def _insert_markdown_inline(self, text):
        """Render inline Markdown elements (bold, italic, code, links)."""
        import re

        token_pattern = re.compile(
            r"(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\[[^\]]+\]\([^)]+\)|\*[^*\n]+\*|_[^_\n]+_)"
        )

        last = 0
        for match in token_pattern.finditer(text):
            start, end = match.span()
            if start > last:
                self.chat_history.insert(tk.END, text[last:start])

            token = match.group(0)
            if token.startswith("**") and token.endswith("**"):
                self.chat_history.insert(tk.END, token[2:-2], ("md_bold",))
            elif token.startswith("__") and token.endswith("__"):
                self.chat_history.insert(tk.END, token[2:-2], ("md_bold",))
            elif token.startswith("`") and token.endswith("`"):
                self.chat_history.insert(tk.END, token[1:-1], ("md_inline_code",))
            elif token.startswith("[") and "](" in token and token.endswith(")"):
                label, url = token[1:-1].split("](", 1)
                self.chat_history.insert(tk.END, f"{label} ({url})", ("md_link",))
            elif token.startswith("*") and token.endswith("*"):
                self.chat_history.insert(tk.END, token[1:-1], ("md_italic",))
            elif token.startswith("_") and token.endswith("_"):
                self.chat_history.insert(tk.END, token[1:-1], ("md_italic",))
            else:
                self.chat_history.insert(tk.END, token)

            last = end

        if last < len(text):
            self.chat_history.insert(tk.END, text[last:])

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

        self.append_to_chat_history("AI", "Ready")

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
        has_folder_opened = bool(
            hasattr(self, "file_explorer")
            and self.file_explorer
            and self.file_explorer.current_folder
        )
        if self.controller.file_path is None and not has_folder_opened:
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

    # ── console directory sync ──────────────────────────────────────────────

    def _on_file_opened(self):
        """Called when a file is opened. Syncs the console to its parent dir."""
        self.update_editor_ai_state()
        if hasattr(self, "syntax_highlighter"):
            self.syntax_highlighter.highlight_all()
        if hasattr(self, "console") and self.controller.file_path:
            parent = os.path.dirname(self.controller.file_path)
            if parent:
                self.console._change_dir(parent)

    def _on_filesystem_changed(self):
        """Refresh the file explorer after filesystem changes triggered by the app."""
        if hasattr(self, "file_explorer") and self.file_explorer:
            self.root.after(100, self.file_explorer.refresh)

    def _on_folder_opened(self, folder_path):
        """Called when a folder is opened in the explorer. Syncs the console to it."""
        if hasattr(self, "console"):
            self.console._change_dir(folder_path)
        # Unlock the chat now that a folder is available
        self.root.after(0, self.update_editor_ai_state)
        # Rebuild RAG index for the newly opened project in the background
        if hasattr(self, "_rag") and folder_path and os.path.isdir(folder_path):
            self._rag.build_index_async(folder_path)
            self.status_label.config(text="RAG: indexing project…")
            self.root.after(3000, lambda: self.status_label.config(text="Folder open — chat available") if self.status_label.cget("text") == "RAG: indexing project…" else None)

    def update_editor_ai_state(self):
        """Update the enabled/disabled state of editor and AI features based on whether a file is opened."""
        has_file_opened = self.controller.file_path is not None
        has_folder_opened = bool(
            hasattr(self, "file_explorer")
            and self.file_explorer
            and self.file_explorer.current_folder
        )

        if has_file_opened:
            self.editor.config(state=tk.NORMAL)
            self.line_numbers.config(state=tk.NORMAL)
        else:
            self.editor.config(state=tk.DISABLED)
            self.line_numbers.config(state=tk.DISABLED)

        # Chat is available whenever a file OR a folder is open
        chat_available = has_file_opened or has_folder_opened
        if hasattr(self, "chat_input"):
            self.chat_input.config(state=tk.NORMAL if chat_available else tk.DISABLED)
        if hasattr(self, "chat_send_btn"):
            self.chat_send_btn.config(state=tk.NORMAL if chat_available else tk.DISABLED)
        if hasattr(self, "chat_clear_btn"):
            self.chat_clear_btn.config(state=tk.NORMAL if chat_available else tk.DISABLED)

        if not self.status_label.cget("text").startswith("AI:"):
            if has_file_opened:
                self.status_label.config(text="Ready")
            elif has_folder_opened:
                self.status_label.config(text="Folder open — chat available")
            else:
                self.status_label.config(
                    text="Open a file or folder from the explorer to start"
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
