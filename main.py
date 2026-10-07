# ============================================================
# ATI BOURSE BOT
# V2.4 - NO BRS API KEY
# بورس ایران - Public Market Data
#
# REAL TRADING: OFF
# هیچ سفارش خرید/فروشی ارسال نمی‌شود.
# ============================================================

import os
import json
import time
import ssl
import csv
import io
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BOT_VERSION = "ATI-BOURSE-V2.4-NO-APIKEY"

# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = (
    os.getenv("BOURSE_TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_BOT_TOKEN")
)

TELEGRAM_CHAT_ID = (
    os.getenv("BOURSE_TELEGRAM_CHAT_ID")
    or os.getenv("TELEGRAM_CHAT_ID")
)

# ============================================================
# SAFETY
# ============================================================

REAL_TRADING = False

TIMEOUT = 25
MAX_SYMBOLS = 100

# ============================================================
# HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "application/json,text/plain,"
        "application/vnd.ms-excel,"
        "application/octet-stream,*/*"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "Referer": "https://www.tsetmc.com/",
    "Origin": "https://www.tsetmc.com",
    "Connection": "close",
}

# ============================================================
# PUBLIC SOURCES
#
# اول CDN جدید
# سپس mirror
# سپس legacy Excel
#
# هیچ API KEY لازم نیست.
# ============================================================

JSON_SOURCES = [

    (
        "TSETMC CDN GetMarketWatch",
        "https://cdn.tsetmc.com/api/ClosingPrice/"
        "GetMarketWatch"
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
    ),

    (
        "TSETMC CDN Mirror",
        "https://cdn10.tsetmc.com/api/ClosingPrice/"
        "GetMarketWatch"
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
    ),
]

EXCEL_SOURCES = [

    (
        "TSETMC Legacy MarketWatchPlus",
        "https://old.tsetmc.com/tsev2/excel/"
        "MarketWatchPlus.aspx?d=0"
    ),

    (
        "TSETMC Legacy MarketWatchPlus Format",
        "https://old.tsetmc.com/tsev2/excel/"
        "MarketWatchPlus.aspx?d=0&format=0"
    ),
]


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
# HTTP
# ============================================================

