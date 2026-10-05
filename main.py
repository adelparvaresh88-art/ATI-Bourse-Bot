# ============================================================
# ATI BOURSE BOT V1.1
# بورس و فرابورس ایران
# TSETMC MARKET WATCH - ROBUST VERSION
# REAL TRADING: OFF
# ============================================================

import os
import io
import time
import json
import traceback
from datetime import datetime, timezone

import requests


# ============================================================
# CONFIG
# ============================================================

VERSION = "ATI-BOURSE-V1.1"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

REAL_TRADING = False

TIMEOUT = 25
RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10; K) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


# ============================================================
# TIME
# ============================================================

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(text):
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN MISSING")
        return False

    if not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_CHAT_ID MISSING")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
    }

    try:
        r = requests.post(
            url,
            json=payload,
            timeout=20,
        )

        if r.ok:
            print("✅ TELEGRAM SENT")
            return True

        print(
            "❌ TELEGRAM ERROR:",
            r.status_code,
            r.text[:500],
        )
        return False

    except Exception as e:
        print("❌ TELEGRAM EXCEPTION:", repr(e))
        return False


# ============================================================
# HTTP GET WITH RETRY
# ============================================================

def http_get(url, timeout=TIMEOUT, retries=RETRIES):
    last_error = None

    for attempt in range(1, retries + 1):

        try:
            print(
                f"🌐 HTTP TRY {attempt}/{retries}"
            )
            print(url)

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=timeout,
            )

            print(
                f"📡 HTTP STATUS: {response.status_code}"
            )

            if response.status_code == 200:
                return response

            last_error = (
                f"HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

        except Exception as e:
            last_error = repr(e)

            print(
                f"⚠️ HTTP ERROR TRY {attempt}: "
                f"{last_error}"
            )

        if attempt < retries:
            sleep_time = attempt * 3

            print(
                f"⏳ RETRY AFTER {sleep_time}s"
            )

            time.sleep(sleep_time)

    print("❌ HTTP FAILED")
    print(last_error)

    return None


# ============================================================
# TSETMC - METHOD 1
# NEW JSON MARKET WATCH
# ============================================================

def get_marketwatch_new():

    url = (
        "https://cdn.tsetmc.com/api/"
        "ClosingPrice/GetMarketWatch"
        "?market=0"
        "&industrialGroup="
        "&paperTypes%5B0%5D=1"
        "&paperTypes%5B1%5D=2"
        "&paperTypes%5B2%5D=3"
        "&paperTypes%5B3%5D=4"
        "&paperTypes%5B4%5D=5"
        "&paperTypes%5B5%5D=6"
        "&paperTypes%5B6%5D=7"
        "&paperTypes%5B7%5D=8"
        "&paperTypes%5B8%5D=9"
        "&showTraded=false"
        "&withBestLimits=false"
        "&hEven=0"
        "&RefID=0"
    )

    response = http_get(url)

    if response is None:
        return None

    try:
        data = response.json()
    except Exception as e:
        print(
            "❌ TSETMC JSON ERROR:",
            repr(e)
        )
        return None

    if not isinstance(data, dict):
        print("❌ TSETMC RESPONSE IS NOT DICT")
        return None

    rows = data.get("marketwatch")

    if rows is None:
        rows = data.get("marketWatch")

    if not isinstance(rows, list):
        print(
            "❌ TSETMC MARKETWATCH KEY NOT FOUND"
        )
        return None

    print(
        f"📊 NEW API MARKET WATCH ROWS: {len(rows)}"
    )

    if len(rows) == 0:
        print(
            "⚠️ NEW API RETURNED ZERO ROWS"
        )
        return None

    return rows


# ============================================================
# TSETMC - METHOD 2
# OLD MARKET WATCH PLUS
# ============================================================

def get_marketwatch_old():

    urls = [
        "https://old.tsetmc.com/"
        "tsev2/excel/MarketWatchPlus.aspx?d=0",

        "https://old.tsetmc.com/"
        "tsev2/excel/MarketWatchPlus.aspx"
        "?d=0&format=0",
    ]

    for url in urls:

        print(
            "🔁 TRY OLD TSETMC MARKET WATCH"
        )

        response = http_get(
            url,
            timeout=30,
            retries=2,
        )

        if response is None:
            continue

        content = response.content

        if not content:
            print(
                "⚠️ OLD TSETMC EMPTY RESPONSE"
            )
            continue

        print(
            f"📦 OLD TSETMC BYTES: "
            f"{len(content)}"
        )

        return content

    return None


# ============================================================
# PARSE OLD EXCEL
# ============================================================

def parse_old_marketwatch(content):

    try:
        import pandas as pd
    except ImportError:
        print(
            "❌ pandas is not installed"
        )
        return []

    try:

        df = pd.read_excel(
            io.BytesIO(content),
            header=None,
        )

        print(
            f"📊 OLD EXCEL SHAPE: "
            f"{df.shape}"
        )

        if df.empty:
            return []

        # حذف ردیف‌های کاملاً خالی
        df = df.dropna(
            how="all"
        )

        if df.empty:
            return []

        rows = []

        for _, row in df.iterrows():

            values = []

            for value in row.tolist():

                if pd.isna(value):
                    values.append("")
                else:
                    values.append(
                        str(value).strip()
                    )

            rows.append(values)

        print(
            f"📊 OLD MARKET WATCH ROWS: "
            f"{len(rows)}"
        )

        return rows

    except Exception as e:

        print(
            "❌ OLD EXCEL PARSE ERROR:",
            repr(e)
        )

        return []


# ============================================================
# UNIFIED MARKET WATCH
# ============================================================

def get_market_watch():

    print("")
    print(
        "🔎 TSETMC METHOD 1: NEW JSON"
    )

    rows = get_marketwatch_new()

    if rows:
        print(
            "✅ TSETMC NEW JSON SUCCESS"
        )

        return {
            "type": "json",
            "rows": rows,
        }

    print("")
    print(
        "⚠️ NEW JSON FAILED"
    )

    print(
        "🔎 TSETMC METHOD 2: OLD EXCEL"
    )

    content = get_marketwatch_old()

    if content:

        rows = parse_old_marketwatch(
            content
        )

        if rows:

            print(
                "✅ TSETMC OLD EXCEL SUCCESS"
            )

            return {
                "type": "excel",
                "rows": rows,
            }

    print("")
    print(
        "❌ ALL TSETMC METHODS FAILED"
    )

    return None


# ============================================================
# JSON NORMALIZER
# ============================================================

def normalize_json_rows(rows):

    result = []

    for item in rows:

        if not isinstance(item, dict):
            continue

        symbol = (
            item.get("lVal18AFC")
            or item.get("lVal18")
            or item.get("symbol")
            or item.get("lVal30")
            or ""
        )

        name = (
            item.get("lVal30")
            or item.get("name")
            or ""
        )

        last_price = (
            item.get("pl")
            or item.get("pDrCotVal")
            or item.get("last")
            or 0
        )

        close_price = (
            item.get("pc")
            or item.get("pClosing")
            or item.get("close")
            or 0
        )

        yesterday = (
            item.get("py")
            or item.get("priceYesterday")
            or 0
        )

        volume = (
            item.get("qTotTran5J")
            or item.get("volume")
            or 0
        )

        try:
            last_price = float(
                str(last_price).replace(",", "")
            )
        except Exception:
            last_price = 0

        try:
            close_price = float(
                str(close_price).replace(",", "")
            )
        except Exception:
            close_price = 0

        try:
            yesterday = float(
                str(yesterday).replace(",", "")
            )
        except Exception:
            yesterday = 0

        try:
            volume = float(
                str(volume).replace(",", "")
            )
        except Exception:
            volume = 0

        if not symbol:
            continue

        result.append({
            "symbol": str(symbol),
            "name": str(name),
            "last": last_price,
            "close": close_price,
            "yesterday": yesterday,
            "volume": volume,
        })

    return result


# ============================================================
# SIMPLE MARKET FILTER
# ============================================================

def find_opportunities(rows):

    candidates = []

    for item in rows:

        last_price = item["last"]
        yesterday = item["yesterday"]
        volume = item["volume"]

        if last_price <= 0:
            continue

        if yesterday <= 0:
            continue

        change_pct = (
            (last_price - yesterday)
            / yesterday
        ) * 100

        # فیلتر محافظه‌کارانه
        if change_pct < 1.0:
            continue

        if volume <= 0:
            continue

        item["change_pct"] = change_pct

        candidates.append(item)

    candidates.sort(
        key=lambda x: x["change_pct"],
        reverse=True,
    )

    return candidates[:10]


# ============================================================
# TELEGRAM MARKET MESSAGE
# ============================================================

def send_market_message(
    opportunities,
    source,
):

    if not opportunities:

        text = (
            "📊 ATI BOURSE\n\n"
            "🔎 اسکن بازار انجام شد.\n"
            f"📡 SOURCE: {source}\n\n"
            "❌ فعلاً فرصت خرید مناسب "
            "طبق فیلتر اولیه پیدا نشد.\n\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

        telegram_send(text)

        return

    lines = [
        "📊 ATI BOURSE",
        "",
        "🔥 فرصت‌های اولیه بازار",
        f"📡 SOURCE: {source}",
        "",
    ]

    for index, item in enumerate(
        opportunities,
        start=1,
    ):

        symbol = item["symbol"]
        name = item["name"]
        last = item["last"]
        change = item["change_pct"]

        lines.append(
            f"{index}. {symbol}"
        )

        if name:
            lines.append(
                f"   🏷 {name}"
            )

        lines.append(
            f"   💰 قیمت: {last:,.0f}"
        )

        lines.append(
            f"   📈 تغییر: +{change:.2f}%"
        )

        lines.append("")

    lines.extend([
        "⚠️ این‌ها فقط فرصت‌های اولیه‌اند.",
        "❌ هنوز سیگنال قطعی خرید نیست.",
        "🔒 REAL TRADING: OFF",
        f"🕐 {now_utc()}",
    ])

    telegram_send(
        "\n".join(lines)
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "🚀 STARTING "
        f"{VERSION}"
    )

    print("")
    print("=" * 60)
    print(
        f"⚡ {VERSION}"
    )
    print(
        "📊 بورس / فرابورس ایران"
    )
    print(
        "🔒 REAL TRADING: OFF"
    )
    print(
        "📡 TSETMC DATA"
    )
    print(
        f"🕐 {now_utc()}"
    )
    print("=" * 60)
    print("")

    # --------------------------------------------------------
    # TELEGRAM ALIVE
    # --------------------------------------------------------

    telegram_send(
        "💓 ATI BOURSE ALIVE\n"
        f"⚡ {VERSION}\n"
        "📊 بورس و فرابورس ایران\n"
        "🔒 REAL TRADING: OFF\n"
        "📡 TSETMC DATA\n"
        f"🕐 {now_utc()}\n\n"
        "🔎 شروع اسکن بازار..."
    )

    # --------------------------------------------------------
    # MARKET WATCH
    # --------------------------------------------------------

    market = get_market_watch()

    if market is None:

        print("")
        print(
            "❌ ATI BOURSE ERROR"
        )

        print(
            "داده Market Watch "
            "از TSETMC دریافت نشد."
        )

        telegram_send(
            "❌ ATI BOURSE ERROR\n\n"
            "داده Market Watch "
            "از TSETMC دریافت نشد.\n\n"
            "🔁 ربات مسیرهای جایگزین "
            "TSETMC را نیز امتحان کرد.\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

        return

    # --------------------------------------------------------
    # NORMALIZE
    # --------------------------------------------------------

    source = market["type"]
    raw_rows = market["rows"]

    if source == "json":

        rows = normalize_json_rows(
            raw_rows
        )

    else:

        # فعلاً برای Excel فقط گزارش دریافت
        # می‌دهیم؛ ساختار ستون‌های نسخه قدیمی
        # ممکن است تغییر کند.
        rows = []

        print(
            "⚠️ OLD EXCEL RECEIVED"
        )

        print(
            "⚠️ Excel parser needs "
            "column mapping for signals."
        )

    print("")
    print(
        f"📡 MARKET SOURCE: {source}"
    )

    print(
        f"📊 MARKET WATCH ROWS: "
        f"{len(raw_rows)}"
    )

    print(
        f"📊 NORMALIZED ROWS: "
        f"{len(rows)}"
    )

    # --------------------------------------------------------
    # JSON SIGNAL ENGINE
    # --------------------------------------------------------

    if rows:

        opportunities = (
            find_opportunities(rows)
        )

        print(
            f"🎯 OPPORTUNITIES: "
            f"{len(opportunities)}"
        )

        send_market_message(
            opportunities,
            source,
        )

    else:

        telegram_send(
            "📊 ATI BOURSE\n\n"
            "✅ اتصال به TSETMC برقرار شد.\n"
            f"📡 SOURCE: {source}\n"
            f"📊 ROWS: {len(raw_rows)}\n\n"
            "⚠️ داده دریافت شد ولی "
            "برای ساخت سیگنال هنوز "
            "نیاز به نگاشت ستون‌ها داریم.\n\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

    print("")
    print(
        "✅ ATI BOURSE RUN COMPLETED"
    )


# ============================================================
# SAFE START
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as e:

        print("")
        print(
            "🚨 FATAL ERROR"
        )

        print(
            repr(e)
        )

        traceback.print_exc()

        telegram_send(
            "🚨 ATI BOURSE FATAL ERROR\n\n"
            f"{repr(e)}\n\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )
