# ============================================================
# ATI BOURSE BOT V2.7 - REST DATA RESCUE
# Iran Stock Market TOP5 Scanner
# GitHub Actions + Telegram
# REAL TRADING = OFF
# ============================================================

import os
import json
import time
import math
import requests
from datetime import datetime, timezone

# ============================================================
# CONFIG
# ============================================================

VERSION = "ATI-BOURSE-V2.7-REST-DATA-RESCUE"

REAL_TRADING = False

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN", ""
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID", ""
).strip()

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 12

MAX_RETRIES = 2
RETRY_DELAY = 1.5

MIN_VALID_ROWS = 5
TOP_N = 5

# ============================================================
# CURRENT REST ENDPOINTS
# ============================================================

MARKET_WATCH_URL = (
    "https://cdn.tsetmc.com/api/ClosingPrice/"
    "GetMarketWatch"
    "?market=0"
    "&paperTypes[0]=1"
    "&paperTypes[1]=2"
    "&paperTypes[2]=3"
    "&paperTypes[3]=4"
    "&paperTypes[4]=5"
    "&paperTypes[5]=6"
    "&paperTypes[6]=7"
    "&paperTypes[7]=8"
    "&paperTypes[8]=9"
    "&withBestLimits=false"
    "&hEven=0"
    "&RefID=0"
)

MARKET_OVERVIEW_URL = (
    "https://cdn.tsetmc.com/api/MarketData/"
    "GetMarketOverview/0"
)

# Secondary endpoint
MARKET_WATCH_SIMPLE_URL = (
    "https://cdn.tsetmc.com/api/ClosingPrice/"
    "GetMarketWatch"
)

# ============================================================
# HTTP HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),

    "Accept": (
        "application/json,text/plain,text/csv,"
        "text/html,*/*"
    ),

    "Accept-Language": (
        "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7"
    ),

    "Referer": "https://www.tsetmc.com/",
    "Origin": "https://www.tsetmc.com",

    "Connection": "keep-alive",
}

session = requests.Session()
session.headers.update(HEADERS)

# ============================================================
# TIME
# ============================================================

def now_utc():

    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message):

    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN missing")
        print(message)
        return False

    if not TELEGRAM_CHAT_ID:
        print("TELEGRAM_CHAT_ID missing")
        print(message)
        return False

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=(5, 10)
        )

        if response.ok:
            return True

        print(
            "Telegram HTTP error:",
            response.status_code,
            response.text[:300]
        )

    except Exception as e:

        print(
            "Telegram error:",
            type(e).__name__,
            str(e)
        )

    return False


# ============================================================
# NUMBER HELPERS
# ============================================================

def to_float(value, default=0.0):

    if value is None:
        return default

    try:

        if isinstance(value, bool):
            return default

        if isinstance(
            value,
            (int, float)
        ):

            if math.isnan(value):
                return default

            if math.isinf(value):
                return default

            return float(value)

        text = str(value).strip()

        if not text:
            return default

        text = (
            text
            .replace(",", "")
            .replace("٬", "")
            .replace("٫", ".")
        )

        return float(text)

    except Exception:
        return default


def to_int(value, default=0):

    try:
        return int(
            float(
                str(value)
                .replace(",", "")
                .strip()
            )
        )

    except Exception:
        return default


# ============================================================
# HTTP REQUEST
# ============================================================

def http_get(url):

    last_error = "UNKNOWN"

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            response = session.get(
                url,
                timeout=(
                    CONNECT_TIMEOUT,
                    READ_TIMEOUT
                ),
                allow_redirects=True
            )

            if response.status_code == 200:

                if not response.content:

                    last_error = (
                        "HTTP 200 / EMPTY BODY"
                    )

                else:

                    return response, "SUCCESS"

            elif response.status_code in (
                429,
                500,
                502,
                503,
                504
            ):

                last_error = (
                    f"HTTP {response.status_code}"
                )

            else:

                last_error = (
                    f"HTTP {response.status_code}"
                )

        except requests.exceptions.ConnectTimeout:

            last_error = "CONNECT TIMEOUT"

        except requests.exceptions.ReadTimeout:

            last_error = "READ TIMEOUT"

        except requests.exceptions.Timeout:

            last_error = "TIMEOUT"

        except requests.exceptions.ConnectionError:

            last_error = "CONNECTION ERROR"

        except Exception as e:

            last_error = (
                f"{type(e).__name__}: "
                f"{str(e)[:120]}"
            )

        if attempt < MAX_RETRIES:

            time.sleep(
                RETRY_DELAY * attempt
            )

    return None, last_error


