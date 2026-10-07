# ============================================================
# ATI BOURSE BOT V4
# Public market-data scanner
# NO BRS_API_KEY
# REAL TRADING = OFF
# ============================================================

import os
import io
import csv
import json
import time
import math
import statistics
from datetime import datetime, timezone

import requests


# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

VERSION = "ATI-BOURSE-V4.0"

REAL_TRADING = False
BRS_API_KEY = ""

TIMEOUT = 12
RETRIES = 2

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


# ------------------------------------------------------------
# HTTP SESSION
# ------------------------------------------------------------

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/140 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
})


# ------------------------------------------------------------
# TELEGRAM
# ------------------------------------------------------------

def telegram_send(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not configured")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }

    try:
        r = SESSION.post(url, json=payload, timeout=15)

        if r.ok:
            return True

        print("Telegram error:", r.status_code, r.text[:300])
        return False

    except Exception as e:
        print("Telegram exception:", repr(e))
        return False


# ------------------------------------------------------------
# SAFE REQUEST
# ------------------------------------------------------------

def http_get(url, params=None, headers=None, timeout=TIMEOUT):

    last_error = ""

    for attempt in range(RETRIES + 1):

        try:

            r = SESSION.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout,
            )

            if r.status_code == 200 and r.content:

                return r

            last_error = f"HTTP {r.status_code}"

        except requests.exceptions.Timeout:
            last_error = "TIMEOUT"

        except requests.exceptions.ConnectionError as e:
            last_error = f"CONNECTION ERROR: {e}"

        except Exception as e:
            last_error = f"ERROR: {e}"

        if attempt < RETRIES:
            time.sleep(1)

    return None


# ------------------------------------------------------------
# SOURCE 1
# TSETMC CDN MARKETWATCH
# ------------------------------------------------------------

def source_tsetmc_cdn():

    diagnostics = []

    urls = [
        "https://cdn.tsetmc.com/api/MarketData/GetMarketWatch",
        "https://cdn.tsetmc.com/api/MarketData/GetMarketWatch?market=0",
    ]

    for url in urls:

        r = http_get(url)

        if r is None:
            diagnostics.append(f"CDN {url}: FAILED")
            continue

        try:

            data = r.json()

            if data:
                return data, "TSETMC-CDN", diagnostics

            diagnostics.append(
                f"CDN {url}: EMPTY"
            )

        except Exception as e:

            diagnostics.append(
                f"CDN {url}: JSON ERROR {e}"
            )

    return None, None, diagnostics


# ------------------------------------------------------------
# SOURCE 2
# OLD TSETMC MARKETWATCHPLUS
# ------------------------------------------------------------

def source_marketwatch_plus():

    diagnostics = []

    urls = [
        "https://old.tsetmc.com/tsev2/excel/MarketWatchPlus.aspx?d=0",
        "https://old.tsetmc.com/tsev2/excel/MarketWatchPlus.aspx?d=0&format=0",
    ]

    for url in urls:

        r = http_get(url, timeout=15)

        if r is None:
            diagnostics.append(
                f"MarketWatchPlus {url}: FAILED"
            )
            continue

        content_type = r.headers.get(
            "content-type",
            ""
        ).lower()

        data = r.content

        # XLS / XLSX signature
        if (
            data.startswith(b"PK")
            or data.startswith(b"\xd0\xcf\x11\xe0")
            or "excel" in content_type
            or "spreadsheet" in content_type
        ):

            return data, "TSETMC-MARKETWATCHPLUS", diagnostics

        diagnostics.append(
            f"MarketWatchPlus {url}: INVALID FILE"
        )

    return None, None, diagnostics


# ------------------------------------------------------------
# SOURCE 3
# JINA READER
# ------------------------------------------------------------

def source_jina(url):

    jina_url = "https://r.jina.ai/" + url

    r = http_get(
        jina_url,
        timeout=20,
    )

    if r is None:
        return None

    if r.status_code == 200 and r.text:
        return r.text

    return None


# ------------------------------------------------------------
# PARSE MARKETWATCHPLUS
# ------------------------------------------------------------

def parse_marketwatchplus(raw):

    """
    Attempts to read the legacy MarketWatchPlus export.

    We deliberately keep this parser tolerant because
    column positions can change between TSETMC versions.
    """

    try:

        # First try pandas if available.
        import pandas as pd

        bio = io.BytesIO(raw)

        sheets = pd.read_excel(
            bio,
            sheet_name=0,
            header=None,
        )

        rows = sheets.values.tolist()

        if not rows:
            return []

        return parse_rows(rows)

    except Exception as e:

        print(
            "⚠️ Excel parser unavailable/failed:",
            repr(e)
        )

        return []


