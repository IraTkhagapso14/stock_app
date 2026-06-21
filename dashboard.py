# dashboard.py
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk
import threading
import io
import datetime
import json
import os
import sys
import time
import re
import webbrowser
import subprocess
import requests

from app_state import app_state
from postgres_storage import CacheRepository, DatabaseUnavailable

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False

import feedparser
import pandas as pd
import xml.etree.ElementTree as ET

# ─── Цветовая схема ──────────────────────────────────────────────────────────
BG       = "#0D1117"
SURFACE  = "#161B22"
SURFACE2 = "#1C2333"
SURFACE3 = "#21262D"
BORDER   = "#30363D"
ACCENT   = "#2F81F7"
ACCENT2  = "#388BFD"
GREEN    = "#3FB950"
GREEN_DIM= "#1A4D2E"
RED      = "#F85149"
RED_DIM  = "#4D1F1F"
AMBER    = "#D29922"
AMBER_DIM= "#3D2E00"
PURPLE   = "#BC8CFF"
TEXT_PRI = "#E6EDF3"
TEXT_SEC = "#8B949E"
TEXT_MUTED= "#484F58"
WHITE    = "#FFFFFF"

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

# ─── Sparkline ────────────────────────────────────────────────────────────────
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

# ─── Кэширование ──────────────────────────────────────────────────────────────
class DataCache:
    CACHE_FILE = "dashboard_cache.json"
    @staticmethod
    def save(data):
        try:
            CacheRepository.save("dashboard_cache", data)
        except Exception as e:
            print("[WARN] Cache save error:", e)
    @staticmethod
    def load():
        try:
            return CacheRepository.load("dashboard_cache")
        except DatabaseUnavailable as e:
            print("[WARN]", e)
            return None
        except Exception as e:
            print("[WARN] Cache load error:", e)
            return None

# ─── Демо-данные (резерв) ─────────────────────────────────────────────────────
DEMO_INDICES = [
    {"name":"Индекс МосБиржи","value":"3,280.5","change":"+0.42%","up":True,"data":[3240,3250,3245,3260,3255,3270,3265,3275,3270,3280,3275,3280]},
    {"name":"Индекс РТС","value":"1,150.3","change":"-0.18%","up":False,"data":[1160,1158,1159,1155,1156,1152,1153,1149,1150,1148,1149,1150]},
    {"name":"USDRUB","value":"92.45","change":"+0.32%","up":True,"data":[92.0,92.1,92.0,92.2,92.1,92.3,92.2,92.4,92.3,92.5,92.4,92.45]},
]
DEMO_GAINERS = [
    {"ticker":"SBER","name":"Сбербанк","price":"318.94 ₽","change":"+1.24%","data":[310,312,311,314,313,316,315,317,316,318,317,318]},
    {"ticker":"GAZP","name":"Газпром","price":"134.47 ₽","change":"+0.86%","data":[132,133,132,134,133,135,134,135,134,136,135,134]},
    {"ticker":"GMKN","name":"Норникель","price":"16,250 ₽","change":"+0.52%","data":[16000,16100,16050,16200,16150,16250,16200,16300,16250,16300,16280,16250]},
]
DEMO_LOSERS = [
    {"ticker":"LKOH","name":"Лукойл","price":"5,506.5 ₽","change":"-0.34%","data":[5540,5530,5535,5520,5525,5510,5515,5500,5505,5500,5505,5506]},
    {"ticker":"TATN","name":"Татнефть","price":"752.4 ₽","change":"-0.48%","data":[758,756,757,755,754,753,752,751,752,751,752,752]},
    {"ticker":"ROSN","name":"Роснефть","price":"580.2 ₽","change":"-0.21%","data":[583,582,582,581,581,580,580,579,580,579,580,580]},
]
DEMO_NEWS = [
    {"title":"ЦБ РФ сохранил ключевую ставку 16%","description":"Банк России принял решение сохранить ключевую ставку на уровне 16% годовых.","source":"Ведомости","time":"2 ч назад","tag":"Экономика","tag_color":GREEN,"img_url":"https://via.placeholder.com/80x60/1C2333/3FB950?text=CBR","link":"#"},
    {"title":"Сбербанк отчитался о рекордной прибыли","description":"Чистая прибыль Сбербанка по МСФО за 2025 год выросла на 22%.","source":"Ведомости","time":"4 ч назад","tag":"Экономика","tag_color":GREEN,"img_url":"https://via.placeholder.com/80x60/1C2333/3FB950?text=SBER","link":"#"},
    {"title":"Газпром увеличил поставки в Китай","description":"Поставки газа по «Силе Сибири» вышли на новый суточный рекорд.","source":"Ведомости","time":"6 ч назад","tag":"Экономика","tag_color":GREEN,"img_url":"https://via.placeholder.com/80x60/1C2333/3FB950?text=GAZP","link":"#"},
]
DEMO_RECENT_IPO = [
    {"ticker":"RBRK","name":"Rubrik","date":"20 мар 2025","price":"$32.00","now":"$41.20","change":"+28.8%","up":True},
    {"ticker":"ALAB","name":"Astera Labs","date":"20 мар 2025","price":"$36.00","now":"$68.50","change":"+90.3%","up":True},
]
DEMO_UPCOMING_IPO = [
    {"ticker":"KLAI","name":"Klarna","date":"15 апр 2025","valuation":"$15 млрд","sector":"Финтех","status":"Подано"},
    {"ticker":"SHPF","name":"Shein","date":"Q2 2025","valuation":"$60 млрд","sector":"Ритейл","status":"Ожидается"},
]

# ─── Работа с MOEX ISS (свечи) ───────────────────────────────────────────────
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

def get_moex_data(url, params):
    try:
        resp = requests.get(url, params=params, timeout=15, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and len(data) >= 2:
            meta = data[0]
            rows = data[1]
            columns = meta.get('columns') if isinstance(meta, dict) else None
            if columns and rows:
                return pd.DataFrame(rows, columns=columns)
        if isinstance(data, dict):
            if 'candles' in data:
                candles = data['candles']
                if isinstance(candles, dict) and 'data' in candles:
                    columns = candles.get('columns', [])
                    rows = candles['data']
                    if columns and rows:
                        return pd.DataFrame(rows, columns=columns)
            history = data.get('history') or data.get('history.cursor')
            if history and isinstance(history, dict):
                columns = history.get('columns')
                rows = history.get('data', [])
                if columns and rows:
                    return pd.DataFrame(rows, columns=columns)
        return pd.DataFrame()
    except Exception as e:
        print(f"[ERROR] MOEX error for {url}: {e}")
        return pd.DataFrame()

def get_moex_candles(security, board='TQBR', interval='24', limit=30):
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=45)
    url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/{board}/securities/{security}/candles.json"
    params = {
        'iss.meta': 'off',
        'interval': interval,
        'from': start_date.strftime('%Y-%m-%d'),
        'till': end_date.strftime('%Y-%m-%d'),
        'limit': limit,
        'sort_order': 'desc',
        'sort_column': 'begin',
    }
    df = get_moex_data(url, params)
    if df.empty:
        url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQTF/securities/{security}/candles.json"
        df = get_moex_data(url, params)
    if df.empty or 'close' not in df.columns:
        return pd.DataFrame()
    df['begin'] = pd.to_datetime(df['begin'])
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df = df.dropna(subset=['close']).sort_values('begin')
    df = df.rename(columns={'begin': 'TRADEDATE', 'close': 'CLOSE'})
    return df[['TRADEDATE', 'CLOSE']]

