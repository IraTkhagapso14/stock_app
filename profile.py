import tkinter as tk
from tkinter import messagebox

from app_state import app_state

BG = "#0D1117"
SURFACE = "#161B22"
SURFACE2 = "#1C2333"
BORDER = "#30363D"
ACCENT = "#2F81F7"
TEXT_PRI = "#E6EDF3"
TEXT_SEC = "#8B949E"
TEXT_MUTED = "#484F58"
WHITE = "#FFFFFF"
RED = "#F85149"
AMBER = "#D29922"


def money(value):
    try:
        return f"{float(value):,.2f} ₽".replace(",", " ")
    except Exception:
        return "—"


class ProfilePage(tk.Frame):
    def __init__(self, parent, dashboard_ref):
        super().__init__(parent, bg=BG)
        self.dashboard = dashboard_ref
        self._ensure_profile_structure()
        self._build_ui()
        self.refresh_all()

    def _ensure_profile_structure(self):
        profile = app_state.profile

        if not isinstance(profile, dict):
            app_state.profile = {}
            profile = app_state.profile

        profile.setdefault("display_name", app_state.user or "")
        profile.setdefault("email", app_state.email or "")
        profile.setdefault("avatar_letter", (app_state.user or "U")[0].upper())
        profile.setdefault("favorites", [])
        profile.setdefault("recently_viewed", [])
        profile.setdefault("gigachat_auth_key", "")
        profile.setdefault("notifications", {
            "price_alerts": True,
            "news_digest": False,
            "ipo_reminders": True,
            "email_notifications": False
        })

        app_state.save()

    def _build_ui(self):
        for w in self.winfo_children():
            w.destroy()

        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=20, pady=(15, 10))

        tk.Label(
            header,
            text="Профиль",
            font=("Helvetica", 18, "bold"),
            bg=BG,
            fg=TEXT_PRI
        ).pack(side="left")

        canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=canvas.yview,
            bg=SURFACE2,
            troughcolor=BG,
            width=6,
            relief="flat"
        )

        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(canvas, bg=BG)
        self.inner_window = canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(self.inner_window, width=e.width)
        )

        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        self.inner.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        self._build_user_card()
        self._build_portfolio_stats_block()
        self._build_favorites_block()
        self._build_recently_viewed_block()
        self._build_logout_block()

        tk.Frame(self.inner, bg=BG, height=30).pack()

    def _card(self, title):
        frame = tk.LabelFrame(
            self.inner,
            text=title,
            font=("Helvetica", 12, "bold"),
            bg=BG,
            fg=TEXT_PRI,
            foreground=TEXT_PRI,
            padx=15,
            pady=12
        )
        frame.pack(fill="x", padx=20, pady=10)
        return frame

    def _build_user_card(self):
        info_frame = tk.Frame(self.inner, bg=SURFACE, padx=20, pady=20)
        info_frame.pack(fill="x", padx=20, pady=(10, 15))
        info_frame.configure(highlightbackground=BORDER, highlightthickness=1)

        avatar_text = app_state.profile.get("avatar_letter", "U")

        avatar = tk.Label(
            info_frame,
            text=avatar_text,
            font=("Helvetica", 28, "bold"),
            bg=ACCENT,
            fg=WHITE,
            width=3,
            height=1,
            pady=10
        )
        avatar.pack(side="left", padx=(0, 20))

        text_frame = tk.Frame(info_frame, bg=SURFACE)
        text_frame.pack(side="left", fill="x", expand=True)

        tk.Label(
            text_frame,
            text=app_state.user or "Пользователь",
            font=("Helvetica", 16, "bold"),
            bg=SURFACE,
            fg=TEXT_PRI
        ).pack(anchor="w")

        tk.Label(
            text_frame,
            text=app_state.email or "",
            font=("Helvetica", 10),
            bg=SURFACE,
            fg=TEXT_SEC
        ).pack(anchor="w", pady=(2, 0))

        portfolio_count = len(app_state.portfolio) if isinstance(app_state.portfolio, list) else 0

        tk.Label(
            text_frame,
            text=f"Позиций в портфеле: {portfolio_count}",
            font=("Helvetica", 9),
            bg=SURFACE,
            fg=ACCENT
        ).pack(anchor="w", pady=(8, 0))

    def _build_portfolio_stats_block(self):
        frame = self._card("Портфель")

        stats = self._calculate_portfolio_stats()

        row = tk.Frame(frame, bg=BG)
        row.pack(fill="x")

        self._stat_card(row, "Позиций", str(stats["positions_count"]), ACCENT)
        self._stat_card(row, "Вложено", money(stats["invested_value"]), TEXT_PRI)
        self._stat_card(row, "Избранное", str(stats["favorites_count"]), AMBER)
        self._stat_card(row, "Просмотрено", str(stats["recent_count"]), TEXT_SEC)

    def _stat_card(self, parent, title, value, color):
        card = tk.Frame(parent, bg=SURFACE, padx=10, pady=10)
        card.pack(side="left", fill="x", expand=True, padx=4)
        card.configure(highlightbackground=BORDER, highlightthickness=1)

        tk.Label(
            card,
            text=title,
            font=("Helvetica", 8),
            bg=SURFACE,
            fg=TEXT_MUTED
        ).pack(anchor="w")

        tk.Label(
            card,
            text=value,
            font=("Helvetica", 12, "bold"),
            bg=SURFACE,
            fg=color
        ).pack(anchor="w", pady=(4, 0))

    def _build_favorites_block(self):
        frame = self._card("Избранные акции")

        favorites = app_state.profile.get("favorites", [])

        if not favorites:
            self._simple_text(frame, "Пока нет избранных акций.")
            return

        self._chips(frame, favorites)

    def _build_recently_viewed_block(self):
        frame = self._card("Недавно просмотренные")

        recent = app_state.profile.get("recently_viewed", [])

        if not recent:
            self._simple_text(frame, "Пока нет просмотренных акций.")
            return

        self._chips(frame, recent[-15:][::-1])

    def _build_logout_block(self):
        logout_btn = tk.Button(
            self.inner,
            text="🚪 Выйти из аккаунта",
            command=self._logout,
            bg=RED,
            fg=WHITE,
            bd=0,
            padx=20,
            pady=8,
            font=("Helvetica", 10, "bold"),
            cursor="hand2"
        )
        logout_btn.pack(pady=(20, 30))

    def _simple_text(self, parent, text):
        tk.Label(
            parent,
            text=text,
            font=("Helvetica", 9),
            bg=BG,
            fg=TEXT_SEC,
            wraplength=600,
            justify="left"
        ).pack(anchor="w")

    def _chips(self, parent, items):
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="x", anchor="w")

        row = tk.Frame(wrap, bg=BG)
        row.pack(fill="x", anchor="w")

        count = 0

        for item in items:
            chip = tk.Label(
                row,
                text=str(item),
                font=("Helvetica", 9, "bold"),
                bg=SURFACE2,
                fg=ACCENT,
                padx=9,
                pady=4
            )
            chip.pack(side="left", padx=(0, 6), pady=4)

            count += 1

            if count % 5 == 0:
                row = tk.Frame(wrap, bg=BG)
                row.pack(fill="x", anchor="w")

    def _calculate_portfolio_stats(self):
        portfolio = app_state.portfolio

        if not isinstance(portfolio, list):
            portfolio = []

        invested = 0
        positions_count = 0

        for item in portfolio:
            if not isinstance(item, dict):
                continue

            qty = float(item.get("quantity", 0) or 0)
            buy_price = float(item.get("buy_price", 0) or 0)

            if qty <= 0:
                continue

            positions_count += 1
            invested += qty * buy_price

        favorites = app_state.profile.get("favorites", [])
        recent = app_state.profile.get("recently_viewed", [])

        return {
            "invested_value": invested,
            "positions_count": positions_count,
            "favorites_count": len(favorites) if isinstance(favorites, list) else 0,
            "recent_count": len(recent) if isinstance(recent, list) else 0
        }

    def _logout(self):
        if messagebox.askyesno("Выход", "Вы уверены, что хотите выйти?"):
            app_state.user = ""
            app_state.email = ""
            app_state.is_guest = False
            app_state.save()
            self.dashboard.destroy()

            from screens.auth import AuthScreen

            root = tk._default_root

            if root:
                auth = AuthScreen(root)
                root.wait_window(auth)

                if app_state.user and app_state.email and not app_state.is_guest:
                    from dashboard import DashboardScreen
                    DashboardScreen(root, username=app_state.user)
                else:
                    root.quit()

    def refresh_all(self):
        self._ensure_profile_structure()
        self._build_ui()



