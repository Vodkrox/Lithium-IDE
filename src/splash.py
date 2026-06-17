import tkinter as tk
from PIL import Image, ImageTk
from src.utils import resource_path


class SplashScreen:
    def __init__(self, root):
        self.root = root

        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)

        self.window.configure(bg="black")

        banner_path = resource_path("src/assets/lithium_banner.png")

        img = Image.open(banner_path)

        width, height = 750, 200

        img = img.resize((width, height), Image.Resampling.LANCZOS)

        self.image = ImageTk.PhotoImage(img)

        label = tk.Label(
            self.window,
            image=self.image,
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0
        )

        label.place(x=0, y=0, width=width, height=height)

        x = (self.window.winfo_screenwidth() - width) // 2
        y = (self.window.winfo_screenheight() - height) // 2

        self.window.geometry(f"{width}x{height}+{x}+{y}")

    def close(self):
        self.window.destroy()
