# -*- coding: utf-8 -*-

import os
import warnings
import datetime
import requests
from postgres_storage import DatabaseUnavailable, ForecastRepository

warnings.filterwarnings("ignore")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor, ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

try:
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.callbacks import EarlyStopping
    KERAS_BACKEND = "tensorflow.keras"
    KERAS_OK = True
except Exception:
    try:
        from keras.models import Sequential
        from keras.layers import LSTM, Dense, Dropout
        from keras.callbacks import EarlyStopping
        KERAS_BACKEND = "keras"
        KERAS_OK = True
    except Exception:
        KERAS_BACKEND = None
        KERAS_OK = False


print("[DEBUG] ЗАГРУЖЕН ai_portfolio_forecast.py:", __file__)


# ============================================================
# НАСТРОЙКА ПРОГНОЗА
# Сейчас прогноз строится на 3 торговых дня.
#
# Для прогноза на 4 дня:
# FORECAST_DAYS = 4
#
# Для прогноза на 5 дней:
# FORECAST_DAYS = 5
# ============================================================

FORECAST_DAYS = 30
TARGET_COL = f"target_return_{FORECAST_DAYS}"

CANDLES_LIMIT = 500
HISTORY_DAYS = 760
LSTM_LOOKBACK = 60
EXPECTED_FEATURES_COUNT = 42
TRAIN_RATIO = 0.80
MIN_ROWS = 120

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

MOEX_BASE = "https://iss.moex.com/iss"

RUSSIAN_TICKERS = [
    "SBER", "GAZP", "LKOH", "GMKN", "TATN", "ROSN", "NVTK", "YDEX", "MTSS", "CHMF",
    "PLZL", "ALRS", "SNGS", "SNGSP", "VTBR", "MOEX", "MAGN", "PHOR", "NLMK",
    "TRNFP", "FIVE", "TCSG", "OZON", "ASTR", "SOFL", "HHRU", "WUSH", "RUAL", "AFLT",
    "IRAO", "FEES", "MVID", "SMLT", "BSPB", "LENT", "KMAZ", "BELU", "FLOT", "TGKA",
    "ROST", "SVAV", "UNAC", "VSMO"
]


def _current_user_email():
    try:
        from app_state import app_state
        return app_state.email
    except Exception:
        return None


def _save_forecast_results(forecast_type, results):
    try:
        ForecastRepository.save_results(
            user_email=_current_user_email(),
            forecast_type=forecast_type,
            results=results,
        )
    except DatabaseUnavailable as e:
        print(f"[FORECAST] PostgreSQL недоступен, прогноз не сохранен: {e}")
    except Exception as e:
        print(f"[FORECAST] Ошибка сохранения прогноза в PostgreSQL: {e}")


# ============================================================
# ЗАГРУЗКА ДАННЫХ MOEX
# ============================================================

def _request_moex_json(url, params=None, timeout=15):
    try:
        response = requests.get(
            url,
            params=params or {},
            headers=HEADERS,
            timeout=timeout
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[MOEX] Ошибка запроса: {e}")
        return None


def _moex_block_to_df(data, block_name="candles"):
    if not data:
        return pd.DataFrame()

    block = data.get(block_name)

    if not block:
        return pd.DataFrame()

    columns = block.get("columns", [])
    rows = block.get("data", [])

    if not columns or not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows, columns=columns)


def _load_moex_candles_board(ticker, board, days=900, limit=1600):
    ticker = str(ticker).upper().strip()

    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days)

    url = (
        f"{MOEX_BASE}/engines/stock/markets/shares/"
        f"boards/{board}/securities/{ticker}/candles.json"
    )

    params = {
        "iss.meta": "off",
        "interval": 24,
        "from": start_date.strftime("%Y-%m-%d"),
        "till": end_date.strftime("%Y-%m-%d"),
        "limit": limit,
        "sort_order": "desc",
        "sort_column": "begin",
    }

    data = _request_moex_json(url, params=params)
    df = _moex_block_to_df(data, "candles")

    if df.empty:
        return pd.DataFrame()

    required_cols = ["begin", "open", "high", "low", "close", "volume"]

    for col in required_cols:
        if col not in df.columns:
            return pd.DataFrame()

    df["begin"] = pd.to_datetime(df["begin"], errors="coerce")

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["begin", "open", "high", "low", "close"])
    df = df.sort_values("begin").reset_index(drop=True)

    if df.empty:
        return pd.DataFrame()

    return df[["begin", "open", "high", "low", "close", "volume"]]