def get_moex_index_candles(index_name='IMOEX', interval='24', limit=30):
    url = f"https://iss.moex.com/iss/engines/stock/markets/index/securities/{index_name}/candles.json"
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=45)
    params = {
        'iss.meta': 'off',
        'interval': interval,
        'from': start_date.strftime('%Y-%m-%d'),
        'till': end_date.strftime('%Y-%m-%d'),
        'limit': limit,
        'sort_order': 'desc',
        'sort_column': 'begin',
    }
    df = get_moex_data(url, params)
    if df.empty or 'close' not in df.columns:
        return pd.DataFrame()
    df['begin'] = pd.to_datetime(df['begin'])
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df = df.dropna(subset=['close']).sort_values('begin')
    df = df.rename(columns={'begin': 'TRADEDATE', 'close': 'CLOSE'})
    return df[['TRADEDATE', 'CLOSE']]

def fetch_cbr_currency(currency_code='USD'):
    try:
        url = "https://www.cbr.ru/scripts/XML_daily.asp"
        resp = requests.get(url, timeout=5, headers=HEADERS)
        resp.encoding = 'windows-1251'
        root = ET.fromstring(resp.text)
        for valute in root.findall('Valute'):
            if valute.find('CharCode').text == currency_code:
                return float(valute.find('Value').text.replace(',', '.'))
    except:
        pass
    return None

def fetch_indices_moex():
    result = []
    indices = {"IMOEX": "Индекс МосБиржи", "RTSI": "Индекс РТС"}
    for ticker, name in indices.items():
        df = get_moex_index_candles(ticker, limit=30)
        if not df.empty and len(df) >= 2:
            closes = df['CLOSE'].tolist()
            last = closes[-1]
            prev = closes[-2]
            change = (last - prev) / prev * 100 if prev != 0 else 0
            hist = closes[-12:] if len(closes) >= 12 else closes
            result.append({
                "name": name,
                "value": f"{last:,.2f}".replace(",", " "),
                "change": f"{change:+.2f}%",
                "up": change >= 0,
                "data": hist
            })
    usd_rate = fetch_cbr_currency('USD')
    eur_rate = fetch_cbr_currency('EUR')
    cny_rate = fetch_cbr_currency('CNY')
    if usd_rate is None:
        df_usd = get_moex_candles('USDRUB_TOM', board='CETS', limit=2)
        if not df_usd.empty and len(df_usd) >= 2:
            usd_rate = df_usd['CLOSE'].iloc[-1]
    if eur_rate is None:
        df_eur = get_moex_candles('EURRUB_TOM', board='CETS', limit=2)
        if not df_eur.empty and len(df_eur) >= 2:
            eur_rate = df_eur['CLOSE'].iloc[-1]
    if cny_rate is None:
        df_cny = get_moex_candles('CNYRUB_TOM', board='CETS', limit=2)
        if not df_cny.empty and len(df_cny) >= 2:
            cny_rate = df_cny['CLOSE'].iloc[-1]
    if usd_rate:
        result.append({"name": "USDRUB", "value": f"{usd_rate:,.2f}".replace(",", " "), "change": "—", "up": True, "data": [usd_rate-1, usd_rate]})
    if eur_rate:
        result.append({"name": "EURRUB", "value": f"{eur_rate:,.2f}".replace(",", " "), "change": "—", "up": True, "data": [eur_rate-1, eur_rate]})
    if cny_rate:
        result.append({"name": "CNYRUB", "value": f"{cny_rate:,.2f}".replace(",", " "), "change": "—", "up": True, "data": [cny_rate-0.1, cny_rate]})
    return result if result else None

def fetch_movers_moex():
    tickers = [
        "SBER", "GAZP", "LKOH", "GMKN", "TATN", "NVTK", "ROSN", "YDEX",
        "PLZL", "ALRS", "MTSS", "CHMF", "SNGS", "SNGSP", "VTBR", "MOEX",
        "POLY", "MAGN", "PHOR", "NLMK", "TRNFP", "FIVE", "TCSG", "OZON",
        "ASTR", "SOFL", "HHRU", "WUSH", "RUAL", "AFLT", "IRAO", "FEES"
    ]
    data = []
    for t in tickers:
        df = get_moex_candles(t, board='TQBR', limit=2)
        if df.empty:
            df = get_moex_candles(t, board='TQTF', limit=2)
        if df.empty or len(df) < 2:
            continue
        last, prev = df['CLOSE'].iloc[-1], df['CLOSE'].iloc[-2]
        change = (last - prev) / prev * 100 if prev != 0 else 0
        data.append({"ticker": t, "name": t, "last": last, "prev": prev, "change": change})
        time.sleep(0.1)
    if not data:
        return None, None
    data.sort(key=lambda x: x['change'], reverse=True)
    gainers_raw = data[:5]
    losers_raw = sorted(data, key=lambda x: x['change'])[:5]
    gainers, losers = [], []
    def build_item(item):
        hist_df = get_moex_candles(item['ticker'], limit=12)
        hist = hist_df['CLOSE'].tolist() if not hist_df.empty else [item['prev'], item['last']]
        return {
            "ticker": item['ticker'],
            "name": item['name'],
            "price": f"{item['last']:,.2f} ₽".replace(",", " "),
            "change": f"{item['change']:+.2f}%",
            "data": hist
        }
    for item in gainers_raw:
        try:
            gainers.append(build_item(item))
        except Exception as e:
            print(f"[WARN] Ошибка обработки {item['ticker']}: {e}")
    for item in losers_raw:
        try:
            losers.append(build_item(item))
        except Exception as e:
            print(f"[WARN] Ошибка обработки {item['ticker']}: {e}")
    return gainers, losers