def http_get(url):

    req = Request(
        url,
        headers=HEADERS,
        method="GET"
    )

    try:

        with urlopen(
            req,
            timeout=TIMEOUT
        ) as response:

            status = response.status

            content_type = (
                response.headers.get(
                    "Content-Type",
                    ""
                )
            )

            data = response.read()

            return (
                status,
                content_type,
                data
            )

    except ssl.SSLError as e:

        raise RuntimeError(
            f"SSL ERROR: {e}"
        )

    except URLError as e:

        reason = getattr(
            e,
            "reason",
            e
        )

        raise RuntimeError(
            f"CONNECTION ERROR: {reason}"
        )


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(text):

    if not TELEGRAM_BOT_TOKEN:

        print(
            "⚠️ TELEGRAM_BOT_TOKEN NOT FOUND"
        )

        return False

    if not TELEGRAM_CHAT_ID:

        print(
            "⚠️ TELEGRAM_CHAT_ID NOT FOUND"
        )

        return False

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}"
        "/sendMessage"
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
                "Content-Type":
                    "application/json",
                "User-Agent":
                    "ATI-Bourse-V2.4",
            },
            method="POST"
        )

        with urlopen(
            req,
            timeout=20
        ) as response:

            return response.status == 200

    except Exception as e:

        print(
            "⚠️ TELEGRAM ERROR:",
            type(e).__name__,
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

        text = str(value).strip()

        if not text:
            return None

        text = (
            text
            .replace(",", "")
            .replace("٬", "")
            .replace("٫", ".")
        )

        return float(text)

    except Exception:

        return None


# ============================================================
# JSON EXTRACTION
# ============================================================

def extract_rows(obj, depth=0):

    if depth > 8:
        return []

    if isinstance(obj, list):

        return obj

    if not isinstance(obj, dict):

        return []

    preferred = [

        "marketwatch",
        "marketWatch",
        "MarketWatch",

        "data",
        "Data",

        "items",
        "Items",

        "rows",
        "Rows",

        "result",
        "Result",

    ]

    for key in preferred:

        value = obj.get(key)

        if (
            isinstance(value, list)
            and value
        ):

            return value

    for value in obj.values():

        if isinstance(
            value,
            dict
        ):

            result = extract_rows(
                value,
                depth + 1
            )

            if result:

                return result

        elif isinstance(
            value,
            list
        ):

            if value:

                return value

    return []


# ============================================================
# NORMALIZE JSON ROW
# ============================================================

def normalize_json_row(row):

    if not isinstance(
        row,
        dict
    ):

        return None

    # --------------------------------------------------------
    # SYMBOL
    # --------------------------------------------------------

    symbol = ""

    for key in [

        "lVal18AFC",
        "symbol",
        "Symbol",
        "tseSymbol",
        "TseSymbol",
        "lVal18",
        "insCode",
        "InsCode",

    ]:

        value = row.get(key)

        if value not in (
            None,
            ""
        ):

            symbol = str(
                value
            ).strip()

            break

    # --------------------------------------------------------
    # NAME
    # --------------------------------------------------------

    name = ""

    for key in [

        "lVal30",
        "name",
        "Name",
        "companyName",
        "CompanyName",
        "title",
        "Title",

    ]:

        value = row.get(key)

        if value not in (
            None,
            ""
        ):

            name = str(
                value
            ).strip()

            break

    # --------------------------------------------------------
    # LAST PRICE
    # --------------------------------------------------------

    last = None

    for key in [

        "pl",
        "pDrCotVal",
        "last",
        "lastPrice",
        "Last",
        "LastPrice",
        "price",
        "Price",

    ]:

        value = to_float(
            row.get(key)
        )

        if value is not None:

            last = value
            break

    # --------------------------------------------------------
    # CLOSE
    # --------------------------------------------------------

    close = None

    for key in [

        "pc",
        "pClosing",
        "close",
        "closePrice",
        "Close",
        "ClosePrice",

    ]:

        value = to_float(
            row.get(key)
        )

        if value is not None:

            close = value
            break

    # --------------------------------------------------------
    # YESTERDAY
    # --------------------------------------------------------

    yesterday = None

    for key in [

        "py",
        "priceYesterday",
        "yesterday",
        "yesterdayPrice",
        "pClosingYesterday",

    ]:

        value = to_float(
            row.get(key)
        )

        if value is not None:

            yesterday = value
            break

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    volume = 0

    for key in [

        "qTotTran5J",
        "volume",
        "Volume",
        "volumeTotal",
        "vol",
        "Vol",

    ]:

        value = to_float(
            row.get(key)
        )

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

    # --------------------------------------------------------
    # CHANGE
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

        "symbol": symbol,

        "name": (
            name
            or symbol
        ),

        "last": last,

        "close": close,

        "yesterday": yesterday,

        "volume": volume,

        "pct": pct,

    }


# ============================================================
# FETCH JSON SOURCE
# ============================================================

def fetch_json_source(
    source_name,
    url
):

    print()
    print(
        "🔎 SOURCE:",
        source_name
    )

    print(
        "🌐",
        url
    )

    try:

        status, content_type, data = (
            http_get(url)
        )

        print(
            "📡 HTTP:",
            status
        )

        print(
            "📦 CONTENT:",
            content_type
        )

        if status != 200:

            return [], (
                f"{source_name}: "
                f"HTTP {status}"
            )

        if not data:

            return [], (
                f"{source_name}: "
                f"EMPTY RESPONSE"
            )

        text = data.decode(
            "utf-8",
            errors="replace"
        ).strip()

        # ----------------------------------------------------
        # BLOCK DETECTION
        # ----------------------------------------------------

        low = text.lower()

        if (
            "دسترسی شما" in text
            or "مسدود" in text
            or "general error" in low
        ):

            return [], (
                f"{source_name}: "
                "TSETMC BLOCKED RESPONSE"
            )

        # ----------------------------------------------------
        # JSON
        # ----------------------------------------------------

        try:

            obj = json.loads(
                text
            )

        except Exception:

            return [], (
                f"{source_name}: "
                "NON-JSON RESPONSE"
            )

        rows = extract_rows(
            obj
        )

        print(
            "📊 RAW ROWS:",
            len(rows)
        )

        result = []

        seen = set()

        for row in rows:

            item = normalize_json_row(
                row
            )

            if not item:
                continue

            key = (
                item["symbol"]
                or item["name"]
            ).strip()

            if not key:
                continue

            if key in seen:
                continue

            seen.add(key)

            result.append(
                item
            )

        print(
            "✅ VALID:",
            len(result)
        )

        if result:

            return result, None

        return [], (
            f"{source_name}: "
            "NO USABLE ROWS"
        )

    except Exception as e:

        return [], (
            f"{source_name}: "
            f"{e}"
        )