def _load_full_candles(ticker, days=900, limit=1600):
    """
    Загружает исторические свечи для обучения модели.
    Важно: пробуем несколько board, потому что у разных бумаг MOEX данные
    могут лежать не только на TQBR.
    """

    ticker = str(ticker).upper().strip()

    boards = ["TQBR", "TQTF"]

    best_df = pd.DataFrame()
    best_board = None

    for board in boards:
        df = _load_moex_candles_board(
            ticker=ticker,
            board=board,
            days=days,
            limit=limit
        )

        if df.empty:
            continue

        if best_df.empty or len(df) > len(best_df):
            best_df = df
            best_board = board

    if best_df.empty:
        print(f"[FORECAST] {ticker}: исторические свечи не найдены")
        return pd.DataFrame()

    print(
        f"[FORECAST] {ticker}: исторические свечи board={best_board}, "
        f"строк={len(best_df)}, от {best_df['begin'].min()} до {best_df['begin'].max()}"
    )

    return best_df


def _safe_dashboard_price(ticker):
    """
    Берёт текущую цену так же, как в dashboard.py:
    через последние дневные свечи MOEX за последние 45 дней.

    Это значение выводится в окне AI-прогноза как «Текущая».
    """

    ticker = str(ticker).upper().strip()

    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=45)

    boards = ["TQBR", "TQTF"]

    for board in boards:
        try:
            url = (
                f"{MOEX_BASE}/engines/stock/markets/shares/"
                f"boards/{board}/securities/{ticker}/candles.json"
            )

            params = {
                "iss.meta": "off",
                "interval": 24,
                "from": start_date.strftime("%Y-%m-%d"),
                "till": end_date.strftime("%Y-%m-%d"),
                "limit": 30,
                "sort_order": "desc",
                "sort_column": "begin",
            }

            data = _request_moex_json(url, params=params)
            df = _moex_block_to_df(data, "candles")

            if df.empty:
                continue

            if "begin" not in df.columns or "close" not in df.columns:
                continue

            df["begin"] = pd.to_datetime(df["begin"], errors="coerce")
            df["close"] = pd.to_numeric(df["close"], errors="coerce")

            df = df.dropna(subset=["begin", "close"])
            df = df.sort_values("begin").reset_index(drop=True)

            if df.empty:
                continue

            price = float(df["close"].iloc[-1])
            price_date = df["begin"].iloc[-1]

            if np.isfinite(price) and price > 0:
                print(
                    f"[FORECAST] {ticker}: ТЕКУЩАЯ ЦЕНА КАК В DASHBOARD = "
                    f"{price:.2f}, дата = {price_date}, board = {board}"
                )
                return price

        except Exception as e:
            print(f"[FORECAST] {ticker}: ошибка получения текущей цены {board} — {e}")

    return None


# ============================================================
# ПРИЗНАКИ
# ============================================================

def _to_float_series(series):
    return pd.to_numeric(series, errors="coerce").astype(float)


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / (avg_loss + 1e-9)

    return 100 - (100 / (1 + rs))


def _feature_columns(df):
    exclude = {
        "begin",
        "future_close",
        "log_close",
    }

    return [
        col for col in df.columns
        if col not in exclude
        and not str(col).startswith("target_return_")
        and np.issubdtype(df[col].dtype, np.number)
    ]


