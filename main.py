# ============================================================
# ATI BOURSE BOT V1.2
# بورس و فرابورس ایران
# TSETMC ROBUST TIMEOUT VERSION
# REAL TRADING: OFF
# ============================================================

import os
import time
import traceback
from datetime import datetime, timezone

import requests


# ============================================================
# CONFIG
# ============================================================

VERSION = "ATI-BOURSE-V1.2"

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    ""
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    ""
).strip()

# ------------------------------------------------------------
# امنیت
# ------------------------------------------------------------

REAL_TRADING = False

# ------------------------------------------------------------
# TSETMC TIMEOUT CONTROL
# ------------------------------------------------------------

TOTAL_TSETMC_LIMIT = 55

CONNECT_TIMEOUT = 6
READ_TIMEOUT = 10

RETRY_COUNT = 3

RETRY_SLEEP = 2


# ============================================================
# HTTP HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10; K) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/125.0 Mobile Safari/537.36"
    ),
    "Accept": (
        "application/json,"
        "text/plain,"
        "*/*"
    ),
    "Accept-Language": (
        "fa-IR,fa;q=0.9,en;q=0.8"
    ),
    "Connection": "close",
}


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

        print(
            "❌ TELEGRAM_BOT_TOKEN MISSING"
        )

        return False

    if not TELEGRAM_CHAT_ID:

        print(
            "❌ TELEGRAM_CHAT_ID MISSING"
        )

        return False

    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_BOT_TOKEN
        + "/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=(5, 10),
        )

        if response.status_code == 200:

            print(
                "✅ TELEGRAM SENT"
            )

            return True

        print(
            "❌ TELEGRAM ERROR:",
            response.status_code,
            response.text[:500],
        )

        return False

    except Exception as e:

        print(
            "❌ TELEGRAM EXCEPTION:",
            repr(e)
        )

        return False


# ============================================================
# TSETMC URL
# ============================================================

TSETMC_MARKETWATCH_URL = (
    "https://cdn.tsetmc.com/api/"
    "ClosingPrice/GetMarketWatch"
    "?market=0"
    "&paperTypes%5B0%5D=1"
    "&paperTypes%5B1%5D=2"
    "&paperTypes%5B2%5D=3"
    "&paperTypes%5B3%5D=4"
    "&paperTypes%5B4%5D=5"
    "&paperTypes%5B5%5D=6"
    "&paperTypes%5B6%5D=7"
    "&paperTypes%5B7%5D=8"
    "&paperTypes%5B8%5D=9"
    "&withBestLimits=false"
    "&hEven=0"
    "&RefID=0"
)


# ============================================================
# TSETMC SINGLE REQUEST
# ============================================================

def tsetmc_request():

    started = time.monotonic()

    print("")
    print(
        "🌐 TSETMC REQUEST START"
    )

    print(
        f"⏱️ TOTAL LIMIT: "
        f"{TOTAL_TSETMC_LIMIT}s"
    )

    try:

        response = requests.get(
            TSETMC_MARKETWATCH_URL,
            headers=HEADERS,
            timeout=(
                CONNECT_TIMEOUT,
                READ_TIMEOUT,
            ),
        )

        elapsed = (
            time.monotonic()
            - started
        )

        print(
            f"⏱️ TSETMC RESPONSE: "
            f"{elapsed:.1f}s"
        )

        print(
            f"📡 HTTP STATUS: "
            f"{response.status_code}"
        )

        if response.status_code != 200:

            print(
                "❌ TSETMC HTTP ERROR"
            )

            print(
                response.text[:500]
            )

            return None

        if not response.content:

            print(
                "❌ TSETMC EMPTY RESPONSE"
            )

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

            print(
                "❌ TSETMC INVALID JSON"
            )

            return None

        return data

    except requests.exceptions.ConnectTimeout:

        print(
            "❌ TSETMC CONNECT TIMEOUT"
        )

        return None

    except requests.exceptions.ReadTimeout:

        print(
            "❌ TSETMC READ TIMEOUT"
        )

        return None

    except requests.exceptions.Timeout:

        print(
            "❌ TSETMC GENERAL TIMEOUT"
        )

        return None

    except requests.exceptions.ConnectionError as e:

        print(
            "❌ TSETMC CONNECTION ERROR:",
            repr(e)
        )

        return None

    except Exception as e:

        print(
            "❌ TSETMC REQUEST ERROR:",
            repr(e)
        )

        return None


