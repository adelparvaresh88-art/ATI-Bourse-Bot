# ============================================================
# ATI BOURSE BOT V2.6 - DATA RESCUE
# Iran Stock Market TOP5 Scanner
# GitHub Actions / Telegram
# REAL TRADING = OFF
# ============================================================

import os
import re
import json
import time
import math
import requests
from datetime import datetime, timezone

# ============================================================
# CONFIG
# ============================================================

VERSION = "ATI-BOURSE-V2.6-DATA-RESCUE"

REAL_TRADING = False

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 10

MAX_RETRIES = 2
RETRY_DELAY = 1.5

MIN_VALID_ROWS = 5
TOP_N = 5

# ============================================================
# URLS
# ============================================================

SOURCE_URLS = {

    # SOURCE 1
    "TSETMC CDN": [
        "https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch"
    ],

    # SOURCE 2
    "TSETMC CDN MIRROR": [
        "https://cdn10.tsetmc.com/api/ClosingPrice/GetMarketWatch"
    ],

    # SOURCE 3
    "TSETMC MARKET MAP": [
        "https://cdn.tsetmc.com/api/ClosingPrice/GetMarketMap"
    ],

    # SOURCE 4
    "TSETMC MARKET OVERVIEW": [
        "https://cdn.tsetmc.com/api/MarketData/GetMarketOverview/0"
    ],

    # SOURCE 5
    "TSE WEBGW": [
        "https://webgw.tse.ir/InstrumentProvider/api/v1/MarketWatch/MarketWatchCash/fa"
    ],

    # SOURCE 6
    "OLD TSETMC HTTPS": [
        "https://old.tsetmc.com/tsev2/data/MarketWatchInit.aspx?h=0&r=0"
    ],

    # SOURCE 7
    "OLD TSETMC HTTP": [
        "http://old.tsetmc.com/tsev2/data/MarketWatchInit.aspx?h=0&r=0"
    ],

    # SOURCE 8
    "TSETMC PLUS": [
        "https://old.tsetmc.com/tsev2/excel/MarketWatchPlus.aspx?d=0"
    ],
}

# ============================================================
# HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "application/json,text/plain,text/csv,"
        "application/vnd.ms-excel,*/*"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Referer": "https://tsetmc.com/",
    "Origin": "https://tsetmc.com",
}

# ============================================================
# SESSION
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)

# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secrets are missing.")
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

        print("Telegram error:", response.status_code, response.text[:300])
        return False

    except Exception as e:
        print("Telegram exception:", e)
        return False


# ============================================================
# HELPERS
# ============================================================

def now_utc():

    return datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def safe_float(value, default=0.0):

    if value is None:
        return default

    try:

        if isinstance(value, bool):
            return default

        if isinstance(value, (int, float)):
            if math.isnan(value) or math.isinf(value):
                return default
            return float(value)

        text = str(value).strip()

        if not text:
            return default

        text = text.replace(",", "")
        text = text.replace("٬", "")
        text = text.replace("٫", ".")

        return float(text)

    except Exception:
        return default


def safe_int(value, default=0):

    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return default


def clean_text(value):

    if value is None:
        return ""

    return str(value).strip()


def first_value(row, keys, default=None):

    if not isinstance(row, dict):
        return default

    for key in keys:

        if key in row:

            value = row[key]

            if value is not None and value != "":
                return value

    return default


def find_list_recursive(obj):

    """
    Finds the largest list of dictionaries inside arbitrary JSON.
    """

    candidates = []

    def walk(value):

        if isinstance(value, list):

            dict_items = [
                x for x in value
                if isinstance(x, dict)
            ]

            if dict_items:
                candidates.append(dict_items)

            for item in value:
                walk(item)

        elif isinstance(value, dict):

            for child in value.values():
                walk(child)

    walk(obj)

    if not candidates:
        return []

    return max(candidates, key=len)


# ============================================================
# HTTP REQUEST WITH RETRY
# ============================================================

def request_url(url):

    last_error = "UNKNOWN"

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            response = session.get(
                url,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                allow_redirects=True
            )

            status = response.status_code

            if status == 200:

                if not response.content:
                    last_error = "EMPTY RESPONSE"

                else:
                    return response

            elif status in (403, 429):

                last_error = f"HTTP {status}"

                time.sleep(RETRY_DELAY * attempt)

            elif status in (500, 502, 503, 504):

                last_error = f"HTTP {status}"

                time.sleep(RETRY_DELAY * attempt)

            else:

                last_error = f"HTTP {status}"

        except requests.exceptions.ConnectTimeout:

            last_error = "CONNECT TIMEOUT"

        except requests.exceptions.ReadTimeout:

            last_error = "READ TIMEOUT"

        except requests.exceptions.Timeout:

            last_error = "TIMEOUT"

        except requests.exceptions.ConnectionError as e:

            last_error = "CONNECTION ERROR"

        except Exception as e:

            last_error = f"{type(e).__name__}: {str(e)[:120]}"

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY * attempt)

    return None, last_error


