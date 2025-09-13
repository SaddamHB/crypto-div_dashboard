from flask import Flask, jsonify
import pandas as pd
import requests
from ta.momentum import RSIIndicator

app = Flask(__name__)

# Liste des cryptos et timeframes à surveiller
cryptos = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]  # à compléter si besoin
timeframes = ["15m", "1h", "4h", "1d"]

def get_klines(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = requests.get(url).json()
    df = pd.DataFrame(data, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote_asset_volume","number_of_trades",
        "taker_buy_base","taker_buy_quote","ignore"
    ])
    df["close"] = df["close"].astype(float)
    return df

def check_rsi_divergence(df, period=14):
    rsi = RSIIndicator(df["close"], period)
    df["rsi"] = rsi.rsi()
    # Ici on simplifie : divergence si RSI < 30 ou > 70
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
            df = get_klines(crypto, tf)
            result[crypto][tf] = check_rsi_divergence(df)
    return jsonify(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