def fetch_news_rss():
    url = "https://www.vedomosti.ru/rss/rubric/economics/macro"
    try:
        feed = feedparser.parse(url)
        if not feed.entries:
            print("[WARN] RSS-лента Ведомостей пуста.")
            return None
        news = []
        for e in feed.entries[:5]:
            title = e.get("title", "")
            link = e.get("link", "#")
            desc = re.sub(r'<[^>]+>', '', e.get("description", "") or e.get("summary", ""))
            if len(desc) > 120:
                desc = desc[:120] + "..."
            published = e.get("published", "") or e.get("pubDate", "")
            time_str = ""
            if published:
                try:
                    dt = datetime.datetime.strptime(published, "%a, %d %b %Y %H:%M:%S %z")
                    time_str = dt.strftime("%d.%m.%Y %H:%M")
                except:
                    time_str = published[:16]
            img_url = "https://via.placeholder.com/80x60/1C2333/3FB950?text=Vedomosti"
            if 'media_content' in e and e.media_content:
                img_url = e.media_content[0].get('url', img_url)
            elif 'enclosure' in e and e.enclosure:
                img_url = e.enclosure.get('url', img_url)
            elif 'description' in e:
                match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', e.description)
                if match:
                    img_url = match.group(1)
            news.append({
                "title": title,
                "description": desc,
                "source": "Ведомости",
                "time": time_str,
                "tag": "Макроэкономика",
                "tag_color": GREEN,
                "img_url": img_url,
                "link": link
            })
        if news:
            print(f"[INFO] Загружено {len(news)} новостей из Ведомостей (Макроэкономика).")
            return news
        else:
            return None
    except Exception as e:
        print(f"[ERROR] Ошибка загрузки RSS {url}: {e}")
        return None


def _parse_moex_ipo_calendar_tables():
    """
    Пытается получить реальные данные IPO с календаря Московской биржи.
    Если страница недоступна или структура изменилась — возвращает пустой список.
    """
    url = "https://www.moex.com/s3767"
    try:
        html = requests.get(url, timeout=10, headers=HEADERS).text
        tables = pd.read_html(html)
        rows = []

        for table in tables:
            if table.empty:
                continue

            # Нормализуем названия колонок
            table.columns = [str(c).strip() for c in table.columns]

            for _, row in table.iterrows():
                values = [str(v).strip() for v in row.tolist() if str(v).strip() not in ("nan", "None", "")]
                if len(values) < 2:
                    continue

                joined = " | ".join(values)

                # Ищем строку, похожую на IPO/размещение
                if not any(word in joined.lower() for word in ["пао", "ооо", "ipo", "размещ", "эмитент"]):
                    continue

                date = values[0] if values else "—"
                name = values[1] if len(values) > 1 else values[0]
                sector = values[2] if len(values) > 2 else "—"

                ticker = "—"
                # Если в строке есть короткий тикер заглавными буквами
                for v in values:
                    if re.fullmatch(r"[A-ZА-Я]{3,6}", v):
                        ticker = v
                        break

                rows.append({
                    "ticker": ticker,
                    "name": name,
                    "date": date,
                    "price": "—",
                    "now": "—",
                    "change": "—",
                    "up": True,
                    "valuation": "—",
                    "sector": sector,
                    "status": "Календарь MOEX"
                })

        return rows[:10]
    except Exception as e:
        print(f"[WARN] Не удалось загрузить IPO с MOEX: {e}")
        return []

def fetch_recent_ipos_moex():
    """
    Недавние IPO: сначала пробуем взять данные из календаря MOEX,
    если не получилось — используем резервные данные.
    """
    moex_rows = _parse_moex_ipo_calendar_tables()
    if moex_rows:
        recent = []
        for row in moex_rows[:5]:
            recent.append({
                "ticker": row.get("ticker", "—"),
                "name": row.get("name", "—"),
                "date": row.get("date", "—"),
                "price": row.get("price", "—"),
                "now": row.get("now", "—"),
                "change": row.get("change", "—"),
                "up": True
            })
        return recent

    return [
        {"ticker": "GLRX", "name": "GloraX", "date": "31.10.2025", "price": "500.00 ₽", "now": "510.50 ₽", "change": "+2.10%", "up": True},
        {"ticker": "DOMR", "name": "ДОМ.РФ", "date": "20.11.2025", "price": "220.00 ₽", "now": "235.80 ₽", "change": "+7.18%", "up": True},
        {"ticker": "STEP", "name": "Steplife", "date": "15.12.2025", "price": "340.00 ₽", "now": "328.50 ₽", "change": "-3.38%", "up": False},
        {"ticker": "BALT", "name": "Балтийский лизинг", "date": "10.02.2026", "price": "195.00 ₽", "now": "201.20 ₽", "change": "+3.18%", "up": True},
        {"ticker": "KOKS", "name": "Кокс", "date": "05.03.2026", "price": "410.00 ₽", "now": "405.30 ₽", "change": "-1.15%", "up": False},
    ]

def fetch_upcoming_ipos_moex_api():
    """
    Предстоящие IPO: сначала пробуем использовать календарь MOEX,
    если реальных будущих строк нет — показываем резервный pipeline.
    """
    moex_rows = _parse_moex_ipo_calendar_tables()
    if moex_rows:
        upcoming = []
        for row in moex_rows[:5]:
            upcoming.append({
                "ticker": row.get("ticker", "—"),
                "name": row.get("name", "—"),
                "date": row.get("date", "—"),
                "valuation": row.get("valuation", "—"),
                "sector": row.get("sector", "—"),
                "status": row.get("status", "Ожидается")
            })
        return upcoming

    upcoming = [
        {"ticker": "VINL", "name": "Винлаб", "date": "Q2 2026", "valuation": "≈20 млрд ₽", "sector": "Ритейл", "status": "Ожидается"},
        {"ticker": "EVRZ", "name": "Евраз", "date": "2026", "valuation": "—", "sector": "Металлургия", "status": "Ожидается"},
        {"ticker": "SLR", "name": "Солар", "date": "H1 2026", "valuation": "≈35 млрд ₽", "sector": "Технологии", "status": "Подано"},
        {"ticker": "MTST", "name": "МТС AdTech", "date": "2026", "valuation": "—", "sector": "Технологии", "status": "Ожидается"},
        {"ticker": "URNT", "name": "Юрент", "date": "Q3 2026", "valuation": "≈15 млрд ₽", "sector": "Технологии", "status": "Ожидается"},
    ]
    return upcoming[:5]

