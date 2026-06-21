import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import datetime
import time
import pandas as pd
import requests
import json
import random
from postgres_storage import CacheRepository, DatabaseUnavailable, StockRepository

BG = "#0D1117"
SURFACE = "#161B22"
SURFACE2 = "#1C2333"
SURFACE3 = "#21262D"
BORDER = "#30363D"
ACCENT = "#2F81F7"
ACCENT2 = "#388BFD"
GREEN = "#3FB950"
RED = "#F85149"
AMBER = "#D29922"
TEXT_PRI = "#E6EDF3"
TEXT_SEC = "#8B949E"
TEXT_MUTED = "#484F58"
WHITE = "#FFFFFF"
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

class Sparkline:
    def __init__(self, canvas, x, y, w, h, data, color=GREEN, filled=True):
        if not data or len(data) < 2:
            return
        mn, mx = min(data), max(data)
        rng = mx - mn or 1
        step = w / (len(data)-1)
        pts = [(x + i*step, y + h - (v-mn)/rng*h) for i, v in enumerate(data)]
        if filled:
            poly = [x, y+h] + [c for p in pts for c in p] + [x+w, y+h]
            r,g,b = hex_to_rgb(color)
            fill_c = "#{:02x}{:02x}{:02x}".format(r//5, g//5, b//5)
            canvas.create_polygon(poly, fill=fill_c, outline="")
        flat = [c for p in pts for c in p]
        canvas.create_line(flat, fill=color, width=1.5, smooth=True)
        lx, ly = pts[-1]
        canvas.create_oval(lx-2.5, ly-2.5, lx+2.5, ly+2.5, fill=color, outline=BG, width=1)

BASE_URL = "https://iss.moex.com/iss"

class MoexClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _request(self, url, params=None, retries=2):
        for attempt in range(retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=5)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.Timeout:
                if attempt < retries:
                    time.sleep(0.5)
                else:
                    print(f"[MOEX] Timeout: {url}")
            except Exception as e:
                print(f"[MOEX] Error: {e}")
                return None
        return None

    def _to_df(self, block):
        if not block:
            return pd.DataFrame()
        data = block.get("data")
        columns = block.get("columns")
        if data and columns:
            return pd.DataFrame(data, columns=columns)
        return pd.DataFrame()

    def get_securities(self, limit=200):
        url = f"{BASE_URL}/securities.json"
        params = {
            "iss.meta": "off",
            "iss.only": "securities",
            "securities.columns": "secid,shortname,status,type",
            "engine": "stock",
            "market": "shares",
            "limit": limit
        }
        data = self._request(url, params)
        if not data:
            return pd.DataFrame()
        df = self._to_df(data.get("securities"))
        if df.empty:
            return df
        return df[
            (df["status"] == "A") &
            (df["type"].str.contains("share", case=False, na=False))
        ]

    def get_bulk_prices(self, secids):
        if not secids:
            return {}
        url = f"{BASE_URL}/engines/stock/markets/shares/securities.json"
        params = {
            "iss.meta": "off",
            "iss.only": "marketdata",
            "securities": ",".join(secids)
        }
        data = self._request(url, params)
        if not data:
            return {}
        df = self._to_df(data.get("marketdata"))
        if df.empty:
            return {}
        result = {}
        for _, row in df.iterrows():
            secid = row.get("SECID")
            last = row.get("LAST") or row.get("LCURRENTPRICE") or row.get("MARKETPRICE")
            prev = row.get("PREVPRICE") or row.get("LCLOSEPRICE")
            change = None
            if last is not None and prev not in (None, 0):
                change = (last - prev) / prev * 100
            result[secid] = {"last": last, "change": change}
        missing = [s for s in secids if s not in result]
        for secid in missing:
            result[secid] = self.get_price(secid)
        return result

    def get_price(self, secid):
        url = f"{BASE_URL}/engines/stock/markets/shares/securities/{secid}.json"
        params = {"iss.meta": "off", "iss.only": "marketdata"}
        data = self._request(url, params)
        if not data:
            return {"last": None, "change": None}
        df = self._to_df(data.get("marketdata"))
        if not df.empty:
            row = df.iloc[0]
            last = row.get("LAST") or row.get("LCURRENTPRICE") or row.get("MARKETPRICE")
            prev = row.get("PREVPRICE") or row.get("LCLOSEPRICE")
            if last is not None and prev not in (None, 0):
                change = (last - prev) / prev * 100
                return {"last": last, "change": change}
        return self._price_from_candles(secid)

    def _price_from_candles(self, secid):
        url = f"{BASE_URL}/engines/stock/markets/shares/securities/{secid}/candles.json"
        params = {"interval": 24, "limit": 2, "iss.meta": "off"}
        data = self._request(url, params)
        if not data:
            return {"last": None, "change": None}
        candles_block = data.get("candles") or (data[0].get("candles") if isinstance(data, list) else None)
        df = self._to_df(candles_block)
        if "close" in df.columns and len(df) >= 1:
            last = df["close"].iloc[-1]
            prev = df["close"].iloc[-2] if len(df) >= 2 else None
            if prev not in (None, 0):
                change = (last - prev) / prev * 100
                return {"last": last, "change": change}
            return {"last": last, "change": None}
        return {"last": None, "change": None}

    def get_history(self, secid, days=12):
        url = f"{BASE_URL}/engines/stock/markets/shares/securities/{secid}/candles.json"
        params = {"interval": 24, "limit": days, "iss.meta": "off"}
        data = self._request(url, params)
        if not data:
            return []
        candles_block = data.get("candles") or (data[0].get("candles") if isinstance(data, list) else None)
        df = self._to_df(candles_block)
        if "close" in df.columns:
            return df["close"].tolist()
        return []

    def get_full_candles(self, ticker, limit=2000, days=45):
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days)

        def load_from_board(board):
            url = f"{BASE_URL}/engines/stock/markets/shares/boards/{board}/securities/{ticker}/candles.json"
            params = {
                "iss.meta": "off",
                "interval": 24,
                "from": start_date.strftime("%Y-%m-%d"),
                "till": end_date.strftime("%Y-%m-%d"),
                "limit": limit
            }
            return self._request(url, params)

        data = load_from_board("TQBR")

        if not data or not data.get("candles", {}).get("data"):
            data = load_from_board("TQTF")

        if not data:
            return pd.DataFrame()

        candles_block = data.get("candles")

        if not candles_block:
            return pd.DataFrame()

        columns = candles_block.get("columns")
        rows = candles_block.get("data")

        if not columns or not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=columns)

        if "begin" not in df.columns:
            return pd.DataFrame()

        df["begin"] = pd.to_datetime(df["begin"], errors="coerce")

        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["begin", "open", "high", "low", "close"])
        df = df.sort_values("begin").reset_index(drop=True)

        
        df = df[
            (df["begin"].dt.date >= start_date) &
            (df["begin"].dt.date <= end_date)
        ]

        return df[["begin", "open", "high", "low", "close", "volume"]]

moex_client = MoexClient()


def fetch_securities_list():
    return moex_client.get_securities()

def fetch_bulk_prices(secids):
    return moex_client.get_bulk_prices(secids)

