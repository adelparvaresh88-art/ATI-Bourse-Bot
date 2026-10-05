import os
import time
from datetime import datetime, timezone

import requests


# ============================================================
# ATI BOURSE BOT V1.3
# بورس و فرابورس ایران
# ============================================================

VERSION = "ATI-BOURSE-V1.3"
REAL_TRADING = False

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 8
RETRIES = 2


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

        print("❌ TELEGRAM ERROR:", r.status_code, r.text)
        return False

    except Exception as e:
        print("❌ TELEGRAM ERROR:", str(e))
        return False


# ============================================================
# HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10) "
        "AppleWebKit/537.36 "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.tse.ir/",
    "Connection": "close",
}


# ============================================================
# SOURCE 1
# TSETMC CDN MARKET WATCH
# ============================================================

def get_tsetmc_market_watch():

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

    for attempt in range(1, RETRIES + 1):

        print(
            f"🌐 SOURCE 1 TSETMC "
            f"{attempt}/{RETRIES}"
        )

        try:

            r = requests.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )

            print(
                "📡 SOURCE 1 HTTP:",
                r.status_code
            )

            if r.status_code != 200:
                continue

            data = r.json()

            if isinstance(data, dict):

                rows = data.get("marketwatch")

                if isinstance(rows, list) and rows:

                    print(
                        "✅ SOURCE 1 SUCCESS:",
                        len(rows),
                        "ROWS"
                    )

                    return rows

            print("⚠️ SOURCE 1 EMPTY")

        except requests.exceptions.Timeout:

            print("⏱️ SOURCE 1 TIMEOUT")

        except Exception as e:

            print(
                "❌ SOURCE 1 ERROR:",
                str(e)
            )

        time.sleep(1)

    return None


# ============================================================
# SOURCE 2
# TSE OFFICIAL GATEWAY
# ============================================================

def get_official_market_watch():

    url = (
        "https://webgw.tse.ir/"
        "InstrumentProvider/api/v1/"
        "MarketWatch/MarketWatchCash/fa"
    )

    print("🌐 SOURCE 2 OFFICIAL TSE")

    try:

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )

        print(
            "📡 SOURCE 2 HTTP:",
            r.status_code
        )

        if r.status_code != 200:
            return None

        data = r.json()

        if isinstance(data, dict):

            rows = data.get("Items")

            if isinstance(rows, list) and rows:

                print(
                    "✅ SOURCE 2 SUCCESS:",
                    len(rows),
                    "ROWS"
                )

                return rows

        print("⚠️ SOURCE 2 EMPTY")

    except requests.exceptions.Timeout:

        print("⏱️ SOURCE 2 TIMEOUT")

    except Exception as e:

        print(
            "❌ SOURCE 2 ERROR:",
            str(e)
        )

    return None


# ============================================================
# MARKET DATA
# ============================================================

def get_market_data():

    print("=" * 60)
    print("🔎 MARKET DATA START")
    print("=" * 60)

    # SOURCE 1
    rows = get_tsetmc_market_watch()

    if rows:
        return rows, "TSETMC-CDN"

    # SOURCE 2
    rows = get_official_market_watch()

    if rows:
        return rows, "TSE-OFFICIAL"

    return None, None


# ============================================================
# SIMPLE SCAN
# ============================================================

def scan_market(rows, source):

    if not rows:
        return (
            "❌ هیچ داده‌ای از بازار دریافت نشد."
        )

    return (
        "✅ MARKET WATCH دریافت شد\n\n"
        f"📊 تعداد نمادها: {len(rows)}\n"
        f"📡 منبع: {source}\n\n"
        "🔎 داده بازار آماده تحلیل است.\n"
        "🔒 معامله واقعی: خاموش"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print(f"⚡ {VERSION}")
    print("📊 بورس و فرابورس ایران")
    print("🔒 REAL TRADING: OFF")
    print("📡 TSETMC / TSE")
    print("🕐", now_utc())
    print("=" * 60)

    telegram_send(
        "💓 ATI BOURSE ALIVE\n"
        f"⚡ {VERSION}\n"
        "📊 بورس و فرابورس ایران\n"
        "🔒 REAL TRADING: OFF\n"
        "📡 TSETMC / TSE\n"
        f"🕐 {now_utc()}\n\n"
        "🔎 شروع دریافت اطلاعات بازار..."
    )

    rows, source = get_market_data()

    if not rows:

        message = (
            "❌ ATI BOURSE ERROR\n\n"
            "داده Market Watch از منابع بازار دریافت نشد.\n\n"
            "🔁 SOURCE 1: TSETMC CDN\n"
            "🔁 SOURCE 2: TSE OFFICIAL\n\n"
            "🚫 ربات هیچ معامله‌ای انجام نداد.\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

        print(message)
        telegram_send(message)
        return

    result = scan_market(rows, source)

    print(result)

    telegram_send(
        "📊 ATI BOURSE RESULT\n\n"
        f"{result}\n\n"
        f"⚡ {VERSION}\n"
        f"🕐 {now_utc()}"
    )

    print("✅ ATI BOURSE RUN COMPLETED")


if __name__ == "__main__":
    main()
