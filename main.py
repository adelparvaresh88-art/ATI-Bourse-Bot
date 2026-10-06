import os
import time
from datetime import datetime, timezone

import requests


# ============================================================
# ATI BOURSE BOT V2.2
# TOP 5 STOCK SCANNER
# ============================================================

VERSION = "ATI-BOURSE-V2.2-TOP5"

REAL_TRADING = False

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CONNECT_TIMEOUT = 4
READ_TIMEOUT = 6

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "Referer": "https://www.tse.ir/",
    "Connection": "close",
}


# ============================================================
# TIME
# ============================================================

def now_utc():
    return datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(text):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM SETTINGS MISSING")
        return False

    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_TOKEN
        + "/sendMessage"
    )

    try:

        r = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
            },
            timeout=(5, 8),
        )

        if r.ok:
            print("✅ TELEGRAM SENT")
            return True

        print(
            "❌ TELEGRAM ERROR:",
            r.status_code,
            r.text[:500]
        )

    except Exception as e:

        print(
            "❌ TELEGRAM ERROR:",
            str(e)
        )

    return False


# ============================================================
# NUMBER
# ============================================================

def to_float(value):

    if value is None:
        return None

    try:

        if isinstance(value, (int, float)):
            return float(value)

        s = str(value).strip()

        if not s:
            return None

        s = s.replace(",", "")
        s = s.replace("٬", "")
        s = s.replace("،", "")

        return float(s)

    except Exception:
        return None


# ============================================================
# GET VALUE FROM DICT
# ============================================================

def get_value(row, names):

    if not isinstance(row, dict):
        return None

    lowered = {}

    for k, v in row.items():
        lowered[str(k).lower()] = v

    for name in names:

        key = name.lower()

        if key in lowered:
            return lowered[key]

    return None


# ============================================================
# TSETMC CDN
# ============================================================

def get_tsetmc_cdn():

    url = (
        "https://cdn.tsetmc.com/api/"
        "ClosingPrice/GetMarketWatch"
    )

    params = {
        "market": 0,
        "industrialGroup": "",
        "paperTypes[0]": 1,
        "paperTypes[1]": 2,
        "paperTypes[2]": 3,
        "paperTypes[3]": 4,
        "paperTypes[4]": 5,
        "paperTypes[5]": 6,
        "paperTypes[6]": 7,
        "paperTypes[7]": 8,
        "paperTypes[8]": 9,
        "showTraded": "false",
        "withBestLimits": "false",
        "hEven": 0,
        "RefID": 0,
    }

    print("🌐 SOURCE 1: TSETMC CDN")

    try:

        r = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=(
                CONNECT_TIMEOUT,
                READ_TIMEOUT,
            ),
        )

        print(
            "📡 SOURCE 1 HTTP:",
            r.status_code,
            "SIZE:",
            len(r.content)
        )

        if r.status_code != 200:
            return None

        data = r.json()

        if isinstance(data, dict):

            rows = data.get("marketwatch")

            if isinstance(rows, list) and rows:

                print(
                    "✅ SOURCE 1 SUCCESS:",
                    len(rows)
                )

                return rows

    except requests.exceptions.Timeout:

        print("⏱️ SOURCE 1 TIMEOUT")

    except Exception as e:

        print(
            "❌ SOURCE 1 ERROR:",
            str(e)
        )

    return None


# ============================================================
# OLD TSETMC
# ============================================================

def parse_old_market_watch(content):

    if not content:
        return None

    content = content.strip()

    if "@" not in content:
        return None

    parts = content.split("@")

    if len(parts) < 3:
        return None

    price_rows = parts[2]

    if not price_rows:
        return None

    result = []

    for raw in price_rows.split(";"):

        cols = raw.strip().split(",")

        if len(cols) < 15:
            continue

        symbol = (
            cols[2].strip()
            if len(cols) > 2
            else ""
        )

        name = (
            cols[3].strip()
            if len(cols) > 3
            else ""
        )

        if not symbol:
            continue

        result.append(
            {
                "ins_code": cols[0],
                "isin": cols[1],
                "symbol": symbol,
                "name": name,
                "heven": cols[4],
                "price": cols[5],
                "close": cols[6],
                "last": cols[7],
                "trades": cols[8],
                "volume": cols[9],
                "value": cols[10],
                "min": cols[11],
                "max": cols[12],
                "yesterday": cols[13],
                "eps": cols[14],
            }
        )

    return result if result else None


