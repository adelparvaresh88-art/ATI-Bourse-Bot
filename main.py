# ============================================================
# ATI BOURSE BOT V3
# NO BRS_API_KEY
# TSETMC + JINA READER FALLBACK
# READ-ONLY / NO REAL TRADING
# ============================================================

import os
import re
import json
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests


# ============================================================
# CONFIG
# ============================================================

BOT_VERSION = "ATI-BOURSE-V3-NO-APIKEY-JINA"

REAL_TRADING = False

TIMEOUT = 25
MAX_SYMBOLS = 80

TELEGRAM_TOKEN = (
    os.getenv("BOURSE_TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_BOT_TOKEN")
    or ""
)

TELEGRAM_CHAT_ID = (
    os.getenv("BOURSE_TELEGRAM_CHAT_ID")
    or os.getenv("TELEGRAM_CHAT_ID")
    or ""
)


# ============================================================
# HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Connection": "close",
}


JINA_HEADERS = {
    "User-Agent": "ATI-Bourse-Bot/3.0",
    "Accept": "application/json",
    "X-No-Cache": "true",
    "X-Engine": "direct",
}


# ============================================================
# TSETMC SOURCES
# ============================================================

DIRECT_SOURCES = [
    (
        "TSETMC CDN MarketWatch",
        "https://cdn.tsetmc.com/api/MarketWatch"
    ),
    (
        "TSETMC CDN GetMarketWatch",
        "https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch"
    ),
    (
        "TSETMC Legacy MarketWatch",
        "https://old.tsetmc.com/tsev2/excel/MarketWatchPlus.aspx?d=0"
    ),
]


# JINA PROXY SOURCES
JINA_SOURCES = [
    (
        "JINA -> TSETMC CDN MarketWatch",
        "https://r.jina.ai/https://cdn.tsetmc.com/api/MarketWatch"
    ),
    (
        "JINA -> TSETMC GetMarketWatch",
        "https://r.jina.ai/https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch"
    ),
    (
        "JINA -> TSETMC Legacy MarketWatch",
        "https://r.jina.ai/http://old.tsetmc.com/tsev2/excel/MarketWatchPlus.aspx?d=0"
    ),
]


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = (
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }

    try:
        r = requests.post(
            url,
            json=payload,
            timeout=20,
        )

        return r.ok

    except Exception:
        return False


# ============================================================
# NUMBER HELPERS
# ============================================================

def clean_number(value):

    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return None

    text = str(value).strip()

    if not text:
        return None

    text = (
        text.replace(",", "")
        .replace("٬", "")
        .replace("،", "")
        .replace("%", "")
        .strip()
    )

    # Persian / Arabic digits
    trans = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )

    text = text.translate(trans)

    try:
        return float(text)
    except Exception:
        return None


def first_number(obj, keys):

    if not isinstance(obj, dict):
        return None

    lower = {
        str(k).lower(): v
        for k, v in obj.items()
    }

    for key in keys:

        if key.lower() in lower:
            value = clean_number(lower[key.lower()])

            if value is not None:
                return value

    return None


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    return str(value).strip()


def find_first_text(obj, keys):

    if not isinstance(obj, dict):
        return ""

    lower = {
        str(k).lower(): v
        for k, v in obj.items()
    }

    for key in keys:

        if key.lower() in lower:

            value = lower[key.lower()]

            if isinstance(value, str):
                value = value.strip()

                if value:
                    return value

    return ""


# ============================================================
# JSON EXTRACTION
# ============================================================

def extract_json_from_text(text):

    if not text:
        return None

    text = text.strip()

    # Direct JSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # Markdown code block
    text2 = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text2 = re.sub(
        r"\s*```$",
        "",
        text2
    )

    try:
        return json.loads(text2)
    except Exception:
        pass

    # Find first object
    start_obj = text.find("{")
    end_obj = text.rfind("}")

    if start_obj >= 0 and end_obj > start_obj:

        candidate = text[start_obj:end_obj + 1]

        try:
            return json.loads(candidate)
        except Exception:
            pass

    # Find first array
    start_arr = text.find("[")
    end_arr = text.rfind("]")

    if start_arr >= 0 and end_arr > start_arr:

        candidate = text[start_arr:end_arr + 1]

        try:
            return json.loads(candidate)
        except Exception:
            pass

    return None


# ============================================================
# RECURSIVE RECORD EXTRACTION
# ============================================================

def recursive_records(obj):

    records = []

    if isinstance(obj, list):

        for item in obj:

            if isinstance(item, dict):

                records.append(item)

                records.extend(
                    recursive_records(item)
                )

            elif isinstance(item, list):

                records.extend(
                    recursive_records(item)
                )

        return records

    if isinstance(obj, dict):

        for value in obj.values():

            if isinstance(value, (list, dict)):

                records.extend(
                    recursive_records(value)
                )

    return records


