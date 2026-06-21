import tkinter as tk
from ui_kit import *
from app_state import app_state


class StockDetailScreen(tk.Toplevel):
    def __init__(self, parent, ticker):
        super().__init__(parent)

        self.ticker = ticker
        self.price = 178.45  # mock

        self.title(ticker)
        self.geometry("420x600")
        self.configure(bg=BG)

        self.build_ui()

    def build_ui(self):
        # Заголовок
        tk.Label(self,
                 text=self.ticker,
                 font=("SF Pro Display", 28, "bold"),
                 bg=BG,
                 fg=TEXT).pack(pady=(20, 5))

        tk.Label(self,
                 text=f"${self.price}",
                 font=("SF Pro Display", 22),
                 bg=BG,
                 fg=TEXT).pack()

        # AI рекомендация
        card = create_card(self)

        tk.Label(card,
                 text="🤖 AI рекомендует",
                 font=FONT_SMALL,
                 bg=CARD,
                 fg=SUBTEXT).pack(anchor="w", padx=10, pady=(10, 0))

        tk.Label(card,
                 text="КУПИТЬ",
                 font=("SF Pro Text", 16, "bold"),
                 bg=CARD,
                 fg="#34C759").pack(anchor="w", padx=10, pady=5)

        tk.Label(card,
                 text="+12% за 30 дней",
                 font=FONT_BODY,
                 bg=CARD,
                 fg=TEXT).pack(anchor="w", padx=10, pady=(0, 10))

        # Кнопка покупки
        buy_btn = primary_button(self, "Купить", self.buy)
        buy_btn.pack(pady=20)

    def buy(self):
        app_state.portfolio.append({
            "secid": self.ticker,
            "quantity": 1,
            "buy_price": self.price
        })
        app_state.save()

        self.destroy()
