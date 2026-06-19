import os
import subprocess
import threading
import tkinter as tk

from src.utils import get_python_executable

_current_process = None
_process_lock = threading.Lock()


def _set_current_process(process):
    global _current_process
    with _process_lock:
        _current_process = process


def is_running():
    with _process_lock:
        return _current_process is not None and _current_process.poll() is None


def stop_code():
    with _process_lock:
        process = _current_process
    if process is None or process.poll() is not None:
        return False
    try:
        process.terminate()
        return True
    except Exception:
        try:
            process.kill()
            return True
        except Exception:
            return False


def run_code(file_path, console_widget, on_complete=None):
    if not file_path:
        return

    def append_output(text):
        console_widget.insert(tk.END, text)
        console_widget.see(tk.END)

    def worker():
        try:
            python_executable = get_python_executable()
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(
                [python_executable, "-u", file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                shell=False,
            )

            if process.stdout is None:
                return

            _set_current_process(process)
            for line in process.stdout:
                console_widget.after(0, append_output, line)

            process.wait()
        except Exception as e:
            console_widget.after(0, append_output, f"Error running script: {str(e)}\n")
        finally:
            _set_current_process(None)
            if on_complete:
                console_widget.after(0, on_complete)

    console_widget.delete(1.0, tk.END)

    threading.Thread(target=worker, daemon=True).start()
