import difflib
import tkinter as tk
from typing import Callable, Optional


class AgenticChangeBar:
    """Represents a unified approval bar for AI-generated changes with diff visualization."""

    def __init__(
        self,
        parent: tk.Widget,
        theme_colors: dict,
        original_content: str,
        new_content: str,
        on_approve: Callable[[], None],
        on_reject: Callable[[], None],
    ):
        """
        Initialize the agentic change bar.

        Args:
            parent: Parent tkinter widget
            theme_colors: Theme color dictionary from theme module
            original_content: Original file content before changes
            new_content: New file content after changes
            on_approve: Callback when user approves changes
            on_reject: Callback when user rejects changes
        """
        self.parent = parent
        self.colors = theme_colors
        self.original = original_content
        self.new = new_content
        self.on_approve = on_approve
        self.on_reject = on_reject
        self.frame = None
        self._compute_diff_stats()

    def _compute_diff_stats(self):
        """Compute added, removed, and modified line counts."""
        orig_lines = self.original.splitlines(keepends=True)
        new_lines = self.new.splitlines(keepends=True)

        matcher = difflib.SequenceMatcher(None, orig_lines, new_lines)
        self.added_lines = 0
        self.removed_lines = 0
        self.modified_lines = 0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                self.removed_lines += i2 - i1
                self.added_lines += j2 - j1
                self.modified_lines += min(i2 - i1, j2 - j1)
            elif tag == "delete":
                self.removed_lines += i2 - i1
            elif tag == "insert":
                self.added_lines += j2 - j1

    def create(self) -> tk.Frame:
        """Create and return the change bar frame."""
        bg = self.colors.get("bg_dark", "#0B0D10")
        accent = self.colors.get("accent", "#7C9EFF")
        success = self.colors.get("success", "#A3BE8C")
        error = self.colors.get("error", "#F07178")
        fg = self.colors.get("fg_light", "#E5E9F0")
        fg_dim = self.colors.get("fg_dim", "#8F99A6")
        sash_color = self.colors.get("sash_color", "#1F2833")

        self.frame = tk.Frame(
            self.parent,
            bg=bg,
            bd=1,
            relief=tk.FLAT,
            highlightbackground=sash_color,
            highlightthickness=1,
            height=34,
        )
        self.frame.pack_propagate(False)

        # Diff statistics: +N -M format (GitHub Copilot style)
        diff_label = tk.Label(
            self.frame,
            text=f"+{self.added_lines}  −{self.removed_lines}",
            font=("DejaVu Sans Mono", 11, "bold"),
            fg=success if self.added_lines > 0 else error,
            bg=bg,
            padx=10,
        )
        diff_label.pack(side=tk.LEFT, padx=(10, 5), pady=6)

        # Separator
        sep = tk.Frame(self.frame, bg=sash_color, width=1)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=4)

        # Description label
        desc_label = tk.Label(
            self.frame,
            text="⚡ AI generated changes:",
            font=("DejaVu Sans", 9),
            fg=accent,
            bg=bg,
        )
        desc_label.pack(side=tk.LEFT, padx=(5, 10), pady=6)

        # Approve button (right-aligned, green, with ✓ icon)
        approve_btn = tk.Button(
            self.frame,
            text="✓ Approve  (Ctrl+Enter)",
            font=("DejaVu Sans", 9, "bold"),
            bg=success,
            fg="#000000",
            bd=0,
            padx=14,
            pady=3,
            cursor="hand2",
            command=self._handle_approve,
            activebackground=self.colors.get("success_hover", "#8FBC7A"),
            activeforeground="#000000",
            relief=tk.FLAT,
        )
        approve_btn.pack(side=tk.RIGHT, padx=(5, 5), pady=4)
        self._approve_button = approve_btn

        # Reject button (right-aligned, grey, with ✗ icon)
        reject_btn = tk.Button(
            self.frame,
            text="✗ Reject  (Esc)",
            font=("DejaVu Sans", 9),
            bg=sash_color,
            fg=fg,
            bd=0,
            padx=14,
            pady=3,
            cursor="hand2",
            command=self._handle_reject,
            activebackground=sash_color,
            activeforeground=accent,
            relief=tk.FLAT,
        )
        reject_btn.pack(side=tk.RIGHT, padx=(0, 5), pady=4)
        self._reject_button = reject_btn

        return self.frame

    def _handle_approve(self):
        """Handle approve button click."""
        self._disable_buttons()
        if self.on_approve:
            self.on_approve()

    def _handle_reject(self):
        """Handle reject button click."""
        self._disable_buttons()
        if self.on_reject:
            self.on_reject()

    def _disable_buttons(self):
        """Disable both buttons after interaction."""
        if hasattr(self, "_approve_button"):
            self._approve_button.config(state=tk.DISABLED)
        if hasattr(self, "_reject_button"):
            self._reject_button.config(state=tk.DISABLED)

    def destroy(self):
        """Destroy the frame."""
        if self.frame and self.frame.winfo_exists():
            self.frame.destroy()
            self.frame = None