def get_old_market_watch():

    urls = [
        (
            "https://old.tsetmc.com/"
            "tsev2/data/MarketWatchInit.aspx?h=0&r=0"
        ),
        (
            "http://old.tsetmc.com/"
            "tsev2/data/MarketWatchInit.aspx?h=0&r=0"
        ),
        (
            "https://www.tsetmc.com/"
            "tsev2/data/MarketWatchInit.aspx?h=0&r=0"
        ),
        (
            "http://www.tsetmc.com/"
            "tsev2/data/MarketWatchInit.aspx?h=0&r=0"
        ),
    ]

    print("🌐 SOURCE 2: OLD TSETMC")

    for i, url in enumerate(urls, 1):

        try:

            print(
                f"🔁 OLD {i}/{len(urls)}"
            )

            r = requests.get(
                url,
                headers=HEADERS,
                timeout=(
                    CONNECT_TIMEOUT,
                    READ_TIMEOUT,
                ),
                allow_redirects=True,
            )

            print(
                "HTTP:",
                r.status_code,
                "SIZE:",
                len(r.content)
            )

            if r.status_code != 200:
                continue

            rows = parse_old_market_watch(
                r.text
            )

            if rows:

                print(
                    "✅ OLD TSETMC SUCCESS:",
                    len(rows)
                )

                return rows

        except requests.exceptions.Timeout:

            print(
                f"⏱️ OLD {i} TIMEOUT"
            )

        except Exception as e:

            print(
                f"❌ OLD {i} ERROR:",
                str(e)
            )

    return None


# ============================================================
# NORMALIZE CDN ROW
# ============================================================

def normalize_row(row):

    if not isinstance(row, dict):
        return None

    symbol = get_value(
        row,
        [
            "symbol",
            "l18",
            "l18name",
            "inscode",
            "insCode",
        ]
    )

    name = get_value(
        row,
        [
            "name",
            "l30",
            "l30name",
        ]
    )

    last = get_value(
        row,
        [
            "last",
            "pl",
            "lastPrice",
            "pLast",
        ]
    )

    close = get_value(
        row,
        [
            "close",
            "pc",
            "closingPrice",
            "pClosing",
        ]
    )

    yesterday = get_value(
        row,
        [
            "yesterday",
            "py",
            "yesterdayPrice",
        ]
    )

    volume = get_value(
        row,
        [
            "volume",
            "tvol",
            "totalVolume",
        ]
    )

    trades = get_value(
        row,
        [
            "trades",
            "tno",
            "numberOfTrades",
        ]
    )

    value = get_value(
        row,
        [
            "value",
            "tval",
            "tradeValue",
        ]
    )

    last = to_float(last)
    close = to_float(close)
    yesterday = to_float(yesterday)
    volume = to_float(volume)
    trades = to_float(trades)
    value = to_float(value)

    if not symbol:
        return None

    if last is None and close is None:
        return None

    price = (
        last
        if last is not None and last > 0
        else close
    )

    if price is None or price <= 0:
        return None

    if yesterday is None or yesterday <= 0:
        yesterday = close

    change = 0.0

    if yesterday and yesterday > 0:
        change = (
            (price - yesterday)
            / yesterday
        ) * 100

    return {
        "symbol": str(symbol),
        "name": str(name or symbol),
        "price": price,
        "close": close or price,
        "yesterday": yesterday,
        "change": change,
        "volume": volume or 0,
        "trades": trades or 0,
        "value": value or 0,
    }


# ============================================================
# NORMALIZE OLD ROW
# ============================================================

def normalize_old_row(row):

    if not isinstance(row, dict):
        return None

    symbol = row.get("symbol")
    name = row.get("name")

    price = to_float(
        row.get("last")
    )

    close = to_float(
        row.get("close")
    )

    yesterday = to_float(
        row.get("yesterday")
    )

    volume = to_float(
        row.get("volume")
    )

    trades = to_float(
        row.get("trades")
    )

    value = to_float(
        row.get("value")
    )

    if not symbol or price is None:
        return None

    if price <= 0:
        return None

    if not yesterday or yesterday <= 0:
        yesterday = close or price

    change = 0.0

    if yesterday > 0:
        change = (
            (price - yesterday)
            / yesterday
        ) * 100

    return {
        "symbol": symbol,
        "name": name or symbol,
        "price": price,
        "close": close or price,
        "yesterday": yesterday,
        "change": change,
        "volume": volume or 0,
        "trades": trades or 0,
        "value": value or 0,
    }


