# ============================================================
# ATI BOURSE BOT
# V2.3 - NO API KEY
# بورس ایران - فقط داده عمومی
# BRS_API_KEY کاملاً حذف شده
# REAL TRADING = OFF
# ============================================================

import os
import json
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BOT_VERSION = "ATI-BOURSE-V2.3-NO-APIKEY"

# ------------------------------------------------------------
# TELEGRAM
# ------------------------------------------------------------

TELEGRAM_BOT_TOKEN = (
    os.getenv("BOURSE_TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_BOT_TOKEN")
)

TELEGRAM_CHAT_ID = (
    os.getenv("BOURSE_TELEGRAM_CHAT_ID")
    or os.getenv("TELEGRAM_CHAT_ID")
)

# ------------------------------------------------------------
# SAFETY
# ------------------------------------------------------------

REAL_TRADING = False

TIMEOUT = 20
MAX_SYMBOLS = 100

# ------------------------------------------------------------
# PUBLIC SOURCES
# هیچ API KEY لازم نیست
# ------------------------------------------------------------

SOURCES = [
    (
        "TSETMC CDN MarketWatch",
        "https://cdn.tsetmc.com/api/MarketWatch"
    ),
    (
        "TSETMC CDN MarketWatchPlus",
        "https://cdn.tsetmc.com/api/MarketWatchPlus"
    ),
    (
        "TSETMC Old MarketWatch",
        "http://old.tsetmc.com/tsev2/data/MarketWatchInit.aspx"
    ),
]

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
# HTTP
# ============================================================

def http_get(url, timeout=TIMEOUT):

    req = Request(
        url,
        headers=HEADERS,
        method="GET"
    )

    with urlopen(req, timeout=timeout) as response:

        status = response.status

        raw = response.read()

        text = raw.decode(
            "utf-8",
            errors="replace"
        )

        return status, text


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(text):

    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM BOT TOKEN NOT FOUND")
        return False

    if not TELEGRAM_CHAT_ID:
        print("⚠️ TELEGRAM CHAT ID NOT FOUND")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }).encode("utf-8")

    try:

        req = Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ATI-Bourse-Bot"
            },
            method="POST"
        )

        with urlopen(req, timeout=20) as response:

            return response.status == 200

    except Exception as e:

        print(
            f"⚠️ TELEGRAM ERROR: "
            f"{type(e).__name__}: {e}"
        )

        return False


# ============================================================
# NUMBER
# ============================================================

def to_float(value):

    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:

        text = str(value).strip()

        if not text:
            return None

        text = (
            text.replace(",", "")
            .replace("٬", "")
            .replace("٫", ".")
        )

        return float(text)

    except Exception:
        return None


# ============================================================
# FIND LISTS INSIDE JSON
# ============================================================

def extract_rows(obj, depth=0):

    if depth > 6:
        return []

    if isinstance(obj, list):

        if obj:
            return obj

        return []

    if not isinstance(obj, dict):
        return []

    preferred_keys = [
        "marketWatch",
        "marketwatch",
        "MarketWatch",
        "marketWatchData",
        "data",
        "Data",
        "items",
        "Items",
        "rows",
        "Rows",
        "instruments",
        "Instruments",
        "instrument",
        "result",
        "Result",
    ]

    for key in preferred_keys:

        value = obj.get(key)

        if isinstance(value, list) and value:
            return value

    for value in obj.values():

        if isinstance(value, list) and value:

            if isinstance(
                value[0],
                (dict, list)
            ):
                return value

        if isinstance(value, dict):

            result = extract_rows(
                value,
                depth + 1
            )

            if result:
                return result

    return []


# ============================================================
# NORMALIZE MARKET ROW
# ============================================================

