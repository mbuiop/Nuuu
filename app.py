# -*- coding: utf-8 -*-
"""
TV-Clone Backend
=================
یک بک‌اند Flask که داده‌های واقعی بازار ارز دیجیتال (از Binance) و فارکس
(از TwelveData) را می‌گیرد و به فرانت‌اند (چارت شبیه‌ساز TradingView) می‌دهد.

اجرا:
    pip install flask requests flask-cors
    python app.py

سپس مرورگر را باز کنید: http://127.0.0.1:5000

نکته درباره‌ی فارکس:
    برای دادهٔ فارکس از سرویس رایگان TwelveData استفاده شده (چون Binance
    جفت‌ارز فارکس ندارد). باید یک API Key رایگان از https://twelvedata.com
    بگیرید و در پنل تنظیمات (⚙) داخل خود برنامه وارد کنید. سطح رایگان آن
    روزانه ۸۰۰ درخواست و در دقیقه ۸ درخواست اجازه می‌دهد که برای دیدن چارت
    ۱۰۰ جفت‌ارز فارکس کافی است (هر جفت را جداگانه و طبق تقاضا لود می‌کنیم،
    نه همه را همزمان).
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import requests
import time

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

BINANCE_BASE = "https://api.binance.com"
TWELVEDATA_BASE = "https://api.twelvedata.com"

# ---------------------------------------------------------------------------
# لیست ۱۰۰ جفت‌ارز فارکس (میجر + مینور + اگزاتیک پرمعامله)
# ---------------------------------------------------------------------------
FOREX_MAJORS = [
    "EUR/USD", "USD/JPY", "GBP/USD", "USD/CHF", "AUD/USD",
    "USD/CAD", "NZD/USD",
]
FOREX_MINORS = [
    "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/AUD", "EUR/CAD", "EUR/NZD",
    "GBP/JPY", "GBP/CHF", "GBP/AUD", "GBP/CAD", "GBP/NZD",
    "AUD/JPY", "AUD/CHF", "AUD/CAD", "AUD/NZD",
    "CAD/JPY", "CAD/CHF", "NZD/JPY", "NZD/CHF", "CHF/JPY",
]
FOREX_EXOTICS = [
    "USD/TRY", "USD/ZAR", "USD/MXN", "USD/SEK", "USD/NOK", "USD/DKK",
    "USD/SGD", "USD/HKD", "USD/THB", "USD/PLN", "USD/HUF", "USD/CZK",
    "USD/ILS", "USD/CNH", "USD/INR", "USD/RUB", "USD/BRL", "USD/IDR",
    "USD/KRW", "USD/PHP", "USD/AED", "USD/SAR", "USD/RON", "USD/CLP",
    "EUR/TRY", "EUR/ZAR", "EUR/MXN", "EUR/SEK", "EUR/NOK", "EUR/PLN",
    "EUR/HUF", "EUR/CZK", "EUR/SGD", "EUR/HKD",
    "GBP/ZAR", "GBP/SGD", "GBP/TRY",
    "AUD/SGD", "AUD/HKD",
    "CHF/ZAR", "CHF/SGD",
    "SGD/JPY", "TRY/JPY", "ZAR/JPY", "MXN/JPY",
    "NOK/SEK", "SEK/JPY", "DKK/NOK",
    "CNH/JPY", "HKD/JPY",
]
# تا رسیدن به ۱۰۰ جفت، ترکیب‌های بیشتری اضافه می‌کنیم
FOREX_EXTRA = [
    "EUR/DKK", "EUR/RON", "EUR/ILS", "EUR/THB",
    "GBP/DKK", "GBP/NOK", "GBP/SEK", "GBP/PLN", "GBP/HKD",
    "AUD/ZAR", "AUD/TRY", "AUD/SEK", "AUD/NOK",
    "CAD/SGD", "CAD/ZAR", "CAD/MXN",
    "NZD/SGD", "NZD/CAD",
    "USD/VND", "USD/PKR", "USD/BDT", "USD/EGP", "USD/NGN", "USD/COP",
    "USD/PEN", "USD/ARS", "USD/KWD", "USD/QAR", "USD/BHD", "USD/JOD",
]

FOREX_PAIRS = list(dict.fromkeys(
    FOREX_MAJORS + FOREX_MINORS + FOREX_EXOTICS + FOREX_EXTRA
))[:100]

# کش سادهٔ حافظه‌ای برای symbol list کریپتو (چون exchangeInfo سنگین است)
_crypto_cache = {"ts": 0, "data": []}
CRYPTO_CACHE_TTL = 300  # 5 دقیقه


@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


# ---------------------------------------------------------------------------
# CRYPTO — Binance (بدون نیاز به API Key)
# ---------------------------------------------------------------------------
@app.route("/api/crypto/symbols")
def crypto_symbols():
    """۱۰۰ کوین برتر بر اساس حجم معاملهٔ ۲۴ ساعته (جفت با USDT)."""
    now = time.time()
    if now - _crypto_cache["ts"] < CRYPTO_CACHE_TTL and _crypto_cache["data"]:
        return jsonify(_crypto_cache["data"])

    try:
        r = requests.get(f"{BINANCE_BASE}/api/v3/ticker/24hr", timeout=10)
        r.raise_for_status()
        tickers = r.json()
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    usdt_pairs = [
        t for t in tickers
        if t["symbol"].endswith("USDT")
        and not any(x in t["symbol"] for x in ["UP", "DOWN", "BULL", "BEAR"])
    ]
    usdt_pairs.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)
    top100 = usdt_pairs[:100]

    result = [
        {
            "symbol": t["symbol"],
            "base": t["symbol"].replace("USDT", ""),
            "price": float(t["lastPrice"]),
            "changePercent": float(t["priceChangePercent"]),
            "volume": float(t["quoteVolume"]),
        }
        for t in top100
    ]
    _crypto_cache["ts"] = now
    _crypto_cache["data"] = result
    return jsonify(result)


@app.route("/api/crypto/klines")
def crypto_klines():
    symbol = request.args.get("symbol", "BTCUSDT").upper()
    interval = request.args.get("interval", "1h")
    limit = int(request.args.get("limit", 500))

    try:
        r = requests.get(
            f"{BINANCE_BASE}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=10,
        )
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    candles = [
        {
            "time": int(k[0] / 1000),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in raw
    ]
    return jsonify(candles)


# ---------------------------------------------------------------------------
# FOREX — TwelveData (نیاز به API Key رایگان کاربر)
# ---------------------------------------------------------------------------
@app.route("/api/forex/symbols")
def forex_symbols():
    return jsonify([{"symbol": p, "base": p.split("/")[0]} for p in FOREX_PAIRS])


@app.route("/api/forex/klines")
def forex_klines():
    symbol = request.args.get("symbol", "EUR/USD")
    interval = request.args.get("interval", "1h")
    outputsize = request.args.get("outputsize", 500)
    api_key = request.args.get("apikey", "")

    if not api_key:
        return jsonify({"error": "نیاز به API Key رایگان از twelvedata.com دارید. آن را در تنظیمات (⚙) وارد کنید."}), 400

    try:
        r = requests.get(
            f"{TWELVEDATA_BASE}/time_series",
            params={
                "symbol": symbol,
                "interval": interval,
                "outputsize": outputsize,
                "apikey": api_key,
                "order": "ASC",
            },
            timeout=10,
        )
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    if raw.get("status") == "error":
        return jsonify({"error": raw.get("message", "خطای نامشخص از TwelveData")}), 400

    values = raw.get("values", [])
    candles = [
        {
            "time": int(time.mktime(time.strptime(v["datetime"][:19], "%Y-%m-%d %H:%M:%S"))
                        if len(v["datetime"]) > 10 else
                        time.mktime(time.strptime(v["datetime"], "%Y-%m-%d"))),
            "open": float(v["open"]),
            "high": float(v["high"]),
            "low": float(v["low"]),
            "close": float(v["close"]),
        }
        for v in values
    ]
    return jsonify(candles)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