# ============================================================
# JSON EXTRACTION
# ============================================================

def unwrap_json(data):

    if not isinstance(data, dict):
        return []

    # Known TSETMC envelope
    known_keys = [
        "marketwatch",
        "marketWatch",
        "marketWatchDto",
        "data",
        "result",
        "items",
    ]

    for key in known_keys:

        value = data.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):

            for nested_key in known_keys:

                nested = value.get(
                    nested_key
                )

                if isinstance(
                    nested,
                    list
                ):
                    return nested

    # Search recursively
    found = []

    def walk(obj):

        nonlocal found

        if isinstance(obj, list):

            dictionaries = [
                x for x in obj
                if isinstance(x, dict)
            ]

            if len(dictionaries) > len(found):
                found = dictionaries

            for x in obj:
                walk(x)

        elif isinstance(obj, dict):

            for value in obj.values():
                walk(value)

    walk(data)

    return found


# ============================================================
# SOURCE 1 - FULL MARKET WATCH
# ============================================================

def get_market_watch():

    print(
        "Trying TSETMC REST MarketWatch..."
    )

    response, status = http_get(
        MARKET_WATCH_URL
    )

    if response is None:

        return [], status

    try:

        data = response.json()

    except Exception:

        return [], "INVALID JSON"

    rows = unwrap_json(data)

    if not rows:

        return [], "JSON OK / NO ROWS"

    return rows, (
        f"SUCCESS / HTTP "
        f"{response.status_code} / "
        f"{len(rows)} RAW ROWS"
    )


# ============================================================
# SOURCE 2 - SIMPLE MARKET WATCH
# ============================================================

def get_market_watch_simple():

    response, status = http_get(
        MARKET_WATCH_SIMPLE_URL
    )

    if response is None:

        return [], status

    try:

        data = response.json()

    except Exception:

        return [], "INVALID JSON"

    rows = unwrap_json(data)

    if not rows:

        return [], "JSON OK / NO ROWS"

    return rows, (
        f"SUCCESS / HTTP "
        f"{response.status_code} / "
        f"{len(rows)} RAW ROWS"
    )


# ============================================================
# SOURCE 3 - MARKET OVERVIEW
# ============================================================

def get_market_overview():

    response, status = http_get(
        MARKET_OVERVIEW_URL
    )

    if response is None:

        return [], status

    try:

        data = response.json()

    except Exception:

        return [], "INVALID JSON"

    rows = unwrap_json(data)

    return rows, (
        f"HTTP {response.status_code} / "
        f"{len(rows)} ROWS"
    )


# ============================================================
# FIND VALUE
# ============================================================

def find_value(
    row,
    names,
    default=None
):

    if not isinstance(row, dict):
        return default

    for name in names:

        if name in row:

            value = row[name]

            if value is not None:
                return value

    return default


# ============================================================
# NORMALIZE MARKET WATCH
# ============================================================