# ============================================================
# SCORE
# ============================================================

def score_stock(stock):

    change = stock["change"]
    volume = stock["volume"]
    trades = stock["trades"]
    value = stock["value"]

    score = 0

    # حرکت مثبت
    if change >= 1:
        score += 25
    elif change >= 0.5:
        score += 18
    elif change > 0:
        score += 10

    # حجم
    if volume > 1000000:
        score += 20
    elif volume > 300000:
        score += 15
    elif volume > 100000:
        score += 10

    # تعداد معاملات
    if trades > 500:
        score += 20
    elif trades > 200:
        score += 15
    elif trades > 50:
        score += 10

    # ارزش معاملات
    if value > 10_000_000_000:
        score += 20
    elif value > 2_000_000_000:
        score += 15
    elif value > 500_000_000:
        score += 10

    # جلوگیری از انتخاب رشدهای بسیار ضعیف
    if change > 2:
        score += 10

    stock["score"] = score

    return stock


# ============================================================
# FIND TOP 5
# ============================================================

def find_top5(rows, source):

    normalized = []

    for row in rows:

        if source == "TSETMC-OLD":

            item = normalize_old_row(row)

        else:

            item = normalize_row(row)

        if not item:
            continue

        # فقط نمادهای مثبت
        if item["change"] <= 0:
            continue

        item = score_stock(item)

        normalized.append(item)

    if not normalized:
        return []

    normalized.sort(
        key=lambda x: (
            x["score"],
            x["change"],
            x["value"],
            x["volume"],
        ),
        reverse=True,
    )

    return normalized[:5]


# ============================================================
# PRICE LEVELS
# ============================================================

def make_levels(stock):

    price = stock["price"]

    # پیشنهاد محافظه‌کارانه
    entry = price

    stop = price * 0.97

    target1 = price * 1.05

    target2 = price * 1.08

    return (
        entry,
        stop,
        target1,
        target2,
    )


# ============================================================
# TELEGRAM TOP 5
# ============================================================

def send_top5(top5, source):

    if not top5:

        telegram_send(
            "⚠️ ATI BOURSE\n\n"
            "داده بازار دریافت شد اما "
            "هیچ نماد مثبت و قابل امتیازدهی "
            "پیدا نشد.\n\n"
            f"📡 SOURCE: {source}\n"
            "🔒 REAL TRADING: OFF"
        )

        return

    header = (
        "🏆 ATI BOURSE TOP 5\n"
        f"⚡ {VERSION}\n\n"
        f"📡 SOURCE: {source}\n"
        "🔒 REAL TRADING: OFF\n\n"
    )

    telegram_send(header)

    for i, stock in enumerate(top5, 1):

        entry, stop, target1, target2 = (
            make_levels(stock)
        )

        message = (
            f"#{i} 🟢 {stock['symbol']}\n"
            f"🏷 {stock['name']}\n\n"
            f"💰 قیمت: {stock['price']:,.0f}\n"
            f"📈 تغییر: {stock['change']:+.2f}%\n"
            f"⭐ امتیاز: {stock['score']}\n"
            f"📊 حجم: {stock['volume']:,.0f}\n"
            f"🔄 معاملات: {stock['trades']:,.0f}\n\n"
            f"🟢 ورود پیشنهادی: {entry:,.0f}\n"
            f"🛑 حد ضرر: {stop:,.0f}\n"
            f"🎯 هدف ۱: {target1:,.0f}\n"
            f"🎯 هدف ۲: {target2:,.0f}\n\n"
            "🧠 دلیل:\n"
            "حرکت مثبت + حجم/ارزش معاملات + "
            "تعداد معاملات مناسب.\n\n"
            "⚠️ سیگنال تحلیلی است؛ "
            "خرید خودکار انجام نمی‌شود."
        )

        telegram_send(message)

        time.sleep(