def fetch_price_data(secid):
    return moex_client.get_price(secid)

def fetch_historical(secid, days=12):
    return moex_client.get_history(secid, days)

def fetch_full_candles(ticker, limit=2000, days=45):
    return moex_client.get_full_candles(ticker, limit=limit, days=days)

class DataCache:
    CACHE_FILE = "dashboard_cache.json"
    @staticmethod
    def save(data):
        try:
            CacheRepository.save("dashboard_cache", data)
        except Exception:
            pass
    @staticmethod
    def load():
        try:
            return CacheRepository.load("dashboard_cache")
        except DatabaseUnavailable as e:
            print(f"[WARN] {e}")
            return None
        except Exception:
            return None

def load_companies_data():
    try:
        stocks = StockRepository.get_all_stocks()
        if stocks:
            return stocks

        json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "companies_data.json")
        with open(json_path, 'r', encoding='utf-8') as f:
            seed_data = json.load(f)
        StockRepository.seed_stocks(seed_data)
        return StockRepository.get_all_stocks()
    except DatabaseUnavailable as e:
        print(f"[ERROR] load_companies_data PostgreSQL: {e}")
        return {}
    except Exception as e:
        print(f"[ERROR] load_companies_data: {e}")
        return {}

COMPANIES_DB = load_companies_data()

RUSSIAN_TICKERS = [
    "SBER", "GAZP", "LKOH", "GMKN", "TATN", "ROSN", "NVTK", "YDEX", "MTSS", "CHMF",
    "PLZL", "ALRS", "SNGS", "SNGSP", "VTBR", "MOEX", "POLY", "MAGN", "PHOR", "NLMK",
    "TRNFP", "FIVE", "TCSG", "OZON", "ASTR", "SOFL", "HHRU", "WUSH", "RUAL", "AFLT",
    "IRAO", "FEES", "MVID", "FIXP", "QIWI", "SMLT", "RSTI", "ABRD", "BSPB", "LENT",
    "MSTT", "RKKE", "KMAZ", "BELU", "FLOT", "TGKA", "ROST", "SVAV", "UNAC", "VSMO"
]
DEMO_SECURITIES = [{"secid": ticker, "shortname": ticker} for ticker in RUSSIAN_TICKERS]

def get_company_details(ticker):
    ticker_upper = str(ticker or "").upper()

    def _safe(value, default="—"):
        if value is None or value == "":
            return default
        return value

    def _format_number(value):
        if isinstance(value, (int, float)):
            return f"{value:,.0f}".replace(",", " ")
        return str(value or "—")

    def _make_big_description(data):
        ticker_value = _safe(data.get("ticker"), ticker_upper)
        name = _safe(data.get("name"), ticker_value)
        fullname = _safe(data.get("fullname"), name)
        base_desc = str(data.get("description") or "").strip()

        sector = _safe(data.get("sector"))
        industry = _safe(data.get("industry"))
        country = _safe(data.get("country"), "Россия")
        founded = _safe(data.get("founded"))
        headquarters = _safe(data.get("headquarters"))
        employees = _format_number(data.get("employees"))
        ceo = _safe(data.get("ceo"))
        cfo = _safe(data.get("cfo"))
        website = _safe(data.get("website"))

        marketcap = data.get("marketcap")
        if isinstance(marketcap, (int, float)) and marketcap > 0:
            marketcap_text = f"{marketcap / 1e9:,.1f} млрд ₽".replace(",", " ")
        else:
            marketcap_text = "—"

        pe = data.get("peratio")
        pb = data.get("pbratio")
        roe = data.get("roe")
        div_yield = data.get("dividendyield")
        beta = data.get("beta")

        pe_text = f"{pe:.2f}" if isinstance(pe, (int, float)) and pe else "—"
        pb_text = f"{pb:.2f}" if isinstance(pb, (int, float)) and pb else "—"
        roe_text = f"{roe:.1f}%" if isinstance(roe, (int, float)) else "—"
        div_text = f"{div_yield:.1f}%" if isinstance(div_yield, (int, float)) else "—"
        beta_text = f"{beta:.2f}" if isinstance(beta, (int, float)) and beta else "—"

        paragraphs = [
            f"{fullname} — компания сектора «{sector}», работающая в отрасли «{industry}». Эмитент представлен на российском фондовом рынке под тикером {ticker_value} и относится к числу инструментов, за которыми инвесторы следят при анализе динамики Московской биржи.",
            base_desc or f"Компания {name} представлена на Московской бирже. В карточке отображаются основные сведения об эмитенте, история цены, рыночные показатели и справочная информация для анализа бумаги.",
            f"Компания была основана в {founded} году. Штаб-квартира расположена: {headquarters}. Основная деятельность компании связана с развитием профильного бизнеса, укреплением рыночных позиций, повышением операционной эффективности и адаптацией к изменениям экономической среды.",
            f"Численность сотрудников составляет около {employees} человек. Управление компанией осуществляет генеральный директор {ceo}; финансовое направление курирует {cfo}. Эти сведения помогают пользователю быстрее понять масштаб бизнеса и структуру управления эмитента.",
            f"С инвестиционной точки зрения бумагу можно рассматривать через несколько групп показателей: рыночную капитализацию, мультипликаторы, рентабельность, дивидендную доходность, волатильность и динамику цены. В локальной базе приложения для компании указана рыночная капитализация {marketcap_text}, P/E — {pe_text}, P/B — {pb_text}, ROE — {roe_text}, дивидендная доходность — {div_text}, beta — {beta_text}.",
            f"При анализе акции важно смотреть не только на текущую цену, но и на поведение графика за месяц, изменение объёмов торгов, устойчивость финансовых результатов и новости по компании. Такой подход позволяет сравнивать {name} с другими компаниями из сектора «{sector}» и принимать более взвешенные инвестиционные решения.",
            f"Дополнительную информацию о компании, корпоративные новости, отчётность и материалы для инвесторов можно найти на официальном сайте: {website}."
        ]

        return "\n\n".join(p.strip() for p in paragraphs if p and p.strip())

    if ticker_upper in COMPANIES_DB:
        data = COMPANIES_DB[ticker_upper].copy()

        data["description"] = _make_big_description(data)

        data["executives"] = [
            {"name": data.get("ceo", "—"), "title": "CEO"},
            {"name": data.get("cfo", "—"), "title": "CFO"}
        ]

        data["contacts"] = {
            "address": data.get("address", "—"),
            "phone": data.get("phone", "—"),
            "website": data.get("website", "—")
        }

        return data

    return {
        "ticker": ticker,
        "name": ticker,
        "sector": "—",
        "industry": "—",
        "country": "Россия",
        "employees": "—",
        "ceo": "—",
        "cfo": "—",
        "website": "—",
        "address": "—",
        "phone": "—",
        "description": (
            f"Компания {ticker} торгуется на Московской бирже.\n\n"
            "Подробная карточка по этому инструменту пока отсутствует в локальном файле companies_data.json.\n\n"
            "В приложении по-прежнему можно использовать поиск, текущую цену, свечной график за месяц, добавление в избранное и добавление бумаги в портфель."
        ),
        "executives": [
            {"name": "—", "title": "CEO"},
            {"name": "—", "title": "CFO"}
        ],
        "contacts": {
            "address": "—",
            "phone": "—",
            "website": "—"
        },
        "marketcap": 0,
        "peratio": 0,
        "pbratio": 0,
        "roe": 0,
        "dividendyield": 0,
        "financials": {}
    }

