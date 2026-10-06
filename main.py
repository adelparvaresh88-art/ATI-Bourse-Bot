import os
import time
from datetime import datetime, timezone

import requests


# ============================================================
# ATI BOURSE BOT V2.0
# بورس و فرابورس ایران
# ============================================================

VERSION = "ATI-BOURSE-V2.0-MARKETWATCH-FIX"

# فعلاً خاموش؛ بعد از تأیید داده بازار جداگانه فعال می‌کنیم
REAL_TRADING = False

TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    ""
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    ""
).strip()

CONNECT_TIMEOUT = 8
READ_TIMEOUT = 15

RETRIES = 2


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

def telegram_send(text):

    if (
        not TELEGRAM_TOKEN
        or not TELEGRAM_CHAT_ID
    ):
        print(
            "❌ TELEGRAM SETTINGS MISSING"
        )
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
            timeout=(5, 10),
        )

        if r.ok:

            print(
                "✅ TELEGRAM SENT"
            )

            return True

        print(
            "❌ TELEGRAM ERROR:",
            r.status_code,
            r.text
        )

        return False

    except Exception as e:

        print(
            "❌ TELEGRAM ERROR:",
            str(e)
        )

        return False


# ============================================================
# HEADERS
# ============================================================

HEADERS = {

    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),

    "Accept": (
        "application/json,"
        "text/plain,"
        "*/*"
    ),

    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",

    "Referer":
        "https://www.tsetmc.com/",

    "Connection": "close",
}


# ============================================================
# PARSE OLD TSETMC MARKET WATCH
# ============================================================

def parse_old_market_watch(
    content
):
    """
    TSETMC MarketWatchInit / MarketWatchPlus
    پاسخ متنی چندبخشی دارد:

    بخش‌ها با @ جدا می‌شوند.

    بخش قیمت‌ها با ; جدا می‌شود.

    هر ردیف با , جدا می‌شود.

    ساختار رایج:
    ins_code,isin,l18,l30,heven,
    pf,pc,pl,tno,tvol,tval,
    pmin,pmax,py,...
    """

    if not content:
        return []

    content = content.strip()

    if not content:
        return []

    parts = content.split("@")

    if len(parts) < 3:
        return []

    # بخش قیمت‌ها
    price_part = parts[2]

    if not price_part:
        return []

    rows = []

    for raw_row in price_part.split(";"):

        raw_row = raw_row.strip()

        if not raw_row:
            continue

        cols = raw_row.split(",")

        if len(cols) < 10:
            continue

        try:

            # ساختار رایج 26 ستونه
            item = {
                "ins_code": cols[0],
                "isin": cols[1]
                    if len(cols) > 1
                    else "",

                "symbol": cols[2]
                    if len(cols) > 2
                    else "",

                "name": cols[3]
                    if len(cols) > 3
                    else "",

                "time": cols[4]
                    if len(cols) > 4
                    else "",

                "first_price": cols[5]
                    if len(cols) > 5
                    else "",

                "close_price": cols[6]
                    if len(cols) > 6
                    else "",

                "last_price": cols[7]
                    if len(cols) > 7
                    else "",

                "trade_count": cols[8]
                    if len(cols) > 8
                    else "",

                "volume": cols[9]
                    if len(cols) > 9
                    else "",

                "value": cols[10]
                    if len(cols) > 10
                    else "",

                "min_price": cols[11]
                    if len(cols) > 11
                    else "",

                "max_price": cols[12]
                    if len(cols) > 12
                    else "",

                "yesterday_price": cols[13]
                    if len(cols) > 13
                    else "",
            }

            rows.append(item)

        except Exception:
            continue

    return rows


# ============================================================
# SOURCE 1
# TSETMC NEW CDN API
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

    for attempt in range(
        1,
        RETRIES + 1
    ):

        print(
            f"🌐 SOURCE 1 TSETMC CDN "
            f"{attempt}/{RETRIES}"
        )

        try:

            r = requests.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=(
                    CONNECT_TIMEOUT,
                    READ_TIMEOUT
                ),
            )

            print(
                "📡 SOURCE 1 HTTP:",
                r.status_code
            )

            if r.status_code != 200:

                time.sleep(1)

                continue

            data = r.json()

            if isinstance(
                data,
                dict
            ):

                rows = data.get(
                    "marketwatch"
                )

                if (
                    isinstance(
                        rows,
                        list
                    )
                    and rows
                ):

                    print(
                        "✅ SOURCE 1 SUCCESS:",
                        len(rows),
                        "ROWS"
                    )

                    return rows

            print(
                "⚠️ SOURCE 1 EMPTY"
            )

        except requests.exceptions.Timeout:

            print(
                "⏱️ SOURCE 1 TIMEOUT"
            )

        except Exception as e:

            print(
                "❌ SOURCE 1 ERROR:",
                str(e)
            )

        time.sleep(1)

    return None


