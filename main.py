
import os
import time
import json
import requests
import traceback
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

MAX_MARKETS = 80
TIMEFRAME = 60
TENKAN = 9
KIJUN = 26
SENKOU_B = 52

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tsetmc.com/"
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram secrets missing")
        return False

    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        r = SESSION.post(
            url,
            data={"chat_id": CHAT_ID, "text": message},
            timeout=20
        )
        print("Telegram:", r.status_code)
        return r.ok
    except Exception as e:
        print("Telegram error:", e)
        return False


def extract_rows(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in (
        "marketwatch",
        "marketWatch",
        "MarketWatch",
        "instrumentState",
        "instrument",
        "data",
        "items",
        "Items"
    ):
        value = data.get(key)

        if isinstance(value, list) and value:
            return value

        if isinstance(value, dict):
            rows = extract_rows(value)
            if rows:
                return rows

    return []


def parse_old_marketwatch(text):
    rows = []

    if not text or "@" not in text:
        return rows

    parts = text.split("@")

    if len(parts) < 3:
        return rows

    price_section = parts[2]

    for line in price_section.split(";"):
        cols = line.split(",")

        if len(cols) < 18:
            continue

        ins_code = cols[0].strip()

        if not ins_code.isdigit():
            continue

        rows.append({
            "insCode": ins_code,
            "lVal18AFC": cols[2].strip(),
            "instrumentName": cols[3].strip(),
            "isin": cols[1].strip()
        })

    return rows


def get_market_list():
    errors = []

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
        "RefID": 0
    }

    sources = [
        (
            "TSETMC CDN",
            "https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch",
            "json"
        ),
        (
            "TSETMC CDN10",
            "https://cdn10.tsetmc.com/api/ClosingPrice/GetMarketWatch",
            "json"
        ),
        (
            "OLD TSETMC",
            "https://old.tsetmc.com/tsev2/data/MarketWatchInit.aspx?h=0&r=0",
            "text"
        ),
        (
            "WWW TSETMC",
            "https://www.tsetmc.com/tsev2/data/MarketWatchInit.aspx?h=0&r=0",
            "text"
        )
    ]

    for name, url, mode in sources:
        try:
            print("Trying market source:", name)

            r = SESSION.get(
                url,
                params=params if mode == "json" else None,
                timeout=35
            )

            r.raise_for_status()

            if mode == "json":
                data = r.json()
                rows = extract_rows(data)
            else:
                rows = parse_old_marketwatch(r.text)

            valid = [
                x for x in rows
                if isinstance(x, dict) and extract_code(x)
            ]

            if valid:
                print(
                    f"SUCCESS: {name} | "
                    f"Markets: {len(valid)}"
                )
                return valid[:MAX_MARKETS]

            errors.append(f"{name}: No valid rows")

        except Exception as e:
            errors.append(f"{name}: {str(e)[:180]}")
            print("Source failed:", name, e)

    raise RuntimeError(
        "No valid market data received from TSETMC.\n"
        + "\n".join(errors)
    )


def extract_code(item):
    if not isinstance(item, dict):
        return None

    for key in (
        "insCode",
        "InsCode",
        "instrumentCode",
        "instrumentId",
        "ins_code"
    ):
        value = item.get(key)
        if value:
            return str(value)

    return None


def get_hourly_candles(ins_code):
    url = (
        "https://cdn.tsetmc.com/api/ClosingPrice/"
        f"GetChartData/{ins_code}/{TIMEFRAME}"
    )

    r = SESSION.get(url, timeout=25)
    r.raise_for_status()

    data = r.json()

    if isinstance(data, dict):
        rows = (
            data.get("chartData")
            or data.get("data")
            or data.get("dataList")
            or []
        )
    elif isinstance(data, list):
        rows = data
    else:
        rows = []

    candles = []

    for row in rows:
        try:
            if isinstance(row, dict):
                close = (
                    row.get("close")
                    or row.get("pClosing")
                    or row.get("y")
                )
                high = (
                    row.get("high")
                    or row.get("priceMax")
                    or row.get("h")
                )
                low = (
                    row.get("low")
                    or row.get("priceMin")
                    or row.get("l")
                )

            elif isinstance(row, (list, tuple)) and len(row) >= 4:
                close, high, low = row[-1], row[-2], row[-3]

            else:
                continue

            candles.append({
                "close": float(close),
                "high": float(high),
                "low": float(low)
            })

        except (TypeError, ValueError):
            continue

    return candles