def _prepare_features(df):
    """
    Готовит признаки для модели.
    Целевая переменная считается на FORECAST_DAYS торговых дней.
    """

    df = df.copy()

    required = ["open", "high", "low", "close", "volume"]

    for col in required:
        if col not in df.columns:
            raise ValueError(f"В данных нет колонки {col}")
        df[col] = _to_float_series(df[col])

    df = df.dropna(subset=required).copy()

    if "begin" in df.columns:
        df["begin"] = pd.to_datetime(df["begin"], errors="coerce")
        df = df.sort_values("begin").reset_index(drop=True)

    df["log_close"] = np.log(df["close"].clip(lower=1e-9))

    df["ret_1"] = df["close"].pct_change(1)
    df["ret_3"] = df["close"].pct_change(3)
    df["ret_7"] = df["close"].pct_change(7)
    df["ret_14"] = df["close"].pct_change(14)
    df["ret_30"] = df["close"].pct_change(30)

    df["log_ret_1"] = df["log_close"].diff(1)

    for p in [7, 14, 30, 60, 120, 180]:
        df[f"sma_{p}"] = df["close"].rolling(p).mean()
        df[f"ema_{p}"] = df["close"].ewm(span=p, adjust=False).mean()
        df[f"close_to_sma_{p}"] = df["close"] / (df[f"sma_{p}"] + 1e-9) - 1

    df["volatility_7"] = df["log_ret_1"].rolling(7).std()
    df["volatility_14"] = df["log_ret_1"].rolling(14).std()
    df["volatility_30"] = df["log_ret_1"].rolling(30).std()

    df["volume_log"] = np.log1p(df["volume"].clip(lower=0))
    df["volume_sma_20"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / (df["volume_sma_20"] + 1e-9)

    df["high_low_range"] = (df["high"] - df["low"]) / (df["close"] + 1e-9)
    df["close_open"] = (df["close"] - df["open"]) / (df["open"] + 1e-9)

    df["rsi_14"] = _rsi(df["close"], 14)
    df["rsi_30"] = _rsi(df["close"], 30)

    ema_12 = df["close"].ewm(span=12, adjust=False).mean()
    ema_26 = df["close"].ewm(span=26, adjust=False).mean()

    df["macd"] = ema_12 - ema_26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_diff"] = df["macd"] - df["macd_signal"]

    df["future_close"] = df["close"].shift(-FORECAST_DAYS)
    df[TARGET_COL] = df["future_close"] / df["close"] - 1

    df = df.replace([np.inf, -np.inf], np.nan)

    feature_cols = _feature_columns(df)

    df = df.dropna(subset=feature_cols + ["close"]).copy()
    df = df.reset_index(drop=True)

    return df


# ============================================================
# МОДЕЛИ
# ============================================================

def _fit_fast_ensemble(X_train, y_train):
    models = [
        (
            "gbr",
            GradientBoostingRegressor(
                n_estimators=220,
                learning_rate=0.035,
                max_depth=3,
                subsample=0.85,
                random_state=42
            )
        ),
        (
            "rf",
            RandomForestRegressor(
                n_estimators=180,
                max_depth=8,
                min_samples_leaf=4,
                random_state=42,
                n_jobs=-1
            )
        ),
        (
            "extra",
            ExtraTreesRegressor(
                n_estimators=160,
                max_depth=8,
                min_samples_leaf=3,
                random_state=42,
                n_jobs=-1
            )
        ),
        (
            "ridge",
            make_pipeline(
                StandardScaler(),
                Ridge(alpha=2.0)
            )
        )
    ]

    fitted = []

    for name, model in models:
        try:
            model.fit(X_train, y_train)
            fitted.append((name, model))
            print(f"[FORECAST] Модель {name} обучена успешно")
        except Exception as e:
            print(f"[FORECAST] Модель {name} не обучилась: {e}")

    return fitted


def _predict_fast_ensemble(models, x_last):
    preds = []

    for name, model in models:
        try:
            p = float(model.predict(x_last)[0])
            preds.append(p)
            print(f"[FORECAST] {name} предсказал: {p:.4f}")
        except Exception as e:
            print(f"[FORECAST] {name} не смог предсказать: {e}")

    if not preds:
        raise ValueError("Не удалось получить прогноз ансамбля")

    preds = np.clip(np.array(preds, dtype=float), -0.15, 0.15)

    return float(np.mean(preds)), float(np.std(preds))


def _lstm_return_forecast(df_train, df_features, feature_cols):
    if not KERAS_OK:
        print("[FORECAST] Keras недоступен, LSTM пропущен")
        return None

    try:
        lookback = LSTM_LOOKBACK

        if len(df_train) < lookback + 80:
            print(f"[FORECAST] Недостаточно данных для LSTM: {len(df_train)}")
            return None

        if len(df_features) < lookback:
            print(f"[FORECAST] Недостаточно строк для LSTM-прогноза: {len(df_features)}")
            return None

        work = df_train[feature_cols + [TARGET_COL]].dropna(
            subset=[TARGET_COL]
        ).copy()

        values = work[feature_cols].values.astype(float)
        target = work[TARGET_COL].values.astype(float)

        scaler = StandardScaler()
        values_scaled = scaler.fit_transform(values)

        X_seq = []
        y_seq = []

        for i in range(lookback, len(values_scaled)):
            X_seq.append(values_scaled[i - lookback:i])
            y_seq.append(target[i])

        X_seq = np.array(X_seq, dtype=np.float32)
        y_seq = np.array(y_seq, dtype=np.float32)

        if len(X_seq) < 80:
            print(f"[FORECAST] Мало последовательностей для LSTM: {len(X_seq)}")
            return None

        print(f"[FORECAST] Обучаю LSTM на {len(X_seq)} последовательностях...")

        split_idx = int(len(X_seq) * TRAIN_RATIO)
        split_idx = max(1, min(split_idx, len(X_seq) - 1))

        X_train_seq = X_seq[:split_idx]
        y_train_seq = y_seq[:split_idx]
        X_test_seq = X_seq[split_idx:]
        y_test_seq = y_seq[split_idx:]

        print(
            f"[FORECAST] LSTM backend={KERAS_BACKEND}, "
            f"train={len(X_train_seq)}, test={len(X_test_seq)}, "
            f"lookback={lookback}, features={len(feature_cols)}"
        )

        model = Sequential([
            LSTM(48, return_sequences=True, input_shape=(X_seq.shape[1], X_seq.shape[2])),
            Dropout(0.20),
            LSTM(24),
            Dropout(0.15),
            Dense(16, activation="relu"),
            Dense(1)
        ])

        model.compile(optimizer="adam", loss="mse")

        model.fit(
            X_train_seq,
            y_train_seq,
            epochs=22,
            batch_size=16,
            verbose=0,
            callbacks=[
                EarlyStopping(
                    monitor="loss",
                    patience=4,
                    restore_best_weights=True
                )
            ]
        )

        test_pred = model.predict(X_test_seq, verbose=0).reshape(-1)
        test_mae = float(np.mean(np.abs(test_pred - y_test_seq)))
        test_rmse = float(np.sqrt(np.mean((test_pred - y_test_seq) ** 2)))
        direction_accuracy = float(np.mean(np.sign(test_pred) == np.sign(y_test_seq)) * 100)

        last_values = df_features[feature_cols].tail(lookback).values.astype(float)

        if len(last_values) < lookback:
            return None

        last_values_scaled = scaler.transform(last_values)
        x_last = last_values_scaled.reshape(1, lookback, len(feature_cols))

        pred = float(model.predict(x_last, verbose=0)[0][0])
        pred = float(np.clip(pred, -0.15, 0.15))

        print(f"[FORECAST] LSTM предсказал: {pred:.4f}")

        return {
            "prediction": pred,
            "lookback": lookback,
            "train_sequences": int(len(X_train_seq)),
            "test_sequences": int(len(X_test_seq)),
            "test_mae": test_mae,
            "test_rmse": test_rmse,
            "direction_accuracy": direction_accuracy,
            "backend": KERAS_BACKEND,
        }

    except Exception as e:
        print(f"[FORECAST] Ошибка LSTM: {e}")
        return None


# ============================================================
# ПОНЯТНОЕ ОПИСАНИЕ ДЛЯ ПОДБОРКИ
# ============================================================

def _format_direction(change_percent):
    if change_percent > 0:
        return f"рост на {change_percent:.2f}%"
    if change_percent < 0:
        return f"снижение на {abs(change_percent):.2f}%"
    return "почти без изменения"


def _trend_text(trend_30):
    try:
        trend_30 = float(trend_30)
    except Exception:
        return "Динамику за последний месяц оценить не удалось."

    if trend_30 >= 0.08:
        return (
            "За последний месяц акция уже заметно выросла. Это показывает интерес к бумаге, "
            "но после сильного роста возможен краткосрочный откат."
        )

    if trend_30 >= 0.03:
        return (
            "За последний месяц акция постепенно росла. Это хороший сигнал: цена уже двигалась вверх, "
            "и модель допускает продолжение роста."
        )

    if trend_30 <= -0.08:
        return (
            "За последний месяц акция заметно снизилась. Это повышает риск покупки: "
            "если слабость сохранится, цена может продолжить падение."
        )

    if trend_30 <= -0.03:
        return (
            "За последний месяц акция немного снижалась. Поэтому покупать её стоит осторожно: "
            "у бумаги пока нет уверенного движения вверх."
        )

    return (
        "За последний месяц цена двигалась спокойно, без сильного роста или падения. "
        "Это значит, что яркого тренда сейчас нет."
    )


def _rsi_text(rsi):
    try:
        rsi = float(rsi)
    except Exception:
        return "Оценить состояние цены по RSI не удалось."

    if rsi < 30:
        return (
            "Акция сильно просела после недавнего снижения. Иногда после такого бывает отскок вверх, "
            "но риск всё равно повышенный."
        )

    if rsi < 40:
        return (
            "Акция находится ближе к зоне снижения. Цена может быть интереснее для входа, "
            "но нужен подтверждающий сигнал на рост."
        )

    if rsi > 75:
        return (
            "Акция выглядит перегретой: она уже сильно выросла. Покупать в такой момент рискованнее, "
            "потому что возможен откат вниз."
        )

    if rsi > 65:
        return (
            "Акция близка к зоне перегрева. Потенциал роста ещё есть, "
            "но риск отката выше обычного."
        )

    return (
        "По текущей динамике акция выглядит нейтрально: она не слишком просевшая "
        "и не слишком перегретая."
    )


def _risk_text(confidence, disagreement, vol):
    try:
        confidence = float(confidence)
        disagreement = float(disagreement)
        vol = float(vol)
    except Exception:
        return "Уровень риска оценить не удалось."

    if confidence >= 75 and disagreement < 0.02 and vol < 0.035:
        return (
            "Уверенность высокая: модели дают похожий результат, а цена не выглядит слишком резкой. "
            "Такой прогноз можно считать относительно стабильным."
        )

    if confidence >= 60 and disagreement < 0.04:
        return (
            "Уверенность средняя: модели в целом согласны с направлением прогноза, "
            "но обычные рыночные колебания всё равно возможны."
        )

    if disagreement >= 0.06:
        return (
            "Риск повышенный: модели дают разные оценки. Это значит, что прогноз менее надёжный, "
            "и покупать только на основании этого сигнала не стоит."
        )

    if vol >= 0.06:
        return (
            "Риск повышенный: цена акции часто меняется резко. Даже положительный прогноз "
            "может быстро не совпасть с реальным движением."
        )

    return (
        "Уверенность невысокая: сильного сигнала нет. Этот прогноз лучше использовать как подсказку, "
        "а не как единственное основание для покупки."
    )


def _plain_reason(
    ticker,
    current_price,
    predicted_price,
    predicted_return,
    confidence,
    disagreement,
    trend_30,
    rsi,
    vol
):
    change_percent = predicted_return * 100
    direction_text = _format_direction(change_percent)

    try:
        current_price = float(current_price)
        predicted_price = float(predicted_price)
    except Exception:
        current_price = 0.0
        predicted_price = 0.0

    if change_percent >= 1.5:
        conclusion = (
            f"Акцию {ticker} можно рассмотреть к покупке. "
            f"Модель ожидает {direction_text} за ближайшие {FORECAST_DAYS} торговых дня: "
            f"с {current_price:.2f} ₽ до {predicted_price:.2f} ₽."
        )
        decision = (
            "Простыми словами: по расчёту цена может немного вырасти, "
            "поэтому бумага попала в подборку."
        )

    elif change_percent >= 0.5:
        conclusion = (
            f"По акции {ticker} есть слабый положительный сигнал. "
            f"Модель ожидает {direction_text} за ближайшие {FORECAST_DAYS} торговых дня: "
            f"с {current_price:.2f} ₽ до {predicted_price:.2f} ₽."
        )
        decision = (
            "Простыми словами: потенциал роста есть, но он небольшой. "
            "Покупку лучше рассматривать осторожно."
        )

    elif change_percent <= -1.0:
        conclusion = (
            f"Акцию {ticker} сейчас лучше не покупать. "
            f"Модель ожидает {direction_text} за ближайшие {FORECAST_DAYS} торговых дня: "
            f"с {current_price:.2f} ₽ до {predicted_price:.2f} ₽."
        )
        decision = (
            "Простыми словами: модель видит риск снижения цены, "
            "поэтому входить в покупку сейчас опаснее."
        )

    else:
        conclusion = (
            f"По акции {ticker} нет сильного сигнала. "
            f"Модель ожидает движение около {change_percent:.2f}% "
            f"за ближайшие {FORECAST_DAYS} торговых дня."
        )
        decision = (
            "Простыми словами: ожидаемое изменение слишком маленькое, "
            "поэтому лучше подождать более понятного сигнала."
        )

    trend_explanation = _trend_text(trend_30)
    rsi_explanation = _rsi_text(rsi)
    risk_explanation = _risk_text(confidence, disagreement, vol)

    if change_percent >= 1.5 and confidence >= 60:
        final_note = (
            "Итог: идея выглядит умеренно привлекательной, но это краткосрочный прогноз. "
            "Перед покупкой лучше дополнительно посмотреть график и новости."
        )
    elif change_percent >= 0.5:
        final_note = (
            "Итог: сигнал есть, но он не сильный. Бумага больше подходит для наблюдения, "
            "чем для уверенной покупки."
        )
    elif change_percent <= -1.0:
        final_note = (
            "Итог: покупать сейчас нежелательно, потому что прогноз показывает отрицательное движение."
        )
    else:
        final_note = (
            "Итог: явного преимущества для покупки нет, лучше дождаться более понятной динамики."
        )

    return (
        f"{conclusion} "
        f"{decision} "
        f"{trend_explanation} "
        f"{rsi_explanation} "
        f"{risk_explanation} "
        f"{final_note}"
    )


# ============================================================
# ОСНОВНОЙ ПРОГНОЗ
# ============================================================

def forecast_ticker(ticker, use_lstm=True):
    ticker = str(ticker).upper().strip()

    print(f"\n[FORECAST] ========== Начинаю прогноз для {ticker} ==========")

    df_raw = _load_full_candles(
        ticker=ticker,
        limit=CANDLES_LIMIT,
        days=HISTORY_DAYS
    )

    print(
        f"[FORECAST] {ticker}: загружено "
        f"{len(df_raw) if df_raw is not None and not df_raw.empty else 0} свечей"
    )

    if df_raw is None or df_raw.empty:
        raise ValueError(f"Не удалось загрузить свечи по {ticker}")

    df_features = _prepare_features(df_raw)

    print(f"[FORECAST] {ticker}: после подготовки признаков осталось {len(df_features)} строк")

    if len(df_features) < MIN_ROWS:
        raise ValueError(
            f"Недостаточно исторических данных по {ticker}: {len(df_features)} строк"
        )

    feature_cols = _feature_columns(df_features)

    if len(feature_cols) != EXPECTED_FEATURES_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_FEATURES_COUNT} features, got {len(feature_cols)}"
        )

    print(f"[FORECAST] {ticker}: признаков для модели: {len(feature_cols)}")
    print(f"[FORECAST] {ticker}: горизонт прогноза = {FORECAST_DAYS} торговых дня")

    df_train = df_features.dropna(subset=[TARGET_COL]).copy()

    if len(df_train) < MIN_ROWS:
        raise ValueError(
            f"Недостаточно обучающих строк по {ticker}: {len(df_train)} строк"
        )

    train = df_train.copy()
    last = df_features.iloc[[-1]].copy()

    X_train = train[feature_cols].values
    y_train = train[TARGET_COL].values
    x_last = last[feature_cols].values

    last_candle_price = float(df_features["close"].iloc[-1])
    last_date = df_features["begin"].iloc[-1] if "begin" in df_features.columns else "—"

    current_price = _safe_dashboard_price(ticker)

    if current_price is None:
        current_price = last_candle_price
        print(
            f"[FORECAST] {ticker}: свежая цена не получена, "
            f"используем последнюю свечу из истории = {current_price:.2f}, дата = {last_date}"
        )
    else:
        print(
            f"[FORECAST] {ticker}: ДЛЯ ОКНА AI current_price = {current_price:.2f}; "
            f"историческая свеча только для обучения = {last_candle_price:.2f}, "
            f"дата свечи = {last_date}"
        )

    models = _fit_fast_ensemble(X_train, y_train)

    fast_pred, disagreement = _predict_fast_ensemble(models, x_last)

    print(f"[FORECAST] {ticker}: ансамбль = {fast_pred:.4f}, разброс = {disagreement:.4f}")

    lstm_result = _lstm_return_forecast(df_train, df_features, feature_cols) if use_lstm else None
    lstm_pred = lstm_result["prediction"] if isinstance(lstm_result, dict) else None

    if lstm_pred is not None:
        predicted_return = 0.75 * fast_pred + 0.25 * lstm_pred
        print(f"[FORECAST] {ticker}: финал ML + LSTM = {predicted_return:.4f}")
    else:
        predicted_return = fast_pred
        print(f"[FORECAST] {ticker}: финал только ML = {predicted_return:.4f}")

    predicted_return = float(np.clip(predicted_return, -0.12, 0.12))

    predicted_price = current_price * (1 + predicted_return)

    trend_30 = float(df_features["ret_30"].iloc[-1])
    rsi = float(df_features["rsi_14"].iloc[-1])
    vol = float(df_features["volatility_30"].iloc[-1])

    confidence = 58 + abs(predicted_return) * 180
    confidence -= disagreement * 130
    confidence -= min(max(vol, 0), 0.08) * 230
    confidence = float(np.clip(confidence, 35, 92))

    reason = _plain_reason(
        ticker=ticker,
        current_price=current_price,
        predicted_price=predicted_price,
        predicted_return=predicted_return,
        confidence=confidence,
        disagreement=disagreement,
        trend_30=trend_30,
        rsi=rsi,
        vol=vol
    )

    print(
        f"[FORECAST] {ticker}: В ОКНО УЙДЁТ "
        f"current_price={current_price:.2f}, "
        f"predicted_price={predicted_price:.2f}, "
        f"change={predicted_return * 100:.2f}%"
    )

    return {
        "ticker": ticker,
        "current_price": float(current_price),
        "predicted_price": float(predicted_price),
        "predicted_return": float(predicted_return),
        "change_percent": float(predicted_return * 100),
        "confidence": float(confidence),
        "reason": reason,
        "train_rows": len(train),
        "features_count": len(feature_cols),
        "candles_limit": CANDLES_LIMIT,
        "lstm_lookback": LSTM_LOOKBACK,
        "train_ratio": TRAIN_RATIO,
        "lstm_used": bool(lstm_pred is not None),
        "lstm_metrics": lstm_result if isinstance(lstm_result, dict) else None,
        "last_candle_date": str(last_date),
        "last_candle_price": float(last_candle_price),
        "forecast_days": FORECAST_DAYS,
        "trend_30": float(trend_30),
        "rsi": float(rsi),
        "volatility_30": float(vol),
        "disagreement": float(disagreement)
    }