# ============================================================
# EXTRACT MARKET ROWS
# ============================================================

def extract_market_rows(data):

    if not isinstance(data, dict):

        return []

    possible_keys = [
        "marketwatch",
        "marketWatch",
        "marketWatchData",
        "data",
        "rows",
    ]

    for key in possible_keys:

        value = data.get(key)

        if isinstance(value, list):

            print(
                f"✅ TSETMC KEY: {key}"
            )

            print(
                f"📊 ROWS: {len(value)}"
            )

            return value

        if isinstance(value, dict):

            for nested_key in [
                "marketwatch",
                "marketWatch",
                "rows",
                "data",
            ]:

                nested = value.get(
                    nested_key
                )

                if isinstance(
                    nested,
                    list
                ):

                    print(
                        f"✅ TSETMC "
                        f"NESTED KEY: "
                        f"{key}/{nested_key}"
                    )

                    print(
                        f"📊 ROWS: "
                        f"{len(nested)}"
                    )

                    return nested

    print(
        "❌ MARKET WATCH ARRAY NOT FOUND"
    )

    print(
        "🔎 JSON KEYS:",
        list(data.keys())[:30]
    )

    return []


# ============================================================
# TSETMC RETRY ENGINE
# ============================================================

def get_market_watch():

    started = time.monotonic()

    last_error = ""

    for attempt in range(
        1,
        RETRY_COUNT + 1
    ):

        elapsed = (
            time.monotonic()
            - started
        )

        if elapsed >= TOTAL_TSETMC_LIMIT:

            print(
                "⛔ TOTAL TSETMC TIME LIMIT REACHED"
            )

            break

        print("")
        print(
            f"🔎 TSETMC TRY "
            f"{attempt}/{RETRY_COUNT}"
        )

        data = tsetmc_request()

        if data is not None:

            rows = extract_market_rows(
                data
            )

            if rows:

                total_time = (
                    time.monotonic()
                    - started
                )

                print(
                    "✅ TSETMC SUCCESS"
                )

                print(
                    f"⏱️ TOTAL TIME: "
                    f"{total_time:.1f}s"
                )

                return rows

            last_error = (
                "Market Watch array empty"
            )

        else:

            last_error = (
                "TSETMC request failed"
            )

        if attempt < RETRY_COUNT:

            elapsed = (
                time.monotonic()
                - started
            )

            if (
                elapsed + RETRY_SLEEP
                >= TOTAL_TSETMC_LIMIT
            ):

                break

            print(
                f"⏳ WAIT "
                f"{RETRY_SLEEP}s "
                "BEFORE RETRY"
            )

            time.sleep(
                RETRY_SLEEP
            )

    print("")
    print(
        "❌ TSETMC FAILED"
    )

    print(
        f"❌ LAST ERROR: "
        f"{last_error}"
    )

    return None


# ============================================================
# NORMALIZE ROWS
# ============================================================

def normalize_rows(rows):

    normalized = []

    for item in rows:

        if not isinstance(
            item,
            dict
        ):

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
                str(
                    last_price
                ).replace(
                    ",",
                    ""
                )
            )

        except Exception:

            last_price = 0

        try:

            close_price = float(
                str(
                    close_price
                ).replace(
                    ",",
                    ""
                )
            )

        except Exception:

            close_price = 0

        try:

            yesterday = float(
                str(
                    yesterday
                ).replace(
                    ",",
                    ""
                )
            )

        except Exception:

            yesterday = 0

        try:

            volume = float(
                str(
                    volume
                ).replace(
                    ",",
                    ""
                )
            )

        except Exception:

            volume = 0

        if not symbol:

            continue

        normalized.append(
            {
                "symbol": str(
                    symbol
                ),
                "name": str(
                    name
                ),
                "last": last_price,
                "close": close_price,
                "yesterday": yesterday,
                "volume": volume,
            }
        )

    return normalized