# ============================================================
# SYMBOL NORMALIZATION
# ============================================================

NAME_KEYS = [
    "lVal18AFC",
    "lVal18",
    "symbol",
    "Symbol",
    "ticker",
    "Ticker",
    "shortName",
    "shortname",
    "name",
    "Name",
    "instrumentName",
]

FULL_NAME_KEYS = [
    "lVal30",
    "name",
    "Name",
    "instrumentName",
    "companyName",
]

LAST_PRICE_KEYS = [
    "pDrCotVal",
    "lastPrice",
    "last",
    "price",
    "close",
    "Close",
    "lastTradePrice",
]

YESTERDAY_KEYS = [
    "priceYesterday",
    "pClosing",
    "yesterday",
    "previousClose",
    "prevClose",
]

HIGH_KEYS = [
    "pMax",
    "maxPrice",
    "high",
    "High",
]

LOW_KEYS = [
    "pMin",
    "minPrice",
    "low",
    "Low",
]

VOLUME_KEYS = [
    "qTotTran5J",
    "qTotVol",
    "volume",
    "Volume",
    "tradeVolume",
]

VALUE_KEYS = [
    "qTotCap",
    "value",
    "Value",
    "tradeValue",
]

TRADE_COUNT_KEYS = [
    "zTotTran",
    "tradeCount",
    "transactions",
    "count",
]


def normalize_record(row):

    if not isinstance(row, dict):
        return None

    symbol = find_first_text(
        row,
        NAME_KEYS
    )

    full_name = find_first_text(
        row,
        FULL_NAME_KEYS
    )

    last_price = first_number(
        row,
        LAST_PRICE_KEYS
    )

    yesterday = first_number(
        row,
        YESTERDAY_KEYS
    )

    high = first_number(
        row,
        HIGH_KEYS
    )

    low = first_number(
        row,
        LOW_KEYS
    )

    volume = first_number(
        row,
        VOLUME_KEYS
    )

    value = first_number(
        row,
        VALUE_KEYS
    )

    trades = first_number(
        row,
        TRADE_COUNT_KEYS
    )

    # Need at least symbol + price
    if not symbol or last_price is None:
        return None

    if yesterday and yesterday > 0:

        change_pct = (
            (last_price - yesterday)
            / yesterday
            * 100
        )

    else:

        change_pct = first_number(
            row,
            [
                "percent",
                "changePercent",
                "priceChangePercent",
                "xVarPClosing",
            ]
        )

    if change_pct is None:
        change_pct = 0.0

    return {
        "symbol": symbol,
        "name": full_name or symbol,
        "last": last_price,
        "yesterday": yesterday or 0,
        "high": high or 0,
        "low": low or 0,
        "volume": volume or 0,
        "value": value or 0,
        "trades": trades or 0,
        "change_pct": change_pct,
    }


# ============================================================
# MARKET DATA PARSER
# ============================================================

def parse_market_data(data):

    if data is None:
        return []

    rows = recursive_records(data)

    result = []

    seen = set()

    for row in rows:

        item = normalize_record(row)

        if not item:
            continue

        symbol = item["symbol"]

        if symbol in seen:
            continue

        seen.add(symbol)

        result.append(item)

    # Sometimes source has direct list
    if not result and isinstance(data, list):

        for row in data:

            item = normalize_record(row)

            if item:

                symbol = item["symbol"]

                if symbol not in seen:

                    seen.add(symbol)
                    result.append(item)

    return result


# ============================================================
# DIRECT FETCH
# ============================================================

def fetch_direct(url):

    try:

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        if not r.ok:

            return None, (
                f"HTTP {r.status_code}"
            )

        content_type = (
            r.headers.get(
                "content-type",
                ""
            ).lower()
        )

        # JSON
        if (
            "json" in content_type
            or r.text.lstrip().startswith("{")
            or r.text.lstrip().startswith("[")
        ):

            try:
                data = r.json()

                return data, "OK"

            except Exception:
                pass

        # Excel / binary
        if (
            "excel" in content_type
            or "spreadsheet" in content_type
            or url.lower().endswith(".aspx")
        ):

            return r.content, "BINARY"

        return r.text, "TEXT"

    except requests.exceptions.Timeout:

        return None, "TIMEOUT"

    except requests.exceptions.ConnectionError as e:

        return None, (
            f"CONNECTION ERROR: {str(e)[:120]}"
        )

    except Exception as e:

        return None, (
            f"ERROR: {str(e)[:120]}"
        )


# ============================================================
# JINA FETCH
# ============================================================

