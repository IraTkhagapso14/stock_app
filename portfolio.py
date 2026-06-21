import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_state import app_state
from screens.search import fetch_bulk_prices, get_company_details
from ai_portfolio_forecast import forecast_portfolio_month, recommend_stocks_to_buy

BG = "#0D1117"
SURFACE = "#161B22"
SURFACE2 = "#1C2333"
SURFACE3 = "#21262D"
BORDER = "#30363D"
ACCENT = "#2F81F7"
ACCENT2 = "#388BFD"
TEXT_PRI = "#E6EDF3"
TEXT_SEC = "#8B949E"
TEXT_MUTED = "#484F58"
RED = "#F85149"
GREEN = "#3FB950"
AMBER = "#D29922"
WHITE = "#FFFFFF"


def money(value, absolute=False, signed=False):
    try:
        value = float(value)
        if absolute:
            value = abs(value)
        if signed:
            return f"{value:+,.2f} ₽".replace(",", " ")
        return f"{value:,.2f} ₽".replace(",", " ")
    except Exception:
        return "—"


def percent(value):
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "—"


class PortfolioPage(tk.Frame):
    def __init__(self, parent, dashboard_ref):
        super().__init__(parent, bg=BG)
        self.dashboard = dashboard_ref
        self.price_cache = {}
        self._price_updater_started = False

        self._build_ui()
        self._refresh_prices()
        self._start_price_updater()

    def _build_ui(self):
        for w in self.winfo_children():
            w.destroy()

        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=20, pady=(15, 10))

        tk.Label(
            header,
            text="Мой портфель",
            font=("Helvetica", 18, "bold"),
            bg=BG,
            fg=TEXT_PRI
        ).pack(side="left")

        top_actions = tk.Frame(header, bg=BG)
        top_actions.pack(side="right")

        tk.Button(
            top_actions,
            text="🧠 AI‑прогноз (4 дня)",
            command=self._run_forecast_async,
            bg=GREEN,
            fg=WHITE,
            activebackground="#2EA043",
            activeforeground=WHITE,
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            font=("Helvetica", 10, "bold")
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            top_actions,
            text="+",
            command=self._increase_selected,
            bg=SURFACE2,
            fg=ACCENT,
            activebackground=SURFACE3,
            activeforeground=ACCENT,
            bd=0,
            width=4,
            pady=6,
            cursor="hand2",
            font=("Helvetica", 10, "bold")
        ).pack(side="left", padx=(0, 4))

        tk.Button(
            top_actions,
            text="−",
            command=self._decrease_selected,
            bg=SURFACE2,
            fg=ACCENT,
            activebackground=SURFACE3,
            activeforeground=ACCENT,
            bd=0,
            width=4,
            pady=6,
            cursor="hand2",
            font=("Helvetica", 10, "bold")
        ).pack(side="left", padx=(0, 4))

        tk.Button(
            top_actions,
            text="Удалить",
            command=self._delete_selected,
            bg=RED,
            fg=WHITE,
            activebackground="#DA3633",
            activeforeground=WHITE,
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            font=("Helvetica", 10, "bold")
        ).pack(side="left")

        self.selected_label = tk.Label(
            self,
            text="Выберите строку, чтобы изменить количество или удалить позицию",
            font=("Helvetica", 9),
            bg=BG,
            fg=TEXT_MUTED
        )
        self.selected_label.pack(anchor="w", padx=22, pady=(0, 8))

        self.tree_frame = tk.Frame(self, bg=BG)
        self.tree_frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        columns = (
            "ticker",
            "name",
            "quantity",
            "buy_price",
            "invested_value",
            "current_price",
            "current_value",
            "profit"
        )

        self.tree = ttk.Treeview(
            self.tree_frame,
            columns=columns,
            show="headings",
            height=18
        )

        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "Portfolio.Treeview",
            background=SURFACE,
            foreground=TEXT_SEC,
            fieldbackground=SURFACE,
            borderwidth=0,
            rowheight=36,
            font=("Helvetica", 9)
        )

        style.configure(
            "Portfolio.Treeview.Heading",
            background=ACCENT,
            foreground=WHITE,
            font=("Helvetica", 9, "bold"),
            relief="flat",
            padding=(8, 9)
        )

        style.map(
            "Portfolio.Treeview",
            background=[("selected", SURFACE2)],
            foreground=[("selected", ACCENT)]
        )

        style.map(
            "Portfolio.Treeview.Heading",
            background=[("active", ACCENT), ("pressed", ACCENT)],
            foreground=[("active", WHITE), ("pressed", WHITE)]
        )

        self.tree.configure(style="Portfolio.Treeview")

        headings = {
            "ticker": "Тикер",
            "name": "Компания",
            "quantity": "Кол-во",
            "buy_price": "Покупка",
            "invested_value": "Вложено",
            "current_price": "Текущая",
            "current_value": "Текущая стоимость",
            "profit": "Общ. приб./убыток"
        }

        for col, title in headings.items():
            self.tree.heading(col, text=title, anchor="center")

        self.tree.column("ticker", width=62, minwidth=58, anchor="center", stretch=False)
        self.tree.column("name", width=145, minwidth=120, anchor="center", stretch=True)
        self.tree.column("quantity", width=62, minwidth=58, anchor="center", stretch=False)
        self.tree.column("buy_price", width=88, minwidth=82, anchor="center", stretch=False)
        self.tree.column("invested_value", width=100, minwidth=92, anchor="center", stretch=False)
        self.tree.column("current_price", width=88, minwidth=82, anchor="center", stretch=False)
        self.tree.column("current_value", width=118, minwidth=108, anchor="center", stretch=False)
        self.tree.column("profit", width=132, minwidth=120, anchor="center", stretch=False)

        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<MouseWheel>", self._on_tree_mousewheel)
        self.tree.bind("<Button-4>", self._on_tree_mousewheel)
        self.tree.bind("<Button-5>", self._on_tree_mousewheel)

        self.tree.tag_configure("normal", foreground=TEXT_SEC)
        self.tree.tag_configure("total", foreground=WHITE, background=SURFACE3)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        self._update_display()

    def _on_tree_mousewheel(self, event):
        try:
            if hasattr(event, "delta") and event.delta:
                self.tree.yview_scroll(int(-event.delta / 120), "units")
            elif getattr(event, "num", None) == 4:
                self.tree.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                self.tree.yview_scroll(1, "units")
        except Exception:
            pass
        return "break"

    def _get_portfolio(self):
        portfolio = app_state.portfolio
        if not isinstance(portfolio, list):
            return []
        return [item for item in portfolio if isinstance(item, dict) and item.get("secid")]

    def _get_company_name(self, ticker):
        try:
            details = get_company_details(ticker)
            name = (
                details.get("name")
                or details.get("shortname")
                or details.get("company_name")
                or ticker
            )
            return str(name)[:28]
        except Exception:
            return ticker

    def _selected_ticker(self):
        selected = self.tree.selection()
        if not selected:
            return None
        values = self.tree.item(selected[0], "values")
        if not values:
            return None
        ticker = values[0]
        if ticker == "ИТОГО":
            return None
        return ticker

    def _on_select(self, event=None):
        ticker = self._selected_ticker()
        if ticker:
            self.selected_label.config(text=f"Выбрано: {ticker}", fg=ACCENT)
        else:
            self.selected_label.config(
                text="Выберите строку, чтобы изменить количество или удалить позицию",
                fg=TEXT_MUTED
            )

    def _update_display(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        portfolio = self._get_portfolio()

        if not portfolio:
            self.tree.insert(
                "",
                "end",
                values=("", "Портфель пуст", "", "", "", "", "", ""),
                tags=("normal",)
            )
            return

        total_invested = 0.0
        total_current_value = 0.0
        total_profit = 0.0
        has_current_prices = False

        for item in portfolio:
            ticker = item.get("secid", "")
            quantity = int(item.get("quantity", 0) or 0)
            buy_price = float(item.get("buy_price", 0) or 0)
            invested = buy_price * quantity
            total_invested += invested

            company_name = self._get_company_name(ticker)
            current_price = self.price_cache.get(ticker, {}).get("last")

            if current_price is None:
                current_price_str = "загрузка..."
                current_value_str = "—"
                profit_str = "—"
            else:
                has_current_prices = True
                current_value = float(current_price) * quantity
                profit_value = current_value - invested

                total_current_value += current_value
                total_profit += profit_value

                current_price_str = money(current_price)
                current_value_str = money(current_value)
                profit_str = money(profit_value, signed=True)

            self.tree.insert(
                "",
                "end",
                values=(
                    ticker,
                    company_name,
                    quantity,
                    money(buy_price),
                    money(invested),
                    current_price_str,
                    current_value_str,
                    profit_str
                ),
                tags=("normal",)
            )

        
        self.tree.insert(
            "",
            "end",
            values=(
                "ИТОГО",
                "Общий итог по портфелю",
                "",
                "",
                money(total_invested),
                "",
                money(total_current_value) if has_current_prices else "—",
                money(total_profit, signed=True) if has_current_prices else "—"
            ),
            tags=("total",)
        )

    def _refresh_prices(self):
        portfolio = self._get_portfolio()
        tickers = list({item.get("secid") for item in portfolio if item.get("secid")})

        if not tickers:
            return

        def fetch():
            try:
                prices = fetch_bulk_prices(tickers)
                self.price_cache.update(prices)
                self.after(0, self._update_display)
            except Exception as e:
                print(f"[Portfolio] Ошибка обновления цен: {e}")

        threading.Thread(target=fetch, daemon=True).start()

    def _start_price_updater(self):
        if self._price_updater_started:
            return

        self._price_updater_started = True

        def loop():
            import time
            while True:
                time.sleep(15)
                try:
                    if self.winfo_exists():
                        self.after(0, self._refresh_prices)
                except Exception:
                    break

        threading.Thread(target=loop, daemon=True).start()

    def refresh(self):
        self._refresh_prices()
        self._update_display()
        self._refresh_dashboard_hero()
        self._refresh_profile_stats()

    def _refresh_dashboard_hero(self):
        try:
            if hasattr(self.dashboard, "refresh_hero"):
                self.dashboard.refresh_hero()
            elif hasattr(self.dashboard, "_draw_hero"):
                self.dashboard._draw_hero()
        except Exception:
            pass

    def _refresh_profile_stats(self):
        try:
            pages = getattr(self.dashboard, "pages", {})
            profile_page = pages.get("profile")
            if profile_page and hasattr(profile_page, "refresh_all"):
                profile_page.refresh_all()
        except Exception:
            pass

    def _increase_selected(self):
        ticker = self._selected_ticker()
        if not ticker:
            messagebox.showinfo("Портфель", "Сначала выберите акцию в таблице.")
            return
        self._increase_quantity(ticker)

    def _decrease_selected(self):
        ticker = self._selected_ticker()
        if not ticker:
            messagebox.showinfo("Портфель", "Сначала выберите акцию в таблице.")
            return
        self._decrease_quantity(ticker)

    def _delete_selected(self):
        ticker = self._selected_ticker()
        if not ticker:
            messagebox.showinfo("Портфель", "Сначала выберите акцию в таблице.")
            return
        self._delete_position(ticker)

    def _increase_quantity(self, ticker):
        for item in app_state.portfolio:
            if isinstance(item, dict) and item.get("secid") == ticker:
                item["quantity"] = int(item.get("quantity", 0) or 0) + 1
                app_state.save()
                self._refresh_prices()
                self._update_display()
                self._refresh_dashboard_hero()
                self._refresh_profile_stats()
                return

    def _decrease_quantity(self, ticker):
        for item in app_state.portfolio:
            if isinstance(item, dict) and item.get("secid") == ticker:
                qty = int(item.get("quantity", 0) or 0)
                if qty > 1:
                    item["quantity"] = qty - 1
                    app_state.save()
                    self._refresh_prices()
                    self._update_display()
                    self._refresh_dashboard_hero()
                    self._refresh_profile_stats()
                else:
                    self._delete_position(ticker)
                return

    def _delete_position(self, ticker):
        if messagebox.askyesno("Подтверждение", f"Удалить позицию {ticker} из портфеля?"):
            app_state.portfolio = [
                item for item in app_state.portfolio
                if not (isinstance(item, dict) and item.get("secid") == ticker)
            ]
            app_state.save()
            self._refresh_prices()
            self._update_display()
            self._refresh_dashboard_hero()
            self._refresh_profile_stats()

    def _run_forecast_async(self):
        portfolio = self._get_portfolio()

        if not portfolio:
            messagebox.showinfo("AI‑прогноз", "Портфель пуст. Добавьте акции для прогноза.")
            return

        loading = tk.Toplevel(self)
        loading.title("AI‑прогноз")
        loading.geometry("540x220")
        loading.configure(bg=BG)
        loading.transient(self)
        loading.grab_set()
        loading.resizable(False, False)

        tk.Label(
            loading,
            text="Строится AI‑прогноз на 4 дня",
            font=("Helvetica", 13, "bold"),
            bg=BG,
            fg=TEXT_PRI
        ).pack(pady=(26, 8))

        tk.Label(
            loading,
            text=(
                "Загружаются данные по акциям, рассчитываются показатели\n"
                "и обучается модель прогнозирования на 4 торговых дня.\n\n"
                "Построение прогноза может занять несколько минут."
            ),
            font=("Helvetica", 10),
            bg=BG,
            fg=TEXT_SEC,
            justify="center"
        ).pack(padx=22)

        def worker():
            try:
                portfolio_results = forecast_portfolio_month(portfolio)

                portfolio_tickers = {
                    item.get("secid")
                    for item in portfolio
                    if item.get("secid")
                }

                recommendations = recommend_stocks_to_buy(
                    exclude_tickers=portfolio_tickers,
                    top_n=10
                )

            except Exception as e:
                self.after(0, lambda err=e: self._forecast_error(loading, err))
                return

            self.after(
                0,
                lambda: self._show_forecast_window(
                    loading,
                    portfolio_results,
                    recommendations
                )
            )

        threading.Thread(target=worker, daemon=True).start()

    def _forecast_error(self, loading, error):
        try:
            loading.destroy()
        except Exception:
            pass
        messagebox.showerror("AI‑прогноз", f"Не удалось построить прогноз:\n{error}")

    def _show_forecast_window(self, loading, portfolio_results, recommendations):
        try:
            loading.destroy()
        except Exception:
            pass

        window = tk.Toplevel(self)
        window.title("Общий прогноз портфеля на 4 дня")
        window.geometry("1280x760")
        window.configure(bg=BG)
        window.minsize(1120, 640)

        try:
            window.state("zoomed")
        except Exception:
            pass

        header = tk.Frame(window, bg=BG)
        header.pack(fill="x", padx=18, pady=(16, 8))

        tk.Label(
            header,
            text="Общий прогноз портфеля на 4 дня",
            font=("Helvetica", 18, "bold"),
            bg=BG,
            fg=TEXT_PRI
        ).pack(anchor="w")

        summary = self._build_summary_text(portfolio_results)

        tk.Label(
            header,
            text=summary,
            font=("Helvetica", 11, "bold"),
            bg=BG,
            fg=ACCENT,
            justify="left",
            wraplength=1200
        ).pack(anchor="w", pady=(8, 0))

        self._build_forecast_portfolio_table(window, portfolio_results)
        self._build_recommendation_table(window, recommendations)

    def _build_forecast_portfolio_table(self, window, portfolio_results):
        tk.Label(
            window,
            text="Акции в портфеле",
            font=("Helvetica", 13, "bold"),
            bg=BG,
            fg=TEXT_PRI
        ).pack(anchor="w", padx=18, pady=(10, 4))

        frame = tk.Frame(window, bg=BG)
        frame.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        cols = (
            "ticker", "qty", "buy_price", "current",
            "forecast", "growth", "forecast_value", "profit", "rec"
        )

        tree = ttk.Treeview(frame, columns=cols, show="headings", height=9)
        self._style_forecast_tree(tree)

        headings = {
            "ticker": "Тикер",
            "qty": "Кол-во",
            "buy_price": "Цена покупки",
            "current": "Текущая",
            "forecast": "Прогноз",
            "growth": "Рост/падение",
            "forecast_value": "Стоимость через 4 дня",
            "profit": "Потенц. прибыль",
            "rec": "Решение"
        }

        for col, title in headings.items():
            tree.heading(col, text=title, anchor="center")
            tree.column(col, anchor="center", stretch=True)

        tree.pack(fill="both", expand=True)
        tree.tag_configure("normal", foreground=TEXT_SEC)
        tree.tag_configure("error", foreground=TEXT_MUTED)

        for r in portfolio_results:
            if r.get("error"):
                tree.insert(
                    "", "end",
                    values=(
                        r.get("ticker", "—"), r.get("quantity", "—"),
                        "—", "—", "—", "—", "—",
                        r.get("error", "Ошибка"), "Нет прогноза"
                    ),
                    tags=("error",)
                )
                continue

            change_pct = r.get("change_percent", 0.0)
            profit_val = r.get("profit_from_buy", 0.0)
            profit_str = money(abs(profit_val))
            if change_pct < 0:
                profit_str = f"-{profit_str}"

            tree.insert(
                "", "end",
                values=(
                    r["ticker"],
                    r["quantity"],
                    money(r["buy_price"]),
                    money(r["current_price"]),
                    money(r["predicted_price"]),
                    percent(change_pct),
                    money(r["predicted_value"]),
                    profit_str,
                    r.get("recommendation", "Держать")
                ),
                tags=("normal",)
            )

    def _build_recommendation_table(self, window, recommendations):
        tk.Label(
            window,
            text="Что можно рассмотреть к покупке вне портфеля",
            font=("Helvetica", 13, "bold"),
            bg=BG,
            fg=TEXT_PRI
        ).pack(anchor="w", padx=18, pady=(4, 4))

        frame = tk.Frame(window, bg=BG)
        frame.pack(fill="both", expand=True, padx=18, pady=(0, 16))

        cols = ("ticker", "current", "forecast", "growth", "confidence", "reason")

        tree = ttk.Treeview(frame, columns=cols, show="headings", height=8)
        self._style_forecast_tree(tree)

        headings = {
            "ticker": "Тикер",
            "current": "Текущая",
            "forecast": "Прогноз",
            "growth": "Потенциал",
            "confidence": "Уверенность",
            "reason": "Почему в подборке"
        }

        for col, title in headings.items():
            tree.heading(col, text=title, anchor="center")

        tree.column("ticker", anchor="center", width=90, stretch=False)
        tree.column("current", anchor="center", width=120, stretch=False)
        tree.column("forecast", anchor="center", width=120, stretch=False)
        tree.column("growth", anchor="center", width=110, stretch=False)
        tree.column("confidence", anchor="center", width=110, stretch=False)
        tree.column("reason", anchor="center", width=650, stretch=True)

        tree.pack(fill="both", expand=True)
        tree.tag_configure("normal", foreground=TEXT_SEC)

        for r in recommendations:
            try:
                conf_str = f"{float(r.get('confidence', 0)):.0f}%"
            except Exception:
                conf_str = "—"

            tree.insert(
                "", "end",
                values=(
                    r.get("ticker", "—"),
                    money(r.get("current_price")),
                    money(r.get("predicted_price")),
                    percent(r.get("change_percent")),
                    conf_str,
                    r.get("reason", "—")
                ),
                tags=("normal",)
            )

    def _style_forecast_tree(self, tree):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "Forecast.Treeview",
            background=SURFACE,
            foreground=TEXT_SEC,
            fieldbackground=SURFACE,
            rowheight=32,
            font=("Helvetica", 10),
            borderwidth=0
        )

        style.configure(
            "Forecast.Treeview.Heading",
            background=ACCENT,
            foreground=WHITE,
            font=("Helvetica", 10, "bold"),
            padding=(8, 8),
            relief="flat"
        )

        style.map(
            "Forecast.Treeview",
            background=[("selected", SURFACE2)],
            foreground=[("selected", ACCENT)]
        )

        style.map(
            "Forecast.Treeview.Heading",
            background=[("active", ACCENT), ("pressed", ACCENT)],
            foreground=[("active", WHITE), ("pressed", WHITE)]
        )

        tree.configure(style="Forecast.Treeview")

    def _build_summary_text(self, results):
        valid = [r for r in results if not r.get("error")]

        if not valid:
            return "Нет данных для сводки"

        total_invested = sum(
            r.get("invested_value", r.get("buy_price", 0) * r.get("quantity", 0))
            for r in valid
        )

        total_current = sum(
            r.get("current_value", r.get("current_price", 0) * r.get("quantity", 0))
            for r in valid
        )

        total_predicted = sum(
            r.get("predicted_value", r.get("predicted_price", 0) * r.get("quantity", 0))
            for r in valid
        )

        profit_now = total_current - total_invested
        profit_forecast = total_predicted - total_invested
        delta_from_current = total_predicted - total_current

        pct_now = (profit_now / total_invested * 100) if total_invested else 0
        pct_forecast = (profit_forecast / total_invested * 100) if total_invested else 0
        pct_from_current = (delta_from_current / total_current * 100) if total_current else 0

        sign_now = "+" if profit_now >= 0 else ""
        sign_forecast = "+" if profit_forecast >= 0 else ""
        sign_delta = "+" if delta_from_current >= 0 else ""

        return (
            f"Вложено: {money(total_invested)}  |  "
            f"Текущая стоимость: {money(total_current)}  |  "
            f"Прибыль/убыток сейчас: {sign_now}{money(profit_now)} ({sign_now}{pct_now:.2f}%)\n"
            f"Прогноз через 4 дня: {money(total_predicted)}  |  "
            f"Прибыль/убыток по прогнозу: {sign_forecast}{money(profit_forecast)} ({sign_forecast}{pct_forecast:.2f}%)  |  "
            f"Изменение к текущей стоимости: {sign_delta}{money(delta_from_current)} ({sign_delta}{pct_from_current:.2f}%)"
        )