def normalize_row(row):

    if not isinstance(row, dict):
        return None

    symbol = find_value(
        row,
        [
            "lVal18AFC",
            "lVal18",
            "symbol",
            "symbolName",
            "shortName",
            "insName",
        ],
        ""
    )

    name = find_value(
        row,
        [
            "lVal30",
            "name",
            "fullName",
            "companyName",
            "insName",
        ],
        ""
    )

    last_price = find_value(
        row,
        [
            "pl",
            "pDrCotVal",
            "lastPrice",
            "priceLast",
            "last",
        ],
        0
    )

    close_price = find_value(
        row,
        [
            "pc",
            "pClosing",
            "closingPrice",
            "close",
        ],
        0
    )

    yesterday = find_value(
        row,
        [
            "py",
            "priceYesterday",
            "previousClose",
        ],
        0
    )

    volume = find_value(
        row,
        [
            "qTotTran5J",
            "volume",
            "totalVolume",
            "volumeToday",
        ],
        0
    )

    trades = find_value(
        row,
        [
            "zTotTran",
            "tradeCount",
            "count",
            "trades",
        ],
        0
    )

    value = find_value(
        row,
        [
            "qTotCap",
            "tradeValue",
            "totalValue",
            "value",
        ],
        0
    )

    symbol = str(symbol).strip()

    if not symbol:
        return None

    price = to_float(
        last_price
    )

    if price <= 0:
        price = to_float(
            close_price
        )

    if price <= 0:
        return None

    close = to_float(
        close_price
    )

    if close <= 0:
        close = price

    py = to_float(
        yesterday
    )

    if py <= 0:
        py = close

    volume = to_float(
        volume
    )

    trades = to_float(
        trades
    )

    value = to_float(
        value
    )

    # If qTotCap is unavailable,
    # approximate trade value.
    if value <= 0 and volume > 0:

        value = (
            price * volume
        )

    change = 0.0

    if py > 0:

        change = (
            (price - py)
            / py
            * 100
        )

    return {
        "symbol": symbol,
        "name": str(name).strip(),
        "price": price,
        "close": close,
        "yesterday": py,
        "change": change,
        "volume": volume,
        "trades": trades,
        "value": value,
    }


# ============================================================
# NORMALIZE ALL
# ============================================================

def normalize_rows(rows):

    result = []

    seen = set()

    for row in rows:

        item = normalize_row(
            row
        )

        if item is None:
            continue

        symbol = item["symbol"]

        if symbol in seen:
            continue

        seen.add(symbol)

        # Remove obvious indexes
        upper = symbol.upper()

        if upper in (
            "TEDPIX",
            "INDEX",
            "شاخص"
        ):
            continue

        result.append(item)

    return result


# ============================================================
# SCORE
# ============================================================

def score_stock(stock):

    score = 0

    change = stock["change"]
    volume = stock["volume"]
    trades = stock["trades"]
    value = stock["value"]

    # ----------------------------
    # MOMENTUM
    # ----------------------------

    if change >= 3:
        score += 30

    elif change >= 2:
        score += 25

    elif change >= 1:
        score += 20

    elif change >= 0.5:
        score += 12

    elif change > 0:
        score += 5

    # ----------------------------
    # VOLUME
    # ----------------------------

    if volume >= 5_000_000:
        score += 25

    elif volume >= 1_000_000:
        score += 20

    elif volume >= 300_000:
        score += 15

    elif volume >= 100_000:
        score += 10

    # ----------------------------
    # TRADES
    # ----------------------------

    if trades >= 1000:
        score += 20

    elif trades >= 500:
        score += 15

    elif trades >= 200:
        score += 10

    elif trades >= 50:
        score += 5

    # ----------------------------
    # VALUE
    # ----------------------------

    if value >= 50_000_000_000:
        score += 25

    elif value >= 10_000_000_000:
        score += 20

    elif value >= 2_000_000_000:
        score += 15

    elif value >= 500_000_000:
        score += 10

    stock["score"] = score

    return stock


# ============================================================
# TOP 5
# ============================================================

def find_top5(rows):

    scored = []

    for row in rows:

        try:

            scored.append(
                score_stock(row)
            )

        except Exception:
            continue

    scored.sort(
        key=lambda x: (
            x["score"],
            x["change"],
            x["value"],
            x["volume"],
            x["trades"],
        ),
        reverse=True
    )

    return scored[:TOP_N]


# ============================================================
# LEVELS
# ============================================================

def make_levels(price):

    return {
        "entry": price,
        "stop": price * 0.97,
        "tp1": price * 1.05,
        "tp2": price * 1.08,
    }


# ============================================================
# FORMAT
# ============================================================