class DiffViewer:
    """Displays a visual diff of code changes with color-coded additions/deletions."""

    def __init__(self, parent: tk.Widget, theme_colors: dict):
        """
        Initialize the diff viewer.

        Args:
            parent: Parent tkinter widget (usually Text widget)
            theme_colors: Theme color dictionary
        """
        self.parent = parent
        self.colors = theme_colors
        self._setup_tags()

    def _setup_tags(self):
        """Configure text tags for diff visualization."""
        if not hasattr(self.parent, "tag_config"):
            return

        bg_editor = self.colors.get("bg_editor", "#080808")
        success = self.colors.get("success", "#A3BE8C")
        error = self.colors.get("error", "#F07178")
        fg_dim = self.colors.get("fg_dim", "#7D8794")

        # Added line (green background, subtle)
        self.parent.tag_config(
            "diff_added",
            background=f"#{success[1:]}20",  # 20% alpha-like effect
            foreground=success,
            font=("DejaVu Sans Mono", 10),
        )

        # Removed line (red background, subtle)
        self.parent.tag_config(
            "diff_removed",
            background=f"#{error[1:]}20",  # 20% alpha-like effect
            foreground=error,
            font=("DejaVu Sans Mono", 10),
        )

        # Modified line (yellow/orange)
        self.parent.tag_config(
            "diff_modified",
            foreground="#FFA500",
            font=("DejaVu Sans Mono", 10),
        )

        # Diff line numbers (context)
        self.parent.tag_config(
            "diff_info",
            foreground=fg_dim,
            font=("DejaVu Sans Mono", 9),
        )

    def display_diff(
        self,
        original: str,
        new: str,
        context_lines: int = 3,
        max_display_lines: int = 50,
    ) -> str:
        """
        Generate a colored diff display string (not directly inserted into widget).

        Args:
            original: Original content
            new: New content
            context_lines: Number of context lines around changes
            max_display_lines: Maximum lines to display

        Returns:
            Formatted diff string ready for display
        """
        orig_lines = original.splitlines()
        new_lines = new.splitlines()

        differ = difflib.unified_diff(
            orig_lines,
            new_lines,
            lineterm="",
            n=context_lines,
        )

        diff_lines = list(differ)
        if not diff_lines:
            return "(No changes detected)"

        # Limit display
        display_lines = diff_lines[:max_display_lines]
        if len(diff_lines) > max_display_lines:
            display_lines.append(f"... ({len(diff_lines) - max_display_lines} more lines)")

        return "\n".join(display_lines)

    def insert_colored_diff(
        self,
        text_widget: tk.Text,
        original: str,
        new: str,
        context_lines: int = 3,
    ):
        """
        Insert a colored diff into a Text widget.

        Args:
            text_widget: tkinter Text widget to insert into
            original: Original content
            new: New content
            context_lines: Number of context lines around changes
        """
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

        text_widget.config(state=tk.NORMAL)
        for line in differ:
            if line.startswith("+++") or line.startswith("---"):
                text_widget.insert(tk.END, line + "\n", "diff_info")
            elif line.startswith("@@"):
                text_widget.insert(tk.END, line + "\n", "diff_info")
            elif line.startswith("+"):
                # Added line
                text_widget.insert(tk.END, line + "\n", "diff_added")
            elif line.startswith("-"):
                # Removed line
                text_widget.insert(tk.END, line + "\n", "diff_removed")
            else:
                # Context line
                text_widget.insert(tk.END, line + "\n")
        text_widget.config(state=tk.DISABLED)


