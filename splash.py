import tkinter as tk
import os

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False

class SplashScreen(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(base_dir, "assets", "logo.png")

        if PIL_OK:
            try:
                img = Image.open(logo_path)
                # Получаем исходные размеры картинки
                self.win_width, self.win_height = img.size
                self.bg_image = ImageTk.PhotoImage(img)
            except Exception as e:
                print(f"Ошибка загрузки фона: {e}")
                self.win_width, self.win_height = 746, 665  # fallback
                self.bg_image = None
        else:
            self.win_width, self.win_height = 746, 665
            self.bg_image = None

        self.geometry(f"{self.win_width}x{self.win_height}")

        # Центрирование окна
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.win_width) // 2
        y = (self.winfo_screenheight() - self.win_height) // 2
        self.geometry(f"+{x}+{y}")

        self.canvas = tk.Canvas(self, width=self.win_width, height=self.win_height,
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        if self.bg_image:
            self.canvas.create_image(0, 0, image=self.bg_image, anchor="nw")
        else:
            self.draw_fallback()

        self.after(2500, self.destroy)

    def draw_fallback(self):
        """Заглушка, если картинка не загрузилась"""
        self.draw_gradient("#1e3a8a", "#7c3aed")
        self.canvas.create_text(self.win_width//2, self.win_height//2,
                                fill="white",
                                font=("Inter Bold", 24))

    def draw_gradient(self, color1, color2):
        for i in range(self.win_height):
            r1, g1, b1 = self.winfo_rgb(color1)
            r2, g2, b2 = self.winfo_rgb(color2)
            r = int(r1 + (r2 - r1) * i / self.win_height) >> 8
            g = int(g1 + (g2 - g1) * i / self.win_height) >> 8
            b = int(b1 + (b2 - b1) * i / self.win_height) >> 8
            color = f"#{r:02x}{g:02x}{b:02x}"
            self.canvas.create_line(0, i, self.win_width, i, fill=color)