def make_recommendation(change_percent, confidence=50):
    try:
        change_percent = float(change_percent)
        confidence = float(confidence)
    except Exception:
        return "Держать"

    if change_percent >= 1.2 and confidence >= 55:
        return "Покупать"

    if change_percent <= -1.0:
        return "Не покупать"

    return "Держать"


def forecast_portfolio_month(portfolio):
    """
    Название функции оставлено старым, потому что её вызывает portfolio.py.
    Фактически прогноз строится на FORECAST_DAYS торговых дня.
    """

    results = []

    if not isinstance(portfolio, list):
        return results

    print(
        f"\n[FORECAST] Запуск прогноза портфеля, позиций: {len(portfolio)}, "
        f"горизонт = {FORECAST_DAYS} торговых дня"
    )

    for item in portfolio:
        if not isinstance(item, dict):
            continue

        ticker = str(item.get("secid", "")).upper().strip()
        quantity = int(item.get("quantity", 0) or 0)
        buy_price = float(item.get("buy_price", 0) or 0)

        if not ticker or quantity <= 0:
            continue

        try:
            forecast = forecast_ticker(ticker, use_lstm=True)

            current_price = _safe_dashboard_price(ticker)

            if current_price is None:
                current_price = float(forecast["current_price"])

            predicted_return = float(forecast["predicted_return"])
            predicted_price = current_price * (1 + predicted_return)
            change_percent = predicted_return * 100

            reason = _plain_reason(
                ticker=ticker,
                current_price=current_price,
                predicted_price=predicted_price,
                predicted_return=predicted_return,
                confidence=forecast["confidence"],
                disagreement=forecast.get("disagreement", 0.0),
                trend_30=forecast.get("trend_30", 0.0),
                rsi=forecast.get("rsi", 50.0),
                vol=forecast.get("volatility_30", 0.03)
            )

            invested_value = buy_price * quantity
            current_value = current_price * quantity
            predicted_value = predicted_price * quantity

            recommendation = make_recommendation(
                change_percent,
                forecast["confidence"]
            )

            print(
                f"[FORECAST] {ticker}: В ТАБЛИЦУ AI-ПРОГНОЗА "
                f"current_price={current_price:.2f}, "
                f"predicted_price={predicted_price:.2f}, "
                f"forecast_days={FORECAST_DAYS}"
            )

            results.append({
                "ticker": ticker,
                "quantity": quantity,
                "buy_price": buy_price,
                "current_price": float(current_price),
                "predicted_price": float(predicted_price),
                "invested_value": float(invested_value),
                "current_value": float(current_value),
                "predicted_value": float(predicted_value),
                "profit_from_buy": float(predicted_value - invested_value),
                "profit_from_current": float(predicted_value - current_value),
                "change_percent": float(change_percent),
                "confidence": float(forecast["confidence"]),
                "recommendation": recommendation,
                "reason": reason,
                "train_rows": forecast.get("train_rows"),
                "features_count": forecast.get("features_count"),
                "candles_limit": forecast.get("candles_limit"),
                "lstm_lookback": forecast.get("lstm_lookback"),
                "train_ratio": forecast.get("train_ratio"),
                "lstm_used": forecast.get("lstm_used"),
                "lstm_metrics": forecast.get("lstm_metrics"),
                "last_candle_date": forecast.get("last_candle_date"),
                "last_candle_price": forecast.get("last_candle_price"),
                "forecast_days": FORECAST_DAYS
            })

            print(f"[FORECAST] {ticker}: прогноз добавлен в результаты")

        except Exception as e:
            print(f"[FORECAST] {ticker}: ОШИБКА — {e}")

            results.append({
                "ticker": ticker,
                "quantity": quantity,
                "error": str(e)
            })

    print(
        f"[FORECAST] Портфель: успешно {sum(1 for r in results if not r.get('error'))}, "
        f"ошибок {sum(1 for r in results if r.get('error'))}"
    )

    _save_forecast_results("portfolio", results)
    return results