# ============================================================
# SOURCE 1/2 - JSON MARKET WATCH
# ============================================================

def get_json_market_watch(source_name, urls):

    for url in urls:

        result = request_url(url)

        if isinstance(result, tuple):
            response = None
            error = result[1]
        else:
            response = result
            error = None

        if response is None:
            continue

        try:

            data = response.json()

        except Exception:

            try:
                data = json.loads(response.text)
            except Exception:
                continue

        rows = find_list_recursive(data)

        if len(rows) >= MIN_VALID_ROWS:

            return rows, (
                f"SUCCESS / HTTP {response.status_code} / "
                f"{len(rows)} rows / {url}"
            )

    return [], "FAILED"


# ============================================================
# SOURCE 3 - MARKET MAP
# ============================================================

def get_market_map():

    urls = SOURCE_URLS["TSETMC MARKET MAP"]

    for url in urls:

        result = request_url(url)

        if isinstance(result, tuple):
            continue

        response = result

        try:
            data = response.json()
        except Exception:
            continue

        rows = find_list_recursive(data)

        if len(rows) >= MIN_VALID_ROWS:

            return rows, (
                f"SUCCESS / HTTP {response.status_code} / "
                f"{len(rows)} rows"
            )

    return [], "FAILED"


# ============================================================
# SOURCE 4 - MARKET OVERVIEW
# ============================================================

def get_market_overview():

    urls = SOURCE_URLS["TSETMC MARKET OVERVIEW"]

    for url in urls:

        result = request_url(url)

        if isinstance(result, tuple):
            continue

        response = result

        try:
            data = response.json()
        except Exception:
            continue

        rows = find_list_recursive(data)

        if rows:

            return rows, (
                f"SUCCESS / HTTP {response.status_code} / "
                f"{len(rows)} rows"
            )

    return [], "FAILED"


# ============================================================
# SOURCE 5 - WEBGW
# ============================================================

def get_webgw():

    urls = SOURCE_URLS["TSE WEBGW"]

    for url in urls:

        result = request_url(url)

        if isinstance(result, tuple):
            continue

        response = result

        try:

            data = response.json()

        except Exception:

            try:
                data = json.loads(response.text)
            except Exception:
                continue

        rows = find_list_recursive(data)

        if len(rows) >= MIN_VALID_ROWS:

            return rows, (
                f"SUCCESS / HTTP {response.status_code} / "
                f"{len(rows)} rows"
            )

    return [], "FAILED"


# ============================================================
# OLD TSETMC PARSER
# ============================================================

def parse_old_market_watch(text):

    rows = []

    if not text:
        return rows

    text = text.strip()

    # Common separators
    records = re.split(r"\r?\n|;", text)

    for record in records:

        record = record.strip()

        if not record:
            continue

        parts = record.split("@")

        if len(parts) < 5:
            continue

        rows.append({
            "raw_parts": parts
        })

    return rows


def get_old_tsetmc():

    all_urls = (
        SOURCE_URLS["OLD TSETMC HTTPS"] +
        SOURCE_URLS["OLD TSETMC HTTP"]
    )

    for url in all_urls:

        result = request_url(url)

        if isinstance(result, tuple):
            continue

        response = result

        rows = parse_old_market_watch(response.text)

        if len(rows) >= MIN_VALID_ROWS:

            return rows, (
                f"SUCCESS / HTTP {response.status_code} / "
                f"{len(rows)} rows"
            )

    return [], "FAILED"


# ============================================================
# MARKETWATCH PLUS
# ============================================================

def parse_plus(text):

    rows = []

    if not text:
        return rows

    lines = re.split(r"\r?\n", text)

    for line in lines:

        line = line.strip()

        if not line:
            continue

        parts = re.split(r"[,;\t]", line)

        if len(parts) >= 5:

            rows.append({
                "raw_parts": parts
            })

    return rows


def get_marketwatch_plus():

    urls = SOURCE_URLS["TSETMC PLUS"]

    for url in urls:

        result = request_url(url)

        if isinstance(result, tuple):
            continue

        response = result

        rows = parse_plus(response.text)

        if len(rows) >= MIN_VALID_ROWS:

            return rows, (
                f"SUCCESS / HTTP {response.status_code} / "
                f"{len(rows)} rows"
            )

    return [], "FAILED"


