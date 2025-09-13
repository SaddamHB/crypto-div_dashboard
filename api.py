# api.py
import os
import time
import requests
import pandas as pd
import numpy as np
from flask import Flask, jsonify
from flask_cors import CORS
import math

# ---- Optional: use the 'ta' library for RSI OR custom simple RSI if ta not available
try:
    from ta.momentum import RSIIndicator
    TA_AVAILABLE = True
except Exception:
    TA_AVAILABLE = False

app = Flask(__name__)
CORS(app)  # allow all origins; for production restreindre à ton domaine Netlify

# ----- Config (tu peux modifier ou définir via variables d'environnement sur Render)
SYMBOLS = os.environ.get("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT").split(",")  # séparer par ,
TIMEFRAMES = {"15m": 500, "1h": 500, "4h": 500, "1d": 500}
RSI_PERIOD = int(os.environ.get("RSI_PERIOD", 14))
LB_L = int(os.environ.get("LB_L", 5))
LB_R = int(os.environ.get("LB_R", 5))
RANGE_LOWER = int(os.environ.get("RANGE_LOWER", 5))
RANGE_UPPER = int(os.environ.get("RANGE_UPPER", 60))
CACHE_TTL = int(os.environ.get("CACHE_TTL", 30))  # secondes

# ---- Simple in-memory cache
CACHE = {"ts": 0, "data": None}

# ---- Helpers
def fetch_ohlcv(symbol, interval, limit=500):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","qav","trades","tbbav","tbqav","ignore"
    ])
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df

def rsi_series(close, period=14):
    if TA_AVAILABLE:
        return RSIIndicator(close, window=period).rsi().to_numpy()
    # fallback simple RSI implementation
    delta = np.diff(close, prepend=close[0])
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(up).rolling(window=period, min_periods=period).mean()
    roll_down = pd.Series(down).rolling(window=period, min_periods=period).mean()
    rs = roll_up / roll_down
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50).to_numpy()

def find_pivots_low(lows, lbL, lbR):
    pivots = []
    n = len(lows)
    for i in range(lbL, n - lbR):
        left = lows[i - lbL : i]
        right = lows[i+1 : i+1+lbR]
        if lows[i] < min(left) and lows[i] <= min(right):
            pivots.append(i)
    return pivots

def find_pivots_high(highs, lbL, lbR):
    pivots = []
    n = len(highs)
    for i in range(lbL, n - lbR):
        left = highs[i - lbL : i]
        right = highs[i+1 : i+1+lbR]
        if highs[i] > max(left) and highs[i] >= max(right):
            pivots.append(i)
    return pivots

def last_two_within_range(pivots, range_lower, range_upper):
    if len(pivots) < 2:
        return None
    # keep only last two
    p1 = pivots[-2]
    p2 = pivots[-1]
    dist = p2 - p1
    if range_lower <= dist <= range_upper:
        return (p1, p2)
    return None

def detect_divergence_from_df(df):
    try:
        closes = df["close"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        rsi = rsi_series(df["close"], RSI_PERIOD)
        # pivots
        pl = find_pivots_low(lows, LB_L, LB_R)
        ph = find_pivots_high(highs, LB_L, LB_R)

        # Regular/Hidden Bullish based on lows
        low_pair = last_two_within_range(pl, RANGE_LOWER, RANGE_UPPER)
        if low_pair:
            i1, i2 = low_pair
            price1, price2 = lows[i1], lows[i2]
            rsi1, rsi2 = rsi[i1], rsi[i2]
            # Regular Bullish: price lower low (price2 < price1) and rsi higher low (rsi2 > rsi1)
            if price2 < price1 and rsi2 > rsi1:
                return "Regular Bullish"
            # Hidden Bullish: price higher low and rsi lower low
            if price2 > price1 and rsi2 < rsi1:
                return "Hidden Bullish"

        # Regular/Hidden Bearish based on highs
        high_pair = last_two_within_range(ph, RANGE_LOWER, RANGE_UPPER)
        if high_pair:
            i1, i2 = high_pair
            price1, price2 = highs[i1], highs[i2]
            rsi1, rsi2 = rsi[i1], rsi[i2]
            # Regular Bearish: price higher high and rsi lower high
            if price2 > price1 and rsi2 < rsi1:
                return "Regular Bearish"
            # Hidden Bearish: price lower high and rsi higher high
            if price2 < price1 and rsi2 > rsi1:
                return "Hidden Bearish"

    except Exception as e:
        print("Error detect_divergence:", e)
    return None

@app.route("/divergences")
def divergences():
    # simple TTL cache to avoid hammering Binance
    now = time.time()
    if CACHE["data"] is not None and now - CACHE["ts"] < CACHE_TTL:
        return jsonify(CACHE["data"])

    results = []
    for sym in SYMBOLS:
        sym = sym.strip().upper()
        for tf, limit in TIMEFRAMES.items():
            try:
                df = fetch_ohlcv(sym, tf, limit)
                sig = detect_divergence_from_df(df)
                results.append({"symbol": sym, "timeframe": tf, "divergence": sig})
            except Exception as e:
                results.append({"symbol": sym, "timeframe": tf, "divergence": None, "error": str(e)})
    # update cache
    CACHE["ts"] = now
    CACHE["data"] = results
    return jsonify(results)

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


