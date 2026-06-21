import os
import sys
import tkinter as tk
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_state import app_state
from user_manager import UserManager


BG = "#0D1117"
LEFT_BG = "#0F172A"
SURFACE = "#161B22"
SURFACE2 = "#1C2333"
BORDER = "#30363D"
ACCENT = "#2F81F7"
ACCENT2 = "#388BFD"
TEXT_PRI = "#E6EDF3"
TEXT_SEC = "#8B949E"
TEXT_MUTED = "#484F58"
WHITE = "#FFFFFF"
RED = "#F85149"


class AuthScreen(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)

        self.parent = parent
        self.user_manager = UserManager()
        self.mode = "login"

        self.title("StockAI Pro")
        self.geometry("820x540")
        self.configure(bg=BG)
        self.resizable(False, False)

        self._center_window()
        self._build_ui()

        self.lift()
        self.focus_force()
        self.grab_set()

        self.bind("<Return>", lambda e: self._submit())

    def _center_window(self):
        self.update_idletasks()

        w, h = 820, 540
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        x = (sw - w) // 2
        y = (sh - h) // 2

        self.geometry(f"{w}x{h}+{x}+{y}")


    def _build_ui(self):
        for w in self.winfo_children():
            w.destroy()

        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True)

        self.left = tk.Frame(root, bg=LEFT_BG, width=330)
        self.left.pack(side="left", fill="both")
        self.left.pack_propagate(False)

        self.brand_canvas = tk.Canvas(self.left, bg=LEFT_BG, highlightthickness=0)
        self.brand_canvas.pack(fill="both", expand=True)
        self.brand_canvas.bind("<Configure>", self._draw_brand_panel)

        self.right = tk.Frame(root, bg=BG)
        self.right.pack(side="right", fill="both", expand=True, padx=32, pady=32)

        self.form_card = tk.Frame(self.right, bg=SURFACE, padx=30, pady=28)
        self.form_card.pack(fill="both", expand=True)
        self.form_card.configure(highlightbackground=BORDER, highlightthickness=1)

        self._draw_form()

    def _draw_brand_panel(self, event=None):
        c = self.brand_canvas
        c.delete("all")

        w = c.winfo_width() or 330
        h = c.winfo_height() or 540


        for i in range(h):
            t = i / max(h, 1)
            r = int(0x0F + (0x1E - 0x0F) * t)
            g = int(0x17 + (0x3A - 0x17) * t)
            b = int(0x2A + (0x5F - 0x2A) * t)
            c.create_line(0, i, w, i, fill=f"#{r:02x}{g:02x}{b:02x}")

       
        c.create_oval(-80, 40, 190, 310, fill="#10213A", outline="")
        c.create_oval(130, -60, 390, 180, fill="#132D55", outline="")
        c.create_oval(150, 330, 390, 590, fill="#0F2442", outline="")

        
        for x in range(0, w + 40, 40):
            c.create_line(x, 0, x, h, fill="#1A2340", width=1)
        for y in range(0, h + 40, 40):
            c.create_line(0, y, w, y, fill="#1A2340", width=1)

        
        c.create_oval(34, 42, 84, 92, fill=ACCENT, outline="")
        c.create_text(59, 67, text="AI", fill=WHITE, font=("Helvetica", 16, "bold"))

        c.create_text(
            34,
            120,
            anchor="w",
            text="StockAI Pro",
            fill=WHITE,
            font=("Helvetica", 24, "bold")
        )

        c.create_text(
            34,
            154,
            anchor="w",
            text="Интеллектуальное приложение\nдля анализа российских акций",
            fill=TEXT_SEC,
            font=("Helvetica", 11),
            justify="left"
        )

        features = [
            ("📈", "Прогноз акций на месяц"),
            ("💼", "Управление портфелем"),
            ("🔍", "Поиск по тикеру и компании"),
            ("🕯", "Свечные графики MOEX")
        ]

        y = 245

        for icon, text in features:
            c.create_rectangle(34, y - 14, 62, y + 14, fill="#1C335A", outline="#274B7A")
            c.create_text(48, y, text=icon, fill=WHITE, font=("Helvetica", 11))
            c.create_text(75, y, anchor="w", text=text, fill=TEXT_PRI, font=("Helvetica", 10, "bold"))
            y += 46

        c.create_text(
            34,
            h - 50,
            anchor="w",
            text="",
            fill=TEXT_MUTED,
            font=("Helvetica", 9)
        )

    def _draw_form(self):
        for w in self.form_card.winfo_children():
            w.destroy()

        if self.mode == "login":
            title = "Вход в аккаунт"
            subtitle = "Войдите для работы с портфелем и прогнозами"
            button_text = "Войти"
            switch_text = "Нет аккаунта? Зарегистрироваться"
        else:
            title = "Регистрация"
            subtitle = "Создайте аккаунт, чтобы сохранять портфель и избранные акции"
            button_text = "Создать аккаунт"
            switch_text = "Уже есть аккаунт? Войти"

        tk.Label(
            self.form_card,
            text=title,
            font=("Helvetica", 22, "bold"),
            bg=SURFACE,
            fg=TEXT_PRI
        ).pack(anchor="w")

        tk.Label(
            self.form_card,
            text=subtitle,
            font=("Helvetica", 10),
            bg=SURFACE,
            fg=TEXT_SEC,
            wraplength=380,
            justify="left"
        ).pack(anchor="w", pady=(6, 24))

        if self.mode == "register":
            self.name_entry = self._input("Имя", "Введите имя")

        self.email_entry = self._input("Email", None)
        self.password_entry = self._input("Пароль", "Введите пароль", show="•")

        tk.Button(
            self.form_card,
            text=button_text,
            command=self._submit,
            bg=ACCENT,
            fg=WHITE,
            activebackground=ACCENT2,
            activeforeground=WHITE,
            bd=0,
            padx=16,
            pady=11,
            font=("Helvetica", 11, "bold"),
            cursor="hand2"
        ).pack(fill="x", pady=(16, 10))

        tk.Button(
            self.form_card,
            text=switch_text,
            command=self._switch_mode,
            bg=SURFACE,
            fg=ACCENT,
            activebackground=SURFACE,
            activeforeground=ACCENT2,
            bd=0,
            font=("Helvetica", 10, "bold"),
            cursor="hand2"
        ).pack(pady=(2, 12))

    

      
    def _input(self, label, placeholder, show=None):
        wrapper = tk.Frame(self.form_card, bg=SURFACE)
        wrapper.pack(fill="x", pady=(0, 13))

        tk.Label(
            wrapper,
            text=label,
            font=("Helvetica", 9, "bold"),
            bg=SURFACE,
            fg=TEXT_SEC
        ).pack(anchor="w", pady=(0, 4))

        entry = tk.Entry(
            wrapper,
            bg=SURFACE2,
            fg=TEXT_PRI,
            insertbackground=TEXT_PRI,
            relief="flat",
            font=("Helvetica", 11),
            show=show or ""
        )
        entry.pack(fill="x", ipady=9)

        entry.placeholder = placeholder
        entry.placeholder_active = False

        if show is None and placeholder:
            self._set_placeholder(entry)
            entry.bind("<FocusIn>", lambda e, ent=entry: self._clear_placeholder(ent))
            entry.bind("<FocusOut>", lambda e, ent=entry: self._set_placeholder(ent))

        return entry

    def _set_placeholder(self, entry):
        if entry.get() == "":
            entry.placeholder_active = True
            entry.insert(0, entry.placeholder)
            entry.config(fg=TEXT_MUTED)

    def _clear_placeholder(self, entry):
        if getattr(entry, "placeholder_active", False):
            entry.delete(0, tk.END)
            entry.placeholder_active = False
            entry.config(fg=TEXT_PRI)

    def _get_value(self, entry):
        if getattr(entry, "placeholder_active", False):
            return ""
        return entry.get().strip()


    def _switch_mode(self):
        self.mode = "register" if self.mode == "login" else "login"
        self._draw_form()

    def _submit(self):
        if self.mode == "login":
            self._login()
        else:
            self._register_user()

    def _login(self):
        email = self._get_value(self.email_entry)
        password = self.password_entry.get().strip()

        if not email or not password:
            messagebox.showwarning("Вход", "Введите email и пароль.")
            return

        ok, name = self.user_manager.authenticate(email, password)

        if ok:
            app_state.set_user(name, email, is_guest=False)
            self.destroy()
        else:
            messagebox.showerror("Ошибка", "Неверный email или пароль.")

    def _register_user(self):
        name = self._get_value(self.name_entry)
        email = self._get_value(self.email_entry)
        password = self.password_entry.get().strip()

        if not name or not email or not password:
            messagebox.showwarning("Регистрация", "Заполните имя, email и пароль.")
            return

        if "@" not in email:
            messagebox.showwarning("Регистрация", "Введите корректный email.")
            return

        if len(password) < 4:
            messagebox.showwarning("Регистрация", "Пароль должен быть не короче 4 символов.")
            return

        ok, msg = self.user_manager.register(email, password, name)

        if ok:
            app_state.set_user(name, email, is_guest=False)
            messagebox.showinfo("Регистрация", "Аккаунт создан. Добро пожаловать!")
            self.destroy()
        else:
            messagebox.showerror("Регистрация", msg)



