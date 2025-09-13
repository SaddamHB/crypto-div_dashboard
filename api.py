from flask import Flask, jsonify
import pandas as pd
import requests
from ta.momentum import RSIIndicator
import time

app = Flask(__name__)

# Liste des cryptos et timeframes à surveiller
cryptos = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]  # tu peux en ajouter
timeframes = ["15m", "1h", "4h", "1d"]

def get_klines(symbol, interval, limit=100, retry=3, wait=1):
    """
    Récupère les données OHLCV depuis Binance avec gestion des erreurs.
    retry: nombre de tentatives si l'API échoue
    wait: temps d'attente entre les tentatives en secondes
    """
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    for _ in range(retry):
        try:
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                raise Exception(f"Binance API error: {response.status_code}")
            data = response.json()
            if not data:
                raise Exception("Empty data from Binance")
            df = pd.DataFrame(data, columns=[
                "open_time","open","high","low","close","volume",
                "close_time","quote_asset_volume","number_of_trades",
                "taker_buy_base","taker_buy_quote","ignore"
            ])
            df["close"] = df["close"].astype(float)
            return df
        except Exception as e:
            last_error = str(e)
            time.sleep(wait)
    # Après toutes les tentatives échouées
    raise Exception(f"Failed to fetch {symbol} {interval}: {last_error}")

def check_rsi_divergence(df, period=14):
    """
    Vérifie une divergence simplifiée basée sur RSI :
    - RSI > 70 -> Bearish
    - RSI < 30 -> Bullish
    """
    if df.empty:
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
                df = get_klines(crypto, tf)
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
