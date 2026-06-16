import subprocess
import sys
import os
import tkinter as tk

def run_code(file_path, console_widget):
    if not file_path:
        return

    console_widget.config(state=tk.NORMAL)
    console_widget.delete(1.0, tk.END)
    console_widget.config(state=tk.DISABLED)

    try:
        python_executable = sys.executable
        process = subprocess.Popen(
            [python_executable, file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False
        )
        
        stdout, stderr = process.communicate()

        console_widget.config(state=tk.NORMAL)
        if stdout:
            console_widget.insert(tk.END, stdout)
        if stderr:
            console_widget.insert(tk.END, stderr)
        console_widget.config(state=tk.DISABLED)
    except Exception as e:
        console_widget.config(state=tk.NORMAL)
        console_widget.insert(tk.END, f"Error running script: {str(e)}")
        console_widget.config(state=tk.DISABLED)