# ─── Главный класс DashboardScreen ──────────────────────────────────────────
class DashboardScreen(tk.Toplevel):
    def __init__(self, parent, username="Пользователь"):
        super().__init__(parent)
        self.username = username or "Пользователь"
        self.title("StockAI Pro")
        self.configure(bg=BG)

        # Параметры плавной прокрутки главной страницы
        self.home_canvas = None
        self._home_scroll_job = None
        self._home_scroll_target = 0.0

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = max(480, min(600, int(sw * 0.44)))
        h = int(sh * 0.93)
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(440, 520)
        self.resizable(True, True)

        cached = DataCache.load()
        if cached:
            self.real_indices = cached.get("indices", [])
            self.real_gainers = cached.get("gainers", [])
            self.real_losers = cached.get("losers", [])
            self.real_news = cached.get("news", [])
            self.recent_ipos = cached.get("recent_ipos", [])
            self.upcoming_ipos = cached.get("upcoming_ipos", [])
        else:
            self.real_indices = DEMO_INDICES
            self.real_gainers = DEMO_GAINERS
            self.real_losers = DEMO_LOSERS
            self.real_news = DEMO_NEWS
            self.recent_ipos = DEMO_RECENT_IPO.copy()
            self.upcoming_ipos = DEMO_UPCOMING_IPO.copy()

        self.current_page = None
        self._build_layout()
        self._start_background_refresh()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self.master.quit()

    def _build_layout(self):
        self._build_bottom_nav()
        self._build_hero()
        self.page_container = tk.Frame(self, bg=BG)
        self.page_container.pack(fill="both", expand=True)
        self.pages = {}
        self.pages['home'] = self._create_home_page()
        self.pages['search'] = self._create_search_page()
        self.pages['ai'] = self._create_ai_page()
        self.pages['portfolio'] = self._create_portfolio_page()
        self.pages['profile'] = self._create_profile_page()
        self.current_page = 'home'
        self.pages['home'].pack(fill="both", expand=True)

    # ---------- ГЛАВНАЯ СТРАНИЦА ----------
    def _create_home_page(self):
        home_frame = tk.Frame(self.page_container, bg=BG)

        canvas = tk.Canvas(
            home_frame,
            bg=BG,
            highlightthickness=0,
            bd=0,
            yscrollincrement=1
        )

        scrollbar = tk.Scrollbar(
            home_frame,
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

        self.home_canvas = canvas

        self.content = tk.Frame(canvas, bg=BG)
        self.home_canvas_window = canvas.create_window(
            (0, 0),
            window=self.content,
            anchor="nw"
        )

        def on_content_configure(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            self._bind_home_scroll_recursive(self.content)

        self.content.bind("<Configure>", on_content_configure)

        def on_canvas_configure(event):
            canvas.itemconfig(self.home_canvas_window, width=event.width)
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", on_canvas_configure)

        # Скролл работает не только по полосе, но и колесом мыши/тачпадом.
        # bind_all включается, когда курсор находится над главной страницей.
        def activate_home_scroll(event=None):
            self.bind_all("<MouseWheel>", self._on_home_mousewheel)
            self.bind_all("<Button-4>", self._on_home_mousewheel)
            self.bind_all("<Button-5>", self._on_home_mousewheel)

        def deactivate_home_scroll(event=None):
            self.unbind_all("<MouseWheel>")
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")

        home_frame.bind("<Enter>", activate_home_scroll)
        home_frame.bind("<Leave>", deactivate_home_scroll)
        canvas.bind("<Enter>", activate_home_scroll)
        self.content.bind("<Enter>", activate_home_scroll)

        self._build_indices_strip()
        self._divider()
        self._build_movers_section()
        self._divider()
        self._build_news_section()
        self._divider()
        self._build_recent_ipo()
        self._divider()
        self._build_upcoming_ipo()
        tk.Frame(self.content, bg=BG, height=20).pack()

        self._bind_home_scroll_recursive(self.content)

        return home_frame

    def _bind_home_scroll_recursive(self, widget):
        """
        Привязывает колесо мыши ко всем виджетам внутри главной страницы.
        Это нужно, чтобы прокрутка работала даже при наведении на карточки,
        тексты, таблицы, новости и другие вложенные элементы.
        """
        try:
            widget.bind("<MouseWheel>", self._on_home_mousewheel)
            widget.bind("<Button-4>", self._on_home_mousewheel)
            widget.bind("<Button-5>", self._on_home_mousewheel)
        except Exception:
            pass

        for child in widget.winfo_children():
            self._bind_home_scroll_recursive(child)

    def _on_home_mousewheel(self, event):
        """
        Плавная прокрутка главной страницы колесом мыши и тачпадом.
        Работает только когда активна вкладка 'home'.
        """
        if self.current_page != "home":
            return

        canvas = getattr(self, "home_canvas", None)
        if canvas is None or not canvas.winfo_exists():
            return

        bbox = canvas.bbox("all")
        if not bbox:
            return "break"

        content_height = bbox[3] - bbox[1]
        visible_height = canvas.winfo_height()

        if content_height <= visible_height:
            return "break"

        # Windows/macOS: event.delta. Linux: Button-4/Button-5.
        if hasattr(event, "delta") and event.delta:
            direction = -1 if event.delta > 0 else 1
            step = abs(event.delta) / 120
            scroll_pixels = direction * max(45, int(70 * step))
        elif getattr(event, "num", None) == 4:
            scroll_pixels = -70
        elif getattr(event, "num", None) == 5:
            scroll_pixels = 70
        else:
            scroll_pixels = 0

        current_top = canvas.canvasy(0)
        max_top = max(0, content_height - visible_height)

        target_top = current_top + scroll_pixels
        target_top = max(0, min(target_top, max_top))

        max_fraction = max(0.0, 1.0 - visible_height / content_height)
        target_fraction = target_top / content_height if content_height else 0
        target_fraction = max(0.0, min(target_fraction, max_fraction))

        self._home_scroll_target = target_fraction
        self._animate_home_scroll()

        return "break"

    def _animate_home_scroll(self):
        """
        Мягкая анимация до целевой позиции прокрутки.
        """
        canvas = getattr(self, "home_canvas", None)
        if canvas is None or not canvas.winfo_exists():
            self._home_scroll_job = None
            return

        current = canvas.yview()[0]
        target = self._home_scroll_target
        diff = target - current

        if abs(diff) < 0.001:
            canvas.yview_moveto(target)
            self._home_scroll_job = None
            return

        canvas.yview_moveto(current + diff * 0.35)
        self._home_scroll_job = self.after(10, self._animate_home_scroll)

    def _create_search_page(self):
        from screens.search import SearchPage
        return SearchPage(self.page_container, self)

    def _create_ai_page(self):
        from screens.ai_assistant import AIAssistantPage
        return AIAssistantPage(self.page_container, self)

    def _create_portfolio_page(self):
        from screens.portfolio import PortfolioPage
        pf = PortfolioPage(self.page_container, self)
        pf.refresh()
        return pf

    def _create_profile_page(self):
        from screens.profile import ProfilePage
        return ProfilePage(self.page_container, self)

    def _divider(self):
        tk.Frame(self.content, bg=BORDER, height=1).pack(fill="x", padx=18, pady=6)

    def _section_header(self, parent, eyebrow, title, right_text="", right_cmd=None):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="x", padx=18, pady=(12,6))
        lf = tk.Frame(f, bg=BG)
        lf.pack(side="left")
        tk.Label(lf, text=eyebrow, font=("Helvetica", 8, "bold"),
                 bg=BG, fg=TEXT_MUTED).pack(anchor="w")
        tk.Label(lf, text=title, font=("Helvetica", 14, "bold"),
                 bg=BG, fg=TEXT_PRI).pack(anchor="w")
        if right_text:
            lbl = tk.Label(f, text=right_text, font=("Helvetica", 9),
                           bg=BG, fg=ACCENT, cursor="hand2")
            lbl.pack(side="right", pady=(10,0))
            if right_cmd:
                lbl.bind("<Button-1>", lambda e: right_cmd())

    def _build_hero(self):
        frame = tk.Frame(self, bg=BG)
        frame.pack(fill="x")
        self.hero_canvas = tk.Canvas(frame, bg=BG, highlightthickness=0, height=200)
        self.hero_canvas.pack(fill="x")
        self.hero_canvas.bind("<Configure>", self._draw_hero)
        self.after(50, self._draw_hero)

    def _draw_hero(self, event=None):
        w = self.hero_canvas.winfo_width() or 560
        self.hero_canvas.delete("all")
        for i in range(200):
            t = i / 200
            r = int(0x0D + (0x1C-0x0D)*t)
            g = int(0x11 + (0x2B-0x11)*t)
            b = int(0x17 + (0x4A-0x17)*t)
            self.hero_canvas.create_line(0, i, w, i, fill=f"#{r:02x}{g:02x}{b:02x}")
        self.hero_canvas.create_oval(w//2-120, -40, w//2+120, 80, fill="#132240", outline="")
        self.hero_canvas.create_oval(-40, 60, 120, 200, fill="#0F1E35", outline="")
        for xi in range(0, w+40, 40):
            self.hero_canvas.create_line(xi, 0, xi, 200, fill="#1A2340", width=1)
        for yi in range(0, 201, 40):
            self.hero_canvas.create_line(0, yi, w, yi, fill="#1A2340", width=1)
        hour = datetime.datetime.now().hour
        greet = "Доброе утро" if hour < 12 else ("Добрый день" if hour < 18 else "Добрый вечер")
        self.hero_canvas.create_text(18, 52, anchor="w", text=f"{greet}, {self.username}!",
                                     font=("Helvetica", 18, "bold"), fill=WHITE)
        self.hero_canvas.create_text(18, 78, anchor="w", text="Рынок открыт  •  AI-аналитика обновлена",
                                     font=("Helvetica", 10), fill=TEXT_SEC)
        total = self._calculate_portfolio_invested_value()
        port_str = f"{total:,.2f} ₽".replace(",", " ") if total > 0 else "Портфель пуст"

        self.hero_canvas.create_text(18, 118, anchor="w", text="Стоимость портфеля",
                                     font=("Helvetica", 9), fill=TEXT_SEC)
        self.hero_canvas.create_text(18, 148, anchor="w", text=port_str,
                                     font=("Helvetica", 26, "bold"), fill=WHITE)

    def _to_float_safe(self, value, default=0.0):
        """
        Безопасно переводит значение в float.
        Нужно, потому что buy_price иногда может сохраниться строкой,
        например '318.94', '318,94' или '318.94 ₽'.
        """
        try:
            if value is None:
                return default
            if isinstance(value, str):
                value = (
                    value.replace("₽", "")
                         .replace(" ", "")
                         .replace(",", ".")
                         .strip()
                )
            return float(value)
        except Exception:
            return default

    def _to_int_safe(self, value, default=0):
        """
        Безопасно переводит количество акций в int.
        """
        try:
            if value is None:
                return default
            if isinstance(value, str):
                value = value.replace(" ", "").strip()
            return int(float(value))
        except Exception:
            return default

    def _calculate_portfolio_invested_value(self):
        """
        Считает сумму портфеля так же, как ты описала:
        сумма по всем позициям = количество акций * цена покупки.
        """
        total = 0.0

        if not isinstance(app_state.portfolio, list):
            return total

        for item in app_state.portfolio:
            if not isinstance(item, dict):
                continue

            quantity = self._to_int_safe(item.get("quantity", 0))
            buy_price = self._to_float_safe(item.get("buy_price", 0))
            total += quantity * buy_price

        return total

    def refresh_hero(self):
        """
        Обновляет верхний блок с суммой портфеля.
        Вызывается после изменений в портфеле и при переходе на главную.
        """
        try:
            if hasattr(self, "hero_canvas") and self.hero_canvas.winfo_exists():
                self._draw_hero()
        except Exception:
            pass

    # ---------- Индексы ----------
    def _build_indices_strip(self):
        outer = tk.Frame(self.content, bg=BG)
        outer.pack(fill="x", padx=18, pady=(12,4))
        tk.Label(outer, text="РЫНОК СЕГОДНЯ", font=("Helvetica", 8, "bold"),
                 bg=BG, fg=TEXT_MUTED).pack(anchor="w", pady=(0,6))
        self.indices_frame = tk.Frame(outer, bg=BG)
        self.indices_frame.pack(fill="x")
        self._refresh_indices_ui()

    def _refresh_indices_ui(self):
        if not hasattr(self, 'indices_frame') or not self.indices_frame.winfo_exists():
            return
        for widget in self.indices_frame.winfo_children():
            widget.destroy()
        if not self.real_indices:
            tk.Label(self.indices_frame, text="Загрузка данных...", bg=BG, fg=TEXT_SEC).pack(pady=10)
            return
        row = tk.Frame(self.indices_frame, bg=BG)
        row.pack(fill="x")
        for idx in self.real_indices:
            color = GREEN if idx["up"] else RED
            c = tk.Frame(row, bg=SURFACE, padx=10, pady=8)
            c.pack(side="left", padx=(0,6), fill="x", expand=True)
            c.configure(highlightbackground=BORDER, highlightthickness=1)
            tk.Label(c, text=idx["name"], font=("Helvetica", 7, "bold"),
                     bg=SURFACE, fg=TEXT_MUTED).pack(anchor="w")
            tk.Label(c, text=idx["value"], font=("Helvetica", 9, "bold"),
                     bg=SURFACE, fg=TEXT_PRI).pack(anchor="w", pady=(1,0))
            arr = "▲ " if idx["up"] else "▼ "
            tk.Label(c, text=arr+idx["change"], font=("Helvetica", 8, "bold"),
                     bg=SURFACE, fg=color).pack(anchor="w")
            sp = tk.Canvas(c, bg=SURFACE, width=66, height=22,
                           highlightthickness=0, bd=0)
            sp.pack(pady=(3,0))
            Sparkline(sp, 0, 2, 66, 18, idx["data"], color)

    # ---------- Лидеры / аутсайдеры ----------
    def _build_movers_section(self):
        self._section_header(self.content, "ДВИЖЕНИЕ РЫНКА", "Лидеры и аутсайдеры")
        nb = tk.Frame(self.content, bg=BG)
        nb.pack(fill="x", padx=18, pady=(0,4))
        self._tab_var = tk.StringVar(value="gainers")
        def tab_btn(parent, text, key):
            active = (key == "gainers")
            btn = tk.Button(parent, text=text,
                            font=("Helvetica", 9, "bold"),
                            bg=ACCENT if active else SURFACE,
                            fg=WHITE if active else TEXT_SEC,
                            activebackground=ACCENT2,
                            bd=0, padx=14, pady=5, cursor="hand2", relief="flat",
                            command=lambda k=key: self._switch_movers(k))
            btn.pack(side="left", padx=(0,4))
            return btn
        self._btn_gain = tab_btn(nb, "▲  Лидеры роста", "gainers")
        self._btn_lose = tab_btn(nb, "▼  Лидеры падения", "losers")
        self._movers_frame = tk.Frame(self.content, bg=BG)
        self._movers_frame.pack(fill="x", padx=18)
        self._render_movers("gainers")

    def _switch_movers(self, key):
        self._tab_var.set(key)
        self._btn_gain.config(bg=ACCENT if key=="gainers" else SURFACE,
                              fg=WHITE if key=="gainers" else TEXT_SEC)
        self._btn_lose.config(bg=ACCENT if key=="losers" else SURFACE,
                              fg=WHITE if key=="losers" else TEXT_SEC)
        self._render_movers(key)

    def _render_movers(self, key):
        if not hasattr(self, '_movers_frame') or not self._movers_frame.winfo_exists():
            return
        for w in self._movers_frame.winfo_children():
            w.destroy()
        stocks = self.real_gainers if key == "gainers" else self.real_losers
        if not stocks:
            tk.Label(self._movers_frame, text="Нет данных", bg=BG, fg=TEXT_SEC).pack(pady=10)
            return
        color = GREEN if key == "gainers" else RED
        bg_dim = GREEN_DIM if key == "gainers" else RED_DIM
        for s in stocks:
            card = tk.Frame(self._movers_frame, bg=SURFACE)
            card.pack(fill="x", pady=3)
            card.configure(highlightbackground=BORDER, highlightthickness=1)
            inn = tk.Frame(card, bg=SURFACE, padx=12, pady=9)
            inn.pack(fill="x")
            av = tk.Label(inn, text=s["ticker"][:2],
                          font=("Helvetica", 9, "bold"),
                          bg=ACCENT, fg=WHITE, width=3, pady=3)
            av.pack(side="left")
            inf = tk.Frame(inn, bg=SURFACE)
            inf.pack(side="left", padx=10, fill="x", expand=True)
            tk.Label(inf, text=s["ticker"], font=("Helvetica", 11, "bold"),
                     bg=SURFACE, fg=TEXT_PRI).pack(anchor="w")
            tk.Label(inf, text=s["name"], font=("Helvetica", 8),
                     bg=SURFACE, fg=TEXT_SEC).pack(anchor="w")
            sp = tk.Canvas(inn, bg=SURFACE, width=62, height=28,
                           highlightthickness=0, bd=0)
            sp.pack(side="right", padx=(8,0))
            Sparkline(sp, 0, 2, 62, 24, s["data"], color, filled=True)
            ri = tk.Frame(inn, bg=SURFACE)
            ri.pack(side="right")
            tk.Label(ri, text=s["price"], font=("Helvetica", 11, "bold"),
                     bg=SURFACE, fg=TEXT_PRI).pack(anchor="e")
            badge = tk.Frame(ri, bg=bg_dim, padx=5, pady=1)
            badge.pack(anchor="e", pady=(2,0))
            arr = "▲ " if key == "gainers" else "▼ "
            tk.Label(badge, text=arr+s["change"], font=("Helvetica", 8, "bold"),
                     bg=bg_dim, fg=color).pack()

    # ---------- Новости ----------
    def _build_news_section(self):
        self._section_header(self.content, "НОВОСТИ РЫНКА", "Актуальные события", "Все →")
        self.news_container = tk.Frame(self.content, bg=BG)
        self.news_container.pack(fill="x", padx=18)
        self._refresh_news_ui()

    def _create_news_card(self, parent, art):
        card = tk.Frame(parent, bg=SURFACE, cursor="hand2")
        card.pack(fill="x", pady=3)
        card.configure(highlightbackground=BORDER, highlightthickness=1)
        inn = tk.Frame(card, bg=SURFACE, padx=12, pady=10)
        inn.pack(fill="x")
        img_frame = tk.Frame(inn, bg=SURFACE2, width=72, height=54)
        img_frame.pack(side="left", padx=(0,10))
        img_frame.pack_propagate(False)
        def set_image():
            if not img_frame.winfo_exists():
                return
            try:
                if PIL_OK and art.get("img_url", "").startswith("http"):
                    resp = requests.get(art["img_url"], timeout=3)
                    img = Image.open(io.BytesIO(resp.content))
                    img = img.resize((72,54), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    img_frame.photo = photo
                    tk.Label(img_frame, image=photo, bg=SURFACE2).pack()
                else:
                    raise Exception("no image")
            except:
                cv = tk.Canvas(img_frame, bg=SURFACE2, width=72, height=54, highlightthickness=0)
                cv.pack()
                cv.create_rectangle(0,0,72,54, fill=SURFACE3, outline="")
                cv.create_text(36,27, text=art.get("tag","N")[0], font=("Helvetica",18,"bold"), fill=ACCENT)
        self.after(10, set_image)
        tf = tk.Frame(inn, bg=SURFACE)
        tf.pack(side="left", fill="x", expand=True)
        tag_color = art.get("tag_color", ACCENT)
        tag_f = tk.Frame(tf, bg=tag_color)
        tag_f.pack(anchor="w", pady=(0,4))
        r,g,b = hex_to_rgb(tag_color)
        dark = "#{:02x}{:02x}{:02x}".format(r//3, g//3, b//3)
        tk.Label(tag_f, text=art.get("tag","Новость"), font=("Helvetica",7,"bold"),
                 bg=dark, fg=tag_color, padx=5, pady=2).pack()
        tk.Label(tf, text=art.get("title",""),
                 font=("Helvetica",10,"bold"),
                 bg=SURFACE, fg=TEXT_PRI,
                 wraplength=280, justify="left").pack(anchor="w")
        if art.get("description"):
            tk.Label(tf, text=art["description"],
                     font=("Helvetica",8),
                     bg=SURFACE, fg=TEXT_SEC,
                     wraplength=280, justify="left").pack(anchor="w", pady=(2,0))
        meta = tk.Frame(tf, bg=SURFACE)
        meta.pack(anchor="w", pady=(4,0))
        tk.Label(meta, text=art.get("source",""), font=("Helvetica",8,"bold"),
                 bg=SURFACE, fg=ACCENT).pack(side="left")
        tk.Label(meta, text="  •  "+art.get("time",""), font=("Helvetica",8),
                 bg=SURFACE, fg=TEXT_MUTED).pack(side="left")
        def _on_enter(e): card.configure(highlightbackground=ACCENT)
        def _on_leave(e): card.configure(highlightbackground=BORDER)
        card.bind("<Enter>", _on_enter)
        card.bind("<Leave>", _on_leave)
        def open_link(e):
            url = art.get("link", "")
            if url and url != "#":
                try:
                    webbrowser.open(url)
                except:
                    try:
                        subprocess.Popen(['cmd', '/c', 'start', url], shell=True)
                    except:
                        pass
        card.bind("<Button-1>", open_link)
        for child in (card, inn, tf, meta):
            child.bind("<Button-1>", open_link)

    def _refresh_news_ui(self):
        if not hasattr(self, 'news_container') or not self.news_container.winfo_exists():
            return
        for widget in self.news_container.winfo_children():
            widget.destroy()
        if not self.real_news:
            tk.Label(self.news_container, text="Нет новостей", bg=BG, fg=TEXT_SEC).pack(pady=10)
            return
        for art in self.real_news:
            self._create_news_card(self.news_container, art)

    # ---------- IPO блоки ----------
    def _build_recent_ipo(self):
        self._section_header(self.content, "IPO", "Недавние размещения", "Все →")
        self.recent_ipos_frame = tk.Frame(self.content, bg=BG)
        self.recent_ipos_frame.pack(fill="x", padx=18)
        self._build_recent_ipo_table()

    def _build_recent_ipo_table(self):
        if not hasattr(self, 'recent_ipos_frame') or not self.recent_ipos_frame.winfo_exists():
            return

        for widget in self.recent_ipos_frame.winfo_children():
            widget.destroy()

        if not self.recent_ipos:
            tk.Label(self.recent_ipos_frame, text="Нет данных", bg=BG, fg=TEXT_SEC).pack(pady=10)
            return

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "IPO.Treeview",
            background=SURFACE,
            foreground=TEXT_SEC,
            fieldbackground=SURFACE,
            borderwidth=0,
            font=("Helvetica", 9),
            rowheight=34
        )
        style.configure(
            "IPO.Treeview.Heading",
            background=ACCENT,
            foreground=WHITE,
            font=("Helvetica", 8, "bold"),
            borderwidth=0,
            relief="flat",
            padding=(6, 7)
        )
        style.map(
            "IPO.Treeview.Heading",
            background=[("active", ACCENT), ("pressed", ACCENT)],
            foreground=[("active", WHITE), ("pressed", WHITE)]
        )

        columns = ("ticker", "company", "date", "price", "now", "change")
        tree = ttk.Treeview(
            self.recent_ipos_frame,
            columns=columns,
            show="headings",
            height=5,
            style="IPO.Treeview"
        )

        headers = {
            "ticker": "Тикер",
            "company": "Компания",
            "date": "Дата",
            "price": "Цена IPO",
            "now": "Сейчас",
            "change": "Доход"
        }

        for col, title in headers.items():
            tree.heading(col, text=title, anchor="center")

        tree.column("ticker", width=70, anchor="center", stretch=False)
        tree.column("company", width=145, anchor="center", stretch=True)
        tree.column("date", width=95, anchor="center", stretch=False)
        tree.column("price", width=90, anchor="center", stretch=False)
        tree.column("now", width=90, anchor="center", stretch=False)
        tree.column("change", width=80, anchor="center", stretch=False)

        for ipo in self.recent_ipos[:5]:
            tree.insert(
                "",
                "end",
                values=(
                    ipo.get("ticker", "—"),
                    ipo.get("name", "—"),
                    ipo.get("date", "—"),
                    ipo.get("price", "—"),
                    ipo.get("now", "—"),
                    ipo.get("change", "—")
                )
            )

        tree.pack(fill="x", pady=(0, 10))

    def _build_upcoming_ipo(self):
        self._section_header(self.content, "IPO", "Предстоящие размещения", "Подписаться →")
        self.upcoming_ipos_frame = tk.Frame(self.content, bg=BG)
        self.upcoming_ipos_frame.pack(fill="x", padx=18)
        self._build_upcoming_ipo_list()

    def _build_upcoming_ipo_list(self):
        if not hasattr(self, 'upcoming_ipos_frame') or not self.upcoming_ipos_frame.winfo_exists():
            return
        for widget in self.upcoming_ipos_frame.winfo_children():
            widget.destroy()
        if not self.upcoming_ipos:
            tk.Label(self.upcoming_ipos_frame, text="Нет данных", bg=BG, fg=TEXT_SEC).pack(pady=10)
            return
        STATUS_COLOR = {"Подано": ACCENT, "Ожидается": AMBER, "Слухи": TEXT_SEC}
        for ipo in self.upcoming_ipos[:5]:
            sc = STATUS_COLOR.get(ipo.get("status","Ожидается"), TEXT_MUTED)
            card = tk.Frame(self.upcoming_ipos_frame, bg=SURFACE)
            card.pack(fill="x", pady=3)
            card.configure(highlightbackground=BORDER, highlightthickness=1)
            inn = tk.Frame(card, bg=SURFACE, padx=12, pady=10)
            inn.pack(fill="x")
            av = tk.Canvas(inn, bg=SURFACE, width=36, height=36, highlightthickness=0)
            av.pack(side="left")
            av.create_oval(1,1,35,35, fill=SURFACE3, outline=ACCENT, width=1)
            av.create_text(18,18, text=ipo["ticker"][:2], font=("Helvetica",9,"bold"), fill=ACCENT)
            tf = tk.Frame(inn, bg=SURFACE)
            tf.pack(side="left", padx=10, fill="x", expand=True)
            tk.Label(tf, text=ipo["name"], font=("Helvetica",10,"bold"),
                     bg=SURFACE, fg=TEXT_PRI).pack(anchor="w")
            tk.Label(tf, text=ipo.get("sector","—"), font=("Helvetica",8),
                     bg=SURFACE, fg=TEXT_SEC).pack(anchor="w")
            rf = tk.Frame(inn, bg=SURFACE)
            rf.pack(side="right")
            tk.Label(rf, text=ipo["date"], font=("Helvetica",8,"bold"),
                     bg=SURFACE, fg=TEXT_PRI).pack(anchor="e")
            tk.Label(rf, text=ipo.get("valuation","—"), font=("Helvetica",8),
                     bg=SURFACE, fg=TEXT_SEC).pack(anchor="e")
            r,g,b = hex_to_rgb(sc)
            sbg = "#{:02x}{:02x}{:02x}".format(r//5, g//5, b//5)
            sbadge = tk.Frame(rf, bg=sbg, padx=5, pady=2)
            sbadge.pack(anchor="e", pady=(3,0))
            tk.Label(sbadge, text=ipo.get("status","Ожидается"), font=("Helvetica",7,"bold"),
                     bg=sbg, fg=sc).pack()

    # ---------- Нижняя навигация ----------
    def _build_bottom_nav(self):
        nav = tk.Frame(self, bg=SURFACE, height=62)
        nav.pack(side="bottom", fill="x")
        nav.pack_propagate(False)
        nav.configure(highlightbackground=BORDER, highlightthickness=1)
        tabs = [("🏠","Главная"),("🔍","Поиск"),("🤖","AI"),
                ("💼","Портфель"),("👤","Профиль")]
        self.nav_items = []
        for i, (icon, label) in enumerate(tabs):
            f = tk.Frame(nav, bg=SURFACE, cursor="hand2")
            f.pack(side="left", expand=True, fill="y")
            icon_lbl = tk.Label(f, text=icon, font=("Helvetica", 18),
                                bg=SURFACE, fg=TEXT_SEC)
            icon_lbl.pack(pady=(7,0))
            text_lbl = tk.Label(f, text=label, font=("Helvetica", 7, "normal"),
                                bg=SURFACE, fg=TEXT_SEC)
            text_lbl.pack()
            indicator = tk.Frame(f, bg=SURFACE, height=2, width=28)
            indicator.pack(pady=(1,0))
            self.nav_items.append({
                "frame": f,
                "icon": icon_lbl,
                "text": text_lbl,
                "indicator": indicator,
                "page": label
            })
            if label == "Главная":
                f.bind("<Button-1>", lambda e: self._switch_page('home'))
                for child in f.winfo_children():
                    child.bind("<Button-1>", lambda e: self._switch_page('home'))
            elif label == "Поиск":
                f.bind("<Button-1>", lambda e: self._switch_page('search'))
                for child in f.winfo_children():
                    child.bind("<Button-1>", lambda e: self._switch_page('search'))
            elif label == "AI":
                f.bind("<Button-1>", lambda e: self._switch_page('ai'))
                for child in f.winfo_children():
                    child.bind("<Button-1>", lambda e: self._switch_page('ai'))
            elif label == "Портфель":
                f.bind("<Button-1>", lambda e: self._switch_page('portfolio'))
                for child in f.winfo_children():
                    child.bind("<Button-1>", lambda e: self._switch_page('portfolio'))
            elif label == "Профиль":
                f.bind("<Button-1>", lambda e: self._switch_page('profile'))
                for child in f.winfo_children():
                    child.bind("<Button-1>", lambda e: self._switch_page('profile'))
        self._update_nav_active('home')

    def _update_nav_active(self, page_name):
        for item in self.nav_items:
            if (page_name == 'home' and item['page'] == 'Главная') or \
               (page_name == 'search' and item['page'] == 'Поиск') or \
               (page_name == 'ai' and item['page'] == 'AI') or \
               (page_name == 'portfolio' and item['page'] == 'Портфель') or \
               (page_name == 'profile' and item['page'] == 'Профиль'):
                item['icon'].config(fg=ACCENT)
                item['text'].config(fg=ACCENT, font=("Helvetica", 7, "bold"))
                item['indicator'].config(bg=ACCENT)
            else:
                item['icon'].config(fg=TEXT_SEC)
                item['text'].config(fg=TEXT_SEC, font=("Helvetica", 7, "normal"))
                item['indicator'].config(bg=SURFACE)

    def _switch_page(self, page_name):
        if page_name == self.current_page:
            return
        self.pages[self.current_page].pack_forget()
        self.pages[page_name].pack(fill="both", expand=True)
        self.current_page = page_name
        self._update_nav_active(page_name)
        if page_name == 'profile':
            if hasattr(self.pages['profile'], 'refresh_all'):
                self.pages['profile'].refresh_all()
        elif page_name == 'portfolio':
            if hasattr(self.pages['portfolio'], 'refresh'):
                self.pages['portfolio'].refresh()
        elif page_name == 'home':
            self.refresh_hero()

    # ---------- Фоновое обновление ----------
    def _start_background_refresh(self):
        def safe_after(func):
            try:
                if self.winfo_exists():
                    self.after(0, func)
            except:
                pass
        def update_indices():
            indices = fetch_indices_moex()
            if indices:
                self.real_indices = indices
                self._save_cache()
                safe_after(self._refresh_indices_ui)
        def update_movers():
            gainers, losers = fetch_movers_moex()
            if gainers and losers:
                self.real_gainers = gainers
                self.real_losers = losers
                self._save_cache()
                safe_after(lambda: self._render_movers(self._tab_var.get()))
        def update_news():
            news = fetch_news_rss()
            if news:
                self.real_news = news
                self._save_cache()
                safe_after(self._refresh_news_ui)
        def update_ipos():
            recent = fetch_recent_ipos_moex()
            upcoming = fetch_upcoming_ipos_moex_api()
            if recent:
                self.recent_ipos = recent
            if upcoming:
                self.upcoming_ipos = upcoming
            if recent or upcoming:
                self._save_cache()
                safe_after(self._refresh_ipo_ui)
        threading.Thread(target=update_indices, daemon=True).start()
        threading.Thread(target=update_movers, daemon=True).start()
        threading.Thread(target=update_news, daemon=True).start()
        threading.Thread(target=update_ipos, daemon=True).start()

    def _refresh_ipo_ui(self):
        self._build_recent_ipo_table()
        self._build_upcoming_ipo_list()

    def _save_cache(self):
        cache_data = {
            "indices": self.real_indices,
            "gainers": self.real_gainers,
            "losers": self.real_losers,
            "news": self.real_news,
            "recent_ipos": self.recent_ipos,
            "upcoming_ipos": self.upcoming_ipos,
        }
        DataCache.save(cache_data)

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    app = DashboardScreen(root, username="Алексей")
    app.mainloop()