def fetch_jina(url):

    try:

        r = requests.get(
            url,
            headers=JINA_HEADERS,
            timeout=TIMEOUT + 10,
            allow_redirects=True,
        )

        if not r.ok:

            return None, (
                f"HTTP {r.status_code}"
            )

        raw = r.text

        # Jina JSON response
        try:

            wrapper = r.json()

            if isinstance(wrapper, dict):

                data = wrapper.get(
                    "data"
                )

                if isinstance(data, dict):

                    content = data.get(
                        "content"
                    )

                    if content:

                        parsed = (
                            extract_json_from_text(
                                content
                            )
                        )

                        if parsed is not None:
                            return parsed, "OK"

                        return content, "TEXT"

        except Exception:
            pass

        # Plain response
        parsed = extract_json_from_text(raw)

        if parsed is not None:

            return parsed, "OK"

        return raw, "TEXT"

    except requests.exceptions.Timeout:

        return None, "TIMEOUT"

    except requests.exceptions.ConnectionError as e:

        return None, (
            f"CONNECTION ERROR: {str(e)[:120]}"
        )

    except Exception as e:

        return None, (
            f"ERROR: {str(e)[:120]}"
        )


# ============================================================
# EXCEL PARSER
# ============================================================

def parse_excel_bytes(content):

    """
    Optional parser.

    Uses pandas only if available.
    GitHub Actions usually can install it if needed,
    but this bot does NOT require pandas for JSON/JINA.
    """

    if not isinstance(content, (bytes, bytearray)):
        return []

    try:

        import io
        import pandas as pd

        sheets = pd.read_excel(
            io.BytesIO(content),
            sheet_name=None,
            header=None,
        )

        result = []

        for _, df in sheets.items():

            for _, row in df.iterrows():

                values = list(row.values)

                if not values:
                    continue

                # Try to identify a symbol and prices
                text_values = [
                    str(x)
                    for x in values
                    if x is not None
                    and str(x) != "nan"
                ]

                if not text_values:
                    continue

                symbol = ""

                for value in text_values:

                    if (
                        len(value) <= 20
                        and not value.replace(
                            ".", "", 1
                        ).isdigit()
                    ):

                        symbol = value
                        break

                if not symbol:
                    continue

                numbers = []

                for value in values:

                    n = clean_number(value)

                    if n is not None:
                        numbers.append(n)

                if not numbers:
                    continue

                last = numbers[0]

                result.append(
                    {
                        "symbol": symbol,
                        "name": symbol,
                        "last": last,
                        "yesterday": 0,
                        "high": 0,
                        "low": 0,
                        "volume": 0,
                        "value": 0,
                        "trades": 0,
                        "change_pct": 0,
                    }
                )

        return result

    except Exception:
        return []


# ============================================================
# SOURCE RUNNER
# ============================================================

def try_source(
    name,
    url,
    is_jina=False,
):

    if is_jina:

        data, status = fetch_jina(url)

    else:

        data, status = fetch_direct(url)

    if data is None:

        return [], status

    # Excel
    if isinstance(data, (bytes, bytearray)):

        rows = parse_excel_bytes(data)

        if rows:

            return rows, "OK"

        return [], "EXCEL PARSE FAILED"

    rows = parse_market_data(data)

    if rows:

        return rows, f"OK ({len(rows)} rows)"

    # If Jina returned text, try JSON again
    if isinstance(data, str):

        parsed = extract_json_from_text(data)

        if parsed is not None:

            rows = parse_market_data(parsed)

            if rows:

                return rows, (
                    f"OK ({len(rows)} rows)"
                )

    return [], "NO VALID MARKET ROWS"


# ============================================================
# MARKET FETCH
# ============================================================

def get_market():

    diagnostics = []

    # --------------------------------------------------------
    # 1. JINA SOURCES FIRST
    # --------------------------------------------------------

    for name, url in JINA_SOURCES:

        rows, status = try_source(
            name,
            url,
            is_jina=True,
        )

        diagnostics.append(
            f"• {name}: {status}"
        )

        if rows:

            return rows, diagnostics, name

        # Avoid hammering the sources
        time.sleep(1)

    # --------------------------------------------------------
    # 2. DIRECT SOURCES
    # --------------------------------------------------------

    for name, url in DIRECT_SOURCES:

        rows, status = try_source(
            name,
            url,
            is_jina=False,
        )

        diagnostics.append(
            f"• {name}: {status}"
        )

        if rows:

            return rows, diagnostics, name

        time.sleep(1)

    return [], diagnostics, ""


# ============================================================
# FILTERS
# ============================================================

