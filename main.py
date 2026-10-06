import os
import time
from datetime import datetime, timezone

import requests


# ============================================================
# ATI BOURSE BOT V2.1
# MARKET WATCH TIMEOUT + MULTI SOURCE + DIAGNOSTIC
# بورس و فرابورس ایران
# ============================================================

VERSION = "ATI-BOURSE-V2.1-MARKETWATCH-DIAGNOSTIC"

# فعلاً معامله واقعی خاموش است
REAL_TRADING = False

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ------------------------------------------------------------
# TIMEOUT
# ------------------------------------------------------------

CONNECT_TIMEOUT = 4
READ_TIMEOUT = 6

SOURCE_RETRIES = 1

# ------------------------------------------------------------
# HEADERS
# ------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": (
        "application/json,"
        "application/vnd.ms-excel,"
        "text/plain,"
        "*/*"
    ),
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

        return False

    except Exception as e:

        print(
            "❌ TELEGRAM ERROR:",
            str(e)
        )

        return False


# ============================================================
# HTTP DIAGNOSTIC
# ============================================================

def diagnostic_response(name, response):

    content_type = response.headers.get(
        "content-type",
        ""
    )

    size = len(response.content)

    preview = ""

    try:
        preview = (
            response.text
            .replace("\n", " ")
            .replace("\r", " ")
            [:150]
        )
    except Exception:
        preview = "<NO PREVIEW>"

    print("=" * 60)
    print(f"📡 {name}")
    print("HTTP:", response.status_code)
    print("TYPE:", content_type)
    print("SIZE:", size)
    print("PREVIEW:", preview)
    print("=" * 60)


# ============================================================
# SOURCE 1
# CDN TSETMC
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

        diagnostic_response(
            "SOURCE 1 TSETMC CDN",
            r
        )

        if r.status_code != 200:
            print(
                "❌ SOURCE 1 HTTP:",
                r.status_code
            )
            return None

        try:
            data = r.json()
        except Exception as e:
            print(
                "❌ SOURCE 1 JSON ERROR:",
                str(e)
            )
            return None

        if isinstance(data, dict):

            rows = data.get("marketwatch")

            if isinstance(rows, list) and rows:

                print(
                    "✅ SOURCE 1 SUCCESS:",
                    len(rows),
                    "ROWS"
                )

                return rows

            print(
                "⚠️ SOURCE 1 marketwatch EMPTY"
            )

        return None

    except requests.exceptions.Timeout:

        print(
            "⏱️ SOURCE 1 TIMEOUT"
        )

    except Exception as e:

        print(
            "❌ SOURCE 1 ERROR:",
            str(e)
        )

    return None


# ============================================================
# OLD MARKET WATCH PARSER
# ============================================================

def parse_old_market_watch(content):

    if not content:
        return None

    content = content.strip()

    print(
        "📦 OLD RESPONSE LENGTH:",
        len(content)
    )

    if "@" not in content:

        print(
            "⚠️ OLD RESPONSE HAS NO @ SEPARATOR"
        )

        print(
            "PREVIEW:",
            content[:300]
        )

        return None

    parts = content.split("@")

    print(
        "🔢 OLD RESPONSE PARTS:",
        len(parts)
    )

    if len(parts) < 5:

        print(
            "⚠️ OLD RESPONSE INVALID"
        )

        return None

    # ساختار:
    # 0 handle messages
    # 1 market state
    # 2 price rows
    # 3 best limits
    # 4 refid

    price_rows = parts[2]

    if not price_rows:

        print(
            "⚠️ OLD PRICE ROWS EMPTY"
        )

        return None

    rows = []

    raw_rows = price_rows.split(";")

    for raw in raw_rows:

        raw = raw.strip()

        if not raw:
            continue

        cols = raw.split(",")

        # طبق ساختار 26 ستونی TSETMC
        if len(cols) < 20:
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

        rows.append(
            {
                "ins_code": cols[0],
                "isin": cols[1],
                "symbol": symbol,
                "name": name,
                "heven": cols[4] if len(cols) > 4 else "",
                "pf": cols[5] if len(cols) > 5 else "",
                "pc": cols[6] if len(cols) > 6 else "",
                "pl": cols[7] if len(cols) > 7 else "",
                "tno": cols[8] if len(cols) > 8 else "",
                "tvol": cols[9] if len(cols) > 9 else "",
                "tval": cols[10] if len(cols) > 10 else "",
                "pmin": cols[11] if len(cols) > 11 else "",
                "pmax": cols[12] if len(cols) > 12 else "",
                "py": cols[13] if len(cols) > 13 else "",
            }
        )

    if rows:

        print(
            "✅ OLD MARKET WATCH SUCCESS:",
            len(rows),
            "ROWS"
        )

        return rows

    print(
        "⚠️ OLD MARKET WATCH PARSED 0 ROWS"
    )

    return None


