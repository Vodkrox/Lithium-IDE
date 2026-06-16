import os
import json
import tkinter as tk
from tkinter import ttk

# Fallback default theme in case loading JSON fails
DEFAULT_CATPPUCCIN = {
    "bg_dark": "#181825",
    "bg_editor": "#1e1e2e",
    "bg_header": "#11111b",
    "fg_light": "#cdd6f4",
    "fg_dim": "#a6adc8",
    "accent": "#cba6f7",
    "accent_hover": "#b4befe",
    "console_bg": "#11111b",
    "console_fg": "#a6e3a1",
    "console_err": "#f38ba8",
    "sash_color": "#313244"
}

THEMES = {}

def load_themes():
    THEMES.clear()
    themes_dir = os.path.join("src", "themes")
    if os.path.exists(themes_dir):
        for filename in os.listdir(themes_dir):
            if filename.endswith(".json"):
                theme_name = os.path.splitext(filename)[0]
                filepath = os.path.join(themes_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        THEMES[theme_name] = json.load(f)
                except Exception:
                    pass
    if "Catppuccin (Default)" not in THEMES:
        THEMES["Catppuccin (Default)"] = DEFAULT_CATPPUCCIN

# Initial load of themes
load_themes()

CURRENT_THEME = "Catppuccin (Default)"
COLORS = dict(THEMES.get(CURRENT_THEME, DEFAULT_CATPPUCCIN))

FONTS = {
    "ui": ("Segoe UI", 10),
    "header": ("Segoe UI", 9, "bold"),
    "editor": ("Consolas", 12),
    "console": ("Consolas", 11)
}

def set_theme(theme_name):
    global CURRENT_THEME
    if theme_name in THEMES:
        CURRENT_THEME = theme_name
        COLORS.update(THEMES[theme_name])

def apply_theme(root, editor, console, paned_window, editor_label, console_label, line_numbers, status_bar, toolbar=None, toolbar_divider=None):
    root.configure(bg=COLORS["bg_dark"])

    if toolbar:
        toolbar.config(bg=COLORS["bg_header"])
    if toolbar_divider:
        toolbar_divider.config(bg=COLORS["sash_color"])

    style = ttk.Style()
    style.theme_use("clam")
    
    style.configure(
        "TScrollbar",
        gripcount=0,
        background=COLORS["bg_dark"],
        darkcolor=COLORS["bg_dark"],
        lightcolor=COLORS["bg_dark"],
        troughcolor=COLORS["bg_editor"],
        bordercolor=COLORS["bg_dark"],
        arrowcolor=COLORS["fg_dim"]
    )
    style.map(
        "TScrollbar",
        background=[("active", COLORS["sash_color"]), ("pressed", COLORS["accent"])]
    )

    editor_label.config(
        bg=COLORS["bg_header"],
        fg=COLORS["fg_dim"],
        font=FONTS["header"],
        padx=12,
        pady=8,
        bd=0,
        anchor="w"
    )
    console_label.config(
        bg=COLORS["bg_header"],
        fg=COLORS["fg_dim"],
        font=FONTS["header"],
        padx=12,
        pady=8,
        bd=0,
        anchor="w"
    )

    editor.config(
        bg=COLORS["bg_editor"],
        fg=COLORS["fg_light"],
        insertbackground=COLORS["accent"],
        selectbackground="#45475a",
        selectforeground=COLORS["fg_light"],
        font=FONTS["editor"],
        padx=10,
        pady=10,
        bd=0,
        highlightthickness=0
    )

    line_numbers.config(
        bg=COLORS["bg_header"],
        fg="#585b70",
        font=FONTS["editor"],
        padx=8,
        pady=10,
        bd=0,
        width=4,
        state=tk.DISABLED,
        highlightthickness=0
    )

    console.config(
        bg=COLORS["console_bg"],
        fg=COLORS["console_fg"],
        insertbackground=COLORS["accent"],
        selectbackground="#45475a",
        selectforeground=COLORS["fg_light"],
        font=FONTS["console"],
        padx=12,
        pady=12,
        bd=0,
        highlightthickness=0
    )

    # status_bar is now a Frame, so we only configure bg
    status_bar.config(
        bg=COLORS["bg_header"],
        bd=0,
        relief=tk.FLAT
    )

    paned_window.config(
        bg=COLORS["bg_dark"],
        bd=0,
        sashwidth=4,
        sashpad=1,
        sashrelief=tk.FLAT
    )

def style_search_dialog(dialog, search_entry, listbox, title_label):
    dialog.configure(bg=COLORS["bg_dark"])
    
    title_label.config(
        bg=COLORS["bg_dark"],
        fg=COLORS["accent"],
        font=FONTS["header"]
    )
    
    search_entry.config(
        bg=COLORS["bg_editor"],
        fg=COLORS["fg_light"],
        insertbackground=COLORS["accent"],
        font=FONTS["ui"],
        bd=0,
        highlightthickness=1,
        highlightbackground=COLORS["sash_color"],
        highlightcolor=COLORS["accent"]
    )
    
    listbox.config(
        bg=COLORS["bg_editor"],
        fg=COLORS["fg_light"],
        font=FONTS["ui"],
        bd=0,
        highlightthickness=1,
        highlightbackground=COLORS["sash_color"],
        highlightcolor=COLORS["accent"],
        selectbackground=COLORS["accent"],
        selectforeground=COLORS["bg_dark"]
    )

def style_autocomplete(popup, listbox):
    popup.configure(bg=COLORS["bg_dark"])
    listbox.config(
        bg=COLORS["bg_header"],
        fg=COLORS["fg_light"],
        font=FONTS["ui"],
        bd=0,
        highlightthickness=1,
        highlightbackground=COLORS["sash_color"],
        highlightcolor=COLORS["accent"],
        selectbackground=COLORS["accent"],
        selectforeground=COLORS["bg_dark"]
    )

def style_toolbar_button(button):
    button.config(
        bg=COLORS["bg_header"],
        fg=COLORS["fg_light"],
        activebackground=COLORS["sash_color"],
        activeforeground=COLORS["accent"],
        font=FONTS["ui"],
        bd=0,
        padx=12,
        pady=5,
        relief=tk.FLAT,
        cursor="hand2"
    )
    def on_enter(e):
        button.config(bg=COLORS["sash_color"], fg=COLORS["accent"])
    def on_leave(e):
        button.config(bg=COLORS["bg_header"], fg=COLORS["fg_light"])
    
    button.bind("<Enter>", on_enter)
    button.bind("<Leave>", on_leave)

def _invert_hex_color(color):
    if not isinstance(color, str) or not color.startswith("#"):
        return "#ffffff"
    hex_value = color.lstrip("#")
    if len(hex_value) != 6:
        return "#ffffff"
    try:
        r = 255 - int(hex_value[0:2], 16)
        g = 255 - int(hex_value[2:4], 16)
        b = 255 - int(hex_value[4:6], 16)
        return f"#{r:02x}{g:02x}{b:02x}"
    except ValueError:
        return "#ffffff"


def style_menu(menu):
    menu.config(
        bg=COLORS["bg_header"],
        fg=COLORS["fg_light"],
        activebackground=COLORS["accent"],
        activeforeground=COLORS["bg_dark"],
        selectcolor=_invert_hex_color(COLORS["bg_header"]),
        bd=1,
        relief=tk.FLAT
    )


