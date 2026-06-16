"""
File Explorer module for Lithium IDE.
Provides a treeview-based file explorer panel that displays the current folder structure.
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import shutil


class FileExplorer:
    """A file explorer panel that displays the project folder structure."""
    
    def __init__(self, parent, controller, theme_colors, theme_fonts):
        """
        Initialize the File Explorer panel.
        
        Args:
            parent: The parent widget (typically a Frame)
            controller: The LithiumEditorController instance for file operations
            theme_colors: Dictionary of theme colors
            theme_fonts: Dictionary of theme fonts
        """
        self.parent = parent
        self.controller = controller
        self.colors = theme_colors
        self.fonts = theme_fonts
        self.current_folder = None
        self.tree = None
        self.icons = {}
        
        self._setup_ui()
        self._load_icons()
        
    def _setup_ui(self):
        """Set up the file explorer UI components."""
        # Main container frame
        self.frame = tk.Frame(self.parent, bg=self.colors["bg_dark"])
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Header frame
        header_frame = tk.Frame(self.frame, bg=self.colors["bg_header"], height=35)
        header_frame.pack(fill=tk.X, side=tk.TOP)
        header_frame.pack_propagate(False)
        
        # Header label
        self.header_label = tk.Label(
            header_frame,
            text="EXPLORER",
            font=self.fonts["header"],
            fg=self.colors["fg_dim"],
            bg=self.colors["bg_header"]
        )
        self.header_label.pack(side=tk.LEFT, padx=12, pady=8)
        
        # Header buttons
        self.btn_refresh = tk.Button(
            header_frame,
            text="⟳",
            font=("Segoe UI", 10),
            fg=self.colors["fg_dim"],
            bg=self.colors["bg_header"],
            bd=0,
            activebackground=self.colors["sash_color"],
            activeforeground=self.colors["accent"],
            command=self.refresh,
            cursor="hand2"
        )
        self.btn_refresh.pack(side=tk.RIGHT, padx=4)
        
        self.btn_collapse = tk.Button(
            header_frame,
            text="≡",
            font=("Segoe UI", 10),
            fg=self.colors["fg_dim"],
            bg=self.colors["bg_header"],
            bd=0,
            activebackground=self.colors["sash_color"],
            activeforeground=self.colors["accent"],
            command=self.collapse_all,
            cursor="hand2"
        )
        self.btn_collapse.pack(side=tk.RIGHT, padx=4)
        
        # Folder path bar
        path_frame = tk.Frame(self.frame, bg=self.colors["bg_editor"], height=28)
        path_frame.pack(fill=tk.X, side=tk.TOP, padx=8, pady=(4, 0))
        path_frame.pack_propagate(False)
        
        self.path_label = tk.Label(
            path_frame,
            text="No folder opened",
            font=("Segoe UI", 9),
            fg=self.colors["fg_dim"],
            bg=self.colors["bg_editor"],
            anchor="w",
            padx=8
        )
        self.path_label.pack(fill=tk.X, expand=True)
        
        # Treeview with scrollbar
        tree_frame = tk.Frame(self.frame, bg=self.colors["bg_editor"])
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))
        
        # Create treeview
        self.tree = ttk.Treeview(
            tree_frame,
            show="tree",
            selectmode="browse"
        )
        
        # Configure scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind events
        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<ButtonRelease-3>", self._show_context_menu)
        self.tree.bind("<Return>", self._on_enter_key)
        
        # Configure treeview styles
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
            font=self.fonts["ui"]
        )
        
        style.configure(
            "FileExplorer.Treeview.Heading",
            background=self.colors["bg_header"],
            foreground=self.colors["fg_dim"],
            borderwidth=0,
            font=self.fonts["header"]
        )
        
        style.map(
            "FileExplorer.Treeview",
            background=[("selected", self.colors["sash_color"])],
            foreground=[("selected", self.colors["fg_light"])]
        )
        
        # Apply the style
        self.tree.configure(style="FileExplorer.Treeview")
        
    def _load_icons(self):
        """Load icons for files and folders."""
        # Try to load icons from assets, use text fallback if not available
        try:
            self.icons["folder"] = tk.PhotoImage(file="src/assets/folder.png")
        except Exception:
            self.icons["folder"] = None
            
        try:
            self.icons["file"] = tk.PhotoImage(file="src/assets/file.png")
        except Exception:
            self.icons["file"] = None
            
        try:
            self.icons["python"] = tk.PhotoImage(file="src/assets/python.png")
        except Exception:
            self.icons["python"] = None
            
        try:
            self.icons["javascript"] = tk.PhotoImage(file="src/assets/javascript.png")
        except Exception:
            self.icons["javascript"] = None
            
        try:
            self.icons["html"] = tk.PhotoImage(file="src/assets/html.png")
        except Exception:
            self.icons["html"] = None
            
        try:
            self.icons["css"] = tk.PhotoImage(file="src/assets/css.png")
        except Exception:
            self.icons["css"] = None
            
        try:
            self.icons["generic"] = tk.PhotoImage(file="src/assets/generic.png")
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
        
        # Clear existing tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Populate tree
        self._populate_tree(self.tree, "", folder_path)
        
        # Expand root
        self.tree.item("", open=True)
    
    def _populate_tree(self, tree, parent, path):
        """
        Recursively populate the tree with files and folders.
        
        Args:
            tree: The Treeview widget
            parent: Parent item ID
            path: File system path
        """
        try:
            items = sorted(os.listdir(path), key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()))
        except PermissionError:
            return
        
        for item in items:
            # Skip hidden files and common ignored folders
            if item.startswith(".") or item in ["__pycache__", "node_modules", ".git"]:
                continue
                
            item_path = os.path.join(path, item)
            
            if os.path.isdir(item_path):
                # Insert folder with empty placeholder for expandable arrow
                node = tree.insert(parent, "end", text=f"📁 {item}", values=(item_path,), open=False)
                # Recursively populate subdirectories (but only one level deep for performance)
                self._populate_tree(tree, node, item_path)
            else:
                # Insert file
                icon = self._get_icon_for_file(item)
                if icon:
                    tree.insert(parent, "end", text=f"  {item}", values=(item_path,), image=icon)
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
    
    def _on_enter_key(self, event):
        """Handle Enter key press on tree item."""
        self._on_double_click(event)
    
    def _open_file(self, path):
        """
        Open a file in the editor.
        
        Args:
            path: Path to the file to open
        """
        if self.controller:
            # Check if file is too large
            try:
                file_size = os.path.getsize(path)
                if file_size > 5 * 1024 * 1024:  # 5MB limit
                    if not messagebox.askyesno(
                        "Large File",
                        f"The file '{os.path.basename(path)}' is large ({file_size / (1024*1024):.1f}MB). "
                        "Opening it may slow down the editor. Do you want to continue?"
                    ):
                        return
            except OSError:
                pass
            
            self.controller.file_path = path
            try:
                with open(path, "r", encoding="utf-8") as file:
                    code = file.read()
                    self.controller.editor.delete("1.0", tk.END)
                    self.controller.editor.insert("1.0", code)
                self.controller.root.title(f"{os.path.basename(path)} - Lithium IDE")
                self.controller.update_line_numbers()
                self.controller.update_status()
                self.controller.save_cache()
            except UnicodeDecodeError:
                messagebox.showerror(
                    "Error",
                    f"Cannot open file: '{os.path.basename(path)}' is not a text file."
                )
            except Exception as e:
                messagebox.showerror("Error", f"Cannot open file: {e}")
    
    def _show_context_menu(self, event):
        """Show context menu on right-click."""
        # Select the item under cursor
        item = self.tree.identify_row(event.y)
        
        # Create context menu
        menu = tk.Menu(self.parent, tearoff=0, bg=self.colors["bg_header"], fg=self.colors["fg_light"])
        
        if item:
            # Click on an item
            self.tree.selection_set(item)
            values = self.tree.item(item, "values")
            
            if values:
                path = values[0]
                is_dir = os.path.isdir(path)
                is_file = os.path.isfile(path)
                
                if is_file:
                    menu.add_command(label="Open", command=lambda: self._open_file(path))
                    menu.add_separator()
                    menu.add_command(label="Rename", command=lambda: self._rename_item(path, item))
                    menu.add_command(label="Delete", command=lambda: self._delete_item(path, item))
                    menu.add_separator()
                    menu.add_command(label="Copy Path", command=lambda: self._copy_path(path))
                elif is_dir:
                    menu.add_command(label="Open Folder", command=lambda: self.load_folder(path))
                    menu.add_separator()
                    menu.add_command(label="New File", command=lambda: self._new_file(item))
                    menu.add_command(label="New Folder", command=lambda: self._new_folder(item))
                    menu.add_separator()
                    menu.add_command(label="Rename", command=lambda: self._rename_item(path, item))
                    menu.add_command(label="Delete", command=lambda: self._delete_item(path, item))
        else:
            # Click on empty area - show options to create new items in current folder
            if self.current_folder:
                menu.add_command(label="New File", command=lambda: self._new_file_in_path(self.current_folder))
                menu.add_command(label="New Folder", command=lambda: self._new_folder_in_path(self.current_folder))
            else:
                menu.add_command(label="Open Folder", command=self.open_folder_dialog)
        
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
    
    def _new_file_in_path(self, folder_path):
        """Create a new file in the specified folder path."""
        # Create dialog for filename
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
            bg=self.colors["bg_dark"]
        ).pack(pady=(15, 5))
        
        entry = tk.Entry(
            dialog,
            font=self.fonts["ui"],
            bg=self.colors["bg_editor"],
            fg=self.colors["fg_light"],
            insertbackground=self.colors["accent"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["sash_color"]
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
            command=create
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
            command=dialog.destroy
        ).pack(side=tk.LEFT, padx=5)
    
    def _new_folder_in_path(self, folder_path):
        """Create a new folder in the specified folder path."""
        # Create dialog for folder name
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
            bg=self.colors["bg_dark"]
        ).pack(pady=(15, 5))
        
        entry = tk.Entry(
            dialog,
            font=self.fonts["ui"],
            bg=self.colors["bg_editor"],
            fg=self.colors["fg_light"],
            insertbackground=self.colors["accent"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["sash_color"]
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
            command=create
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
            command=dialog.destroy
        ).pack(side=tk.LEFT, padx=5)
    
    def _new_file(self, parent_item):
        """Create a new file in the selected folder."""
        values = self.tree.item(parent_item, "values")
        if not values:
            return
        
        folder_path = values[0]
        
        # Create dialog for filename
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
            bg=self.colors["bg_dark"]
        ).pack(pady=(15, 5))
        
        entry = tk.Entry(
            dialog,
            font=self.fonts["ui"],
            bg=self.colors["bg_editor"],
            fg=self.colors["fg_light"],
            insertbackground=self.colors["accent"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["sash_color"]
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
            command=create
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
            command=dialog.destroy
        ).pack(side=tk.LEFT, padx=5)
    
    def _new_folder(self, parent_item):
        """Create a new folder in the selected folder."""
        values = self.tree.item(parent_item, "values")
        if not values:
            return
        
        folder_path = values[0]
        
        # Create dialog for folder name
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
            bg=self.colors["bg_dark"]
        ).pack(pady=(15, 5))
        
        entry = tk.Entry(
            dialog,
            font=self.fonts["ui"],
            bg=self.colors["bg_editor"],
            fg=self.colors["fg_light"],
            insertbackground=self.colors["accent"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["sash_color"]
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
            command=create
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
            command=dialog.destroy
        ).pack(side=tk.LEFT, padx=5)
    
    def _rename_item(self, path, item_id):
        """Rename a file or folder."""
        old_name = os.path.basename(path)
        
        # Create dialog for new name
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
            bg=self.colors["bg_dark"]
        ).pack(pady=(15, 5))
        
        entry = tk.Entry(
            dialog,
            font=self.fonts["ui"],
            bg=self.colors["bg_editor"],
            fg=self.colors["fg_light"],
            insertbackground=self.colors["accent"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.colors["sash_color"]
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
            command=rename
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
            command=dialog.destroy
        ).pack(side=tk.LEFT, padx=5)
    
    def _delete_item(self, path, item_id):
        """Delete a file or folder."""
        name = os.path.basename(path)
        is_dir = os.path.isdir(path)
        
        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete {'folder' if is_dir else 'file'} '{name}'?\n"
            f"{'This action cannot be undone.' if is_dir else ''}"
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
        # Update colors reference
        self.colors = self.colors  # Already updated via reference
        
        # Update frame backgrounds
        self.frame.configure(bg=self.colors["bg_dark"])
        
        # Update header
        for widget in self.frame.winfo_children():
            if isinstance(widget, tk.Frame):
                children = widget.winfo_children()
                for child in children:
                    if isinstance(child, tk.Label) and child.cget("text") == "EXPLORER":
                        child.configure(bg=self.colors["bg_header"], fg=self.colors["fg_dim"])
                    elif isinstance(child, tk.Button):
                        child.configure(bg=self.colors["bg_header"], fg=self.colors["fg_dim"])
        
        # Update path bar
        # Reconfigure tree style
        self._configure_tree_style()
    
    def get_frame(self):
        """Get the main frame widget."""
        return self.frame