def create_approval_dialog_inline(
    chat_widget: tk.Text,
    theme_colors: dict,
    message: str,
    change_type: str,
    added_lines: int = 0,
    removed_lines: int = 0,
    preview_code: Optional[str] = None,
    on_approve: Optional[Callable[[], None]] = None,
    on_reject: Optional[Callable[[], None]] = None,
) -> tk.Frame:
    """
    Create an inline approval dialog in the chat widget (Copilot-style).

    Args:
        chat_widget: Chat Text widget
        theme_colors: Theme colors dictionary
        message: Action message (e.g., "Add 5 lines")
        change_type: Type of change ("add_lines", "delete_lines", "replace_file", etc.)
        added_lines: Number of added lines
        removed_lines: Number of removed lines
        preview_code: Code preview to display
        on_approve: Callback on approve
        on_reject: Callback on reject

    Returns:
        Frame widget representing the approval dialog
    """
    bg = theme_colors.get("bg_dark", "#0B0D10")
    accent = theme_colors.get("accent", "#7C9EFF")
    success = theme_colors.get("success", "#A3BE8C")
    error = theme_colors.get("error", "#F07178")
    fg = theme_colors.get("fg_light", "#E5E9F0")
    fg_dim = theme_colors.get("fg_dim", "#8F99A6")
    sash_color = theme_colors.get("sash_color", "#1F2833")

    # Main container
    container = tk.Frame(chat_widget, bg=bg)

    # Title with action icon
    title = f"⚡ **AI wants to: {message}**"
    title_label = tk.Label(
        container,
        text=title,
        font=("DejaVu Sans", 10, "bold"),
        fg=accent,
        bg=bg,
        wraplength=300,
        justify=tk.LEFT,
    )
    title_label.pack(anchor=tk.W, padx=8, pady=(8, 4))

    # Change summary
    summary = f"Changes: +{added_lines} −{removed_lines}"
    summary_label = tk.Label(
        container,
        text=summary,
        font=("DejaVu Sans Mono", 9),
        fg=success if added_lines > 0 else error,
        bg=bg,
    )
    summary_label.pack(anchor=tk.W, padx=8, pady=(0, 6))

    # Code preview (if provided)
    if preview_code:
        preview_frame = tk.Frame(container, bg=theme_colors.get("bg_editor", "#0A0E14"))
        preview_frame.pack(fill=tk.X, padx=8, pady=4)

        preview_text = tk.Text(
            preview_frame,
            height=min(8, preview_code.count("\n") + 1),
            width=60,
            font=("DejaVu Sans Mono", 9),
            bg=theme_colors.get("bg_editor", "#0A0E14"),
            fg=fg_dim,
            bd=0,
            highlightthickness=0,
            wrap=tk.WORD,
        )
        preview_text.pack(fill=tk.X)
        preview_text.insert("1.0", preview_code)
        preview_text.config(state=tk.DISABLED)

    # Button container
    btn_frame = tk.Frame(container, bg=bg)
    btn_frame.pack(fill=tk.X, padx=8, pady=(4, 8))

    # Approve button
    approve_btn = tk.Button(
        btn_frame,
        text="✓ Approve",
        font=("DejaVu Sans", 9, "bold"),
        bg=success,
        fg="#000000",
        bd=0,
        padx=12,
        pady=3,
        cursor="hand2",
        command=on_approve,
        activebackground=theme_colors.get("success_hover", "#8FBC7A"),
        activeforeground="#000000",
        relief=tk.FLAT,
    )
    approve_btn.pack(side=tk.LEFT, padx=(0, 4))

    # Reject button
    reject_btn = tk.Button(
        btn_frame,
        text="✗ Reject",
        font=("DejaVu Sans", 9),
        bg=sash_color,
        fg=fg,
        bd=0,
        padx=12,
        pady=3,
        cursor="hand2",
        command=on_reject,
        activebackground=sash_color,
        activeforeground=accent,
        relief=tk.FLAT,
    )
    reject_btn.pack(side=tk.LEFT)

    return container
