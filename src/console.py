"""
Lithium IDE - System Console.

A tkinter widget that behaves like a real system terminal:
executes shell commands via subprocess, shows live output,
and displays the current directory as the prompt.
"""

import os
import subprocess
import sys
import tkinter as tk
from tkinter import font as tkfont


class Console(tk.Frame):
    """A system console widget for Lithium IDE.

    Usage inside a tkinter app::

        console = Console(parent)
        console.pack(fill="both", expand=True)

    The console can be themed after creation by calling
    ``apply_theme(theme_dict)``.
    """

    PRIMARY_COLOR = "#1e1e1e"
    SECONDARY_COLOR = "#252526"
    TEXT_COLOR = "#d4d4d4"
    PROMPT_COLOR = "#569cd6"
    ERROR_COLOR = "#f44747"
    CARET_COLOR = "#d4d4d4"

    _PROMPT_TAG = "prompt"
    _ERROR_TAG = "error"

    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)

        self._cwd = os.getcwd()
        self._history: list[str] = []
        self._history_index: int | None = None
        self._current_input: str = ""

        self._build_ui()
        self._bind_keys()
        self._show_prompt()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.configure(bg=self.PRIMARY_COLOR)

        # ── text widget (main area) ──
        self.text = tk.Text(
            self,
            wrap="word",
            bg=self.PRIMARY_COLOR,
            fg=self.TEXT_COLOR,
            insertbackground=self.CARET_COLOR,
            relief="flat",
            borderwidth=0,
            padx=6,
            pady=6,
            font=self._mono_font(),
            state="normal",
            undo=False,
        )
        self.text.pack(fill="both", expand=True, side="top")

        scrollbar = tk.Scrollbar(self, command=self.text.yview)
        scrollbar.pack(fill="y", side="right")
        self.text.config(yscrollcommand=scrollbar.set)

        self.text.tag_configure(self._PROMPT_TAG, foreground=self.PROMPT_COLOR)
        self.text.tag_configure(self._ERROR_TAG, foreground=self.ERROR_COLOR)

        # ── status bar ──
        self.status = tk.Label(
            self,
            anchor="w",
            bg=self.SECONDARY_COLOR,
            fg=self.TEXT_COLOR,
            font=tkfont.nametofont("TkSmallCaptionFont"),
            padx=6,
        )
        self.status.pack(fill="x", side="bottom")
        self.status.config(text=" Console ready")

    @staticmethod
    def _mono_font() -> tkfont.Font:
        family = "Consolas" if sys.platform == "win32" else "Courier New"
        return tkfont.Font(family=family, size=11)

    # ── key bindings ──────────────────────────────────────────────────────

    def _bind_keys(self) -> None:
        self.text.bind("<KeyRelease>", self._on_key_release)
        self.text.bind("<Return>", self._on_enter)
        self.text.bind("<BackSpace>", self._on_backspace)
        self.text.bind("<Up>", self._on_up)
        self.text.bind("<Down>", self._on_down)
        self.text.bind("<Control-l>", self._on_ctrl_l)
        self.text.bind("<Button-1>", self._on_click)

    # ── prompt helpers ────────────────────────────────────────────────────

    def _prompt_str(self) -> str:
        """Return the system-like prompt string for the current directory."""
        return f"{self._cwd}>"

    def _input_start(self) -> str:
        """Return the index of the first character of the current input line."""
        return self.text.index("end-1c linestart")

    def _get_input(self) -> str:
        """Return the text the user typed after the prompt."""
        start = self._input_start()
        raw = self.text.get(start, "end-1c")
        prompt = self._prompt_str()
        if raw.startswith(prompt):
            return raw[len(prompt) :]
        return raw

    def _replace_input(self, text: str) -> None:
        """Replace the current input line with *text*."""
        start = self._input_start()
        self.text.delete(start, "end-1c")
        self.text.insert(start, self._prompt_str() + text, self._PROMPT_TAG)
        self.text.mark_set("insert", "end-1c")
        self.text.see("end")

    def _show_prompt(self) -> None:
        """Insert a new prompt at the end of the widget."""
        self.text.insert("end", self._prompt_str(), self._PROMPT_TAG)
        self.text.mark_set("insert", "end-1c")
        self.text.see("end")

    # ── output writing ────────────────────────────────────────────────────

    def _write(self, text: str) -> None:
        self.text.insert("end-1c", text)
        self.text.mark_set("insert", "end-1c")
        self.text.see("end")

    # ── command execution ─────────────────────────────────────────────────

    def _execute_current(self) -> None:
        """Read the current input, execute it as a shell command, and print results."""
        cmd = self._get_input()
        self._writeln()  # newline after the command line

        if not cmd.strip():
            self._show_prompt()
            return

        self._history.append(cmd)
        self._history_index = None

        # Handle internal commands
        if self._handle_internal(cmd):
            self._show_prompt()
            return

        # Run as a system command
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                cwd=self._cwd,
                text=True,
                timeout=60,
            )
            if result.stdout:
                self._write(result.stdout)
            if result.stderr:
                self._write(result.stderr)
            if result.returncode != 0 and not result.stderr:
                self._write(f"  [exit code {result.returncode}]\n")
        except subprocess.TimeoutExpired:
            self.text.insert("end-1c", "  [command timed out]\n", self._ERROR_TAG)
        except Exception as e:
            self.text.insert("end-1c", f"  [error: {e}]\n", self._ERROR_TAG)

        self._show_prompt()

    def _handle_internal(self, cmd: str) -> bool:
        """Handle built-in commands. Return True if the command was handled."""
        stripped = cmd.strip()

        if stripped == "exit" or stripped == "quit":
            self._write("\n  Console closed.\n")
            self.text.config(state="disabled")
            self.status.config(text=" Console closed")
            return True

        if stripped == "clear" or stripped == "cls":
            self._clear_screen()
            return True

        if stripped.startswith("cd "):
            path = stripped[3:].strip().strip('"').strip("'")
            self._change_dir(path)
            return True

        if stripped == "cd":
            self._change_dir(os.path.expanduser("~"))
            return True

        return False

    def _change_dir(self, target: str) -> None:
        """Change the current working directory."""
        try:
            new_dir = os.path.abspath(os.path.join(self._cwd, target))
            os.chdir(new_dir)
            self._cwd = os.getcwd()
        except Exception as e:
            self._write(f"  cd: {e}\n")

    def _writeln(self, text: str = "") -> None:
        self._write(text + "\n")

    def _clear_screen(self) -> None:
        self.text.delete("1.0", "end")
        self._show_prompt()

    # ── event handlers ────────────────────────────────────────────────────

    def _at_input_line(self) -> bool:
        """Return True if the cursor is on the current input line."""
        cursor = self.text.index("insert")
        line = cursor.split(".")[0]
        last_line = self.text.index("end-1c").split(".")[0]
        return line == last_line

    def _on_click(self, event):
        self.text.focus_set()
        if not self._at_input_line():
            self.text.mark_set("insert", "end-1c")

    def _on_key_release(self, event):
        if event.keysym in (
            "Return",
            "Up",
            "Down",
            "BackSpace",
            "Left",
            "Right",
            "Home",
            "End",
        ):
            return
        if not self._at_input_line():
            self.text.mark_set("insert", "end-1c")

    def _on_enter(self, event):
        if not self._at_input_line():
            self.text.mark_set("insert", "end-1c")
            return "break"
        self._execute_current()
        return "break"

    def _on_backspace(self, event):
        if not self._at_input_line():
            return "break"
        cursor_col = int(self.text.index("insert").split(".")[1])
        prompt_len = len(self._prompt_str())
        if cursor_col <= prompt_len:
            return "break"
        return None

    def _on_up(self, event):
        if not self._at_input_line():
            return "break"
        if not self._history:
            return "break"
        if self._history_index is None:
            self._current_input = self._get_input()
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        self._replace_input(self._history[self._history_index])
        return "break"

    def _on_down(self, event):
        if not self._at_input_line():
            return "break"
        if self._history_index is None:
            return "break"
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._replace_input(self._history[self._history_index])
        else:
            self._history_index = None
            self._replace_input(self._current_input)
        return "break"

    def _on_ctrl_l(self, event):
        """Clear screen on Ctrl+L."""
        self._clear_screen()
        return "break"

    # ── public helpers ────────────────────────────────────────────────────

    def apply_theme(self, colors: dict) -> None:
        """Apply a theme color dict to the console widgets."""
        self.PRIMARY_COLOR = colors.get("console_bg", self.PRIMARY_COLOR)
        self.SECONDARY_COLOR = colors.get("bg_header", self.SECONDARY_COLOR)
        self.TEXT_COLOR = colors.get("console_fg", self.TEXT_COLOR)
        self.PROMPT_COLOR = colors.get("accent", self.PROMPT_COLOR)
        self.ERROR_COLOR = colors.get("console_err", self.ERROR_COLOR)
        self.CARET_COLOR = colors.get("console_fg", self.CARET_COLOR)

        self.configure(bg=self.PRIMARY_COLOR)
        self.text.config(
            bg=self.PRIMARY_COLOR,
            fg=self.TEXT_COLOR,
            insertbackground=self.CARET_COLOR,
        )
        self.status.config(bg=self.SECONDARY_COLOR, fg=self.TEXT_COLOR)
        self.text.tag_configure(self._PROMPT_TAG, foreground=self.PROMPT_COLOR)
        self.text.tag_configure(self._ERROR_TAG, foreground=self.ERROR_COLOR)

    def focus(self):
        self.text.focus_set()
        self.text.mark_set("insert", "end-1c")


# ── standalone entry point ─────────────────────────────────────────────────────


def main():
    """Launch the console in its own standalone window."""
    root = tk.Tk()
    root.title("Lithium IDE System Console")
    root.geometry("900x550")

    root.configure(bg=Console.PRIMARY_COLOR)

    console = Console(root)
    console.pack(fill="both", expand=True)

    console.focus()
    root.mainloop()


if __name__ == "__main__":
    main()
