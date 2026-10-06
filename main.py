import os
import time
from datetime import datetime, timezone

import requests


# ============================================================
# ATI BOURSE BOT V2.4
# TOP 5 STOCK SCANNER - MULTI SOURCE FAILOVER
# ============================================================

VERSION = "ATI-BOURSE-V2.4-FAILOVER-TOP5"

# فعلاً فقط تحلیل و ارسال تلگرام
REAL_TRADING = False

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 8

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "Referer": "https://www.tsetmc.com/",
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

    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN MISSING")
        return False

    if not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_CHAT_ID MISSING")
        return False

    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_TOKEN
        + "/sendMessage"
    )

    try:

        response = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
            },
            timeout=(5, 10),
        )

        if response.ok:
            print("✅ TELEGRAM SENT")
            return True

        print(
            "❌ TELEGRAM ERROR:",
            response.status_code,
            response.text[:500],
        )

    except Exception as error:

        print(
            "❌ TELEGRAM EXCEPTION:",
            str(error),
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

        text = str(value).strip()

        if not text:
            return None

        text = text.replace(",", "")
        text = text.replace("٬", "")
        text = text.replace("،", "")

        return float(text)

    except Exception:

        return None


# ============================================================
# DICT VALUE
# ============================================================

def get_value(row, names):

    if not isinstance(row, dict):
        return None

    lowered = {}

    for key, value in row.items():
        lowered[str(key).lower()] = value

    for name in names:

        key = str(name).lower()

        if key in lowered:
            return lowered[key]

    return None


# ============================================================
# SOURCE 1 - TSETMC CDN
# ============================================================

def get_tsetmc_cdn():

    url = (
        "https://cdn.tsetmc.com/api/"
        "ClosingPrice/GetMarketWatch"
    )

    params = {
        "market": 0,
        "paperTypes[0]": 1,
        "paperTypes[1]": 2,
        "paperTypes[2]": 3,
        "paperTypes[3]": 4,
        "paperTypes[4]": 5,
        "paperTypes[5]": 6,
        "paperTypes[6]": 7,
        "paperTypes[7]": 8,
        "paperTypes[8]": 9,
        "withBestLimits": "false",
        "hEven": 0,
        "RefID": 0,
    }

    print("🌐 SOURCE 1: TSETMC CDN")

    try:

        response = requests.get(
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
            response.status_code,
            "SIZE:",
            len(response.content),
        )

        if response.status_code != 200:
            return None

        data = response.json()

        if not isinstance(data, dict):
            return None

        rows = data.get("marketwatch")

        if isinstance(rows, list) and rows:

            print(
                "✅ SOURCE 1 SUCCESS:",
                len(rows),
            )

            return rows

    except requests.exceptions.Timeout:

        print("⏱️ SOURCE 1 TIMEOUT")

    except Exception as error:

        print(
            "❌ SOURCE 1 ERROR:",
            str(error),
        )

    return None


# ============================================================
# OLD TSETMC PARSER
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

        columns = raw.strip().split(",")

        if len(columns) < 15:
            continue

        symbol = columns[2].strip()
        name = columns[3].strip()

        if not symbol:
            continue

        result.append(
            {
                "ins_code": columns[0],
                "isin": columns[1],
                "symbol": symbol,
                "name": name,
                "heven": columns[4],
                "price": columns[5],
                "close": columns[6],
                "last": columns[7],
                "trades": columns[8],
                "volume": columns[9],
                "value": columns[10],
                "min": columns[11],
                "max": columns[12],
                "yesterday": columns[13],
                "eps": columns[14],
            }
        )

    if result:
        return result

    return None


# ============================================================
# SOURCE 2 - OLD TSETMC FAILOVER
# ============================================================

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

    for index, url in enumerate(urls, 1):

        try:

            print(
                f"🔁 OLD SOURCE {index}/{len(urls)}"
            )

            response = requests.get(
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
                response.status_code,
                "SIZE:",
                len(response.content),
            )

            if response.status_code != 200:
                continue

            rows = parse_old_market_watch(
                response.text
            )

            if rows:

                print(
                    "✅ OLD TSETMC SUCCESS:",
                    len(rows),
                )

                return rows

        except requests.exceptions.Timeout:

            print(
                f"⏱️ OLD SOURCE {index} TIMEOUT"
            )

        except Exception as error:

            print(
                f"❌ OLD SOURCE {index} ERROR:",
                str(error),
            )

    return None


# ============================================================
# SOURCE MANAGER
# ============================================================

def get_market_data():

    errors = []

    # --------------------------------------------------------
    # SOURCE 1
    # --------------------------------------------------------

    print("")
    print("🔎 FAILOVER SOURCE 1/2")

    try:

        rows = get_tsetmc_cdn()

        if rows:

            return rows, "TSETMC-CDN", errors

        errors.append(
            "TSETMC-CDN: no valid data"
        )

    except Exception as error:

        errors.append(
            "TSETMC-CDN: " + str(error)
        )

    # --------------------------------------------------------
    # SOURCE 2
    # --------------------------------------------------------

    print("")
    print("🔎 FAILOVER SOURCE 2/2")

    try:

        rows = get_old_market_watch()

        if rows:

            return rows, "TSETMC-OLD", errors

        errors.append(
            "TSETMC-OLD: no valid data"
        )

    except Exception as error:

        errors.append(
            "TSETMC-OLD: " + str(error)
        )

    # --------------------------------------------------------
    # ALL FAILED
    # --------------------------------------------------------

    return None, None, errors


# ============================================================
# NORMALIZE CDN
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
        ],
    )

    name = get_value(
        row,
        [
            "name",
            "l30",
            "l30name",
        ],
    )

    last = get_value(
        row,
        [
            "last",
            "pl",
            "lastPrice",
            "pLast",
        ],
    )

    close = get_value(
        row,
        [
            "close",
            "pc",
            "closingPrice",
            "pClosing",
        ],
    )

    yesterday = get_value(
        row,
        [
            "yesterday",
            "py",
            "yesterdayPrice",
        ],
    )

    volume = get_value(
        row,
        [
            "volume",
            "tvol",
            "totalVolume",
        ],
    )

    trades = get_value(
        row,
        [
            "trades",
            "tno",
            "numberOfTrades",
        ],
    )

    value = get_value(
        row,
        [
            "value",
            "tval",
            "tradeValue",
        ],
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

    price = last if last and last > 0 else close

    if price is None or price <= 0:
        return None

    if yesterday is None or yesterday <= 0:
        yesterday = close

    if yesterday is None or yesterday <= 0:
        return None

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
# NORMALIZE OLD
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

    if not symbol:
        return None

    if price is None or price <= 0:
        return None

    if yesterday is None or yesterday <= 0:
        yesterday = close or price

    if yesterday <= 0:
        return None

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
# SCORE
# ============================================================

def score_stock(stock):

    change = stock["change"]
    volume = stock["volume"]
    trades = stock["trades"]
    value = stock["value"]

    score = 0

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

    if volume >= 5_000_000:
        score += 25
    elif volume >= 1_000_000:
        score += 20
    elif volume >= 300_000:
        score += 15
    elif volume >= 100_000:
        score += 10

    if trades >= 1000:
        score += 20
    elif trades >= 500:
        score += 15
    elif trades >= 200:
        score += 10
    elif trades >= 50:
        score += 5

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
# FIND TOP 5
# ============================================================

def find_top5(rows, source):

    stocks = []

    for row in rows:

        if source == "TSETMC-OLD":
            stock = normalize_old_row(row)
        else:
            stock = normalize_row(row)

        if not stock:
            continue

        if stock["change"] <= 0:
            continue

        stock = score_stock(stock)

        stocks.append(stock)

    stocks.sort(
        key=lambda item: (
            item["score"],
            item["change"],
            item["value"],
            item["volume"],
            item["trades"],
        ),
        reverse=True,
    )

    return stocks[:5]


# ============================================================
# PRICE LEVELS
# ============================================================

def make_levels(stock):

    price = stock["price"]

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
# SEND TOP 5
# ============================================================

def send_top5(top5, source):

    if not top5:

        telegram_send(
            "⚠️ ATI BOURSE\n\n"
            "داده بازار دریافت شد اما "
            "هیچ سهم مثبت قابل قبول پیدا نشد.\n\n"
            f"📡 SOURCE: {source}\n"
            "🔒 REAL TRADING: OFF"
        )

        return

    telegram_send(
        "🏆 ATI BOURSE TOP 5\n"
        f"⚡ {VERSION}\n\n"
        f"📡 SOURCE: {source}\n"
        "🔒 REAL TRADING: OFF\n\n"
        "۵ سهم برتر بازار:"
    )

    for index, stock in enumerate(top5, 1):

        (
            entry,
            stop,
            target1,
            target2,
        ) = make_levels(stock)

        message = (
            f"#{index} 🟢 {stock['symbol']}\n"
            f"🏷 {stock['name']}\n\n"
            f"💰 قیمت: {stock['price']:,.0f}\n"
            f"📈 تغییر: {stock['change']:+.2f}%\n"
            f"⭐ امتیاز: {stock['score']}\n"
            f"📊 حجم: {stock['volume']:,.0f}\n"
            f"🔄 معاملات: {stock['trades']:,.0f}\n"
            f"💵 ارزش: {stock['value']:,.0f}\n\n"
            f"🟢 ورود پیشنهادی: {entry:,.0f}\n"
            f"🛑 حد ضرر: {stop:,.0f}\n"
            f"🎯 هدف ۱: {target1:,.0f}\n"
            f"🎯 هدف ۲: {target2:,.0f}\n\n"
            "🧠 دلیل انتخاب:\n"
            "رشد مثبت + حجم + تعداد معاملات "
            "+ ارزش معاملات.\n\n"
            "⚠️ این نسخه فقط سیگنال تحلیلی "
            "ارسال می‌کند.\n"
            "🚫 خرید خودکار خاموش است."
        )

        telegram_send(message)

        time.sleep(1)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("ATI BOURSE BOT - START")
    print(VERSION)
    print("📊 بورس و فرابورس ایران")
    print("🔒 REAL TRADING:", REAL_TRADING)
    print(now_utc())
    print("=" * 60)

    telegram_send(
        "💓 ATI BOURSE ALIVE\n"
        f"⚡ {VERSION}\n"
        "📊 بورس و فرابورس ایران\n"
        "🔒 REAL TRADING: OFF\n"
        "🎯 هدف: پیدا کردن ۵ سهم برتر\n"
        f"🕐 {now_utc()}\n\n"
        "🔎 شروع اسکن بازار..."
    )

    # ========================================================
    # MULTI SOURCE FAILOVER
    # ========================================================

    telegram_send(
        "🔄 ATI BOURSE FAILOVER\n\n"
        "در صورت قطع منبع اول، "
        "ربات خودکار منبع بعدی را امتحان می‌کند.\n\n"
        "1️⃣ TSETMC CDN\n"
        "2️⃣ OLD TSETMC"
    )

    rows, source, errors = get_market_data()

    # ========================================================
    # NO DATA
    # ========================================================

    if not rows:

        error_text = "\n".join(
            "• " + error
            for error in errors
        )

        telegram_send(
            "❌ ATI BOURSE ERROR\n\n"
            "هیچ داده‌ای از منابع بازار دریافت نشد.\n\n"
            "🔁 منابع بررسی‌شده:\n"
            "1️⃣ TSETMC CDN\n"
            "2️⃣ OLD TSETMC\n\n"
            "📋 نتیجه منابع:\n"
            f"{error_text}\n\n"
            "🚫 هیچ سهمی انتخاب نشد.\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

        print("❌ NO MARKET DATA")
        print("📋 ERRORS:")

        for error in errors:
            print(" -", error)

        return

    # ========================================================
    # DATA OK
    # ========================================================

    print(
        "📊 MARKET ROWS:",
        len(rows),
    )

    telegram_send(
        "✅ MARKET DATA RECEIVED\n\n"
        f"📈 تعداد داده‌ها: {len(rows)}\n"
        f"📡 منبع موفق: {source}\n\n"
        "🧠 در حال امتیازدهی سهم‌ها..."
    )

    # ========================================================
    # TOP 5
    # ========================================================

    top5 = find_top5(
        rows,
        source,
    )

    print(
        "🏆 TOP 5:",
        len(top5),
    )

    send_top5(
        top5,
        source,
    )

    print("=" * 60)
    print("✅ ATI BOURSE SCAN COMPLETED")
    print("=" * 60)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    try:
        main()
    except Exception as error:

        print(
            "🚨 FATAL ERROR:",
            str(error),
        )

        telegram_send(
            "🚨 ATI BOURSE FATAL ERROR\n\n"
            f"❌ {error}\n\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

        raise