from app_state import app_state

class SearchPage(tk.Frame):
    def __init__(self, parent, dashboard_ref):
        super().__init__(parent, bg=BG)
        self.dashboard = dashboard_ref
        self.configure(bg=BG)

        self.securities_df = pd.DataFrame()
        self.filtered_list = []
        self.selected_secid = None
        self.search_after_id = None
        self.loading_completed = False
        self.favorite_set = set(app_state.profile.get('favorites', []))
        self.price_cache = {}

        self._load_securities_cache()
        self._build_ui()
        self._start_background_loading()
        self._start_price_updater()

    def _load_securities_cache(self):
        cache = DataCache.load()
        if cache and 'securities' in cache:
            self.securities_df = pd.DataFrame(cache['securities'])
        else:
            self.securities_df = pd.DataFrame()

    def _save_securities_cache(self):
        if not self.securities_df.empty:
            cache = DataCache.load() or {}
            cache['securities'] = self.securities_df.to_dict(orient='records')
            DataCache.save(cache)

    def _start_background_loading(self):
        def load():
            try:
                df = fetch_securities_list()
                if not df.empty:
                    self.securities_df = df
                    self._save_securities_cache()
                    self.after(0, self._on_data_loaded)
                else:
                    self.securities_df = pd.DataFrame(DEMO_SECURITIES)
                    self.after(0, self._on_data_loaded)
            except Exception:
                self.securities_df = pd.DataFrame(DEMO_SECURITIES)
                self.after(0, self._on_data_loaded)
        threading.Thread(target=load, daemon=True).start()

    def _on_data_loaded(self):
        self.loading_completed = True
        self.status_var.set(f"Загружено {len(self.securities_df)} инструментов")
        self._perform_search()

    def _build_ui(self):
        top_frame = tk.Frame(self, bg=BG)
        top_frame.pack(fill="x", padx=18, pady=(18, 8))

        tk.Label(top_frame, text="Поиск по тикеру или названию",
                 font=("Helvetica", 13, "bold"), bg=BG, fg=TEXT_PRI).pack(anchor="w", pady=(0,6))

        search_container = tk.Frame(top_frame, bg=BG)
        search_container.pack(fill="x")

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_change)
        self.search_entry = tk.Entry(search_container, textvariable=self.search_var,
                                     font=("Helvetica", 12), bg=SURFACE, fg=TEXT_PRI,
                                     insertbackground=TEXT_PRI, relief="flat",
                                     highlightthickness=1, highlightcolor=ACCENT,
                                     highlightbackground=BORDER)
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=6)

        search_btn = tk.Button(search_container, text="🔍 Найти", font=("Helvetica", 10, "bold"),
                               bg=ACCENT, fg="white", activebackground=ACCENT2,
                               bd=0, padx=16, pady=4, cursor="hand2", relief="flat",
                               command=self._perform_search)
        search_btn.pack(side="left", padx=(8,0))

        self.status_var = tk.StringVar(value="Загрузка списка инструментов...")
        tk.Label(top_frame, textvariable=self.status_var,
                 font=("Helvetica", 8), bg=BG, fg=TEXT_MUTED).pack(anchor="w", pady=(4,0))

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=18, pady=4)

        main_paned = tk.PanedWindow(self, orient="horizontal", bg=BG, sashwidth=2,
                                    sashrelief="flat", bd=0)
        main_paned.pack(fill="both", expand=True, padx=18, pady=(8,18))

        left_frame = tk.Frame(main_paned, bg=BG)
        main_paned.add(left_frame, width=320, minsize=220)

        tk.Label(left_frame, text="Результаты", font=("Helvetica", 10, "bold"),
                 bg=BG, fg=TEXT_SEC).pack(anchor="w", pady=(0,6))

        list_container = tk.Frame(left_frame, bg=SURFACE, bd=0,
                                  highlightthickness=1, highlightbackground=BORDER)
        list_container.pack(fill="both", expand=True)

        self.results_canvas = tk.Canvas(list_container, bg=SURFACE, highlightthickness=0)
        scrollbar = tk.Scrollbar(list_container, orient="vertical",
                                 command=self.results_canvas.yview,
                                 bg=SURFACE3, troughcolor=SURFACE2, width=12, relief="flat")
        self.results_canvas.configure(yscrollcommand=scrollbar.set)

        self.results_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.results_frame = tk.Frame(self.results_canvas, bg=SURFACE)
        self.results_window = self.results_canvas.create_window((0, 0), window=self.results_frame,
                                                                anchor="nw")

        def on_frame_configure(event):
            self.results_canvas.configure(scrollregion=self.results_canvas.bbox("all"))
        self.results_frame.bind("<Configure>", on_frame_configure)

        def on_canvas_configure(event):
            self.results_canvas.itemconfig(self.results_window, width=event.width)
        self.results_canvas.bind("<Configure>", on_canvas_configure)

        self.results_canvas.configure(yscrollincrement=1)
        self.results_canvas.bind("<MouseWheel>", self._on_results_scroll)
        self.results_canvas.bind("<Button-4>", self._on_results_scroll)
        self.results_canvas.bind("<Button-5>", self._on_results_scroll)
        self.results_frame.bind("<MouseWheel>", self._on_results_scroll)
        self.results_frame.bind("<Button-4>", self._on_results_scroll)
        self.results_frame.bind("<Button-5>", self._on_results_scroll)
        self.results_canvas.bind("<Enter>", lambda e: self.results_canvas.focus_force())

        # ---------- ПРАВАЯ ПАНЕЛЬ ----------
        right_frame = tk.Frame(main_paned, bg=SURFACE)
        main_paned.add(right_frame, width=450, minsize=300)
        right_frame.configure(highlightthickness=1, highlightbackground=BORDER)

        self.detail_canvas = tk.Canvas(right_frame, bg=SURFACE, highlightthickness=0)
        detail_scrollbar = tk.Scrollbar(right_frame, orient="vertical",
                                        command=self.detail_canvas.yview, bg=SURFACE2, width=8)
        self.detail_canvas.configure(yscrollcommand=detail_scrollbar.set)

        self.detail_container = tk.Frame(self.detail_canvas, bg=SURFACE, padx=12, pady=12)
        self.detail_window = self.detail_canvas.create_window((0,0), window=self.detail_container,
                                                              anchor="nw", width=self.detail_canvas.winfo_reqwidth())

        self.detail_canvas.pack(side="left", fill="both", expand=True)
        detail_scrollbar.pack(side="right", fill="y")

        self.detail_canvas.bind("<MouseWheel>", self._on_detail_mousewheel)
        self.detail_canvas.bind("<Button-4>", self._on_detail_mousewheel)
        self.detail_canvas.bind("<Button-5>", self._on_detail_mousewheel)

        self.detail_container.bind("<Configure>",
            lambda e: self.detail_canvas.configure(scrollregion=self.detail_canvas.bbox("all")))
        self.detail_canvas.bind("<Configure>",
            lambda e: self.detail_canvas.itemconfig(self.detail_window, width=e.width))

        self._show_placeholder_detail()

    def _on_results_scroll(self, event):
        try:
            if hasattr(event, "delta") and event.delta:
                step = int(-event.delta / 12)
                if step == 0:
                    step = -1 if event.delta > 0 else 1
                self.results_canvas.yview_scroll(step, "units")
            elif getattr(event, "num", None) == 4:
                self.results_canvas.yview_scroll(-8, "units")
            elif getattr(event, "num", None) == 5:
                self.results_canvas.yview_scroll(8, "units")
        except tk.TclError:
            pass
        return "break"


    def _on_detail_mousewheel(self, event):
        try:
            if hasattr(event, "delta") and event.delta:
                step = int(-event.delta / 120)
                if step == 0:
                    step = -1 if event.delta > 0 else 1
                self.detail_canvas.yview_scroll(step, "units")
            elif getattr(event, "num", None) == 4:
                self.detail_canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                self.detail_canvas.yview_scroll(1, "units")
        except Exception:
            pass
        return "break"

    def _bind_detail_mousewheel_recursive(self, widget):
        try:
            widget.bind("<MouseWheel>", self._on_detail_mousewheel)
            widget.bind("<Button-4>", self._on_detail_mousewheel)
            widget.bind("<Button-5>", self._on_detail_mousewheel)
        except Exception:
            pass

        for child in widget.winfo_children():
            self._bind_detail_mousewheel_recursive(child)


    def _bind_mousewheel_recursive(self, widget, handler):
        widget.bind("<MouseWheel>", handler)
        widget.bind("<Button-4>", handler)
        widget.bind("<Button-5>", handler)
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child, handler)

    def _get_company_name_for_list(self, secid, fallback=""):
        secid = str(secid or "").upper()
        fallback = str(fallback or "").strip()

        company = COMPANIES_DB.get(secid, {})
        name = (
            company.get("name")
            or company.get("shortname")
            or company.get("company_name")
            or company.get("title")
            or fallback
            or secid
        )

        name = str(name).strip()

        if name.upper() == secid:
            description = str(company.get("description") or company.get("about") or "").strip()
            if description:
                name = description.split("—")[0].strip()[:45]
            else:
                name = "Название компании не найдено"

        return name[:55]

    def _search_company_text(self, secid, shortname=""):
        secid = str(secid or "")
        shortname = str(shortname or "")
        company = COMPANIES_DB.get(secid.upper(), {})

        parts = [
            secid,
            shortname,
            company.get("name", ""),
            company.get("shortname", ""),
            company.get("company_name", ""),
            company.get("sector", ""),
            company.get("industry", ""),
            company.get("description", ""),
            company.get("about", ""),
        ]
        return " ".join(str(x) for x in parts if x).lower()

    def _bind_results_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_results_scroll)
        widget.bind("<Button-4>", self._on_results_scroll)
        widget.bind("<Button-5>", self._on_results_scroll)
        for child in widget.winfo_children():
            self._bind_results_mousewheel(child)

    def _show_placeholder_detail(self):
        for w in self.detail_container.winfo_children():
            w.destroy()
        tk.Label(self.detail_container, text="Выберите инструмент из списка",
                 font=("Helvetica", 11), bg=SURFACE, fg=TEXT_MUTED).pack(expand=True)

    def _on_search_change(self, *args):
        if self.search_after_id:
            self.after_cancel(self.search_after_id)
        self.search_after_id = self.after(300, self._perform_search)

    def _perform_search(self):
        query = self.search_var.get().strip().lower()
        if self.securities_df.empty:
            self.status_var.set("Данные ещё не загружены")
            self._update_results_display()
            return

        df = self.securities_df.copy()

        if query:
            rows = []
            for _, row in df.iterrows():
                secid = row.get("secid", "")
                shortname = row.get("shortname", "")
                search_text = self._search_company_text(secid, shortname)
                if query in search_text:
                    rows.append(row)
            filtered = pd.DataFrame(rows) if rows else df.iloc[0:0]
        else:
            filtered = df.head(100)

        self.filtered_list = filtered.to_dict(orient='records')
        self._update_results_display()
        self.status_var.set(f"Найдено: {len(self.filtered_list)}")

    def _update_results_display(self):
        for w in self.results_frame.winfo_children():
            w.destroy()
        if not self.filtered_list:
            tk.Label(self.results_frame, text="Нет результатов", bg=SURFACE, fg=TEXT_SEC,
                     font=("Helvetica", 10)).pack(pady=20)
            return
        for item in self.filtered_list:
            self._create_result_item(item)
        self.after(100, self._update_prices_bulk)
        self.results_frame.update_idletasks()
        self.results_canvas.configure(scrollregion=self.results_canvas.bbox("all"))

    def _create_result_item(self, item):
        secid = item['secid']
        name = self._get_company_name_for_list(secid, item.get('shortname', ''))

        frame = tk.Frame(self.results_frame, bg=SURFACE)
        frame.pack(fill="x", pady=1, padx=1)
        frame.secid = secid

        frame.grid_columnconfigure(0, minsize=44, weight=0)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, minsize=54, weight=0)
        frame.grid_columnconfigure(3, minsize=78, weight=0)

        icon = tk.Label(
            frame,
            text=secid[:2].upper(),
            font=("Helvetica", 10, "bold"),
            bg=ACCENT,
            fg=WHITE,
            width=3,
            pady=4,
            cursor="hand2"
        )
        icon.grid(row=0, column=0, padx=(6, 8), pady=6, sticky="nw")
        icon.bind("<Button-1>", lambda e, sid=secid: self._select_security(sid))

        text_frame = tk.Frame(frame, bg=SURFACE, cursor="hand2")
        text_frame.grid(row=0, column=1, sticky="ew", pady=5)
        text_frame.grid_columnconfigure(0, weight=1)
        text_frame.bind("<Button-1>", lambda e, sid=secid: self._select_security(sid))

        ticker_label = tk.Label(
            text_frame,
            text=secid,
            font=("Helvetica", 11, "bold"),
            bg=SURFACE,
            fg=ACCENT,          
            anchor="w",
            cursor="hand2"
        )
        ticker_label.grid(row=0, column=0, sticky="w")
        ticker_label.bind("<Button-1>", lambda e, sid=secid: self._select_security(sid))

        company_label = tk.Label(
            text_frame,
            text=name,
            font=("Helvetica", 8),
            bg=SURFACE,
            fg=TEXT_SEC,
            anchor="w",
            justify="left",
            wraplength=165,     
            cursor="hand2"
        )
        company_label.grid(row=1, column=0, sticky="w")
        company_label.bind("<Button-1>", lambda e, sid=secid: self._select_security(sid))

        actions_frame = tk.Frame(frame, bg=SURFACE)
        actions_frame.grid(row=0, column=2, padx=(6, 4), pady=6, sticky="n")

        fav_btn = tk.Button(
            actions_frame,
            text="⭐",
            font=("Helvetica", 10),
            bg=SURFACE,
            fg=TEXT_SEC,
            bd=0,
            padx=3,
            cursor="hand2",
            activebackground=SURFACE2
        )
        fav_btn.pack(side="left", padx=1)
        if secid in self.favorite_set:
            fav_btn.config(fg=AMBER, text="★")
        fav_btn.config(command=lambda s=secid, b=fav_btn: self._toggle_favorite(s, b))

        port_btn = tk.Button(
            actions_frame,
            text="📊",
            font=("Helvetica", 10),
            bg=SURFACE,
            fg=TEXT_SEC,
            bd=0,
            padx=3,
            cursor="hand2",
            activebackground=SURFACE2,
            command=lambda s=secid: self._add_to_portfolio(s)
        )
        port_btn.pack(side="left", padx=1)

        price_label = tk.Label(
            frame,
            text="...",
            font=("Helvetica", 10),
            bg=SURFACE,
            fg=TEXT_SEC,
            width=9,
            anchor="e"
        )
        price_label.grid(row=0, column=3, padx=(2, 8), pady=6, sticky="ne")
        frame.price_label = price_label

        def apply_row_bg(color):
            frame.configure(bg=color)
            text_frame.configure(bg=color)
            actions_frame.configure(bg=color)
            ticker_label.configure(bg=color, fg=ACCENT)
            company_label.configure(bg=color)
            price_label.configure(bg=color)
            fav_btn.configure(bg=color, activebackground=color)
            port_btn.configure(bg=color, activebackground=color)
            icon.configure(bg=ACCENT, fg=WHITE) 

        def on_enter(e):
            apply_row_bg("#102A4C")  

        def on_leave(e):
            apply_row_bg(SURFACE)

        for w in [frame, icon, text_frame, ticker_label, company_label,
                  actions_frame, fav_btn, port_btn, price_label]:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)

        frame.bind("<Button-1>", lambda e, sid=secid: self._select_security(sid))

        self._bind_results_mousewheel(frame)

    def _update_prices_bulk(self):
        if not self.filtered_list:
            return

        secids = [item['secid'] for item in self.filtered_list[:50]]

        prices = fetch_bulk_prices(secids)

        self.price_cache.update(prices)

        for widget in self.results_frame.winfo_children():

            if hasattr(widget, 'price_label'):

                secid = getattr(widget, 'secid', None)

                if not secid:
                    continue

                data = prices.get(secid)

                if data and data["last"] is not None:

                    price = f"{data['last']:,.2f}".replace(",", " ")

                    widget.price_label.config(
                        text=price,
                        fg=TEXT_SEC         
                    )

                else:

                    widget.price_label.config(
                        text="—",
                        fg=TEXT_MUTED
                    )


    def _start_price_updater(self):
        def loop():
            while True:
                time.sleep(5)
                if self.winfo_exists():
                    self.after(0, self._update_prices_bulk)
        threading.Thread(target=loop, daemon=True).start()

    def _toggle_favorite(self, secid, btn):
        if secid in self.favorite_set:
            self.favorite_set.remove(secid)
            app_state.profile['favorites'] = list(self.favorite_set)
            app_state.save()
            btn.config(fg=TEXT_SEC, text="⭐")
            messagebox.showinfo("Избранное", f"{secid} удалён из избранного")
        else:
            self.favorite_set.add(secid)
            app_state.profile['favorites'] = list(self.favorite_set)
            app_state.save()
            btn.config(fg=AMBER, text="★")
            messagebox.showinfo("Избранное", f"{secid} добавлен в избранное")
        if self.selected_secid == secid:
            self._update_detail_favorite_button(secid)

    def _update_detail_favorite_button(self, secid):
        if hasattr(self, 'detail_fav_btn') and self.detail_fav_btn.winfo_exists():
            if secid in self.favorite_set:
                self.detail_fav_btn.config(fg=AMBER, text="★ В избранном")
            else:
                self.detail_fav_btn.config(fg=TEXT_SEC, text="⭐ В избранное")

    def _add_to_portfolio(self, secid):
        data = self.price_cache.get(secid) or fetch_price_data(secid)
        current_price = data['last'] if data and data.get('last') else None
        if current_price is None:
            messagebox.showerror("Ошибка", f"Не удалось получить текущую цену для {secid}.")
            return

        dialog = tk.Toplevel(self)
        dialog.title(f"Добавить {secid} в портфель")
        dialog.geometry("400x280")
        dialog.configure(bg=BG)
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text=f"Добавление {secid}",
                 font=("Helvetica", 14, "bold"), bg=BG, fg=TEXT_PRI).pack(pady=15)

        price_frame = tk.Frame(dialog, bg=BG)
        price_frame.pack(fill="x", padx=20, pady=5)
        tk.Label(price_frame, text="Текущая цена:", font=("Helvetica", 11),
                 bg=BG, fg=TEXT_SEC).pack(side="left")
        tk.Label(price_frame, text=f"{current_price:.2f} ₽",
                 font=("Helvetica", 11, "bold"), bg=BG, fg=ACCENT).pack(side="right")

        form = tk.Frame(dialog, bg=BG)
        form.pack(fill="x", padx=20, pady=15)

        tk.Label(form, text="Цена покупки (₽):", bg=BG, fg=TEXT_SEC).grid(row=0, column=0, sticky="w", pady=5)
        price_var = tk.StringVar(value=f"{current_price:.2f}")
        price_entry = tk.Entry(form, textvariable=price_var, font=("Helvetica", 11),
                               bg=SURFACE, fg=TEXT_PRI, relief="flat", width=12)
        price_entry.grid(row=0, column=1, sticky="e", pady=5)

        tk.Label(form, text="Количество (лотов):", bg=BG, fg=TEXT_SEC).grid(row=1, column=0, sticky="w", pady=5)
        qty_var = tk.StringVar(value="1")
        qty_entry = tk.Entry(form, textvariable=qty_var, font=("Helvetica", 11),
                             bg=SURFACE, fg=TEXT_PRI, relief="flat", width=12)
        qty_entry.grid(row=1, column=1, sticky="e", pady=5)

        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        btn_frame = tk.Frame(dialog, bg=BG)
        btn_frame.pack(pady=20)

        def save():
            try:
                price = float(price_var.get())
                if price <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Ошибка", "Цена должна быть положительным числом")
                return
            try:
                qty = int(qty_var.get())
                if qty <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Ошибка", "Количество должно быть целым положительным числом")
                return

            existing = None
            for item in app_state.portfolio:
                if isinstance(item, dict) and item.get("secid") == secid:
                    existing = item
                    break

            if existing:
                old_qty = existing["quantity"]
                old_total = old_qty * existing["buy_price"]
                new_total = old_total + qty * price
                new_qty = old_qty + qty
                avg_price = new_total / new_qty
                existing["quantity"] = new_qty
                existing["buy_price"] = avg_price
                existing["buy_date"] = datetime.date.today().isoformat()
                messagebox.showinfo("Портфель", f"В портфеле уже было {old_qty} шт. {secid}.\n"
                                                f"Добавлено ещё {qty} шт. Теперь {new_qty} шт. по средней цене {avg_price:.2f} ₽")
            else:
                app_state.portfolio.append({
                    "secid": secid,
                    "quantity": qty,
                    "buy_price": price,
                    "buy_date": datetime.date.today().isoformat(),
                    "comment": ""
                })
                messagebox.showinfo("Портфель", f"{secid} добавлен в портфель в количестве {qty} шт.")

            app_state.save()
            dialog.destroy()
            if hasattr(self.dashboard, 'pages'):
                if 'portfolio' in self.dashboard.pages:
                    self.dashboard.pages['portfolio'].refresh()
                if 'profile' in self.dashboard.pages:
                    self.dashboard.pages['profile'].refresh_all()

        tk.Button(btn_frame, text="Сохранить", command=save,
                  font=("Helvetica", 10, "bold"), bg=ACCENT, fg=WHITE,
                  activebackground=ACCENT2, bd=0, padx=20, pady=6, cursor="hand2").pack(side="left", padx=5)
        tk.Button(btn_frame, text="Отмена", command=dialog.destroy,
                  font=("Helvetica", 10), bg=SURFACE2, fg=TEXT_PRI,
                  bd=0, padx=20, pady=6, cursor="hand2").pack(side="left", padx=5)

    def _select_security(self, secid):
        self.selected_secid = secid
        self._update_prices_bulk()
        self._show_detail_loading()
        threading.Thread(target=self._load_detail_data, args=(secid,), daemon=True).start()

        recent = app_state.profile.get('recently_viewed', [])
        if secid in recent:
            recent.remove(secid)
        recent.append(secid)
        if len(recent) > 20:
            recent = recent[-20:]
        app_state.profile['recently_viewed'] = recent
        app_state.save()

    def select_ticker(self, ticker):
        self._select_security(ticker)

    def _show_detail_loading(self):
        for w in self.detail_container.winfo_children():
            w.destroy()
        tk.Label(self.detail_container, text="Загрузка...", bg=SURFACE, fg=TEXT_MUTED).pack(expand=True)

    def _load_detail_data(self, secid):
        if not self.securities_df.empty:
            row = self.securities_df[self.securities_df['secid'] == secid]
            name = row.iloc[0]['shortname'] if not row.empty else secid
        else:
            name = secid
        price_info = self.price_cache.get(secid)
        if not price_info:
            price_info = fetch_price_data(secid)
        hist = fetch_historical(secid, 12)
        candles_30d = fetch_full_candles(secid, limit=80, days=45)
        details = get_company_details(secid)
        self.after(0, lambda: self._build_detail_panel(secid, name, price_info, hist, details, candles_30d))


    def _draw_candlestick_chart(self, parent, candles_df, ticker):
        chart_frame = tk.LabelFrame(
            parent,
            text=f"Свечной график за месяц — {ticker} (данные MOEX)",
            font=("Helvetica", 11, "bold"),
            bg=BG,
            fg=TEXT_PRI,
            foreground=TEXT_PRI
        )
        chart_frame.pack(fill="x", pady=(8, 12))

        canvas_width = 520
        canvas_height = 240
        canvas_holder = tk.Frame(chart_frame, bg=BG)
        canvas_holder.pack(fill="x", padx=10, pady=10)

        canvas = tk.Canvas(
            canvas_holder,
            bg=BG,
            width=canvas_width,
            height=canvas_height,
            highlightthickness=0
        )
        canvas.pack(anchor="center")

        try:
            if candles_df is None or candles_df.empty:
                raise ValueError("empty candles")

            df = candles_df.copy()

            df = df.tail(30).reset_index(drop=True)

            for col in ["open", "high", "low", "close"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.dropna(subset=["open", "high", "low", "close"])

            if df.empty or len(df) < 2:
                raise ValueError("not enough candles")

            left_pad = 48
            right_pad = 18
            top_pad = 20
            bottom_pad = 34

            chart_w = canvas_width - left_pad - right_pad
            chart_h = canvas_height - top_pad - bottom_pad

            min_price = float(df["low"].min())
            max_price = float(df["high"].max())

            price_range = max_price - min_price
            if price_range == 0:
                price_range = 1

            min_price -= price_range * 0.06
            max_price += price_range * 0.06
            price_range = max_price - min_price

            def y(price):
                return top_pad + (max_price - price) / price_range * chart_h

            def x(i):
                if len(df) == 1:
                    return left_pad + chart_w / 2
                return left_pad + i * (chart_w / (len(df) - 1))

            grid_color = BORDER
            for k in range(5):
                yy = top_pad + k * chart_h / 4
                canvas.create_line(left_pad, yy, canvas_width - right_pad, yy, fill=grid_color)
                price_val = max_price - k * price_range / 4
                canvas.create_text(
                    6,
                    yy,
                    anchor="w",
                    text=f"{price_val:.0f}",
                    fill=TEXT_MUTED,
                    font=("Helvetica", 8)
                )

            step = chart_w / max(len(df), 1)
            body_w = max(5, min(12, step * 0.55))

            for i, row in df.iterrows():
                o = float(row["open"])
                h = float(row["high"])
                l = float(row["low"])
                c = float(row["close"])

                xx = x(i)

                candle_color = GREEN if c >= o else RED

                y_open = y(o)
                y_close = y(c)
                y_high = y(h)
                y_low = y(l)

                
                canvas.create_line(
                    xx,
                    y_high,
                    xx,
                    y_low,
                    fill=candle_color,
                    width=1.2
                )

                
                top = min(y_open, y_close)
                bottom = max(y_open, y_close)

                if abs(bottom - top) < 2:
                    bottom = top + 2

                canvas.create_rectangle(
                    xx - body_w / 2,
                    top,
                    xx + body_w / 2,
                    bottom,
                    fill=candle_color,
                    outline=candle_color
                )

            
            if "begin" in df.columns:
                try:
                    first_date = pd.to_datetime(df["begin"].iloc[0]).strftime("%d.%m")
                    last_date = pd.to_datetime(df["begin"].iloc[-1]).strftime("%d.%m")

                    canvas.create_text(
                        left_pad,
                        canvas_height - 12,
                        text=first_date,
                        fill=TEXT_MUTED,
                        font=("Helvetica", 8),
                        anchor="w"
                    )

                    canvas.create_text(
                        canvas_width - right_pad,
                        canvas_height - 12,
                        text=last_date,
                        fill=TEXT_MUTED,
                        font=("Helvetica", 8),
                        anchor="e"
                    )
                except Exception:
                    pass

            
            first_close = float(df["close"].iloc[0])
            last_close = float(df["close"].iloc[-1])
            month_change = (last_close - first_close) / first_close * 100 if first_close else 0

            info_color = GREEN if month_change >= 0 else RED
            sign = "+" if month_change >= 0 else ""

            canvas.create_text(
                left_pad,
                8,
                anchor="w",
                text=f"Изменение за месяц: {sign}{month_change:.2f}%",
                fill=info_color,
                font=("Helvetica", 9, "bold")
            )

        except Exception:
            canvas.create_text(
                canvas_width / 2,
                canvas_height / 2,
                text="Не удалось загрузить свечной график",
                fill=TEXT_MUTED,
                font=("Helvetica", 10)
            )


    def _format_company_description(self, description):
        """Берёт описание из companies_data.json и красиво разбивает его на абзацы."""
        description = str(description or "").strip()
        if not description:
            return "Информация о компании пока не заполнена."

        if "\n" in description:
            return description

        parts = []
        for sentence in description.split(". "):
            sentence = sentence.strip()
            if not sentence:
                continue
            if not sentence.endswith("."):
                sentence += "."
            parts.append(sentence)

        return "\n\n".join(parts)


    def _build_detail_panel(self, secid, name, price_info, hist, details, candles_30d=None):
        for w in self.detail_container.winfo_children():
            w.destroy()

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', background=SURFACE, foreground=TEXT_SEC,
                        padding=[12, 4], borderwidth=0, font=('Helvetica', 10))
        style.map('TNotebook.Tab',
                  background=[('selected', ACCENT)],
                  foreground=[('selected', WHITE)])

        notebook = ttk.Notebook(self.detail_container)
        notebook.pack(fill='both', expand=True)

        overview_frame = tk.Frame(notebook, bg=BG)
        notebook.add(overview_frame, text='Обзор')

        header_frame = tk.Frame(overview_frame, bg=BG)
        header_frame.pack(fill='x', pady=(0, 15))
        tk.Label(header_frame, text=secid, font=("Helvetica", 20, "bold"),
                 bg=BG, fg=ACCENT).pack(side='left')
        tk.Label(header_frame, text=name, font=("Helvetica", 13),
                 bg=BG, fg=TEXT_SEC).pack(side='left', padx=10)

        price_frame = tk.Frame(overview_frame, bg=BG)
        price_frame.pack(fill='x', pady=(0, 15))
        if price_info and price_info['last'] is not None:
            last = price_info['last']
            change = price_info.get('change')
            color = GREEN if change is not None and change >= 0 else RED
            arrow = "▲" if change is not None and change >= 0 else "▼"
            tk.Label(price_frame, text=f"{last:,.2f} ₽".replace(",", " "),
                     font=("Helvetica", 26, "bold"), bg=BG, fg=TEXT_PRI).pack(side='left')
            if change is not None:
                change_badge = tk.Frame(price_frame,
                                        bg=SURFACE2 if color == GREEN else RED)
                change_badge.pack(side='left', padx=12, pady=4)
                tk.Label(change_badge, text=f"{arrow} {change:+.2f}%",
                         font=("Helvetica", 13, "bold"),
                         bg=change_badge['bg'], fg=color).pack(padx=8, pady=3)
        else:
            tk.Label(price_frame, text="Нет данных", font=("Helvetica", 16),
                     bg=BG, fg=TEXT_MUTED).pack()

        self._draw_candlestick_chart(overview_frame, candles_30d, secid)

        info_frame = tk.Frame(overview_frame, bg=BG)
        info_frame.pack(fill='x', pady=5)
        cols = [
            ("Сектор", details.get('sector', '—')),
            ("Индустрия", details.get('industry', '—')),
            ("Страна", details.get('country', '—')),
            ("Сотрудников", f"{details.get('employees', '—'):,}".replace(",", " ") if isinstance(details.get('employees'), int) else '—')
        ]
        for i, (label, value) in enumerate(cols):
            f = tk.Frame(info_frame, bg=BG)
            f.pack(side='left', expand=True, fill='x', padx=5)
            tk.Label(f, text=label, font=("Helvetica", 8), bg=BG, fg=TEXT_MUTED).pack(anchor='w')
            tk.Label(f, text=value, font=("Helvetica", 10, "bold"), bg=BG, fg=TEXT_PRI).pack(anchor='w')

        stats_frame = tk.LabelFrame(overview_frame, text="Ключевые показатели",
                                    font=("Helvetica", 11, "bold"),
                                    bg=BG, fg=TEXT_PRI, foreground=TEXT_PRI)
        stats_frame.pack(fill='x', pady=12)

        market_cap = details.get('marketcap')
        market_cap_str = f"{market_cap / 1e9:,.1f} млрд ₽" if isinstance(market_cap, (int, float)) else "—"
        rows = [
            ("Рыночная капитализация", market_cap_str),
            ("P/E", f"{details.get('peratio'):.2f}" if details.get('peratio') else "—"),
            ("P/B", f"{details.get('pbratio'):.2f}" if details.get('pbratio') else "—"),
            ("ROE", f"{details.get('roe'):.1f}%" if details.get('roe') else "—"),
            ("Дивидендная доходность", f"{details.get('dividendyield'):.1f}%" if details.get('dividendyield') else "—"),
            ("Beta", f"{details.get('beta'):.2f}" if details.get('beta') else "—"),
        ]
        for label, value in rows:
            if value and value != "—":
                rowf = tk.Frame(stats_frame, bg=BG)
                rowf.pack(fill='x', padx=10, pady=2)
                tk.Label(rowf, text=label + ":", font=("Helvetica", 9), bg=BG, fg=TEXT_SEC).pack(side='left')
                tk.Label(rowf, text=value, font=("Helvetica", 9, "bold"), bg=BG, fg=TEXT_PRI).pack(side='right')

        description = details.get('description') or f"Компания {secid} представлена на Московской бирже. В карточке отображаются основные сведения об эмитенте, рыночные показатели, история цены и доступная справочная информация."
        description = self._format_company_description(description)

        about_frame = tk.LabelFrame(overview_frame, text="О компании",
                                    font=("Helvetica", 11, "bold"),
                                    bg=BG, fg=TEXT_PRI, foreground=TEXT_PRI)
        about_frame.pack(fill='x', pady=12)

        about_text = tk.Text(
            about_frame,
            height=18,
            bg=BG,
            fg=TEXT_PRI,
            font=("Helvetica", 10),
            wrap='word',
            borderwidth=0,
            spacing1=5,
            spacing2=3,
            spacing3=5
        )
        about_text.insert('1.0', description)
        about_text.config(state='disabled')
        about_text.pack(fill='x', padx=14, pady=12)
