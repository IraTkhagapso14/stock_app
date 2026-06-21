import tkinter as tk
from PIL import Image, ImageTk
import os

BG = "#F9FAFB"
TEXT = "#111827"
SUBTEXT = "#6B7280"
ACCENT = "#2563EB"
ACCENT_DARK = "#1D4ED8"
MUTED = "#9CA3AF"


class OnboardingScreen(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)

        self.geometry("640x430")
        self.overrideredirect(True)
        self.configure(bg=BG)
        self.resizable(False, False)

        self._center_window()
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.slides = [
            {
                "image": "assets/onboarding1.png",
                "icon": "📈",
                "title": "Прогноз акций на месяц",
                "desc": "Приложение анализирует исторические свечи MOEX, рассчитывает показатели и строит AI‑прогноз цены акции на месяц вперёд.",
            },
            {
                "image": "assets/onboarding2.png",
                "icon": "💼",
                "title": "Портфель и будущая стоимость",
                "desc": "Добавляйте акции в портфель, указывайте количество и цену покупки. AI покажет, сколько может стоить каждая позиция через месяц.",
            },
            {
                "image": "assets/onboarding3.png",
                "icon": "🔍",
                "title": "Поиск, графики и информация",
                "desc": "Ищите акции по тикеру или названию компании, смотрите карточку эмитента, свечной график за месяц и ключевые сведения.",
            }
        ]

        self.current_slide = 0
        self.image = None

        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.skip_btn = tk.Button(
            self,
            text="Пропустить",
            bg=BG,
            fg=MUTED,
            activebackground=BG,
            activeforeground=SUBTEXT,
            bd=0,
            font=("Inter", 10),
            cursor="hand2",
            command=self.close,
        )
        self.skip_btn.place(x=535, y=16)

        self.next_btn = tk.Button(
            self,
            text="Далее",
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_DARK,
            activeforeground="white",
            bd=0,
            font=("Inter", 11, "bold"),
            padx=22,
            pady=9,
            cursor="hand2",
            command=self.next_slide,
        )
        self.next_btn.place(x=500, y=365)

        self.back_btn = tk.Button(
            self,
            text="Назад",
            bg=BG,
            fg=SUBTEXT,
            activebackground=BG,
            activeforeground=TEXT,
            bd=0,
            font=("Inter", 10, "bold"),
            cursor="hand2",
            command=self.prev_slide,
        )
        self.back_btn.place(x=34, y=374)

        self.show_slide()
        self.lift()
        self.focus_force()
        self.grab_set()

    def _center_window(self):
        self.update_idletasks()
        w, h = 640, 430
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def get_path(self, path):
        return os.path.join(self.base_dir, path)

    def load_image(self, path):
        try:
            full_path = self.get_path(path)
            if not os.path.exists(full_path):
                return None
            img = Image.open(full_path)
            img = img.resize((190, 190), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"Ошибка загрузки изображения {path}: {e}")
            return None

    def draw_indicators(self):
        total = len(self.slides)
        start_x = 320 - ((total - 1) * 18) // 2

        for i in range(total):
            color = ACCENT if i == self.current_slide else "#D1D5DB"
            self.canvas.create_oval(start_x + i * 18, 382, start_x + i * 18 + 8, 390, fill=color, outline="")

    def show_slide(self):
        self.canvas.delete("all")
        slide = self.slides[self.current_slide]

        self.canvas.create_rectangle(24, 48, 616, 350, fill="#FFFFFF", outline="#E5E7EB")
        self.image = self.load_image(slide.get("image", ""))

        if self.image:
            self.canvas.create_image(320, 145, image=self.image)
        else:
            self.canvas.create_oval(250, 76, 390, 216, fill="#EFF6FF", outline="#DBEAFE")
            self.canvas.create_text(320, 146, text=slide["icon"], font=("Segoe UI Emoji", 48), fill=ACCENT)

        self.canvas.create_text(320, 258, text=slide["title"], font=("Inter", 21, "bold"), fill=TEXT)
        self.canvas.create_text(320, 303, text=slide["desc"], font=("Inter", 12), fill=SUBTEXT, width=500, justify="center")

        self.draw_indicators()

        if self.current_slide == 0:
            self.back_btn.place_forget()
        else:
            self.back_btn.place(x=34, y=374)

        if self.current_slide == len(self.slides) - 1:
            self.next_btn.config(text="Начать")
        else:
            self.next_btn.config(text="Далее")

    def next_slide(self):
        if self.current_slide < len(self.slides) - 1:
            self.current_slide += 1
            self.show_slide()
        else:
            self.close()

    def prev_slide(self):
        if self.current_slide > 0:
            self.current_slide -= 1
            self.show_slide()

    def close(self):
        self.destroy()