def recommend_stocks_to_buy(exclude_tickers=None, top_n=10):
    exclude_tickers = {str(t).upper() for t in (exclude_tickers or set())}

    print(
        f"\n[FORECAST] Подбор рекомендаций, исключаем: {exclude_tickers}, "
        f"горизонт = {FORECAST_DAYS} торговых дня"
    )

    candidates = []

    for ticker in RUSSIAN_TICKERS:
        if ticker in exclude_tickers:
            continue

        try:
            forecast = forecast_ticker(ticker, use_lstm=False)

            fresh_price = _safe_dashboard_price(ticker)

            if fresh_price is not None:
                forecast["current_price"] = float(fresh_price)
                forecast["predicted_price"] = float(
                    fresh_price * (1 + forecast["predicted_return"])
                )

                forecast["reason"] = _plain_reason(
                    ticker=ticker,
                    current_price=forecast["current_price"],
                    predicted_price=forecast["predicted_price"],
                    predicted_return=forecast["predicted_return"],
                    confidence=forecast["confidence"],
                    disagreement=forecast.get("disagreement", 0.0),
                    trend_30=forecast.get("trend_30", 0.0),
                    rsi=forecast.get("rsi", 50.0),
                    vol=forecast.get("volatility_30", 0.03)
                )

            change_percent = float(forecast.get("change_percent", 0))
            confidence = float(forecast.get("confidence", 0))

            if change_percent <= 0.8 or confidence < 45:
                print(
                    f"[FORECAST] {ticker}: потенциал "
                    f"{change_percent:.2f}% или уверенность {confidence:.1f}% — пропускаем"
                )
                continue

            candidates.append(forecast)

            print(
                f"[FORECAST] {ticker}: добавлен в кандидаты "
                f"({change_percent:.2f}%, уверенность {confidence:.1f}%)"
            )

        except Exception as e:
            print(f"[FORECAST] {ticker}: пропущен — {e}")
            continue

    candidates.sort(
        key=lambda x: (
            x.get("change_percent", 0) * 0.70
            + x.get("confidence", 0) * 0.03
        ),
        reverse=True
    )

    print(f"[FORECAST] Рекомендаций найдено: {len(candidates)}, возвращаем топ {top_n}")

    top_candidates = candidates[:top_n]
    _save_forecast_results("recommendations", top_candidates)
    return top_candidates


if __name__ == "__main__":
    demo_portfolio = [
        {"secid": "SBER", "quantity": 10, "buy_price": 300},
        {"secid": "LKOH", "quantity": 1, "buy_price": 5500},
    ]

    print(forecast_portfolio_month(demo_portfolio))
    print(recommend_stocks_to_buy({"SBER", "LKOH"}))