.
        about_text.bind("<MouseWheel>", self._on_detail_mousewheel)
        about_text.bind("<Button-4>", self._on_detail_mousewheel)
        about_text.bind("<Button-5>", self._on_detail_mousewheel)


        action_frame = tk.Frame(overview_frame, bg=BG)
        action_frame.pack(pady=(10, 0))

        if secid in self.favorite_set:
            fav_text = "★ В избранном"
            fav_color = AMBER
        else:
            fav_text = "⭐ В избранное"
            fav_color = TEXT_SEC
        self.detail_fav_btn = tk.Button(action_frame, text=fav_text,
                                        font=("Helvetica", 11), bg=SURFACE2, fg=fav_color,
                                        activebackground=SURFACE3, bd=0, padx=16, pady=8, cursor="hand2",
                                        command=lambda s=secid: self._toggle_favorite_from_detail(s))
        self.detail_fav_btn.pack(side='left', padx=5)

        port_btn_state = "normal" if (price_info and price_info['last']) else "disabled"
        port_btn = tk.Button(action_frame, text="📊 В портфель",
                             font=("Helvetica", 11), bg=ACCENT, fg=WHITE,
                             activebackground=ACCENT2, bd=0, padx=16, pady=8,
                             cursor="hand2", state=port_btn_state,
                             command=lambda: self._add_to_portfolio(secid))
        port_btn.pack(side='left', padx=5)

    
        financials = details.get('financials', {})
        if financials:
            finance_frame = tk.Frame(notebook, bg=BG)
            notebook.add(finance_frame, text='Финансы')
            tree_frame = tk.Frame(finance_frame, bg=BG)
            tree_frame.pack(fill='both', expand=True, padx=5, pady=5)
            columns = ('year', 'revenue', 'net_income', 'ebitda', 'total_debt', 'free_cash_flow')
            tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=6)
            style.configure('Treeview',
                            background=SURFACE,
                            foreground=TEXT_PRI,
                            fieldbackground=SURFACE,
                            rowheight=26,
                            borderwidth=0)
            style.configure('Treeview.Heading',
                            background=ACCENT,
                            foreground=WHITE,
                            font=('Helvetica', 10, 'bold'),
                            borderwidth=0)
            tree.column('year', width=70, anchor='center', stretch=False)
            tree.column('revenue', width=130, anchor='e', stretch=False)
            tree.column('net_income', width=150, anchor='e', stretch=False)
            tree.column('ebitda', width=120, anchor='e', stretch=False)
            tree.column('total_debt', width=130, anchor='e', stretch=False)
            tree.column('free_cash_flow', width=160, anchor='e', stretch=False)
            tree.heading('year', text='Год', anchor='center')
            tree.heading('revenue', text='Выручка (млрд ₽)', anchor='center')
            tree.heading('net_income', text='Чистая прибыль', anchor='center')
            tree.heading('ebitda', text='EBITDA', anchor='center')
            tree.heading('total_debt', text='Долг', anchor='center')
            tree.heading('free_cash_flow', text='FCF', anchor='center')
            scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            tree.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
            for year, data in financials.items():
                tree.insert('', 'end', values=(
                    year,
                    f"{data.get('revenue', 0)/1e9:.1f}",
                    f"{data.get('net_income', 0)/1e9:.1f}",
                    f"{data.get('ebitda', 0)/1e9:.1f}",
                    f"{data.get('total_debt', 0)/1e9:.1f}",
                    f"{data.get('free_cash_flow', 0)/1e9:.1f}",
                ))

        execs = details.get('executives', [])
        if execs:
            exec_frame = tk.Frame(notebook, bg=BG)
            notebook.add(exec_frame, text='Руководство')
            for ex in execs:
                f = tk.Frame(exec_frame, bg=SURFACE)
                f.pack(fill='x', pady=2, padx=10)
                f.configure(highlightthickness=1, highlightbackground=BORDER)
                tk.Label(f, text=ex.get('name', '—'), font=("Helvetica", 11, "bold"),
                         bg=SURFACE, fg=TEXT_PRI).pack(anchor='w', padx=10, pady=(8,0))
                tk.Label(f, text=ex.get('title', '—'), font=("Helvetica", 9),
                         bg=SURFACE, fg=TEXT_SEC).pack(anchor='w', padx=10, pady=(0,8))

   
        contacts = details.get('contacts', {})
        if contacts:
            contact_frame = tk.Frame(notebook, bg=BG)
            notebook.add(contact_frame, text='Контакты')
            for label, key in [('Адрес', 'address'), ('Телефон', 'phone'), ('Веб-сайт', 'website')]:
                val = contacts.get(key, '—')
                if val and val != '—':
                    f = tk.Frame(contact_frame, bg=BG)
                    f.pack(fill='x', pady=5, padx=15)
                    tk.Label(f, text=label+":", font=("Helvetica", 10, "bold"), bg=BG, fg=TEXT_SEC).pack(anchor='w')
                    tk.Label(f, text=val, font=("Helvetica", 10), bg=BG, fg=TEXT_PRI, wraplength=350, justify='left').pack(anchor='w', pady=(2,0))

      
        stock_frame = tk.Frame(notebook, bg=BG)
        notebook.add(stock_frame, text='Детали акций')
        left_col = tk.Frame(stock_frame, bg=BG)
        left_col.pack(side='left', fill='both', expand=True, padx=(0,5))
        right_col = tk.Frame(stock_frame, bg=BG)
        right_col.pack(side='right', fill='both', expand=True, padx=(5,0))

        def add_field(parent, label, value):
            f = tk.Frame(parent, bg=SURFACE)
            f.pack(fill='x', pady=2)
            f.configure(highlightthickness=1, highlightbackground=BORDER)
            tk.Label(f, text=label, font=("Helvetica", 10, "bold"), bg=SURFACE, fg=TEXT_SEC).pack(side='left', padx=10, pady=6)
            tk.Label(f, text=value, font=("Helvetica", 10), bg=SURFACE, fg=TEXT_PRI).pack(side='right', padx=10, pady=6)

        add_field(left_col, "ISIN", details.get('isin', '—'))
        add_field(left_col, "CUSIP", details.get('cusip', '—'))
        add_field(left_col, "CIK", details.get('cik', '—'))
        add_field(left_col, "Фискальный год", details.get('fiscalyearend', '—'))
        add_field(left_col, "Дата основания", str(details.get('founded', '—')))
        add_field(left_col, "Штаб-квартира", details.get('headquarters', '—'))

        prev_close = details.get('previousclose')
        add_field(right_col, "Пред. закрытие", f"{prev_close:.2f} ₽" if prev_close else "—")
        open_price = details.get('open')
        add_field(right_col, "Открытие", f"{open_price:.2f} ₽" if open_price else "—")
        add_field(right_col, "Дневной диапазон", details.get('dayrange', '—'))
        add_field(right_col, "52-нед. диапазон", details.get('52weekrange', '—'))
        volume = details.get('volume')
        add_field(right_col, "Объём (посл.)", f"{volume:,.0f}".replace(",", " ") if volume else "—")
        avg_volume = details.get('avgvolume')
        add_field(right_col, "Ср. объём (3 мес.)", f"{avg_volume:,.0f}".replace(",", " ") if avg_volume else "—")

        
        self._bind_detail_mousewheel_recursive(self.detail_container)

    def _toggle_favorite_from_detail(self, secid):
        if secid in self.favorite_set:
            self.favorite_set.remove(secid)
            app_state.profile['favorites'] = list(self.favorite_set)
            app_state.save()
            self.detail_fav_btn.config(text="⭐ В избранное", fg=TEXT_SEC)
            messagebox.showinfo("Избранное", f"{secid} удалён из избранного")
        else:
            self.favorite_set.add(secid)
            app_state.profile['favorites'] = list(self.favorite_set)
            app_state.save()
            self.detail_fav_btn.config(text="★ В избранном", fg=AMBER)
            messagebox.showinfo("Избранное", f"{secid} добавлен в избранное")

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    class FakeDashboard: pass
    dashboard = FakeDashboard()
    app = SearchPage(root, dashboard)
    app.pack(fill="both", expand=True)
    root.deiconify()
    root.mainloop()