# ============================================================
# BASIC OPPORTUNITY SCAN
# ============================================================

def scan_opportunities(rows):

    candidates = []

    for item in rows:

        last_price = item[
            "last"
        ]

        yesterday = item[
            "yesterday"
        ]

        volume = item[
            "volume"
        ]

        if last_price <= 0:

            continue

        if yesterday <= 0:

            continue

        change_pct = (
            (
                last_price
                - yesterday
            )
            / yesterday
        ) * 100

        if volume <= 0:

            continue

        # فیلتر اولیه
        if change_pct < 1.0:

            continue

        item[
            "change_pct"
        ] = change_pct

        candidates.append(
            item
        )

    candidates.sort(
        key=lambda x:
        x["change_pct"],
        reverse=True,
    )

    return candidates[:10]


# ============================================================
# TELEGRAM MARKET RESULT
# ============================================================

def send_market_result(
    rows,
    opportunities
):

    if not rows:

        telegram_send(
            "⚠️ ATI BOURSE\n\n"
            "TSETMC پاسخ داد، "
            "اما Market Watch خالی بود.\n\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

        return

    if not opportunities:

        telegram_send(
            "📊 ATI BOURSE\n\n"
            "✅ Market Watch دریافت شد.\n"
            f"📊 تعداد داده‌ها: "
            f"{len(rows)}\n\n"
            "🔎 در اسکن اولیه "
            "فرصت مناسب پیدا نشد.\n\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

        return

    lines = [
        "📊 ATI BOURSE",
        "",
        "🔥 فرصت‌های اولیه بازار",
        "",
        f"📊 Market Watch: "
        f"{len(rows)}",
        "",
    ]

    for index, item in enumerate(
        opportunities,
        1
    ):

        symbol = item[
            "symbol"
        ]

        name = item[
            "name"
        ]

        last = item[
            "last"
        ]

        change = item[
            "change_pct"
        ]

        lines.append(
            f"{index}. {symbol}"
        )

        if name:

            lines.append(
                f"🏷 {name}"
            )

        lines.append(
            f"💰 {last:,.0f}"
        )

        lines.append(
            f"📈 +{change:.2f}%"
        )

        lines.append("")

    lines.extend(
        [
            "⚠️ این فقط اسکن اولیه است.",
            "❌ سیگنال قطعی خرید نیست.",
            "🔒 REAL TRADING: OFF",
            f"🕐 {now_utc()}",
        ]
    )

    telegram_send(
        "\n".join(lines)
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print(
        "=" * 60
    )

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

    print(
        "=" * 60
    )

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
    # TSETMC
    # --------------------------------------------------------

    print("")
    print(
        "🔎 START TSETMC SCAN"
    )

    rows = get_market_watch()

    if rows is None:

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
            "⏱️ ربات بعد از چند تلاش "
            "به دلیل Timeout متوقف شد.\n"
            "🚫 ربات گیر نکرد.\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

        return

    # --------------------------------------------------------
    # NORMALIZE
    # --------------------------------------------------------

    normalized = normalize_rows(
        rows
    )

    print("")
    print(
        f"📊 RAW ROWS: "
        f"{len(rows)}"
    )

    print(
        f"📊 NORMALIZED ROWS: "
        f"{len(normalized)}"
    )

    # --------------------------------------------------------
    # SCAN
    # --------------------------------------------------------

    opportunities = (
        scan_opportunities(
            normalized
        )
    )

    print("")
    print(
        f"🎯 OPPORTUNITIES: "
        f"{len(opportunities)}"
    )

    # --------------------------------------------------------
    # TELEGRAM RESULT
    # --------------------------------------------------------

    send_market_result(
        normalized,
        opportunities
    )

    print("")
    print(
        "✅ ATI BOURSE RUN COMPLETED"
    )

    print(
        f"🕐 {now_utc()}"
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
            "🚨 ATI BOURSE FATAL ERROR"
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