def fmt(value):

    value = float(value)

    if value >= 1_000_000_000:

        return (
            f"{value / 1_000_000_000:.2f}B"
        )

    if value >= 1_000_000:

        return (
            f"{value / 1_000_000:.2f}M"
        )

    if value >= 1_000:

        return (
            f"{value / 1_000:.2f}K"
        )

    if value >= 1:

        return f"{value:.2f}"

    return f"{value:.6f}"


# ============================================================
# SEND TOP 5
# ============================================================

def send_top5(
    top5,
    source
):

    if not top5:

        telegram_send(
            "⚠️ ATI BOURSE\n\n"
            "داده دریافت شد اما "
            "TOP5 قابل انتخاب نبود.\n\n"
            f"📡 SOURCE: {source}\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

        return

    telegram_send(
        "🚀 ATI BOURSE TOP5\n"
        f"⚡ {VERSION}\n"
        "📊 بورس و فرابورس ایران\n"
        f"📡 DATA: {source}\n"
        "🔒 REAL TRADING: OFF\n"
        f"🕐 {now_utc()}"
    )

    for index, stock in enumerate(
        top5,
        1
    ):

        levels = make_levels(
            stock["price"]
        )

        reasons = []

        if stock["change"] > 0:
            reasons.append(
                f"رشد {stock['change']:.2f}%"
            )

        if stock["volume"] >= 1_000_000:
            reasons.append(
                "حجم معاملات بالا"
            )

        if stock["trades"] >= 500:
            reasons.append(
                "تعداد معاملات مناسب"
            )

        if stock["value"] >= 10_000_000_000:
            reasons.append(
                "ارزش معاملات بالا"
            )

        reason = " + ".join(
            reasons
        )

        if not reason:
            reason = (
                "امتیاز مناسب در فیلتر بازار"
            )

        message = (
            f"#{index} 🟢 "
            f"{stock['symbol']}\n"
            f"📌 {stock['name']}\n\n"

            f"⭐ SCORE: "
            f"{stock['score']}\n"

            f"📈 CHANGE: "
            f"{stock['change']:.2f}%\n"

            f"📊 VOLUME: "
            f"{fmt(stock['volume'])}\n"

            f"🔄 TRADES: "
            f"{fmt(stock['trades'])}\n"

            f"💰 VALUE: "
            f"{fmt(stock['value'])}\n\n"

            f"🎯 ENTRY: "
            f"{fmt(levels['entry'])}\n"

            f"🛑 STOP -3%: "
            f"{fmt(levels['stop'])}\n"

            f"🎯 TP1 +5%: "
            f"{fmt(levels['tp1'])}\n"

            f"🚀 TP2 +8%: "
            f"{fmt(levels['tp2'])}\n\n"

            f"🧠 دلیل:\n"
            f"{reason}\n\n"

            "⚠️ تحلیل و پیشنهاد است.\n"
            "🚫 معامله واقعی انجام نمی‌شود."
        )

        telegram_send(
            message
        )

        time.sleep(0.5)


# ============================================================
# DIAGNOSTIC
# ============================================================

def diagnostic_message(
    diagnostics
):

    lines = []

    for index, item in enumerate(
        diagnostics,
        1
    ):

        lines.append(
            f"{index}️⃣ {item}"
        )

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "================================"
    )

    print(
        VERSION
    )

    print(
        "REAL TRADING:",
        REAL_TRADING
    )

    print(
        "TIME:",
        now_utc()
    )

    print(
        "================================"
    )

    telegram_send(
        "💓 ATI BOURSE ALIVE\n"
        f"⚡ {VERSION}\n"
        "📊 بورس و فرابورس ایران\n"
        "🔒 REAL TRADING: OFF\n"
        "🎯 هدف: پیدا کردن ۵ سهم برتر\n"
        "🌐 REST API DATA MODE\n"
        f"🕐 {now_utc()}"
    )

    diagnostics = []

    # ========================================================
    # SOURCE 1
    # ========================================================

    telegram_send(
        "🔎 SOURCE 1\n"
        "📡 TSETMC REST MarketWatch\n"
        "⏳ در حال دریافت داده..."
    )

    rows, status = (
        get_market_watch()
    )

    if rows:

        normalized = normalize_rows(
            rows
        )

        if len(normalized) >= MIN_VALID_ROWS:

            telegram_send(
                "✅ SOURCE 1 SUCCESS\n"
                "📡 TSETMC REST MarketWatch\n"
                f"📊 RAW: {len(rows)}\n"
                f"📈 VALID: {len(normalized)}\n"
                "➡️ انتخاب TOP5..."
            )

            top5 = find_top5(
                normalized
            )

            send_top5(
                top5,
                "TSETMC REST MarketWatch"
            )

            return

        diagnostics.append(
            "TSETMC REST MarketWatch: "
            f"RAW={len(rows)} / "
            f"VALID={len(normalized)}"
        )

    else:

        diagnostics.append(
            "TSETMC REST MarketWatch: "
            f"{status}"
        )

    telegram_send(
        "❌ SOURCE 1 FAILED\n"
        "📡 TSETMC REST MarketWatch\n"
        f"⚠️ {status}\n"
        "➡️ رفتن به SOURCE 2..."
    )

    # ========================================================
    # SOURCE 2
    # ========================================================

    telegram_send(
        "🔎 SOURCE 2\n"
        "📡 TSETMC REST SIMPLE\n"
        "⏳ در حال دریافت داده..."
    )

    rows, status = (
        get_market_watch_simple()
    )

    if rows:

        normalized = normalize_rows(
            rows
        )

        if len(normalized) >= MIN_VALID_ROWS:

            telegram_send(
                "✅ SOURCE 2 SUCCESS\n"
                "📡 TSETMC REST SIMPLE\n"
                f"📊 RAW: {len(rows)}\n"
                f"📈 VALID: {len(normalized)}\n"
                "➡️ انتخاب TOP5..."
            )

            top5 = find_top5(
                normalized
            )

            send_top5(
                top5,
                "TSETMC REST SIMPLE"
            )

            return

        diagnostics.append(
            "TSETMC REST SIMPLE: "
            f"RAW={len(rows)} / "
            f"VALID={len(normalized)}"
        )

    else:

        diagnostics.append(
            "TSETMC REST SIMPLE: "
            f"{status}"
        )

    telegram_send(
        "❌ SOURCE 2 FAILED\n"
        "📡 TSETMC REST SIMPLE\n"
        f"⚠️ {status}\n"
        "➡️ بررسی نهایی..."
    )

    # ========================================================
    # SOURCE 3 - OVERVIEW
    # ========================================================

    telegram_send(
        "🔎 SOURCE 3\n"
        "📡 TSETMC MARKET OVERVIEW\n"
        "⏳ بررسی اتصال REST..."
    )

    rows, status = (
        get_market_overview()
    )

    if rows:

        telegram_send(
            "⚠️ SOURCE 3 پاسخ داد\n"
            "📡 TSETMC MARKET OVERVIEW\n"
            f"📊 ROWS: {len(rows)}\n\n"
            "ℹ️ این endpoint برای TOP5 "
            "کافی نیست؛ MarketWatch لازم است."
        )

        diagnostics.append(
            "Market Overview: "
            f"reachable / {len(rows)} rows"
        )

    else:

        diagnostics.append(
            "Market Overview: "
            f"{status}"
        )

    # ========================================================
    # ALL FAILED
    # ========================================================

    final = (
        "❌ ATI BOURSE ERROR\n\n"
        "REST API نیز از GitHub Actions "
        "داده معتبر بازار دریافت نکرد.\n\n"
        "📋 DIAGNOSTIC:\n"
        f"{diagnostic_message(diagnostics)}\n\n"
        "🚫 هیچ سهمی انتخاب نشد.\n"
        "🔒 REAL TRADING: OFF\n"
        f"🕐 {now_utc()}\n\n"
        "⚠️ اگر REST MarketWatch هم "
        "TIMEOUT باشد، مشکل شبکه/IP "
        "GitHub Actions است، نه TOP5."
    )

    telegram_send(
        final
    )

    print(final)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
