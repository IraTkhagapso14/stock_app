import os
import threading
from contextlib import contextmanager
from decimal import Decimal

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except ImportError:  # pragma: no cover - handled at runtime for the desktop app
    psycopg2 = None
    Json = None
    RealDictCursor = None


DEFAULT_PROFILE = {
    "display_name": "",
    "email": "",
    "avatar_letter": "",
    "favorites": [],
    "recently_viewed": [],
    "notifications": {
        "price_alerts": True,
        "news_digest": False,
        "ipo_reminders": True,
        "email_notifications": False,
    },
    "theme": "dark",
    "language": "ru",
    "auth_token": "",
    "gigachat_auth_key": "",
}


class DatabaseUnavailable(RuntimeError):
    pass


class Database:
    _schema_ready = False
    _lock = threading.Lock()

    @staticmethod
    def _connect_kwargs():
        dsn = os.getenv("POSTGRES_DSN") or os.getenv("DATABASE_URL")
        if dsn:
            return {"dsn": dsn, "connect_timeout": 5}
        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "5432")),
            "dbname": os.getenv("DB_NAME", "stockai_pro"),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "connect_timeout": 5,
        }

    @classmethod
    def connect(cls):
        if psycopg2 is None:
            raise DatabaseUnavailable(
                "Не установлен драйвер PostgreSQL. Выполните: pip install psycopg2-binary"
            )
        try:
            kwargs = cls._connect_kwargs()
            if "dsn" in kwargs:
                conn = psycopg2.connect(kwargs.pop("dsn"), **kwargs)
            else:
                conn = psycopg2.connect(**kwargs)
            conn.autocommit = True
            cls.ensure_schema(conn)
            return conn
        except Exception as e:
            raise DatabaseUnavailable(f"PostgreSQL недоступен: {e}") from e

    @classmethod
    def ensure_schema(cls, conn=None):
        if cls._schema_ready:
            return
        with cls._lock:
            if cls._schema_ready:
                return
            owns_connection = conn is None
            if owns_connection:
                conn = cls.connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS users (
                            email TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            password_hash TEXT NOT NULL,
                            salt TEXT NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );

                        CREATE TABLE IF NOT EXISTS user_profiles (
                            email TEXT PRIMARY KEY REFERENCES users(email) ON DELETE CASCADE,
                            display_name TEXT NOT NULL DEFAULT '',
                            avatar_letter TEXT NOT NULL DEFAULT '',
                            favorites TEXT[] NOT NULL DEFAULT '{}',
                            recently_viewed TEXT[] NOT NULL DEFAULT '{}',
                            notifications JSONB NOT NULL DEFAULT '{}'::jsonb,
                            theme TEXT NOT NULL DEFAULT 'dark',
                            language TEXT NOT NULL DEFAULT 'ru',
                            auth_token TEXT NOT NULL DEFAULT '',
                            gigachat_auth_key TEXT NOT NULL DEFAULT '',
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );

                        CREATE TABLE IF NOT EXISTS portfolio_positions (
                            id BIGSERIAL PRIMARY KEY,
                            user_email TEXT NOT NULL REFERENCES users(email) ON DELETE CASCADE,
                            secid TEXT NOT NULL,
                            quantity INTEGER NOT NULL DEFAULT 0,
                            buy_price NUMERIC(18, 6) NOT NULL DEFAULT 0,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (user_email, secid)
                        );

                        CREATE TABLE IF NOT EXISTS stocks (
                            ticker TEXT PRIMARY KEY,
                            name TEXT NOT NULL DEFAULT '',
                            fullname TEXT NOT NULL DEFAULT '',
                            sector TEXT NOT NULL DEFAULT '',
                            industry TEXT NOT NULL DEFAULT '',
                            data JSONB NOT NULL DEFAULT '{}'::jsonb,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );

                        CREATE TABLE IF NOT EXISTS app_cache (
                            cache_key TEXT PRIMARY KEY,
                            data JSONB NOT NULL,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );

                        CREATE TABLE IF NOT EXISTS forecast_runs (
                            id BIGSERIAL PRIMARY KEY,
                            user_email TEXT,
                            forecast_type TEXT NOT NULL,
                            source TEXT NOT NULL DEFAULT 'ai_portfolio_forecast',
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );

                        CREATE TABLE IF NOT EXISTS forecast_results (
                            id BIGSERIAL PRIMARY KEY,
                            run_id BIGINT NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
                            ticker TEXT NOT NULL,
                            result JSONB NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );
                        """
                    )
                cls._schema_ready = True
            finally:
                if owns_connection and conn is not None:
                    conn.close()

    @classmethod
    @contextmanager
    def cursor(cls):
        conn = cls.connect()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
        finally:
            conn.close()


def _profile_from_row(row):
    profile = DEFAULT_PROFILE.copy()
    if not row:
        return profile
    profile.update(
        {
            "display_name": row.get("display_name") or "",
            "email": row.get("email") or "",
            "avatar_letter": row.get("avatar_letter") or "",
            "favorites": list(row.get("favorites") or []),
            "recently_viewed": list(row.get("recently_viewed") or []),
            "notifications": row.get("notifications") or DEFAULT_PROFILE["notifications"].copy(),
            "theme": row.get("theme") or "dark",
            "language": row.get("language") or "ru",
            "auth_token": row.get("auth_token") or "",
            "gigachat_auth_key": row.get("gigachat_auth_key") or "",
        }
    )
    return profile


def _to_portfolio_item(row):
    return {
        "secid": row["secid"],
        "quantity": int(row.get("quantity") or 0),
        "buy_price": float(row.get("buy_price") or 0),
    }


class UserRepository:
    @staticmethod
    def create_user(email, name, password_hash, salt):
        with Database.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                return False
            cur.execute(
                """
                INSERT INTO users(email, name, password_hash, salt)
                VALUES (%s, %s, %s, %s)
                """,
                (email, name, password_hash, salt),
            )
            ProfileRepository.ensure_profile(email, name)
            return True

    @staticmethod
    def get_user(email):
        with Database.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            return cur.fetchone()

    @staticmethod
    def list_users():
        with Database.cursor() as cur:
            cur.execute("SELECT email, name, created_at FROM users ORDER BY created_at")
            return cur.fetchall()


class ProfileRepository:
    @staticmethod
    def ensure_guest_user(email):
        with Database.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users(email, name, password_hash, salt)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                """,
                (email, "Guest" if email == "guest" else email, "", ""),
            )

    @staticmethod
    def ensure_profile(email, display_name=""):
        ProfileRepository.ensure_guest_user(email)
        avatar = (display_name or email or "U")[0].upper()
        with Database.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_profiles(
                    email, display_name, avatar_letter, notifications, theme, language
                )
                VALUES (%s, %s, %s, %s, 'dark', 'ru')
                ON CONFLICT (email) DO NOTHING
                """,
                (email, display_name or "", avatar, Json(DEFAULT_PROFILE["notifications"])),
            )

    @staticmethod
    def get_user_data(email):
        ProfileRepository.ensure_profile(email)
        with Database.cursor() as cur:
            cur.execute("SELECT * FROM user_profiles WHERE email = %s", (email,))
            profile = _profile_from_row(cur.fetchone())
            cur.execute(
                """
                SELECT secid, quantity, buy_price
                FROM portfolio_positions
                WHERE user_email = %s AND quantity > 0
                ORDER BY created_at, secid
                """,
                (email,),
            )
            portfolio = [_to_portfolio_item(row) for row in cur.fetchall()]
        return {"profile": profile, "portfolio": portfolio}

    @staticmethod
    def save_user_data(email, profile, portfolio):
        if not isinstance(profile, dict):
            profile = {}
        if not isinstance(portfolio, list):
            portfolio = []

        ProfileRepository.ensure_profile(email, profile.get("display_name") or email)
        favorites = [str(x) for x in profile.get("favorites", []) if x]
        recently_viewed = [str(x) for x in profile.get("recently_viewed", []) if x]
        notifications = profile.get("notifications") or DEFAULT_PROFILE["notifications"].copy()

        with Database.cursor() as cur:
            cur.execute(
                """
                UPDATE user_profiles
                SET display_name = %s,
                    avatar_letter = %s,
                    favorites = %s,
                    recently_viewed = %s,
                    notifications = %s,
                    theme = %s,
                    language = %s,
                    auth_token = %s,
                    gigachat_auth_key = %s,
                    updated_at = NOW()
                WHERE email = %s
                """,
                (
                    profile.get("display_name") or "",
                    profile.get("avatar_letter") or (email[0].upper() if email else "U"),
                    favorites,
                    recently_viewed,
                    Json(notifications),
                    profile.get("theme") or "dark",
                    profile.get("language") or "ru",
                    profile.get("auth_token") or "",
                    profile.get("gigachat_auth_key") or "",
                    email,
                ),
            )
            cur.execute("DELETE FROM portfolio_positions WHERE user_email = %s", (email,))
            for item in portfolio:
                if not isinstance(item, dict):
                    continue
                secid = str(item.get("secid") or item.get("ticker") or "").upper().strip()
                if not secid:
                    continue
                quantity = int(float(item.get("quantity", item.get("qty", 0)) or 0))
                buy_price = Decimal(str(item.get("buy_price", item.get("price", 0)) or 0))
                if quantity <= 0:
                    continue
                cur.execute(
                    """
                    INSERT INTO portfolio_positions(user_email, secid, quantity, buy_price)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_email, secid) DO UPDATE
                    SET quantity = EXCLUDED.quantity,
                        buy_price = EXCLUDED.buy_price,
                        updated_at = NOW()
                    """,
                    (email, secid, quantity, buy_price),
                )


class PortfolioRepository:
    @staticmethod
    def load(email):
        return ProfileRepository.get_user_data(email)["portfolio"]

    @staticmethod
    def save(email, portfolio):
        data = ProfileRepository.get_user_data(email)
        ProfileRepository.save_user_data(email, data["profile"], portfolio)
        return True


class StockRepository:
    @staticmethod
    def upsert_stock(ticker, data):
        if not isinstance(data, dict):
            data = {}
        ticker = str(ticker or data.get("ticker") or "").upper().strip()
        if not ticker:
            return
        payload = dict(data)
        payload["ticker"] = ticker
        with Database.cursor() as cur:
            cur.execute(
                """
                INSERT INTO stocks(ticker, name, fullname, sector, industry, data)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE
                SET name = EXCLUDED.name,
                    fullname = EXCLUDED.fullname,
                    sector = EXCLUDED.sector,
                    industry = EXCLUDED.industry,
                    data = EXCLUDED.data,
                    updated_at = NOW()
                """,
                (
                    ticker,
                    str(payload.get("name") or ""),
                    str(payload.get("fullname") or ""),
                    str(payload.get("sector") or ""),
                    str(payload.get("industry") or ""),
                    Json(payload),
                ),
            )

    @staticmethod
    def seed_stocks(stocks):
        if not isinstance(stocks, dict) or not stocks:
            return
        with Database.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM stocks")
            count = int(cur.fetchone()["count"])
        if count:
            return
        for ticker, data in stocks.items():
            StockRepository.upsert_stock(ticker, data)

    @staticmethod
    def get_all_stocks():
        with Database.cursor() as cur:
            cur.execute("SELECT ticker, data FROM stocks ORDER BY ticker")
            rows = cur.fetchall()
        return {row["ticker"]: row["data"] for row in rows}

    @staticmethod
    def get_stock(ticker):
        with Database.cursor() as cur:
            cur.execute("SELECT data FROM stocks WHERE ticker = %s", (str(ticker).upper(),))
            row = cur.fetchone()
        return row["data"] if row else None


class CacheRepository:
    @staticmethod
    def save(key, data):
        with Database.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_cache(cache_key, data)
                VALUES (%s, %s)
                ON CONFLICT (cache_key) DO UPDATE
                SET data = EXCLUDED.data,
                    updated_at = NOW()
                """,
                (key, Json(data)),
            )

    @staticmethod
    def load(key):
        with Database.cursor() as cur:
            cur.execute("SELECT data FROM app_cache WHERE cache_key = %s", (key,))
            row = cur.fetchone()
        return row["data"] if row else None


class ForecastRepository:
    @staticmethod
    def save_results(user_email, forecast_type, results, source="ai_portfolio_forecast"):
        if not isinstance(results, list):
            return None
        with Database.cursor() as cur:
            cur.execute(
                """
                INSERT INTO forecast_runs(user_email, forecast_type, source)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (user_email, forecast_type, source),
            )
            run_id = cur.fetchone()["id"]
            for result in results:
                ticker = str(result.get("ticker", "") if isinstance(result, dict) else "").upper()
                cur.execute(
                    """
                    INSERT INTO forecast_results(run_id, ticker, result)
                    VALUES (%s, %s, %s)
                    """,
                    (run_id, ticker, Json(result)),
                )
            return run_id