# ============================================================
# NORMALIZE JSON ROW
# ============================================================

def normalize_json_row(row):

    if not isinstance(row, dict):
        return None

    symbol = first_value(
        row,
        [
            "lVal18AFC",
            "lVal18",
            "symbol",
            "symbolName",
            "shortName",
            "insName",
            "name",
            "lval18"
        ]
    )

    name = first_value(
        row,
        [
            "lVal30",
            "name",
            "fullName",
            "insName"
        ],
        ""
    )

    price = first_value(
        row,
        [
            "pl",
            "pDrCotVal",
            "last",
            "lastPrice",
            "priceLast",
            "currentPrice"
        ]
    )

    close = first_value(
        row,
        [
            "pc",
            "pClosing",
            "close",
            "closingPrice"
        ]
    )

    yesterday = first_value(
        row,
        [
            "py",
            "priceYesterday",
            "yesterday",
            "previousClose"
        ]
    )

    volume = first_value(
        row,
        [
            "qTotTran5J",
            "volume",
            "volumeToday",
            "totalVolume"
        ]
    )

    trades = first_value(
        row,
        [
            "zTotTran",
            "count",
            "tradeCount",
            "trades"
        ]
    )

    value = first_value(
        row,
        [
            "qTotCap",
            "value",
            "tradeValue",
            "totalValue"
        ]
    )

    if not symbol:
        return None

    price = safe_float(price)

    if price <= 0:
        price = safe_float(close)

    if price <= 0:
        return None

    close = safe_float(close)

    if close <= 0:
        close = price

    yesterday = safe_float(yesterday)

    if yesterday <= 0:
        yesterday = close

    volume = safe_float(volume)
    trades = safe_float(trades)
    value = safe_float(value)

    change = 0.0

    if yesterday > 0:
        change = ((price - yesterday) / yesterday) * 100

    return {
        "symbol": clean_text(symbol),
        "name": clean_text(name),
        "price": price,
        "close": close,
        "yesterday": yesterday,
        "change": change,
        "volume": volume,
        "trades": trades,
        "value": value,
    }


# ============================================================
# NORMALIZE OLD ROW
# ============================================================

def normalize_old_row(row):

    if not isinstance(row, dict):
        return None

    parts = row.get("raw_parts", [])

    if len(parts) < 5:
        return None

    # Old TSETMC format differs between versions.
    # Try to detect useful numeric fields.

    text_parts = [
        clean_text(x)
        for x in parts
    ]

    symbol = ""

    for item in text_parts[:10]:

        if re.search(r"[\u0600-\u06FF]", item):

            if 1 <= len(item) <= 30:

                symbol = item
                break

    if not symbol:
        return None

    numbers = []

    for item in text_parts:

        value = safe_float(item, None)

        if value is not None:
            numbers.append(value)

    if not numbers:
        return None

    # Heuristic extraction
    price = 0
    yesterday = 0
    volume = 0
    trades = 0
    value = 0

    # Prefer realistic price range
    for n in numbers:

        if 1 <= n <= 100000000:

            if price == 0:
                price = n

    if price <= 0:
        return None

    for n in numbers:

        if n > 100000:
            volume = max(volume, n)

        if 20 <= n <= 100000:
            if n != price:
                yesterday = n

        if 1 <= n <= 10000:
            trades = max(trades, n)

    value = price * volume

    if yesterday <= 0:
        yesterday = price

    change = 0.0

    if yesterday > 0:
        change = ((price - yesterday) / yesterday) * 100

    return {
        "symbol": symbol,
        "name": "",
        "price": price,
        "close": price,
        "yesterday": yesterday,
        "change": change,
        "volume": volume,
        "trades": trades,
        "value": value,
    }


# ============================================================
# NORMALIZE ANY SOURCE
# ============================================================

def normalize_rows(rows):

    normalized = []

    for row in rows:

        item = None

        if isinstance(row, dict):

            if "raw_parts" in row:
                item = normalize_old_row(row)
            else:
                item = normalize_json_row(row)

        if item:

            symbol = item["symbol"]

            # Remove index / invalid rows
            if not symbol:
                continue

            if len(symbol) > 40:
                continue

            # Avoid obvious non-stock rows
            bad_names = [
                "شاخص",
                "INDEX",
                "TEDPIX",
            ]

            if any(
                bad.lower() in symbol.lower()
                for bad in bad_names
            ):
                continue

            normalized.append(item)

    # Deduplicate
    unique = {}

    for item in normalized:

        symbol = item["symbol"]

        if symbol not in unique:
            unique[symbol] = item

    return list(unique.values())