# ============================================================
# SOURCE 2
# TSETMC OLD MARKET WATCH INIT
# ============================================================

def get_tsetmc_old_market_watch():

    urls = [

        (
            "https://old.tsetmc.com/"
            "tsev2/data/"
            "MarketWatchInit.aspx"
            "?h=0&r=0"
        ),

        (
            "http://old.tsetmc.com/"
            "tsev2/data/"
            "MarketWatchInit.aspx"
            "?h=0&r=0"
        ),

        (
            "https://www.tsetmc.com/"
            "tsev2/data/"
            "MarketWatchInit.aspx"
            "?h=0&r=0"
        ),

        (
            "http://www.tsetmc.com/"
            "tsev2/data/"
            "MarketWatchInit.aspx"
            "?h=0&r=0"
        ),
    ]

    for url in urls:

        print(
            "🌐 SOURCE 2 OLD TSETMC"
        )

        print(
            "🔗",
            url
        )

        for attempt in range(
            1,
            RETRIES + 1
        ):

            try:

                r = requests.get(
                    url,
                    headers=HEADERS,
                    timeout=(
                        CONNECT_TIMEOUT,
                        READ_TIMEOUT
                    ),
                )

                print(
                    "📡 SOURCE 2 HTTP:",
                    r.status_code
                )

                if r.status_code != 200:

                    continue

                content = r.text

                rows = parse_old_market_watch(
                    content
                )

                if rows:

                    print(
                        "✅ SOURCE 2 SUCCESS:",
                        len(rows),
                        "ROWS"
                    )

                    return rows

                print(
                    "⚠️ SOURCE 2 EMPTY"
                )

            except requests.exceptions.Timeout:

                print(
                    "⏱️ SOURCE 2 TIMEOUT"
                )

            except Exception as e:

                print(
                    "❌ SOURCE 2 ERROR:",
                    str(e)
                )

            time.sleep(1)

    return None


# ============================================================
# SOURCE 3
# TSETMC MARKET WATCH PLUS
# ============================================================

def get_market_watch_plus():

    urls = [

        (
            "https://old.tsetmc.com/"
            "tsev2/data/"
            "MarketWatchPlus.aspx"
        ),

        (
            "http://old.tsetmc.com/"
            "tsev2/data/"
            "MarketWatchPlus.aspx"
        ),

        (
            "https://www.tsetmc.com/"
            "tsev2/data/"
            "MarketWatchPlus.aspx"
        ),

        (
            "http://www.tsetmc.com/"
            "tsev2/data/"
            "MarketWatchPlus.aspx"
        ),
    ]

    for url in urls:

        print(
            "🌐 SOURCE 3 MARKET WATCH PLUS"
        )

        print(
            "🔗",
            url
        )

        for attempt in range(
            1,
            RETRIES + 1
        ):

            try:

                r = requests.get(
                    url,
                    headers=HEADERS,
                    timeout=(
                        CONNECT_TIMEOUT,
                        READ_TIMEOUT
                    ),
                )

                print(
                    "📡 SOURCE 3 HTTP:",
                    r.status_code
                )

                if r.status_code != 200:
                    continue

                content = r.text

                rows = parse_old_market_watch(
                    content
                )

                if rows:

                    print(
                        "✅ SOURCE 3 SUCCESS:",
                        len(rows),
                        "ROWS"
                    )

                    return rows

                print(
                    "⚠️ SOURCE 3 EMPTY"
                )

            except requests.exceptions.Timeout:

                print(
                    "⏱️ SOURCE 3 TIMEOUT"
                )

            except Exception as e:

                print(
                    "❌ SOURCE 3 ERROR:",
                    str(e)
                )

            time.sleep(1)

    return None


# ============================================================
# SOURCE 4
# TSE OFFICIAL GATEWAY
# ============================================================