# ============================================================
# EXCEL PARSER
# ============================================================

def parse_excel_bytes(data):

    # --------------------------------------------------------
    # Try openpyxl
    # --------------------------------------------------------

    try:

        from openpyxl import (
            load_workbook
        )

        workbook = load_workbook(
            filename=io.BytesIO(data),
            read_only=True,
            data_only=True
        )

        sheet = workbook.active

        rows = list(
            sheet.iter_rows(
                values_only=True
            )
        )

        if not rows:

            return []

        # Find first non-empty row
        header_index = None

        for i, row in enumerate(
            rows[:20]
        ):

            values = [
                str(x).strip()
                if x is not None
                else ""
                for x in row
            ]

            joined = " ".join(
                values
            )

            if (
                "نماد" in joined
                or "Symbol" in joined
                or "آخرین" in joined
            ):

                header_index = i
                break

        if header_index is None:

            header_index = 0

        headers = [
            str(x).strip()
            if x is not None
            else ""
            for x in rows[
                header_index
            ]
        ]

        result = []

        for row in rows[
            header_index + 1:
        ]:

            record = {}

            for i, value in enumerate(
                row
            ):

                if i < len(headers):

                    key = headers[i]

                    if key:

                        record[key] = value

            if record:

                result.append(
                    record
                )

        return normalize_excel_records(
            result
        )

    except ImportError:

        raise RuntimeError(
            "OPENPYXL NOT INSTALLED"
        )

    except Exception as e:

        raise RuntimeError(
            f"EXCEL PARSE ERROR: {e}"
        )


# ============================================================
# NORMALIZE EXCEL
# ============================================================

def normalize_excel_records(
    records
):

    result = []

    for row in records:

        if not isinstance(
            row,
            dict
        ):

            continue

        symbol = ""
        name = ""

        last = None
        close = None
        yesterday = None
        volume = 0

        for key, value in row.items():

            k = str(
                key
            ).strip().lower()

            # symbol
            if (
                not symbol
                and (
                    "نماد" in k
                    or "symbol" in k
                )
            ):

                symbol = str(
                    value or ""
                ).strip()

            # name
            if (
                not name
                and (
                    "نام" in k
                    or "name" in k
                )
            ):

                name = str(
                    value or ""
                ).strip()

            # last
            if last is None and (
                "آخرین" in k
                or "last" in k
                or "قیمت" in k
            ):

                last = to_float(
                    value
                )

            # close
            if close is None and (
                "پایانی" in k
                or "close" in k
            ):

                close = to_float(
                    value
                )

            # yesterday
            if yesterday is None and (
                "دیروز" in k
                or "yesterday" in k
            ):

                yesterday = to_float(
                    value
                )

            # volume
            if (
                volume == 0
                and (
                    "حجم" in k
                    or "volume" in k
                )
            ):

                volume = (
                    to_float(value)
                    or 0
                )

        if last is None:

            last = close

        if close is None:

            close = last

        if last is None:
            continue

        if last <= 0:
            continue

        pct = 0.0

        if (
            yesterday
            and yesterday > 0
        ):

            pct = (
                (last - yesterday)
                / yesterday
            ) * 100

        result.append({

            "symbol": symbol,

            "name": (
                name
                or symbol
            ),

            "last": last,

            "close": close,

            "yesterday": yesterday,

            "volume": volume,

            "pct": pct,

        })

    return result


# ============================================================
# FETCH EXCEL
# ============================================================

def fetch_excel_source(
    source_name,
    url
):

    print()
    print(
        "🔎 EXCEL SOURCE:",
        source_name
    )

    try:

        status, content_type, data = (
            http_get(url)
        )

        print(
            "📡 HTTP:",
            status
        )

        print(
            "📦 BYTES:",
            len(data)
        )

        if status != 200:

            return [], (
                f"{source_name}: "
                f"HTTP {status}"
            )

        if not data:

            return [], (
                f"{source_name}: "
                "EMPTY RESPONSE"
            )

        result = parse_excel_bytes(
            data
        )

        print(
            "✅ EXCEL VALID:",
            len(result)
        )

        if result:

            return result, None

        return [], (
            f"{source_name}: "
            "NO USABLE EXCEL ROWS"
        )

    except Exception as e:

        return [], (
            f"{source_name}: {e}"
        )