# ============================================================
# SOURCE 2
# OLD TSETMC MarketWatchInit
# ============================================================

def get_old_market_watch():

    urls = [
        "https://old.tsetmc.com/"
        "tsev2/data/MarketWatchInit.aspx?h=0&r=0",

        "http://old.tsetmc.com/"
        "tsev2/data/MarketWatchInit.aspx?h=0&r=0",

        "https://www.tsetmc.com/"
        "tsev2/data/MarketWatchInit.aspx?h=0&r=0",

        "http://www.tsetmc.com/"
        "tsev2/data/MarketWatchInit.aspx?h=0&r=0",
    ]

    print(
        "🌐 SOURCE 2: OLD TSETMC"
    )

    for index, url in enumerate(urls, 1):

        print(
            f"🔁 OLD ENDPOINT {index}/{len(urls)}"
        )

        try:

            r = requests.get(
                url,
                headers=HEADERS,
                timeout=(
                    CONNECT_TIMEOUT,
                    READ_TIMEOUT,
                ),
                allow_redirects=True,
            )

            diagnostic_response(
                f"OLD TSETMC {index}",
                r
            )

            if r.status_code != 200:
                continue

            rows = parse_old_market_watch(
                r.text
            )

            if rows:
                return rows

        except requests.exceptions.Timeout:

            print(
                f"⏱️ OLD ENDPOINT {index} TIMEOUT"
            )

        except Exception as e:

            print(
                f"❌ OLD ENDPOINT {index} ERROR:",
                str(e)
            )

    return None


# ============================================================
# SOURCE 3
# MARKETWATCHPLUS
# ============================================================

def get_market_watch_plus():

    urls = [

        "https://old.tsetmc.com/"
        "tsev2/excel/MarketWatchPlus.aspx?d=0",

        "http://old.tsetmc.com/"
        "tsev2/excel/MarketWatchPlus.aspx?d=0",

        "https://www.tsetmc.com/"
        "tsev2/excel/MarketWatchPlus.aspx?d=0",

        "http://www.tsetmc.com/"
        "tsev2/excel/MarketWatchPlus.aspx?d=0",

    ]

    print(
        "🌐 SOURCE 3: MARKET WATCH PLUS"
    )

    for index, url in enumerate(urls, 1):

        print(
            f"🔁 PLUS ENDPOINT {index}/{len(urls)}"
        )

        try:

            r = requests.get(
                url,
                headers=HEADERS,
                timeout=(
                    CONNECT_TIMEOUT,
                    READ_TIMEOUT,
                ),
                allow_redirects=True,
            )

            diagnostic_response(
                f"MARKET WATCH PLUS {index}",
                r
            )

            if r.status_code != 200:
                continue

            # Excel response
            content_type = (
                r.headers.get(
                    "content-type",
                    ""
                ).lower()
            )

            # اگر Excel بود، فعلاً فقط
            # دریافت موفق را گزارش می‌کنیم.
            # برای تحلیل CSV/Excel در نسخه بعدی
            # می‌توان openpyxl را اضافه کرد.

            if (
                "excel" in content_type
                or "spreadsheet" in content_type
                or "octet-stream" in content_type
            ):

                if len(r.content) > 1000:

                    print(
                        "✅ MARKET WATCH PLUS "
                        "RESPONSE RECEIVED:",
                        len(r.content),
                        "BYTES"
                    )

                    return {
                        "type": "binary",
                        "content": r.content,
                    }

            # بعضی سرورها خروجی متنی می‌دهند
            if "@" in r.text:

                rows = parse_old_market_watch(
                    r.text
                )

                if rows:
                    return rows

            print(
                "⚠️ PLUS RESPONSE NOT PARSED"
            )

        except requests.exceptions.Timeout:

            print(
                f"⏱️ PLUS ENDPOINT {index} TIMEOUT"
            )

        except Exception as e:

            print(
                f"❌ PLUS ENDPOINT {index} ERROR:",
                str(e)
            )

    return None


# ============================================================
# SOURCE 4
# OFFICIAL TSE GATEWAY
# ============================================================