def normalize_row(row):

    if not isinstance(row, dict):
        return None

    # --------------------------------------------------------
    # SYMBOL
    # --------------------------------------------------------

    symbol = None

    symbol_keys = [
        "symbol",
        "Symbol",
        "tseSymbol",
        "TseSymbol",
        "insCode",
        "InsCode",
        "instrumentCode",
        "InstrumentCode",
        "lVal18AFC",
        "lVal18",
    ]

    for key in symbol_keys:

        value = row.get(key)

        if value not in (None, ""):

            symbol = str(value).strip()
            break

    # --------------------------------------------------------
    # NAME
    # --------------------------------------------------------

    name = None

    name_keys = [
        "name",
        "Name",
        "lVal30",
        "lVal18",
        "companyName",
        "CompanyName",
        "title",
        "Title",
    ]

    for key in name_keys:

        value = row.get(key)

        if value not in (None, ""):

            name = str(value).strip()
            break

    # --------------------------------------------------------
    # LAST
    # --------------------------------------------------------

    last = None

    last_keys = [
        "last",
        "Last",
        "lastPrice",
        "LastPrice",
        "pDrCotVal",
        "price",
        "Price",
        "pl",
        "PL",
        "lastTradedPrice",
    ]

    for key in last_keys:

        value = to_float(row.get(key))

        if value is not None:

            last = value
            break

    # --------------------------------------------------------
    # CLOSE
    # --------------------------------------------------------

    close = None

    close_keys = [
        "close",
        "Close",
        "closePrice",
        "ClosePrice",
        "pClosing",
        "PC",
        "pc",
    ]

    for key in close_keys:

        value = to_float(row.get(key))

        if value is not None:

            close = value
            break

    # --------------------------------------------------------
    # YESTERDAY
    # --------------------------------------------------------

    yesterday = None

    yesterday_keys = [
        "yesterday",
        "Yesterday",
        "yesterdayPrice",
        "priceYesterday",
        "pClosingYesterday",
        "py",
        "PY",
    ]

    for key in yesterday_keys:

        value = to_float(row.get(key))

        if value is not None:

            yesterday = value
            break

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    volume = None

    volume_keys = [
        "volume",
        "Volume",
        "qTotTran5J",
        "volumeTotal",
        "vol",
        "Vol",
        "tradeVolume",
        "TradeVolume",
    ]

    for key in volume_keys:

        value = to_float(row.get(key))

        if value is not None:

            volume = value
            break

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    if last is None:
        last = close

    if close is None:
        close = last

    if last is None:
        return None

    if last <= 0:
        return None

    if yesterday is not None and yesterday <= 0:
        yesterday = None

    if volume is None:
        volume = 0

    # --------------------------------------------------------
    # PERCENT
    # --------------------------------------------------------

    pct = 0.0

    if (
        yesterday is not None
        and yesterday > 0
    ):

        pct = (
            (last - yesterday)
            / yesterday
        ) * 100

    return {
        "symbol": symbol or "",
        "name": name or symbol or "",
        "last": last,
        "close": close,
        "yesterday": yesterday,
        "volume": volume,
        "pct": pct,
    }


# ============================================================
# FETCH ONE SOURCE
# ============================================================

def fetch_source(source_name, url):

    print(
        f"🔎 SOURCE: {source_name}"
    )

    print(
        f"🌐 {url}"
    )

    try:

        status, raw = http_get(url)

        print(
            f"📡 HTTP STATUS: {status}"
        )

        if status != 200:

            return [], (
                f"{source_name}: HTTP {status}"
            )

        if not raw.strip():

            return [], (
                f"{source_name}: EMPTY RESPONSE"
            )

        # ----------------------------------------------------
        # JSON
        # ----------------------------------------------------

        try:

            obj = json.loads(raw)

        except Exception:

            return [], (
                f"{source_name}: INVALID JSON"
            )

        rows = extract_rows(obj)

        print(
            f"📊 RAW ROWS: {len(rows)}"
        )

        normalized = []

        for row in rows:

            item = normalize_row(row)

            if item:

                normalized.append(item)

        # ----------------------------------------------------
        # REMOVE DUPLICATES
        # ----------------------------------------------------

        unique = {}

        for item in normalized:

            key = (
                item["symbol"]
                or item["name"]
            ).strip()

            if not key:
                continue

            unique[key] = item

        normalized = list(
            unique.values()
        )

        print(
            f"✅ VALID ROWS: "
            f"{len(normalized)}"
        )

        if normalized:

            return normalized, None

        return [], (
            f"{source_name}: "
            f"NO USABLE MARKET ROWS"
        )

    except HTTPError as e:

        return [], (
            f"{source_name}: "
            f"HTTP ERROR {e.code}"
        )

    except URLError as e:

        return [], (
            f"{source_name}: "
            f"CONNECTION ERROR"
        )

    except TimeoutError:

        return [], (
            f"{source_name}: TIMEOUT"
        )

    except Exception as e:

        return [], (
            f"{source_name}: "
            f"{type(e).__name__}: {e}"
        )


# ============================================================
# FETCH MARKET
# ============================================================

def fetch_market():

    errors = []

    for source_name, url in SOURCES:

        rows, error = fetch_source(
            source_name,
            url
        )

        if rows:

            return (
                source_name,
                rows,
                errors
            )

        if error:

            errors.append(error)

        # کمی فاصله بین منابع
        time.sleep(1)

    return (
        None,
        [],
        errors
    )


# ============================================================
# SCORE
# ============================================================

def score_stock(item):

    pct = item.get(
        "pct",
        0
    )

    volume = item.get(
        "volume",
        0
    )

    score = 0

    # --------------------------------------------------------
    # PRICE MOMENTUM
    # --------------------------------------------------------

    if pct >= 5:
        score += 6

    elif pct >= 4:
        score += 5

    elif pct >= 3:
        score += 4

    elif pct >= 2:
        score += 3

    elif pct >= 1:
        score += 2

    elif pct > 0:
        score += 1

    # --------------------------------------------------------
    # NEGATIVE
    # --------------------------------------------------------

    if pct <= -5:
        score -= 4

    elif pct <= -3:
        score -= 2

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    if volume >= 50_000_000:

        score += 3

    elif volume >= 10_000_000:

        score += 2

    elif volume >= 1_000_000:

        score += 1

    return score


