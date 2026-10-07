# ATI Bourse Bot - NO API KEY VERSION
# بورس ایران - بدون نیاز به BRS_API_KEY
# Public market data only. Real trading is intentionally OFF.

import os
import json
import time
import math
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BOT_VERSION = "ATI-BOURSE-V2.2-NO-APIKEY"

TELEGRAM_BOT_TOKEN = os.getenv("BOURSE_TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("BOURSE_TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")

# Safety: this version NEVER places real orders.
REAL_TRADING = False

TIMEOUT = 15
MAX_SYMBOLS = 80

# Public TSETMC endpoints. No API key is required.
SOURCES = [
    ("TSETMC MarketWatch", "https://cdn.tsetmc.com/api/MarketWatch"),
    ("TSETMC MarketWatch2", "https://cdn.tsetmc.com/api/MarketWatchPlus"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.tsetmc.com/",
}


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def http_get(url):
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def telegram_send(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram secrets not configured.")
        print(text)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }).encode()

    try:
        req = Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception as e:
        print(f"⚠️ Telegram error: {e}")
        return False


def to_float(value):
    try:
        if value is None or value == "":
            return None
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def extract_rows(obj):
    """Find list-like market rows inside different public TSETMC JSON shapes."""
    if isinstance(obj, list):
        return obj

    if not isinstance(obj, dict):
        return []

    preferred = [
        "marketWatch",
        "marketwatch",
        "data",
        "Data",
        "items",
        "Items",
        "instrument",
        "instruments",
        "rows",
        "Rows",
    ]

    for key in preferred:
        value = obj.get(key)
        if isinstance(value, list):
            return value

    # Recursive fallback, limited to avoid wandering through huge objects.
    for value in obj.values():
        if isinstance(value, dict):
            rows = extract_rows(value)
            if rows:
                return rows
        elif isinstance(value, list) and value and isinstance(value[0], (dict, list)):
            return value

    return []


def normalize_row(row):
    if not isinstance(row, dict):
        return None

    # Different public feeds may use different field names.
    symbol = (
        row.get("symbol")
        or row.get("Symbol")
        or row.get("tseSymbol")
        or row.get("insCode")
        or row.get("InsCode")
    )

    name = (
        row.get("name")
        or row.get("Name")
        or row.get("lVal18")
        or row.get("lVal30")
        or symbol
    )

    last = None
    close = None
    yesterday = None
    volume = None

    for k in ("last", "lastPrice", "pDrCotVal", "Last", "Price", "pl"):
        last = to_float(row.get(k))
        if last is not None:
            break

    for k in ("close", "closePrice", "pClosing", "Close", "pc"):
        close = to_float(row.get(k))
        if close is not None:
            break

    for k in ("yesterday", "yesterdayPrice", "priceYesterday", "pClosingYesterday", "py"):
        yesterday = to_float(row.get(k))
        if yesterday is not None:
            break

    for k in ("volume", "qTotTran5J", "volumeTotal", "vol", "Volume"):
        volume = to_float(row.get(k))
        if volume is not None:
            break

    # Some feeds use close as last price.
    if last is None:
        last = close

    if last is None:
        return None

    if close is None:
        close = last

    # Calculate percentage change.
    pct = None
    if yesterday and yesterday > 0:
        pct = ((last - yesterday) / yesterday) * 100

    return {
        "symbol": str(symbol or "").strip(),
        "name": str(name or "").strip(),
        "last": last,
        "close": close,
        "yesterday": yesterday,
        "volume": volume or 0,
        "pct": pct if pct is not None else 0,
    }


def fetch_market():
    errors = []

    for source_name, url in SOURCES:
        try:
            raw = http_get(url)
            obj = json.loads(raw)
            rows = extract_rows(obj)

            normalized = []
            for row in rows:
                item = normalize_row(row)
                if item and item["last"] > 0:
                    normalized.append(item)

            if normalized:
                return source_name, normalized, errors

            errors.append(f"{source_name}: no usable rows")

        except HTTPError as e:
            errors.append(f"{source_name}: HTTP {e.code}")
        except URLError as e:
            errors.append(f"{source_name}: connection error")
        except Exception as e:
            errors.append(f"{source_name}: {type(e).__name__}")

    return None, [], errors


def score_stock(x):
    pct = x.get("pct", 0)
    volume = x.get("volume", 0)

    score = 0

    # Positive momentum.
    if pct >= 4:
        score += 5
    elif pct >= 2:
        score += 4
    elif pct >= 1:
        score += 2
    elif pct > 0:
        score += 1

    # Avoid extreme negative moves.
    if pct < -5:
        score -= 4

    # Volume contributes only when it is available.
    if volume > 10_000_000:
        score += 2
    elif volume > 1_000_000:
        score += 1

    return score


def select_candidates(rows):
    valid = []

    for x in rows:
        symbol = x.get("symbol", "")
        name = x.get("name", "")

        if not symbol and not name:
            continue

        # Skip obvious index/non-equity rows where possible.
        text = f"{symbol} {name}".lower()
        if "شاخص" in text or "index" in text:
            continue

        x["score"] = score_stock(x)
        valid.append(x)

    valid.sort(key=lambda z: (z["score"], z["pct"], z["volume"]), reverse=True)
    return valid[:MAX_SYMBOLS]


def format_price(v):
    if v is None:
        return "-"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    return f"{v:,.4f}".rstrip("0").rstrip(".")


def build_report(source, candidates):
    lines = [
        "💓 ATI BOURSE ALIVE",
        f"⚡ {BOT_VERSION}",
        "📊 بورس ایران / داده عمومی",
        "🔑 API KEY: NOT REQUIRED",
        "🔒 REAL TRADING: OFF",
        f"🕐 {now_utc()}",
        "",
        f"✅ DATA SOURCE: {source}",
        f"📈 VALID SYMBOLS: {len(candidates)}",
        "",
    ]

    top = candidates[:10]

    if not top:
        lines.append("⚠️ سهم قابل استفاده‌ای پیدا نشد.")
        return "\n".join(lines)

    lines.append("🔥 TOP MARKET MOMENTUM")
    lines.append("")

    for i, x in enumerate(top, 1):
        sign = "+" if x["pct"] >= 0 else ""
        lines.append(
            f"{i}️⃣ {x['symbol'] or x['name']}\n"
            f"   💰 {format_price(x['last'])} | 📊 {sign}{x['pct']:.2f}% | ⭐ {x['score']}"
        )

    lines.extend([
        "",
        "⚠️ این نسخه فقط اسکن و گزارش می‌کند.",
        "🚫 هیچ سفارش خرید/فروشی ارسال نمی‌شود.",
    ])

    return "\n".join(lines)


def main():
    print(f"ATI BOURSE {BOT_VERSION}")
    print("API KEY: NOT REQUIRED")
    print("REAL TRADING: OFF")
    print(now_utc())

    source, rows, errors = fetch_market()

    if not rows:
        report = (
            "❌ ATI BOURSE ERROR\n\n"
            "هیچ داده عمومی معتبری از بازار دریافت نشد.\n\n"
            "🔑 BRS_API_KEY لازم نیست.\n"
            "🔒 REAL TRADING: OFF\n\n"
            "📋 DIAGNOSTIC:\n"
            + "\n".join(f"• {e}" for e in errors)
        )
        print(report)
        telegram_send(report)
        return 0

    candidates = select_candidates(rows)
    report = build_report(source, candidates)

    print(report)
    telegram_send(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