# ------------------------------------------------------------
# GENERIC ROW PARSER
# ------------------------------------------------------------

def parse_rows(rows):

    results = []

    for row in rows:

        if not row:
            continue

        values = []

        for x in row:

            if x is None:
                values.append("")

            else:
                values.append(str(x).strip())

        # Need a symbol-like field.
        symbol = ""

        for value in values:

            if (
                value
                and len(value) <= 30
                and not value.replace(".", "", 1).isdigit()
                and not value.startswith("http")
            ):

                symbol = value
                break

        if not symbol:
            continue

        # Extract numeric values.
        nums = []

        for value in values:

            try:

                clean = (
                    value
                    .replace(",", "")
                    .replace("٬", "")
                    .replace("%", "")
                    .strip()
                )

                if clean:
                    n = float(clean)

                    if math.isfinite(n):
                        nums.append(n)

            except Exception:
                pass

        if len(nums) < 2:
            continue

        last_price = nums[-1]

        if last_price <= 0:
            continue

        results.append({
            "symbol": symbol,
            "price": last_price,
            "numbers": nums,
        })

    return results


# ------------------------------------------------------------
# NORMALIZE CDN JSON
# ------------------------------------------------------------

def normalize_cdn(data):

    output = []

    def walk(obj):

        if isinstance(obj, dict):

            # Search recursively.
            for key, value in obj.items():

                if isinstance(value, list):

                    for item in value:

                        if isinstance(item, dict):
                            parse_dict(item)

                elif isinstance(value, dict):
                    walk(value)

        elif isinstance(obj, list):

            for item in obj:

                if isinstance(item, dict):
                    parse_dict(item)

    def parse_dict(item):

        symbol = (
            item.get("lVal18AFC")
            or item.get("symbol")
            or item.get("Symbol")
            or item.get("insCode")
            or item.get("instrument")
            or item.get("name")
        )

        price = (
            item.get("pClosing")
            or item.get("pDrCotVal")
            or item.get("lastPrice")
            or item.get("price")
        )

        change = (
            item.get("percent")
            or item.get("changePercent")
            or item.get("percentChange")
        )

        volume = (
            item.get("qTotTran5J")
            or item.get("volume")
            or item.get("Volume")
        )

        try:

            if price is None:
                return

            price = float(price)

            if price <= 0:
                return

        except Exception:
            return

        output.append({
            "symbol": str(symbol or ""),
            "price": price,
            "change": safe_float(change),
            "volume": safe_float(volume),
        })

    walk(data)

    return output


# ------------------------------------------------------------
# SAFE FLOAT
# ------------------------------------------------------------

def safe_float(value):

    try:

        if value is None:
            return 0.0

        return float(
            str(value)
            .replace(",", "")
            .replace("%", "")
            .strip()
        )

    except Exception:
        return 0.0


# ------------------------------------------------------------
# MARKET DATA
# ------------------------------------------------------------

def get_market():

    diagnostics = []

    # SOURCE 1
    try:

        data, source, diag = source_tsetmc_cdn()

        diagnostics.extend(diag)

        if data:

            normalized = normalize_cdn(data)

            if normalized:

                return normalized, source, diagnostics

    except Exception as e:

        diagnostics.append(
            f"CDN exception: {e}"
        )

    # SOURCE 2
    try:

        raw, source, diag = source_marketwatch_plus()

        diagnostics.extend(diag)

        if raw:

            normalized = parse_marketwatchplus(raw)

            if normalized:

                return normalized, source, diagnostics

    except Exception as e:

        diagnostics.append(
            f"MarketWatchPlus exception: {e}"
        )

    return [], None, diagnostics


# ------------------------------------------------------------
# FILTER
# ------------------------------------------------------------

def clean_market(items):

    clean = []

    for item in items:

        symbol = str(
            item.get("symbol", "")
        ).strip()

        price = safe_float(
            item.get("price")
        )

        if not symbol:
            continue

        if price <= 0:
            continue

        # Ignore obvious non-stock rows.
        bad_words = [
            "شاخص",
            "ارزش",
            "تعداد",
            "بازار",
            "Market",
            "Index",
        ]

        if any(
            word.lower() in symbol.lower()
            for word in bad_words
        ):
            continue

        item["price"] = price

        clean.append(item)

    return clean