def midpoint(candles, period):
    if len(candles) < period:
        return None

    recent = candles[-period:]

    highest = max(x["high"] for x in recent)
    lowest = min(x["low"] for x in recent)

    return (highest + lowest) / 2


def ichimoku_buy_signal(candles):
    if len(candles) < SENKOU_B + 3:
        return False, "Not enough candles"

    closed = candles[:-1]

    if len(closed) < SENKOU_B + 2:
        return False, "Not enough closed candles"

    previous = closed[:-1]
    current = closed

    tenkan_now = midpoint(current, TENKAN)
    kijun_now = midpoint(current, KIJUN)

    tenkan_prev = midpoint(previous, TENKAN)
    kijun_prev = midpoint(previous, KIJUN)

    if None in (
        tenkan_now,
        kijun_now,
        tenkan_prev,
        kijun_prev
    ):
        return False, "Calculation unavailable"

    span_a = (tenkan_now + kijun_now) / 2
    span_b = midpoint(current, SENKOU_B)

    price = current[-1]["close"]
    cloud_top = max(span_a, span_b)

    bullish_cross = (
        tenkan_prev <= kijun_prev
        and tenkan_now > kijun_now
    )

    above_cloud = price > cloud_top

    if bullish_cross and above_cloud:
        return True, (
            f"قیمت: {price:.2f}\n"
            f"تنکان: {tenkan_now:.2f}\n"
            f"کیجون: {kijun_now:.2f}"
        )

    return False, "No buy signal"


def main():
    now = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    send_telegram(
        "🤖 ATI BOURSE BOT\n"
        "ربات ایچیموکو فعال شد.\n"
        "تایم‌فریم: یک‌ساعته\n"
        "حالت: فقط سیگنال خرید\n"
        "معامله خودکار: خاموش\n"
        f"زمان: {now}"
    )

    print("ATI BOURSE BOT started")

    try:
        markets = get_market_list()

        signals = []
        checked = 0
        errors = 0

        for item in markets:
            ins_code = extract_code(item)

            if not ins_code:
                continue

            checked += 1

            try:
                candles = get_hourly_candles(ins_code)

                signal, details = ichimoku_buy_signal(
                    candles
                )

                if signal:
                    name = (
                        item.get("lVal18AFC")
                        or item.get("instrumentName")
                        or item.get("l18")
                        or ins_code
                    )

                    signals.append(
                        "🟢 سیگنال خرید ایچیموکو\n"
                        f"نماد: {name}\n"
                        f"کد: {ins_code}\n"
                        "تایم‌فریم: ۱ ساعته\n"
                        f"{details}"
                    )

            except Exception as e:
                errors += 1
                print("Symbol error:", ins_code, e)

            time.sleep(0.2)

        print(
            f"Markets: {len(markets)} | "
            f"Checked: {checked} | "
            f"Signals: {len(signals)} | "
            f"Errors: {errors}"
        )

        if signals:
            for signal in signals[:10]:
                send_telegram(signal)
        else:
            send_telegram(
                "ATI BOURSE BOT\n"
                "در این اجرا سیگنال خرید پیدا نشد.\n"
                f"نمادهای بررسی‌شده: {checked}\n"
                f"خطاها: {errors}"
            )

    except Exception:
        error = traceback.format_exc()
        print(error)

        send_telegram(
            "⚠️ خطای ربات بورس ATI\n"
            f"{error[-2500:]}"
        )


if __name__ == "__main__":
    main()