# ============================================================
# FETCH MARKET
# ============================================================

def fetch_market():

    errors = []

    # --------------------------------------------------------
    # JSON SOURCES
    # --------------------------------------------------------

    for source_name, url in JSON_SOURCES:

        rows, error = (
            fetch_json_source(
                source_name,
                url
            )
        )

        if rows:

            return (
                source_name,
                rows,
                errors
            )

        if error:

            errors.append(
                error
            )

        time.sleep(1)

    # --------------------------------------------------------
    # EXCEL SOURCES
    # --------------------------------------------------------

    for source_name, url in EXCEL_SOURCES:

        rows, error = (
            fetch_excel_source(
                source_name,
                url
            )
        )

        if rows:

            return (
                source_name,
                rows,
                errors
            )

        if error:

            errors.append(
                error
            )

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

    # Momentum
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

    # Strong negative
    if pct <= -5:

        score -= 4

    elif pct <= -3:

        score -= 2

    # Volume
    if volume >= 50_000_000:

        score += 3

    elif volume >= 10_000_000:

        score += 2

    elif volume >= 1_000_000:

        score += 1

    return score


# ============================================================
# SELECT CANDIDATES
# ============================================================

def select_candidates(rows):

    valid = []

    seen = set()

    for item in rows:

        symbol = str(
            item.get(
                "symbol",
                ""
            )
        ).strip()

        name = str(
            item.get(
                "name",
                ""
            )
        ).strip()

        if not symbol and not name:
            continue

        key = (
            symbol
            or name
        )

        if key in seen:
            continue

        seen.add(key)

        text = (
            f"{symbol} {name}"
            .lower()
        )

        # Skip indexes
        if "شاخص" in text:
            continue

        if "index" in text:
            continue

        item["score"] = (
            score_stock(item)
        )

        valid.append(
            item
        )

    valid.sort(
        key=lambda x: (
            x.get(
                "score",
                0
            ),
            x.get(
                "pct",
                0
            ),
            x.get(
                "volume",
                0
            ),
        ),
        reverse=True
    )

    return valid[
        :MAX_SYMBOLS
    ]


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
    total
):

    lines = [

        "💓 ATI BOURSE ALIVE",

        f"⚡ {BOT_VERSION}",

        "📊 بورس ایران",

        "🔑 BRS_API_KEY: NOT REQUIRED",

        "🔒 REAL TRADING: OFF",

        f"🕐 {now_utc()}",

        "",

        f"✅ DATA SOURCE: {source}",

        f"📈 RAW MARKET ROWS: {total}",

        f"📊 VALID SYMBOLS: {len(candidates)}",

        "",

        "🔥 TOP MARKET MOMENTUM",

        "",
    ]

    top = candidates[:10]

    for i, item in enumerate(
        top,
        1
    ):

        symbol = (
            item.get(
                "symbol"
            )
            or item.get(
                "name"
            )
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

        price = format_price(
            item.get(
                "last"
            )
        )

        sign = (
            "+"
            if pct >= 0
            else ""
        )

        lines.append(
            f"{i}️⃣ {symbol}\n"
            f"   💰 {price}"
            f" | 📊 {sign}{pct:.2f}%"
            f" | ⭐ {score}"
        )

    lines.extend([

        "",

        "⚠️ این نسخه فقط داده بازار را می‌خواند.",

        "🚫 هیچ سفارش خرید/فروشی ارسال نمی‌شود.",

        "🔑 BRS_API_KEY لازم نیست.",

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

    if errors:

        for error in errors:

            lines.append(
                f"• {error}"
            )

    else:

        lines.append(
            "• UNKNOWN ERROR"
        )

    lines.extend([

        "",

        "💡 نسخه V2.4 چند مسیر عمومی TSETMC را امتحان کرد.",

        f"🕐 {now_utc()}",

    ])

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 65)

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

    print("=" * 65)

    source, rows, errors = (
        fetch_market()
    )

    # --------------------------------------------------------
    # ERROR
    # --------------------------------------------------------

    if not rows:

        report = (
            build_error_report(
                errors
            )
        )

        print()
        print(report)
        print()

        telegram_send(
            report
        )

        return 0

    # --------------------------------------------------------
    # CANDIDATES
    # --------------------------------------------------------

    candidates = (
        select_candidates(
            rows
        )
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