# ============================================================
# SCORE
# ============================================================

def score_stock(stock):

    score = 0

    change = stock["change"]
    volume = stock["volume"]
    trades = stock["trades"]
    value = stock["value"]

    # PRICE MOMENTUM
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

    # VOLUME
    if volume >= 5_000_000:
        score += 25

    elif volume >= 1_000_000:
        score += 20

    elif volume >= 300_000:
        score += 15

    elif volume >= 100_000:
        score += 10

    # TRADES
    if trades >= 1000:
        score += 20

    elif trades >= 500:
        score += 15

    elif trades >= 200:
        score += 10

    elif trades >= 50:
        score += 5

    # VALUE
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

    if not rows:
        return []

    scored = []

    for row in rows:

        try:
            scored.append(
                score_stock(row)
            )
        except Exception:
            pass

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
# PRICE LEVELS
# ============================================================

def make_levels(price):

    entry = price

    stop = price * 0.97

    target1 = price * 1.05

    target2 = price * 1.08

    return {
        "entry": entry,
        "stop": stop,
        "target1": target1,
        "target2": target2,
    }


# ============================================================
# FORMAT NUMBER
# ============================================================

def fmt(value):

    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"

    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"

    if value >= 1_000:
        return f"{value / 1_000:.2f}K"

    if value >= 1:
        return f"{value:.2f}"

    return f"{value:.6f}"


# ============================================================
# SEND TOP5
# ============================================================