# ============================================================
# SELECT
# ============================================================

def select_candidates(rows):

    valid = []

    for item in rows:

        symbol = (
            item.get("symbol")
            or ""
        ).strip()

        name = (
            item.get("name")
            or ""
        ).strip()

        if not symbol and not name:
            continue

        text = (
            f"{symbol} {name}"
        ).lower()

        # ----------------------------------------------------
        # حذف شاخص‌ها
        # ----------------------------------------------------

        if "شاخص" in text:
            continue

        if "index" in text:
            continue

        item["score"] = score_stock(
            item
        )

        valid.append(item)

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    valid.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get("pct", 0),
            x.get("volume", 0),
        ),
        reverse=True
    )

    return valid[:MAX_SYMBOLS]


# ============================================================
# PRICE FORMAT
# ============================================================

def format_price(value):

    if value is None:
        return "-"

    try:

        if abs(value) >= 1000:

            return f"{value:,.0f}"

        if abs(value) >= 1:

            return (
                f"{value:,.2f}"
                .rstrip("0")
                .rstrip(".")
            )

        return (
            f"{value:.6f}"
            .rstrip("0")
            .rstrip(".")
        )

    except Exception:

        return str(value)


# ============================================================
# REPORT
# ============================================================

def build_report(
    source,
    candidates,
    total_rows
):

    lines = [

        "💓 ATI BOURSE ALIVE",

        f"⚡ {BOT_VERSION}",

        "📊 بورس ایران",

        "🔑 BRS_API_KEY: NOT REQUIRED",

        "🔒 REAL TRADING: OFF",

        f"🕐 {now_utc()}",

        "",

        f"✅ SOURCE: {source}",

        f"📈 MARKET ROWS: {total_rows}",

        f"📊 VALID SYMBOLS: {len(candidates)}",

        "",
    ]

    if not candidates:

        lines.extend([
            "⚠️ سهم قابل استفاده‌ای پیدا نشد.",
            "",
            "🔒 هیچ معامله‌ای انجام نشد.",
        ])

        return "\n".join(lines)

    lines.extend([
        "🔥 TOP MARKET MOMENTUM",
        "",
    ])

    top = candidates[:10]

    for i, item in enumerate(
        top,
        1
    ):

        symbol = (
            item.get("symbol")
            or item.get("name")
            or "-"
        )

        pct = item.get(
            "pct",
            0
        )

        score = item.get(
            "score",
            0
        )

        sign = (
            "+"
            if pct >= 0
            else ""
        )

        price = format_price(
            item.get("last")
        )

        lines.append(
            f"{i}️⃣ {symbol}\n"
            f"   💰 {price}"
            f" | 📊 {sign}{pct:.2f}%"
            f" | ⭐ {score}"
        )

    lines.extend([

        "",

        "⚠️ این نسخه فقط اسکن بازار است.",

        "🚫 هیچ سفارش خرید/فروشی ارسال نمی‌شود.",

        "🔑 هیچ BRS_API_KEY لازم نیست.",

    ])

    return "\n".join(lines)


# ============================================================
# ERROR REPORT
# ============================================================

def build_error_report(errors):

    lines = [

        "❌ ATI BOURSE ERROR",

        "",

        "هیچ داده عمومی معتبری از بازار دریافت نشد.",

        "",

        "🔑 BRS_API_KEY لازم نیست.",

        "🔒 REAL TRADING: OFF",

        "",

        "📋 DIAGNOSTIC:",

    ]

    if not errors:

        lines.append(
            "• UNKNOWN MARKET DATA ERROR"
        )

    else:

        for error in errors:

            lines.append(
                f"• {error}"
            )

    lines.extend([

        "",

        f"🕐 {now_utc()}",

    ])

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)

    print(
        f"ATI BOURSE {BOT_VERSION}"
    )

    print(
        "🔑 BRS_API_KEY: NOT REQUIRED"
    )

    print(
        "🔒 REAL TRADING: OFF"
    )

    print(
        f"🕐 {now_utc()}"
    )

    print("=" * 60)

    source, rows, errors = fetch_market()

    # --------------------------------------------------------
    # NO DATA
    # --------------------------------------------------------

    if not rows:

        report = build_error_report(
            errors
        )

        print()
        print(report)
        print()

        telegram_send(
            report
        )

        return 0

    # --------------------------------------------------------
    # SELECT
    # --------------------------------------------------------

    candidates = select_candidates(
        rows
    )

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    report = build_report(
        source,
        candidates,
        len(rows)
    )

    print()
    print(report)
    print()

    telegram_send(
        report
    )

    return 0


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )
