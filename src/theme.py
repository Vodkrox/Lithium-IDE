import json
import os
import sys
import tkinter as tk
from tkinter import ttk

DEFAULT_GRAPHITE = {
    "bg_dark": "#000000",
    "bg_editor": "#080808",
    "bg_header": "#000000",
    "fg_light": "#FFFFFF",
    "fg_dim": "#7D8794",
    "accent": "#4DA3FF",
    "accent_hover": "#2F7DD1",
    "console_bg": "#080808",
    "console_fg": "#E6EDF3",
    "console_err": "#FF5C5C",
    "sash_color": "#000000",
    "selection_bg": "#1A1A1A",
    "line_number_fg": "#4B5563",
    "success": "#7EE787",
    "error": "#FF5C5C",
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
    if "Graphite" not in THEMES:
        THEMES["Graphite (Default)"] = DEFAULT_GRAPHITE


load_themes()


def _complete_theme(theme_data):
    """Return a complete color palette for a theme.

    Theme JSON files may omit optional/derived colors.  Keeping this merge in
    one place prevents old Catppuccin-only values from leaking into another
    theme when the user switches themes.
    """
    theme_data = theme_data or {}
    complete = dict(DEFAULT_GRAPHITE)
    complete.update(theme_data)

    if "selection_bg" not in theme_data:
        complete["selection_bg"] = complete["sash_color"]
    if "line_number_fg" not in theme_data:
        complete["line_number_fg"] = complete["fg_dim"]
    if "success" not in theme_data:
        complete["success"] = complete["console_fg"]
    if "error" not in theme_data:
        complete["error"] = complete["console_err"]
    return complete


def get_color(name, fallback=None):
    """Read a color from the active theme with a safe fallback."""
    return COLORS.get(
        name,
        fallback if fallback is not None else DEFAULT_GRAPHITE.get(name, "#ffffff"),
    )


CURRENT_THEME = "Graphite"
COLORS = _complete_theme(THEMES.get(CURRENT_THEME, DEFAULT_GRAPHITE))

if sys.platform == "win32":
    _FONT_UI = "Segoe UI"
    _FONT_MONO = "Consolas"
else:
    # Linux / macOS — fuentes compatibles
    _FONT_UI = "DejaVu Sans"
    _FONT_MONO = "DejaVu Sans Mono"

FONTS = {
    "ui": (_FONT_UI, 10),
    "header": (_FONT_UI, 9, "bold"),
    "editor": (_FONT_MONO, 12),
    "console": (_FONT_MONO, 11),
}


def set_theme(theme_name):
    global CURRENT_THEME
    if theme_name in THEMES:
        CURRENT_THEME = theme_name
        COLORS.clear()
        COLORS.update(_complete_theme(THEMES[theme_name]))


def apply_theme(
    root,
    editor,
    console,
    paned_window,
    editor_label,
    console_label,
    line_numbers,
    status_bar,
    toolbar=None,
    toolbar_divider=None,
):
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
        arrowcolor=COLORS["fg_dim"],
    )
    style.map(
        "TScrollbar",
        background=[("active", COLORS["sash_color"]), ("pressed", COLORS["accent"])],
    )

    editor_label.config(
        bg=COLORS["bg_header"],
        fg=COLORS["fg_dim"],
        font=FONTS["header"],
        padx=12,
        pady=8,
        bd=0,
        anchor="w",
    )
    console_label.config(
        bg=COLORS["bg_header"],
        fg=COLORS["fg_dim"],
        font=FONTS["header"],
        padx=12,
        pady=8,
        bd=0,
        anchor="w",
    )

    editor.config(
        bg=COLORS["bg_editor"],
        fg=COLORS["fg_light"],
        insertbackground=COLORS["accent"],
        selectbackground=COLORS["selection_bg"],
        selectforeground=COLORS["fg_light"],
        font=FONTS["editor"],
        padx=10,
        pady=10,
        bd=0,
        highlightthickness=0,
    )

    line_numbers.config(
        bg=COLORS["bg_header"],
        fg=COLORS["line_number_fg"],
        font=FONTS["editor"],
        padx=8,
        pady=10,
        bd=0,
        width=4,
        state=tk.DISABLED,
        highlightthickness=0,
    )

    console.config(
        bg=COLORS["console_bg"],
        fg=COLORS["console_fg"],
        insertbackground=COLORS["accent"],
        selectbackground=COLORS["selection_bg"],
        selectforeground=COLORS["fg_light"],
        font=FONTS["console"],
        padx=12,
        pady=12,
        bd=0,
        highlightthickness=0,
    )

    status_bar.config(bg=COLORS["bg_header"], bd=0, relief=tk.FLAT)

    paned_window.config(
        bg=COLORS["bg_dark"], bd=0, sashwidth=4, sashpad=1, sashrelief=tk.FLAT
    )


def style_search_dialog(dialog, search_entry, listbox, title_label):
    dialog.configure(bg=COLORS["bg_dark"])

    title_label.config(bg=COLORS["bg_dark"], fg=COLORS["accent"], font=FONTS["header"])

    search_entry.config(
        bg=COLORS["bg_editor"],
        fg=COLORS["fg_light"],
        insertbackground=COLORS["accent"],
        font=FONTS["ui"],
        bd=0,
        highlightthickness=1,
        highlightbackground=COLORS["sash_color"],
        highlightcolor=COLORS["accent"],
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
        selectforeground=COLORS["bg_dark"],
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
        selectforeground=COLORS["bg_dark"],
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
        cursor="hand2",
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
        relief=tk.FLAT,
    )
