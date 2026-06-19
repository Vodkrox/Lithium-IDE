"""
File Explorer module for Lithium IDE.
Provides a treeview-based file explorer panel that displays the current folder structure.
"""

import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.utils import resource_path


class FileExplorer:
    """A file explorer panel that displays the project folder structure."""

    def __init__(
        self,
        parent,
        controller,
        theme_colors,
        theme_fonts,
        on_folder_open_callback=None,
    ):
        """
        Initialize the File Explorer panel.

        Args:
            parent: The parent widget (typically a Frame)
            controller: The LithiumEditorController instance for file operations
            theme_colors: Dictionary of theme colors
            theme_fonts: Dictionary of theme fonts
            on_folder_open_callback: Optional callable(c Folder path) when a folder is opened
        """
        self.parent = parent
        self.controller = controller
        self.colors = theme_colors
        self.fonts = theme_fonts
        self.current_folder = None
        self.on_folder_open_callback = on_folder_open_callback
        self.tree = None
        self.icons = {}

        self._setup_ui()
        self._load_icons()

    def _setup_ui(self):
        """Set up the file explorer UI components."""
        self.frame = tk.Frame(self.parent, bg=self.colors["bg_dark"])
        self.frame.pack(fill=tk.BOTH, expand=True)

        self.header_frame = tk.Frame(self.frame, bg=self.colors["bg_header"], height=35)
        self.header_frame.pack(fill=tk.X, side=tk.TOP)
        self.header_frame.pack_propagate(False)

        self.header_label = tk.Label(
            self.header_frame,
            text="EXPLORER",
            font=self.fonts["header"],
            fg=self.colors["fg_dim"],
            bg=self.colors["bg_header"],
        )
        self.header_label.pack(side=tk.LEFT, padx=12, pady=8)

        self.btn_refresh = tk.Button(
            self.header_frame,
            text="⟳",
            font=("Segoe UI", 10),
            fg=self.colors["fg_dim"],
            bg=self.colors["bg_header"],
            bd=0,
            activebackground=self.colors["sash_color"],
            activeforeground=self.colors["accent"],
            command=self.refresh,
            cursor="hand2",
        )
        self.btn_refresh.pack(side=tk.RIGHT, padx=4)

        self.btn_collapse = tk.Button(
            self.header_frame,
            text="≡",
            font=("Segoe UI", 10),
            fg=self.colors["fg_dim"],
            bg=self.colors["bg_header"],
            bd=0,
            activebackground=self.colors["sash_color"],
            activeforeground=self.colors["accent"],
            command=self.collapse_all,
            cursor="hand2",
        )
        self.btn_collapse.pack(side=tk.RIGHT, padx=4)

        self.path_frame = tk.Frame(self.frame, bg=self.colors["bg_editor"], height=28)
        self.path_frame.pack(fill=tk.X, side=tk.TOP, padx=8, pady=(4, 0))
        self.path_frame.pack_propagate(False)

        self.btn_back = tk.Button(
            self.path_frame,
            text="←",
            font=("Segoe UI", 10),
            fg=self.colors["fg_dim"],
            bg=self.colors["bg_editor"],
            bd=0,
            activebackground=self.colors["sash_color"],
            activeforeground=self.colors["accent"],
            command=self.go_to_parent,
            cursor="hand2",
        )
        self.btn_back.pack(side=tk.LEFT, padx=(4, 6))
        self.btn_back.config(state=tk.DISABLED)

        self.path_label = tk.Label(
            self.path_frame,
            text="No folder opened",
            font=("Segoe UI", 9),
            fg=self.colors["fg_dim"],
            bg=self.colors["bg_editor"],
            anchor="w",
            padx=8,
        )
        self.path_label.pack(fill=tk.X, expand=True)

        self.tree_frame = tk.Frame(self.frame, bg=self.colors["bg_editor"])
        self.tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        self.tree = ttk.Treeview(self.tree_frame, show="tree", selectmode="browse")

        self.scrollbar = ttk.Scrollbar(
            self.tree_frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=self.scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<ButtonRelease-3>", self._show_context_menu)
        self.tree.bind("<Return>", self._on_enter_key)

        self._configure_tree_style()

    def _configure_tree_style(self):
        """Configure the treeview style to match the theme."""
        style = ttk.Style()

        style.configure(
            "FileExplorer.Treeview",
            background=self.colors["bg_editor"],
            foreground=self.colors["fg_light"],
            fieldbackground=self.colors["bg_editor"],
            borderwidth=0,
            font=self.fonts["ui"],
        )

        style.configure(
            "FileExplorer.Treeview.Heading",
            background=self.colors["bg_header"],
            foreground=self.colors["fg_dim"],
            borderwidth=0,
            font=self.fonts["header"],
        )

        style.map(
            "FileExplorer.Treeview",
            background=[("selected", self.colors["sash_color"])],
            foreground=[("selected", self.colors["fg_light"])],
        )

        self.tree.configure(style="FileExplorer.Treeview")

    def _load_icons(self):
        """Load icons for files and folders."""
        try:
            self.icons["folder"] = tk.PhotoImage(
                file=resource_path("src/assets/folder.png")
            )
        except Exception:
            self.icons["folder"] = None

        try:
            self.icons["file"] = tk.PhotoImage(
                file=resource_path("src/assets/file.png")
            )
        except Exception:
            self.icons["file"] = None

        try:
            self.icons["python"] = tk.PhotoImage(
                file=resource_path("src/assets/python.png")
            )
        except Exception:
            self.icons["python"] = None

        try:
            self.icons["javascript"] = tk.PhotoImage(
                file=resource_path("src/assets/javascript.png")
            )
        except Exception:
            self.icons["javascript"] = None

        try:
            self.icons["html"] = tk.PhotoImage(
                file=resource_path("src/assets/html.png")
            )
        except Exception:
            self.icons["html"] = None

        try:
            self.icons["css"] = tk.PhotoImage(file=resource_path("src/assets/css.png"))
        except Exception:
            self.icons["css"] = None

        try:
            self.icons["generic"] = tk.PhotoImage(
                file=resource_path("src/assets/generic.png")
            )
        except Exception:
            self.icons["generic"] = None

    def _get_icon_for_file(self, filename):
        """Get the appropriate icon for a file based on its extension."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "javascript",
            ".tsx": "javascript",
            ".html": "html",
            ".htm": "html",
            ".css": "css",
            ".scss": "css",
            ".sass": "css",
            ".json": "generic",
            ".md": "generic",
            ".txt": "generic",
            ".xml": "generic",
            ".yaml": "generic",
            ".yml": "generic",
            ".toml": "generic",
            ".ini": "generic",
            ".cfg": "generic",
            ".env": "generic",
        }

        ext = os.path.splitext(filename)[1].lower()
        icon_key = ext_map.get(ext, "generic")
        return self.icons.get(icon_key, self.icons.get("generic"))

    def open_folder_dialog(self):
        """Open a folder selection dialog."""
        folder = filedialog.askdirectory(title="Open Folder")
        if folder:
            self.load_folder(folder)

    def load_folder(self, folder_path):
        """
        Load a folder into the file explorer.

        Args:
            folder_path: Path to the folder to load
        """
        if not os.path.isdir(folder_path):
            messagebox.showerror("Error", "The selected path is not a valid directory.")
            return

        self.current_folder = folder_path
        self.path_label.config(text=folder_path)
        for item in self.tree.get_children():
            self.tree.delete(item)

        if self.on_folder_open_callback:
            self.on_folder_open_callback(folder_path)

        self._populate_tree(self.tree, "", folder_path)
        self.tree.item("", open=True)
        parent = os.path.dirname(folder_path)
        if parent and parent != folder_path:
            try:
                self.btn_back.config(state=tk.NORMAL)
            except Exception:
                pass
        else:
            try:
                self.btn_back.config(state=tk.DISABLED)
            except Exception:
                pass

    def _find_item_by_path(self, parent, target_path):
        """Recursively search the tree for an item matching target_path and return its item id or None."""
        for child in self.tree.get_children(parent):
            vals = self.tree.item(child, "values")
            if vals and vals[0] == target_path:
                return child
            found = self._find_item_by_path(child, target_path)
            if found:
                return found
        return None

    def mark_file_dirty(self, file_path, is_dirty):
        """Mark the file in the treeview with an unsaved marker (e.g., a dot) next to its name.

        Args:
            file_path: absolute path to the file to mark
            is_dirty: boolean indicating dirty state
        """
        if not file_path or not os.path.exists(file_path):
            return
        item_id = self._find_item_by_path("", file_path)
        if not item_id:
            return
        cur_text = self.tree.item(item_id, "text") or ""
        stripped = cur_text.replace(" *", "").replace(" • Unsaved", "").strip()
        leading = ""
        if cur_text.startswith("  "):
            leading = "  "
        new_text = f"{leading}{stripped}{' *' if is_dirty else ''}"
        try:
            self.tree.item(item_id, text=new_text)
        except Exception:
            pass
        return

    def _populate_tree(self, tree, parent, path):
        """
        Recursively populate the tree with files and folders.

        Args:
            tree: The Treeview widget
            parent: Parent item ID
            path: File system path
        """
        try:
            items = sorted(
                os.listdir(path),
                key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()),
            )
        except PermissionError:
            return

        for item in items:
            if item.startswith(".") or item in ["__pycache__", "node_modules", ".git"]:
                continue

            item_path = os.path.join(path, item)

            if os.path.isdir(item_path):
                node = tree.insert(
                    parent, "end", text=f"📁 {item}", values=(item_path,), open=False
                )
                self._populate_tree(tree, node, item_path)
            else:
                icon = self._get_icon_for_file(item)
                if icon:
                    tree.insert(
                        parent, "end", text=f"  {item}", values=(item_path,), image=icon
                    )
                else:
                    tree.insert(parent, "end", text=f"  {item}", values=(item_path,))

    def _on_double_click(self, event):
        """Handle double-click on tree item."""
        selection = self.tree.selection()
        if not selection:
            return

        item = selection[0]
        values = self.tree.item(item, "values")

        if values:
            path = values[0]
            if os.path.isfile(path):
                self._open_file(path)
            elif os.path.isdir(path):
                try:
                    self.load_folder(path)
                except Exception:
                    pass

    def _on_enter_key(self, event):
        """Handle Enter key press on tree item."""
        self._on_double_click(event)

    def _open_file(self, path):
        """
        Open a file in the editor. Prompts to save if current file has unsaved changes.

        Args:
            path: Path to the file to open
        """
        if not self.controller:
            return

        # Check for unsaved changes before switching
        if self.controller.has_unsaved_changes and self.controller.file_path:
            current_name = os.path.basename(self.controller.file_path)
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                f"'{current_name}' has unsaved changes.\n\n"
                "Yes  = Save changes and open the new file\n"
                "No   = Discard changes and open the new file\n"
                "Cancel = Go back",
            )
            if result is None:  # Cancel
                return
            if result:  # Yes → save
                if not self.controller.save_file():
                    messagebox.showwarning(
                        "Save Failed",
                        "Could not save the current file. Open cancelled.",
                    )
                    return

        try:
            file_size = os.path.getsize(path)
            if file_size > 5 * 1024 * 1024:
                if not messagebox.askyesno(
                    "Large File",
                    f"The file '{os.path.basename(path)}' is large ({file_size / (1024 * 1024):.1f}MB). "
                    "Opening it may slow down the editor. Do you want to continue?",
                ):
                    return
        except OSError:
            pass

        self.controller.file_path = path
        try:
            with open(path, "r", encoding="utf-8") as file:
                code = file.read()
                self.controller.editor.config(state=tk.NORMAL)
                self.controller.editor.delete("1.0", tk.END)
                self.controller.editor.insert("1.0", code)
            self.controller.root.title(f"{os.path.basename(path)} - Lithium IDE")
            self.controller.update_line_numbers()
            self.controller.update_status()
            if self.controller.on_file_open_callback:
                self.controller.on_file_open_callback()
            self.controller.has_unsaved_changes = False
            self.controller.mark_clean()
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open file: {e}")

    def _show_context_menu(self, event):
        """Show context menu on right-click."""
        item = self.tree.identify_row(event.y)

        menu = tk.Menu(
            self.parent,
            tearoff=0,
            bg=self.colors["bg_header"],
            fg=self.colors["fg_light"],
        )

        if item:
            self.tree.selection_set(item)
            values = self.tree.item(item, "values")

            if values:
                path = values[0]
                is_dir = os.path.isdir(path)
                is_file = os.path.isfile(path)

                if is_file:
                    menu.add_command(
                        label="Open", command=lambda: self._open_file(path)
                    )
                    menu.add_separator()
                    menu.add_command(
                        label="Rename", command=lambda: self._rename_item(path, item)
                    )
                    menu.add_command(
                        label="Delete", command=lambda: self._delete_item(path, item)
                    )
                    menu.add_separator()
                    menu.add_command(
                        label="Copy Path", command=lambda: self._copy_path(path)
                    )
                elif is_dir:
                    menu.add_command(
                        label="Open Folder", command=lambda: self.load_folder(path)
                    )
                    menu.add_separator()
                    menu.add_command(
                        label="New File", command=lambda: self._new_file(item)
                    )
                    menu.add_command(
                        label="New Folder", command=lambda: self._new_folder(item)
                    )
                    menu.add_separator()
                    menu.add_command(
                        label="Rename", command=lambda: self._rename_item(path, item)
                    )
                    menu.add_command(
                        label="Delete", command=lambda: self._delete_item(path, item)
                    )
        else:
            if self.current_folder:
                menu.add_command(
                    label="New File",
                    command=lambda: self._new_file_in_path(self.current_folder),
                )
                menu.add_command(
                    label="New Folder",
                    command=lambda: self._new_folder_in_path(self.current_folder),
                )
            else:
                menu.add_command(label="Open Folder", command=self.open_folder_dialog)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _new_file_in_path(self, folder_path):
        """Create a new file in the specified folder path."""
        dialog = tk.Toplevel(self.parent)
        dialog.title("New File")
        dialog.geometry("300x120")
        dialog.transient(self.parent)
        dialog.grab_set()
        dialog.configure(bg=self.colors["bg_dark"])

        tk.Label(
            dialog,
            text="Enter file name:",
            font=self.fonts["ui"],
            fg=self.colors["fg_light"],
            bg=self.colors["bg_dark"],
        ).pack(pady=(15, 5))

        entry = tk.Entry(
            dialog,
            font=self.fonts["ui"],
            bg=self.colors["bg_editor"],
            fg=self.colors["fg_light"],
            insertbackground=self.colors["accent"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["sash_color"],
        )
        entry.pack(fill=tk.X, padx=20, pady=5)
        entry.focus_set()

        def create():
            filename = entry.get().strip()
            if filename:
                file_path = os.path.join(folder_path, filename)
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        pass
                    self.refresh()
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("Error", f"Cannot create file: {e}")

        def on_enter(event):
            create()

        entry.bind("<Return>", on_enter)

        btn_frame = tk.Frame(dialog, bg=self.colors["bg_dark"])
        btn_frame.pack(pady=10)

        tk.Button(
            btn_frame,
            text="Create",
            font=self.fonts["ui"],
            bg=self.colors["accent"],
            fg=self.colors["bg_dark"],
            bd=0,
            padx=15,
            pady=5,
            cursor="hand2",
            command=create,
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame,
            text="Cancel",
            font=self.fonts["ui"],
            bg=self.colors["sash_color"],
            fg=self.colors["fg_light"],
            bd=0,
            padx=15,
            pady=5,
            cursor="hand2",
            command=dialog.destroy,
        ).pack(side=tk.LEFT, padx=5)

    def go_to_parent(self):
        """Navigate to the parent folder of the currently-opened folder."""
        if not self.current_folder:
            return
        parent = os.path.dirname(self.current_folder)
        if parent and os.path.isdir(parent) and parent != self.current_folder:
            try:
                self.load_folder(parent)
            except Exception:
                pass

    def _new_folder_in_path(self, folder_path):
        """Create a new folder in the specified folder path."""
        dialog = tk.Toplevel(self.parent)
        dialog.title("New Folder")
        dialog.geometry("300x120")
        dialog.transient(self.parent)
        dialog.grab_set()
        dialog.configure(bg=self.colors["bg_dark"])

        tk.Label(
            dialog,
            text="Enter folder name:",
            font=self.fonts["ui"],
            fg=self.colors["fg_light"],
            bg=self.colors["bg_dark"],
        ).pack(pady=(15, 5))

        entry = tk.Entry(
            dialog,
            font=self.fonts["ui"],
            bg=self.colors["bg_editor"],
            fg=self.colors["fg_light"],
            insertbackground=self.colors["accent"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["sash_color"],
        )
        entry.pack(fill=tk.X, padx=20, pady=5)
        entry.focus_set()

        def create():
            folder_name = entry.get().strip()
            if folder_name:
                new_folder_path = os.path.join(folder_path, folder_name)
                try:
                    os.makedirs(new_folder_path, exist_ok=True)
                    self.refresh()
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("Error", f"Cannot create folder: {e}")

        def on_enter(event):
            create()

        entry.bind("<Return>", on_enter)

        btn_frame = tk.Frame(dialog, bg=self.colors["bg_dark"])
        btn_frame.pack(pady=10)

        tk.Button(
            btn_frame,
            text="Create",
            font=self.fonts["ui"],
            bg=self.colors["accent"],
            fg=self.colors["bg_dark"],
            bd=0,
            padx=15,
            pady=5,
            cursor="hand2",
            command=create,
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame,
            text="Cancel",
            font=self.fonts["ui"],
            bg=self.colors["sash_color"],
            fg=self.colors["fg_light"],
            bd=0,
            padx=15,
            pady=5,
            cursor="hand2",
            command=dialog.destroy,
        ).pack(side=tk.LEFT, padx=5)

    def _new_file(self, parent_item):
        """Create a new file in the selected folder."""
        values = self.tree.item(parent_item, "values")
        if not values:
            return

        folder_path = values[0]

        dialog = tk.Toplevel(self.parent)
        dialog.title("New File")
        dialog.geometry("300x120")
        dialog.transient(self.parent)
        dialog.grab_set()
        dialog.configure(bg=self.colors["bg_dark"])

        tk.Label(
            dialog,
            text="Enter file name:",
            font=self.fonts["ui"],
            fg=self.colors["fg_light"],
            bg=self.colors["bg_dark"],
        ).pack(pady=(15, 5))

        entry = tk.Entry(
            dialog,
            font=self.fonts["ui"],
            bg=self.colors["bg_editor"],
            fg=self.colors["fg_light"],
            insertbackground=self.colors["accent"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["sash_color"],
        )
        entry.pack(fill=tk.X, padx=20, pady=5)
        entry.focus_set()

        def create():
            filename = entry.get().strip()
            if filename:
                file_path = os.path.join(folder_path, filename)
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        pass
                    self.refresh()
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("Error", f"Cannot create file: {e}")

        def on_enter(event):
            create()

        entry.bind("<Return>", on_enter)

        btn_frame = tk.Frame(dialog, bg=self.colors["bg_dark"])
        btn_frame.pack(pady=10)

        tk.Button(
            btn_frame,
            text="Create",
            font=self.fonts["ui"],
            bg=self.colors["accent"],
            fg=self.colors["bg_dark"],
            bd=0,
            padx=15,
            pady=5,
            cursor="hand2",
            command=create,
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame,
            text="Cancel",
            font=self.fonts["ui"],
            bg=self.colors["sash_color"],
            fg=self.colors["fg_light"],
            bd=0,
            padx=15,
            pady=5,
            cursor="hand2",
            command=dialog.destroy,
        ).pack(side=tk.LEFT, padx=5)

    def _new_folder(self, parent_item):
        """Create a new folder in the selected folder."""
        values = self.tree.item(parent_item, "values")
        if not values:
            return

        folder_path = values[0]

        dialog = tk.Toplevel(self.parent)
        dialog.title("New Folder")
        dialog.geometry("300x120")
        dialog.transient(self.parent)
        dialog.grab_set()
        dialog.configure(bg=self.colors["bg_dark"])

        tk.Label(
            dialog,
            text="Enter folder name:",
            font=self.fonts["ui"],
            fg=self.colors["fg_light"],
            bg=self.colors["bg_dark"],
        ).pack(pady=(15, 5))

        entry = tk.Entry(
            dialog,
            font=self.fonts["ui"],
            bg=self.colors["bg_editor"],
            fg=self.colors["fg_light"],
            insertbackground=self.colors["accent"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["sash_color"],
        )
        entry.pack(fill=tk.X, padx=20, pady=5)
        entry.focus_set()

        def create():
            folder_name = entry.get().strip()
            if folder_name:
                new_folder_path = os.path.join(folder_path, folder_name)
                try:
                    os.makedirs(new_folder_path, exist_ok=True)
                    self.refresh()
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("Error", f"Cannot create folder: {e}")

        def on_enter(event):
            create()

        entry.bind("<Return>", on_enter)

        btn_frame = tk.Frame(dialog, bg=self.colors["bg_dark"])
        btn_frame.pack(pady=10)

        tk.Button(
            btn_frame,
            text="Create",
            font=self.fonts["ui"],
            bg=self.colors["accent"],
            fg=self.colors["bg_dark"],
            bd=0,
            padx=15,
            pady=5,
            cursor="hand2",
            command=create,
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame,
            text="Cancel",
            font=self.fonts["ui"],
            bg=self.colors["sash_color"],
            fg=self.colors["fg_light"],
            bd=0,
            padx=15,
            pady=5,
            cursor="hand2",
            command=dialog.destroy,
        ).pack(side=tk.LEFT, padx=5)

    def _rename_item(self, path, item_id):
        """Rename a file or folder."""
        old_name = os.path.basename(path)

        dialog = tk.Toplevel(self.parent)
        dialog.title("Rename")
        dialog.geometry("300x120")
        dialog.transient(self.parent)
        dialog.grab_set()
        dialog.configure(bg=self.colors["bg_dark"])

        tk.Label(
            dialog,
            text="Enter new name:",
            font=self.fonts["ui"],
            fg=self.colors["fg_light"],
            bg=self.colors["bg_dark"],
        ).pack(pady=(15, 5))

        entry = tk.Entry(
            dialog,
            font=self.fonts["ui"],
            bg=self.colors["bg_editor"],
            fg=self.colors["fg_light"],
            insertbackground=self.colors["accent"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["sash_color"],
        )
        entry.pack(fill=tk.X, padx=20, pady=5)
        entry.insert(0, old_name)
        entry.focus_set()
        entry.select_range(0, tk.END)

        def rename():
            new_name = entry.get().strip()
            if new_name and new_name != old_name:
                parent_dir = os.path.dirname(path)
                new_path = os.path.join(parent_dir, new_name)
                try:
                    os.rename(path, new_path)
                    self.refresh()
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("Error", f"Cannot rename: {e}")

        def on_enter(event):
            rename()

        entry.bind("<Return>", on_enter)

        btn_frame = tk.Frame(dialog, bg=self.colors["bg_dark"])
        btn_frame.pack(pady=10)

        tk.Button(
            btn_frame,
            text="Rename",
            font=self.fonts["ui"],
            bg=self.colors["accent"],
            fg=self.colors["bg_dark"],
            bd=0,
            padx=15,
            pady=5,
            cursor="hand2",
            command=rename,
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame,
            text="Cancel",
            font=self.fonts["ui"],
            bg=self.colors["sash_color"],
            fg=self.colors["fg_light"],
            bd=0,
            padx=15,
            pady=5,
            cursor="hand2",
            command=dialog.destroy,
        ).pack(side=tk.LEFT, padx=5)

    def _delete_item(self, path, item_id):
        """Delete a file or folder."""
        name = os.path.basename(path)
        is_dir = os.path.isdir(path)

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete {'folder' if is_dir else 'file'} '{name}'?\n"
            f"{'This action cannot be undone.' if is_dir else ''}",
        )

        if confirm:
            try:
                if is_dir:
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                self.tree.delete(item_id)
            except Exception as e:
                messagebox.showerror("Error", f"Cannot delete: {e}")

    def _copy_path(self, path):
        """Copy the file path to clipboard."""
        self.parent.clipboard_clear()
        self.parent.clipboard_append(path)
        self.parent.update()

    def refresh(self):
        """Refresh the file explorer."""
        if self.current_folder:
            self.load_folder(self.current_folder)

    def collapse_all(self):
        """Collapse all tree nodes."""
        for item in self.tree.get_children():
            self._collapse_recursive(item)

    def _collapse_recursive(self, item):
        """Recursively collapse tree nodes."""
        self.tree.item(item, open=False)
        for child in self.tree.get_children(item):
            self._collapse_recursive(child)

    def apply_theme(self):
        """Apply theme colors to the file explorer."""
        self.frame.configure(bg=self.colors["bg_dark"])
        self.header_frame.configure(bg=self.colors["bg_header"])
        self.header_label.configure(
            bg=self.colors["bg_header"], fg=self.colors["fg_dim"]
        )

        for button in (self.btn_refresh, self.btn_collapse):
            button.configure(
                bg=self.colors["bg_header"],
                fg=self.colors["fg_dim"],
                activebackground=self.colors["sash_color"],
                activeforeground=self.colors["accent"],
            )

        self.path_frame.configure(bg=self.colors["bg_editor"])
        self.btn_back.configure(
            bg=self.colors["bg_editor"],
            fg=self.colors["fg_dim"],
            activebackground=self.colors["sash_color"],
            activeforeground=self.colors["accent"],
        )
        self.path_label.configure(bg=self.colors["bg_editor"], fg=self.colors["fg_dim"])
        self.tree_frame.configure(bg=self.colors["bg_editor"])
        self._configure_tree_style()

    def get_frame(self):
        """Get the main frame widget."""
        return self.frame
