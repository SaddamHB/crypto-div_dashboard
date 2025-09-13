from flask import Flask, jsonify
import pandas as pd
import requests
from ta.momentum import RSIIndicator
import time
from datetime import datetime

app = Flask(__name__)

# Liste des cryptos et timeframes
# Pour CoinGecko, on utilise les ids : 'bitcoin', 'ethereum', 'solana'
cryptos = ["bitcoin", "ethereum", "solana"]
timeframes = ["15m", "1h", "4h", "1d"]

# Mapping timeframe → nombre de minutes pour CoinGecko (pour simplifier)
tf_to_minutes = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440
}

def get_ohlcv(crypto_id, minutes, limit=100):
    """
    Récupère les prix historiques depuis CoinGecko.
    minutes: intervalle en minutes
    limit: nombre de bougies
    """
    # CoinGecko ne fournit pas directement le OHLCV avec minutes → on utilise "market_chart"
    days = max(1, int((minutes*limit)/(60*24)))  # approx pour "vs USD" over days
    url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart?vs_currency=usd&days={days}&interval=hourly"
    response = requests.get(url, timeout=5)
    if response.status_code != 200:
        raise Exception(f"CoinGecko API error: {response.status_code}")
    data = response.json()
    prices = data.get("prices", [])
    if not prices:
        raise Exception("Empty data from CoinGecko")
    df = pd.DataFrame(prices, columns=["timestamp", "price"])
    df["close"] = df["price"]
    return df.tail(limit)  # dernière "limit" valeurs

def check_rsi_divergence(df, period=14):
    """
    Divergence simplifiée : RSI > 70 = Bearish, RSI < 30 = Bullish
    """
    if df.empty or len(df) < period:
        return "Error"
    rsi = RSIIndicator(df["close"], period)
    df["rsi"] = rsi.rsi()
    last_rsi = df["rsi"].iloc[-1]
    if last_rsi > 70:
        return "Bearish"
    elif last_rsi < 30:
        return "Bullish"
    else:
        return "None"

@app.route("/divergences")
def divergences():
    result = {}
    for crypto in cryptos:
        result[crypto] = {}
        for tf in timeframes:
            try:
                df = get_ohlcv(crypto, tf_to_minutes[tf])
                result[crypto][tf] = check_rsi_divergence(df)
                time.sleep(0.2)  # petite pause pour limiter les requêtes
            except Exception as e:
                result[crypto][tf] = f"Error: {str(e)}"
    return jsonify(result)

@app.route("/")
def home():
    return "API Crypto Divergences: allez sur /divergences"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
