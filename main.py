import os
import time
from datetime import datetime, timezone

import requests


# ============================================================
# ATI BOURSE BOT V1.2
# بورس و فرابورس ایران
# ============================================================

VERSION = "ATI-BOURSE-V1.2"
REAL_TRADING = False

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CONNECT_TIMEOUT = 6
READ_TIMEOUT = 10
RETRY_COUNT = 3
RETRY_SLEEP = 2


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM SETTINGS MISSING")
        return False

    url = (
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }

    try:
        r = requests.post(
            url,
            json=payload,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )

        if r.ok:
            print("✅ TELEGRAM SENT")
            return True

        print("❌ TELEGRAM ERROR:", r.status_code, r.text)
        return False

    except Exception as e:
        print("❌ TELEGRAM EXCEPTION:", str(e))
        return False


# ============================================================
# TIME
# ============================================================

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ============================================================
# TSETMC
# ============================================================

def get_market_watch():
    """
    دریافت Market Watch از TSETMC
    با timeout و retry محدود.
    """

    url = "https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch"

    params = {
        "market": 0,
        "flow": 0,
        "price": 0,
        "order": 0,
        "orderBy": 1,
        "start": 0,
        "length": 100,
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 10) "
            "AppleWebKit/537.36 "
            "Chrome/120.0 Mobile Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://www.tsetmc.com/",
        "Connection": "close",
    }

    for attempt in range(1, RETRY_COUNT + 1):

        print(
            f"🌐 TSETMC REQUEST "
            f"{attempt}/{RETRY_COUNT}"
        )

        try:

            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )

            print(
                "📡 TSETMC HTTP:",
                response.status_code
            )

            if response.status_code != 200:
                print(
                    "❌ TSETMC BAD STATUS:",
                    response.status_code
                )

            else:

                data = response.json()

                if data:
                    print("✅ TSETMC DATA RECEIVED")
                    return data

                print("⚠️ TSETMC EMPTY DATA")

        except requests.exceptions.ConnectTimeout:
            print("⏱️ TSETMC CONNECT TIMEOUT")

        except requests.exceptions.ReadTimeout:
            print("⏱️ TSETMC READ TIMEOUT")

        except requests.exceptions.Timeout:
            print("⏱️ TSETMC TIMEOUT")

        except Exception as e:
            print("❌ TSETMC ERROR:", str(e))

        if attempt < RETRY_COUNT:
            print(
                f"⏳ WAIT {RETRY_SLEEP}s..."
            )
            time.sleep(RETRY_SLEEP)

    return None


# ============================================================
# NORMALIZE
# ============================================================

def normalize_market_data(data):

    if data is None:
        return []

    rows = []

    try:

        if isinstance(data, list):
            rows = data

        elif isinstance(data, dict):

            possible_keys = [
                "marketWatch",
                "marketwatch",
                "data",
                "rows",
                "items",
                "result",
            ]

            for key in possible_keys:

                value = data.get(key)

                if isinstance(value, list):
                    rows = value
                    break

            if not rows:

                for value in data.values():

                    if isinstance(value, list):
                        rows = value
                        break

        print(
            "📊 MARKET WATCH ROWS:",
            len(rows)
        )

        return rows

    except Exception as e:

        print(
            "❌ NORMALIZE ERROR:",
            str(e)
        )

        return []


# ============================================================
# BASIC MARKET SCAN
# ============================================================

def scan_market(rows):

    if not rows:

        return (
            "❌ Market Watch خالی است.\n"
            "هیچ نمادی برای بررسی دریافت نشد."
        )

    # فعلاً فقط دریافت صحیح بازار را تأیید می‌کنیم.
    # معامله واقعی خاموش است.

    return (
        "✅ MARKET WATCH دریافت شد.\n\n"
        f"📊 تعداد داده‌های دریافتی: {len(rows)}\n\n"
        "🔎 مرحله تحلیل بازار آماده است.\n"
        "🔒 معامله واقعی: خاموش"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print(f"⚡ {VERSION}")
    print("📊 بورس / فرابورس ایران")
    print("🔒 REAL TRADING:", "ON" if REAL_TRADING else "OFF")
    print("📡 TSETMC DATA")
    print("🕐", now_utc())
    print("=" * 60)

    telegram_send(
        "💓 ATI BOURSE ALIVE\n"
        f"⚡ {VERSION}\n"
        "📊 بورس و فرابورس ایران\n"
        f"🔒 REAL TRADING: "
        f"{'ON' if REAL_TRADING else 'OFF'}\n"
        "📡 TSETMC DATA\n"
        f"🕐 {now_utc()}\n\n"
        "🔎 شروع اسکن بازار..."
    )

    print("🔎 شروع اسکن بازار...")

    data = get_market_watch()

    if data is None:

        message = (
            "❌ ATI BOURSE ERROR\n\n"
            "داده Market Watch از TSETMC دریافت نشد.\n"
            "ربات هیچ معامله‌ای انجام نداد.\n\n"
            f"⚡ {VERSION}\n"
            f"🕐 {now_utc()}"
        )

        print(message)
        telegram_send(message)

        return

    rows = normalize_market_data(data)

    result = scan_market(rows)

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
