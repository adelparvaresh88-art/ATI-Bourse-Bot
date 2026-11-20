
import os
import time
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
RECENT_CROSS_BARS = 3

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
        "marketwatch", "marketWatch", "MarketWatch",
        "instrumentState", "instrument", "data",
        "items", "Items"
    ):
        value = data.get(key)

        if isinstance(value, list) and value:
            return value

        if isinstance(value, dict):
            rows = extract_rows(value)
            if rows:
                return rows

    return []


def extract_code(item):
    if not isinstance(item, dict):
        return None

    for key in (
        "insCode", "InsCode", "instrumentCode",
        "instrumentId", "ins_code"
    ):
        value = item.get(key)
        if value:
            return str(value)

    return None


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
                rows = extract_rows(r.json())
            else:
                rows = parse_old_marketwatch(r.text)

            valid = [
                x for x in rows
                if isinstance(x, dict) and extract_code(x)
            ]

            if valid:
                print(f"SUCCESS: {name} | Markets: {len(valid)}")
                return valid[:MAX_MARKETS]

            errors.append(f"{name}: No valid rows")

        except Exception as e:
            errors.append(f"{name}: {str(e)[:180]}")
            print("Source failed:", name, e)

    raise RuntimeError(
        "No valid market data received from TSETMC.\n"
        + "\n".join(errors)
    )


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


def midpoint(candles, period, end_index):
    start = end_index - period + 1

    if start < 0:
        return None

    recent = candles[start:end_index + 1]

    if len(recent) != period:
        return None

    highest = max(x["high"] for x in recent)
    lowest = min(x["low"] for x in recent)

    return (highest + lowest) / 2


def ichimoku_analysis(candles):
    if len(candles) < SENKOU_B + KIJUN + 5:
        return False, "Not enough candles", "insufficient"

    # آخرین کندل حذف می‌شود تا فقط کندل‌های بسته‌شده بررسی شوند.
    closed = candles[:-1]
    last = len(closed) - 1

    tenkan_values = []
    kijun_values = []
    span_a_values = []
    span_b_values = []

    for i in range(len(closed)):
        tenkan = midpoint(closed, TENKAN, i)
        kijun = midpoint(closed, KIJUN, i)
        span_b = midpoint(closed, SENKOU_B, i)

        tenkan_values.append(tenkan)
        kijun_values.append(kijun)

        if tenkan is not None and kijun is not None:
            span_a_values.append((tenkan + kijun) / 2)
        else:
            span_a_values.append(None)

        span_b_values.append(span_b)

    # ابر قابل مشاهده در زمان فعلی، ۲۶ کندل قبل محاسبه شده است.
    cloud_index = last - KIJUN

    if cloud_index < 0:
        return False, "Cloud unavailable", "insufficient"

    span_a = span_a_values[cloud_index]
    span_b = span_b_values[cloud_index]

    if span_a is None or span_b is None:
        return False, "Cloud unavailable", "insufficient"

    cloud_top = max(span_a, span_b)
    price = closed[last]["close"]

    above_cloud = price > cloud_top

    tenkan_now = tenkan_values[last]
    kijun_now = kijun_values[last]

    if tenkan_now is None or kijun_now is None:
        return False, "Calculation unavailable", "insufficient"

    bullish_position = tenkan_now > kijun_now

    # کراس صعودی در سه کندل بسته‌شده اخیر جست‌وجو می‌شود.
    cross_found = False
    cross_index = None

    first_index = max(KIJUN + 1, last - RECENT_CROSS_BARS + 1)

    for i in range(first_index, last + 1):
        previous_tenkan = tenkan_values[i - 1]
        previous_kijun = kijun_values[i - 1]
        current_tenkan = tenkan_values[i]
        current_kijun = kijun_values[i]

        if None in (
            previous_tenkan,
            previous_kijun,
            current_tenkan,
            current_kijun
        ):
            continue

        if (
            previous_tenkan <= previous_kijun
            and current_tenkan > current_kijun
        ):
            cross_found = True
            cross_index = i

    if above_cloud and bullish_position and cross_found:
        bars_ago = last - cross_index

        details = (
            f"قیمت: {price:.2f}\n"
            f"تنکان: {tenkan_now:.2f}\n"
            f"کیجون: {kijun_now:.2f}\n"
            f"فاصله از کراس: {bars_ago} کندل"
        )

        return True, details, "buy"

    if above_cloud and bullish_position:
        return False, "Above cloud and bullish position", "bullish_no_cross"

    if above_cloud:
        return False, "Above cloud", "above_cloud"

    if bullish_position:
        return False, "Tenkan above Kijun", "bullish_position"

    return False, "No buy condition", "none"


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
        above_cloud_count = 0
        bullish_count = 0
        recent_cross_count = 0
        insufficient_count = 0

        for item in markets:
            ins_code = extract_code(item)

            if not ins_code:
                continue

            checked += 1

            try:
                candles = get_hourly_candles(ins_code)

                signal, details, status = ichimoku_analysis(candles)

                if status == "above_cloud":
                    above_cloud_count += 1

                elif status == "bullish_position":
                    bullish_count += 1

                elif status == "bullish_no_cross":
                    above_cloud_count += 1
                    bullish_count += 1

                elif status == "buy":
                    above_cloud_count += 1
                    bullish_count += 1
                    recent_cross_count += 1

                elif status == "insufficient":
                    insufficient_count += 1

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
            f"Above cloud: {above_cloud_count} | "
            f"Bullish: {bullish_count} | "
            f"Recent crosses: {recent_cross_count} | "
            f"Insufficient candles: {insufficient_count} | "
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
                f"بالای ابر کومو: {above_cloud_count}\n"
                f"تنکان بالای کیجون: {bullish_count}\n"
                f"کراس صعودی اخیر: {recent_cross_count}\n"
                f"کندل ناکافی: {insufficient_count}\n"
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