def get_official_market_watch():

    url = (
        "https://webgw.tse.ir/"
        "InstrumentProvider/api/v1/"
        "MarketWatch/MarketWatchCash/fa"
    )

    print(
        "🌐 SOURCE 4: TSE OFFICIAL"
    )

    try:

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=(
                CONNECT_TIMEOUT,
                READ_TIMEOUT,
            ),
        )

        diagnostic_response(
            "SOURCE 4 TSE OFFICIAL",
            r
        )

        if r.status_code != 200:
            return None

        try:
            data = r.json()
        except Exception as e:

            print(
                "❌ OFFICIAL JSON ERROR:",
                str(e)
            )

            return None

        if isinstance(data, dict):

            rows = data.get("Items")

            if isinstance(rows, list) and rows:

                print(
                    "✅ SOURCE 4 SUCCESS:",
                    len(rows),
                    "ROWS"
                )

                return rows

            # بعض پاسخ‌ها ممکن است
            # با کلیدهای دیگری برگردند
            for key, value in data.items():

                if isinstance(value, list) and value:

                    print(
                        "✅ OFFICIAL LIST FOUND:",
                        key,
                        len(value)
                    )

                    return value

        print(
            "⚠️ OFFICIAL EMPTY"
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

    return None


# ============================================================
# MARKET DATA CONTROLLER
# ============================================================

def get_market_data():

    print("=" * 60)
    print("🔎 MARKET DATA START")
    print("=" * 60)

    # --------------------------------------------------------
    # SOURCE 1
    # --------------------------------------------------------

    start = time.time()

    rows = get_tsetmc_cdn()

    elapsed = round(
        time.time() - start,
        2
    )

    print(
        f"⏱️ SOURCE 1 TIME: {elapsed}s"
    )

    if rows:
        return rows, "TSETMC-CDN"

    # --------------------------------------------------------
    # SOURCE 2
    # --------------------------------------------------------

    start = time.time()

    rows = get_old_market_watch()

    elapsed = round(
        time.time() - start,
        2
    )

    print(
        f"⏱️ SOURCE 2 TIME: {elapsed}s"
    )

    if rows:
        return rows, "TSETMC-OLD"

    # --------------------------------------------------------
    # SOURCE 3
    # --------------------------------------------------------

    start = time.time()

    rows = get_market_watch_plus()

    elapsed = round(
        time.time() - start,
        2
    )

    print(
        f"⏱️ SOURCE 3 TIME: {elapsed}s"
    )

    if rows:

        # اگر پاسخ باینری Excel بود،
        # فعلاً آن را به عنوان دریافت موفق
        # نگه نمی‌داریم چون هنوز parse نشده.
        if isinstance(rows, dict):

            print(
                "⚠️ SOURCE 3 RECEIVED EXCEL "
                "BUT PARSER NOT ENABLED"
            )

        else:

            return rows, "MARKET-WATCH-PLUS"

    # --------------------------------------------------------
    # SOURCE 4
    # --------------------------------------------------------

    start = time.time()

    rows = get_official_market_watch()

    elapsed = round(
        time.time() - start,
        2
    )

    print(
        f"⏱️ SOURCE 4 TIME: {elapsed}s"
    )

    if rows:
        return rows, "TSE-OFFICIAL"

    return None, None


# ============================================================
# SCANNER
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
        "📈 مرحله بعد: تحلیل نمادها\n"
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
        "🔎 شروع دریافت اطلاعات بازار...\n"
        "⏱️ هر منبع حداکثر چند ثانیه بررسی می‌شود."
    )

    # --------------------------------------------------------
    # GET MARKET DATA
    # --------------------------------------------------------

    try:

        rows, source = get_market_data()

    except Exception as e:

        error_text = (
            "🚨 ATI BOURSE FATAL ERROR\n\n"
            f"⚡ {VERSION}\n\n"
            "❌ خطای غیرمنتظره در دریافت بازار\n\n"
            f"DETAIL:\n{str(e)[:1000]}\n\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

        print(error_text)

        telegram_send(error_text)

        return

    # --------------------------------------------------------
    # NO DATA
    # --------------------------------------------------------

    if not rows:

        message = (
            "❌ ATI BOURSE MARKET DATA ERROR\n\n"
            f"⚡ {VERSION}\n\n"
            "هیچ‌کدام از منابع بازار داده قابل "
            "استفاده برنگرداندند.\n\n"
            "🔁 SOURCE 1: TSETMC CDN\n"
            "🔁 SOURCE 2: OLD TSETMC\n"
            "🔁 SOURCE 3: MARKET WATCH PLUS\n"
            "🔁 SOURCE 4: TSE OFFICIAL\n\n"
            "⏱️ Timeout فعال است؛ ربات نباید "
            "روی دریافت بازار قفل شود.\n\n"
            "🚫 هیچ معامله‌ای انجام نشد.\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now_utc()}"
        )

        print(message)

        telegram_send(message)

        return

    # --------------------------------------------------------
    # SCAN
    # --------------------------------------------------------

    result = scan_market(
        rows,
        source
    )

    print("=" * 60)
    print(result)
    print("=" * 60)

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
    main()