# ------------------------------------------------------------
# SIMPLE MOMENTUM SCORE
# ------------------------------------------------------------

def score_item(item):

    score = 0.0

    change = safe_float(
        item.get("change")
    )

    volume = safe_float(
        item.get("volume")
    )

    # Positive price movement.
    if change > 0:
        score += min(change * 2.0, 20)

    if change >= 2:
        score += 5

    if change >= 4:
        score += 5

    # Volume bonus.
    if volume > 0:
        score += 2

    item["score"] = round(score, 2)

    return item


# ------------------------------------------------------------
# SELECT TOP SYMBOLS
# ------------------------------------------------------------

def select_symbols(items, limit=10):

    scored = []

    for item in items:

        try:
            scored.append(
                score_item(dict(item))
            )

        except Exception:
            continue

    scored.sort(
        key=lambda x: x.get("score", 0),
        reverse=True,
    )

    return scored[:limit]


# ------------------------------------------------------------
# TELEGRAM REPORT
# ------------------------------------------------------------

def build_report(items, source):

    now = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "💓 ATI BOURSE ALIVE",
        f"⚡ {VERSION}",
        "📊 بورس و فرابورس ایران",
        f"📡 SOURCE: {source}",
        "🔑 BRS_API_KEY: NOT USED",
        "🔒 REAL TRADING: OFF",
        "",
    ]

    if not items:

        lines.extend([
            "⚠️ سهم قابل‌اعتماد پیدا نشد.",
            "",
            f"🕐 {now}",
        ])

        return "\n".join(lines)

    lines.append(
        f"📈 TOP {len(items)} CANDIDATES"
    )

    lines.append("")

    for i, item in enumerate(items, 1):

        symbol = item.get(
            "symbol",
            "UNKNOWN"
        )

        price = item.get(
            "price",
            0
        )

        change = item.get(
            "change",
            0
        )

        score = item.get(
            "score",
            0
        )

        lines.append(
            f"{i}️⃣ {symbol}\n"
            f"   💰 قیمت: {price:g}\n"
            f"   📈 تغییر: {change:.2f}%\n"
            f"   🎯 Score: {score:g}"
        )

    lines.extend([
        "",
        "⚠️ این خروجی فقط اسکن بازار است.",
        "🚫 هیچ سفارش خرید/فروشی ارسال نمی‌شود.",
        "",
        f"🕐 {now}",
    ])

    return "\n".join(lines)


# ------------------------------------------------------------
# DIAGNOSTIC ERROR
# ------------------------------------------------------------

def build_error(diagnostics):

    now = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "❌ ATI BOURSE ERROR",
        "",
        "هیچ داده عمومی معتبری از بازار دریافت نشد.",
        "",
        "🔑 BRS_API_KEY استفاده نمی‌شود.",
        "🔒 REAL TRADING: OFF",
        "",
        "📋 DIAGNOSTIC:",
    ]

    # Only show useful unique diagnostics.
    seen = set()

    for d in diagnostics:

        d = str(d).strip()

        if not d:
            continue

        if d in seen:
            continue

        seen.add(d)

        lines.append(
            f"• {d}"
        )

        if len(seen) >= 10:
            break

    lines.extend([
        "",
        "🔁 ATI V4 چند منبع عمومی را امتحان کرد.",
        "⚠️ اگر همه منابع TIMEOUT باشند، مشکل دسترسی شبکه/IP است؛ نه API Key.",
        "",
        f"🕐 {now}",
    ])

    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    print("=" * 60)
    print(f"ATI BOURSE {VERSION}")
    print("=" * 60)

    print("🔑 BRS_API_KEY: NOT USED")
    print("🔒 REAL TRADING: OFF")
    print("📡 Starting market scan...")

    items, source, diagnostics = get_market()

    items = clean_market(items)

    print(
        f"📊 Raw/clean items: {len(items)}"
    )

    if not items:

        message = build_error(
            diagnostics
        )

        print(message)
        telegram_send(message)

        return 0

    selected = select_symbols(
        items,
        limit=10,
    )

    message = build_report(
        selected,
        source or "UNKNOWN",
    )

    print(message)

    telegram_send(message)

    return 0


if __name__ == "__main__":

    try:

        raise SystemExit(
            main()
        )

    except Exception as e:

        error = (
            "🚨 ATI BOURSE FATAL ERROR\n\n"
            f"{type(e).__name__}: {e}\n\n"
            "🔒 REAL TRADING: OFF"
        )

        print(error)

        telegram_send(error)

        raise