def send_top5(top5, source_name):

    if not top5:

        telegram_send(
            "❌ ATI BOURSE ERROR\n\n"
            "داده دریافت شد اما سهم قابل‌قبولی "
            "برای انتخاب TOP5 پیدا نشد.\n\n"
            f"📡 SOURCE: {source_name}\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

        return

    header = (
        "🚀 ATI BOURSE TOP5\n"
        f"⚡ {VERSION}\n"
        "📊 بورس و فرابورس ایران\n"
        f"📡 DATA: {source_name}\n"
        "🔒 REAL TRADING: OFF\n"
        f"🕐 {now_utc()}\n"
    )

    telegram_send(header)

    for index, stock in enumerate(top5, 1):

        levels = make_levels(
            stock["price"]
        )

        reason_parts = []

        if stock["change"] > 0:
            reason_parts.append(
                f"رشد {stock['change']:.2f}%"
            )

        if stock["volume"] >= 1_000_000:
            reason_parts.append("حجم بالا")

        if stock["trades"] >= 500:
            reason_parts.append("معاملات قوی")

        if stock["value"] >= 10_000_000_000:
            reason_parts.append("ارزش معاملات بالا")

        reason = " + ".join(reason_parts)

        if not reason:
            reason = "امتیاز کلی بازار"

        message = (
            f"#{index} 🟢 {stock['symbol']}\n"
            f"📌 {stock['name']}\n\n"

            f"⭐ SCORE: {stock['score']}\n"
            f"📈 CHANGE: {stock['change']:.2f}%\n"
            f"📊 VOLUME: {fmt(stock['volume'])}\n"
            f"🔄 TRADES: {fmt(stock['trades'])}\n"
            f"💰 VALUE: {fmt(stock['value'])}\n\n"

            f"🎯 ENTRY: {fmt(levels['entry'])}\n"
            f"🛑 STOP: {fmt(levels['stop'])}\n"
            f"🎯 TP1 +5%: {fmt(levels['target1'])}\n"
            f"🚀 TP2 +8%: {fmt(levels['target2'])}\n\n"

            f"🧠 دلیل انتخاب:\n"
            f"{reason}\n\n"

            "⚠️ این فقط سیگنال تحلیلی است.\n"
            "🚫 معامله واقعی انجام نمی‌شود."
        )

        telegram_send(message)

        time.sleep(0.5)


# ============================================================
# SOURCE TEST
# ============================================================

def try_source(source_name):

    print(
        f"\n========== {source_name} =========="
    )

    # --------------------------------------------------------
    # JSON MARKET WATCH
    # --------------------------------------------------------

    if source_name == "TSETMC CDN":

        rows, status = get_json_market_watch(
            source_name,
            SOURCE_URLS[source_name]
        )

        if rows:
            return rows, status

        return [], "TIMEOUT / FAILED"

    # --------------------------------------------------------

    if source_name == "TSETMC CDN MIRROR":

        rows, status = get_json_market_watch(
            source_name,
            SOURCE_URLS[source_name]
        )

        if rows:
            return rows, status

        return [], "TIMEOUT / FAILED"

    # --------------------------------------------------------

    if source_name == "TSETMC MARKET MAP":

        rows, status = get_market_map()

        if rows:
            return rows, status

        return [], "TIMEOUT / FAILED"

    # --------------------------------------------------------

    if source_name == "TSETMC MARKET OVERVIEW":

        rows, status = get_market_overview()

        if rows:
            return rows, status

        return [], "TIMEOUT / FAILED"

    # --------------------------------------------------------

    if source_name == "TSE WEBGW":

        rows, status = get_webgw()

        if rows:
            return rows, status

        return [], "TIMEOUT / FAILED"

    # --------------------------------------------------------

    if source_name in (
        "OLD TSETMC HTTPS",
        "OLD TSETMC HTTP"
    ):

        rows, status = get_old_tsetmc()

        if rows:
            return rows, status

        return [], "TIMEOUT / FAILED"

    # --------------------------------------------------------

    if source_name == "TSETMC PLUS":

        rows, status = get_marketwatch_plus()

        if rows:
            return rows, status

        return [], "TIMEOUT / FAILED"

    return [], "UNKNOWN SOURCE"


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        f"ATI BOURSE {VERSION}"
    )

    print(
        "REAL TRADING:",
        REAL_TRADING
    )

    telegram_send(
        "💓 ATI BOURSE ALIVE\n"
        f"⚡ {VERSION}\n"
        "📊 بورس و فرابورس ایران\n"
        "🔒 REAL TRADING: OFF\n"
        "🎯 هدف: پیدا کردن ۵ سهم برتر\n"
        "🔎 شروع DATA RESCUE..."
    )

    diagnostic = []

    source_order = [
        "TSETMC CDN",
        "TSETMC CDN MIRROR",
        "TSETMC MARKET MAP",
        "TSETMC MARKET OVERVIEW",
        "TSE WEBGW",
        "OLD TSETMC HTTPS",
        "OLD TSETMC HTTP",
        "TSETMC PLUS",
    ]

    for number, source_name in enumerate(
        source_order,
        1
    ):

        telegram_send(
            f"🔎 SOURCE {number}\n"
            f"📡 {source_name}\n"
            "⏳ در حال دریافت داده..."
        )

        try:

            rows, status = try_source(
                source_name
            )

        except Exception as e:

            rows = []

            status = (
                f"ERROR: "
                f"{type(e).__name__}: "
                f"{str(e)[:150]}"
            )

        if rows:

            normalized = normalize_rows(
                rows
            )

            print(
                source_name,
                "RAW:",
                len(rows),
                "NORMALIZED:",
                len(normalized)
            )

            if len(normalized) >= MIN_VALID_ROWS:

                telegram_send(
                    f"✅ SOURCE {number} SUCCESS\n"
                    f"📡 {source_name}\n"
                    f"📊 RAW: {len(rows)}\n"
                    f"📈 VALID: {len(normalized)}\n"
                    "➡️ شروع انتخاب TOP5..."
                )

                top5 = find_top5(
                    normalized
                )

                send_top5(
                    top5,
                    source_name
                )

                return

            else:

                diagnostic.append(
                    f"{number}️⃣ {source_name}: "
                    f"DATA BUT INVALID "
                    f"({len(normalized)} valid)"
                )

                telegram_send(
                    f"⚠️ SOURCE {number} DATA دریافت شد\n"
                    f"📡 {source_name}\n"
                    f"📊 RAW: {len(rows)}\n"
                    f"❌ VALID: {len(normalized)}\n"
                    "➡️ رفتن به منبع بعدی..."
                )

        else:

            diagnostic.append(
                f"{number}️⃣ {source_name}: "
                f"{status}"
            )

            telegram_send(
                f"❌ SOURCE {number} FAILED\n"
                f"📡 {source_name}\n"
                f"⚠️ {status}\n"
                "➡️ رفتن به SOURCE بعدی..."
            )

    # ========================================================
    # ALL FAILED
    # ========================================================

    diagnostic_text = "\n".join(
        diagnostic
    )

    final_message = (
        "❌ ATI BOURSE ERROR\n\n"
        "تمام منابع داده شکست خوردند.\n\n"
        "📋 DIAGNOSTIC:\n"
        f"{diagnostic_text}\n\n"
        "🚫 هیچ سهمی انتخاب نشد.\n"
        "🔒 REAL TRADING: OFF\n"
        f"🕐 {now_utc()}\n\n"
        "💡 احتمال زیاد GitHub Actions "
        "به سرویس‌های بازار TSETMC/TSE "
        "دسترسی شبکه‌ای ندارد."
    )

    telegram_send(
        final_message
    )

    print(final_message)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