def is_valid_stock(item):

    symbol = item.get(
        "symbol",
        ""
    ).strip()

    if not symbol:
        return False

    if len(symbol) > 30:
        return False

    last = item.get(
        "last",
        0
    )

    if last <= 0:
        return False

    # Ignore obvious index rows
    bad_words = [
        "شاخص",
        "index",
        "کل",
        "هم وزن",
        "هم‌وزن",
    ]

    text = (
        symbol.lower()
        + " "
        + item.get(
            "name",
            ""
        ).lower()
    )

    for word in bad_words:

        if word.lower() in text:
            return False

    return True


# ============================================================
# SCORE
# ============================================================

def score_stock(item):

    score = 0.0

    change = item.get(
        "change_pct",
        0
    )

    volume = item.get(
        "volume",
        0
    )

    value = item.get(
        "value",
        0
    )

    trades = item.get(
        "trades",
        0
    )

    # Momentum
    if change >= 4:
        score += 40

    elif change >= 3:
        score += 34

    elif change >= 2:
        score += 28

    elif change >= 1:
        score += 18

    elif change > 0:
        score += 8

    elif change < -4:
        score -= 30

    elif change < -2:
        score -= 20

    elif change < 0:
        score -= 8

    # Volume
    if volume > 0:

        if volume >= 10_000_000:
            score += 20

        elif volume >= 1_000_000:
            score += 14

        elif volume >= 100_000:
            score += 8

        else:
            score += 3

    # Value
    if value > 0:

        if value >= 100_000_000_000:
            score += 20

        elif value >= 10_000_000_000:
            score += 14

        elif value >= 1_000_000_000:
            score += 8

    # Number of trades
    if trades > 10_000:
        score += 10

    elif trades > 2_000:
        score += 7

    elif trades > 500:
        score += 4

    return score


# ============================================================
# REPORT
# ============================================================

def make_report(
    rows,
    source_name,
):

    valid = [
        x
        for x in rows
        if is_valid_stock(x)
    ]

    for item in valid:

        item["score"] = score_stock(item)

    valid.sort(
        key=lambda x: (
            x["score"],
            x["change_pct"],
        ),
        reverse=True,
    )

    top = valid[:10]

    now = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    lines = []

    lines.append(
        "💓 ATI BOURSE ALIVE"
    )

    lines.append(
        f"⚡ {BOT_VERSION}"
    )

    lines.append(
        "📊 بورس و فرابورس ایران"
    )

    lines.append(
        "🔒 REAL TRADING: OFF"
    )

    lines.append(
        f"📡 SOURCE: {source_name}"
    )

    lines.append(
        f"📈 VALID SYMBOLS: {len(valid)}"
    )

    lines.append("")

    if not top:

        lines.append(
            "⚠️ نماد معتبر برای تحلیل پیدا نشد."
        )

    else:

        lines.append(
            "🔥 برترین نمادهای صعودی:"
        )

        for i, item in enumerate(
            top,
            start=1
        ):

            symbol = item["symbol"]

            change = item[
                "change_pct"
            ]

            price = item["last"]

            score = item["score"]

            lines.append(
                f"{i}️⃣ {symbol} | "
                f"💰 {price:,.0f} | "
                f"📈 {change:+.2f}% | "
                f"⭐ {score:.0f}"
            )

    lines.append("")

    lines.append(
        "⚠️ این خروجی سیگنال قطعی خرید نیست."
    )

    lines.append(
        f"🕐 {now}"
    )

    return "\n".join(lines)


# ============================================================
# ERROR REPORT
# ============================================================

def make_error_report(
    diagnostics
):

    now = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    lines = []

    lines.append(
        "❌ ATI BOURSE ERROR"
    )

    lines.append("")

    lines.append(
        "هیچ داده عمومی معتبری از بازار دریافت نشد."
    )

    lines.append("")

    lines.append(
        "🔑 BRS_API_KEY استفاده نمی‌شود."
    )

    lines.append(
        "🔒 REAL TRADING: OFF"
    )

    lines.append("")

    lines.append(
        "📋 DIAGNOSTIC:"
    )

    lines.extend(
        diagnostics
    )

    lines.append("")

    lines.append(
        "🔁 نسخه V3 ابتدا JINA → TSETMC "
        "و سپس TSETMC مستقیم را امتحان کرد."
    )

    lines.append(
        "🕐 " + now
    )

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "========================================"
    )

    print(
        f"ATI BOURSE {BOT_VERSION}"
    )

    print(
        "BRS_API_KEY: NOT USED"
    )

    print(
        "REAL TRADING: OFF"
    )

    print(
        "========================================"
    )

    rows, diagnostics, source = (
        get_market()
    )

    if not rows:

        message = make_error_report(
            diagnostics
        )

        print(message)

        telegram_send(message)

        return

    message = make_report(
        rows,
        source,
    )

    print(message)

    telegram_send(message)


if __name__ == "__main__":
    main()