def get_official_market_watch():

    url = (
        "https://webgw.tse.ir/"
        "InstrumentProvider/api/v1/"
        "MarketWatch/"
        "MarketWatchCash/fa"
    )

    print(
        "🌐 SOURCE 4 OFFICIAL TSE"
    )

    for attempt in range(
        1,
        RETRIES + 1
    ):

        try:

            r = requests.get(
                url,
                headers=HEADERS,
                timeout=(
                    CONNECT_TIMEOUT,
                    READ_TIMEOUT
                ),
            )

            print(
                "📡 SOURCE 4 HTTP:",
                r.status_code
            )

            if r.status_code != 200:

                time.sleep(1)

                continue

            data = r.json()

            if isinstance(
                data,
                dict
            ):

                rows = data.get(
                    "Items"
                )

                if (
                    isinstance(
                        rows,
                        list
                    )
                    and rows
                ):

                    print(
                        "✅ SOURCE 4 SUCCESS:",
                        len(rows),
                        "ROWS"
                    )

                    return rows

            print(
                "⚠️ SOURCE 4 EMPTY"
            )

        except requests.exceptions.Timeout:

            print(
                "⏱️ SOURCE 4 TIMEOUT"
            )

        except Exception as e:

            print(
                "❌ SOURCE 4 ERROR:",
                str(e)
            )

        time.sleep(1)

    return None


# ============================================================
# MARKET DATA
# ============================================================

def get_market_data():

    print("=" * 60)

    print(
        "🔎 MARKET DATA START"
    )

    print("=" * 60)

    # --------------------------------------------------------
    # SOURCE 1
    # --------------------------------------------------------

    rows = get_tsetmc_market_watch()

    if rows:

        return (
            rows,
            "TSETMC-CDN"
        )

    # --------------------------------------------------------
    # SOURCE 2
    # --------------------------------------------------------

    rows = get_tsetmc_old_market_watch()

    if rows:

        return (
            rows,
            "TSETMC-OLD"
        )

    # --------------------------------------------------------
    # SOURCE 3
    # --------------------------------------------------------

    rows = get_market_watch_plus()

    if rows:

        return (
            rows,
            "TSETMC-MARKETWATCHPLUS"
        )

    # --------------------------------------------------------
    # SOURCE 4
    # --------------------------------------------------------

    rows = get_official_market_watch()

    if rows:

        return (
            rows,
            "TSE-OFFICIAL"
        )

    return (
        None,
        None
    )


# ============================================================
# SIMPLE MARKET SCAN
# ============================================================

def scan_market(
    rows,
    source
):

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

    print(
        f"⚡ {VERSION}"
    )

    print(
        "📊 بورس و فرابورس ایران"
    )

    print(
        "🔒 REAL TRADING: OFF"
    )

    print(
        "📡 TSETMC / TSE"
    )

    print(
        "🕐",
        now_utc()
    )

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

    # ========================================================
    # MARKET DATA
    # ========================================================

    rows, source = get_market_data()

    # ========================================================
    # FAILED
    # ========================================================

    if not rows:

        message = (
            "❌ ATI BOURSE ERROR\n\n"

            "داده Market Watch از هیچ‌کدام "
            "از منابع دریافت نشد.\n\n"

            "🔁 SOURCE 1: TSETMC CDN\n"
            "🔁 SOURCE 2: TSETMC OLD\n"
            "🔁 SOURCE 3: MARKET WATCH PLUS\n"
            "🔁 SOURCE 4: TSE OFFICIAL\n\n"

            "🚫 ربات هیچ معامله‌ای انجام نداد.\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

        print(
            message
        )

        telegram_send(
            message
        )

        return

    # ========================================================
    # SUCCESS
    # ========================================================

    result = scan_market(
        rows,
        source
    )

    print(
        result
    )

    telegram_send(
        "📊 ATI BOURSE RESULT\n\n"
        f"{result}\n\n"
        f"⚡ {VERSION}\n"
        f"🕐 {now_utc()}"
    )

    print(
        "✅ ATI BOURSE RUN COMPLETED"
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as e:

        error_message = (
            "🚨 ATI BOURSE CRITICAL ERROR\n\n"
            f"❌ {e}\n\n"
            f"⚡ {VERSION}\n"
            f"🕐 {now_utc()}"
        )

        print(
            error_message
        )

        telegram_send(
            error_message
        )

        raise
