
import os
import json
import time
import requests
import traceback
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

MAX_MARKETS = 10
HISTORY_DAYS = 24
CACHE_DIR = "hourly_cache"

TENKAN = 9
KIJUN = 26
SENKOU_B = 52
RECENT_CROSS_BARS = 3

HEADERS = {
    "User-Agent": "Mozilla/5.0 Chrome/120.0 Safari/537.36",
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
        response = SESSION.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": message},
            timeout=15
        )
        print("Telegram:", response.status_code, response.text[:300])
        return response.ok
    except Exception as error:
        print("Telegram error:", error)
        return False


def extract_rows(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in (
        "marketwatch", "marketWatch", "MarketWatch",
        "instrumentState", "instrument", "data", "items", "Items"
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

    for line in parts[2].split(";"):
        cols = line.split(",")

        if len(cols) < 18:
            continue

        code = cols[0].strip()

        if code.isdigit():
            rows.append({
                "insCode": code,
                "lVal18AFC": cols[2].strip(),
                "instrumentName": cols[3].strip()
            })

    return rows


def get_market_list():
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
        ("https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch", True),
        ("https://cdn10.tsetmc.com/api/ClosingPrice/GetMarketWatch", True),
        ("https://old.tsetmc.com/tsev2/data/MarketWatchInit.aspx?h=0&r=0", False),
        ("https://www.tsetmc.com/tsev2/data/MarketWatchInit.aspx?h=0&r=0", False)
    ]

    errors = []

    for url, is_json in sources:
        try:
            response = SESSION.get(
                url,
                params=params if is_json else None,
                timeout=20
            )

            response.raise_for_status()

            rows = (
                extract_rows(response.json())
                if is_json
                else parse_old_marketwatch(response.text)
            )

            valid = [x for x in rows if extract_code(x)]

            if valid:
                print("Market source OK:", url, len(valid))
                return valid[:MAX_MARKETS]

        except Exception as error:
            errors.append(str(error))
            print("Market source error:", error)

    raise RuntimeError(
        "دریافت فهرست نمادها ناموفق بود: " + str(errors)
    )


def get_hourly_candles(ins_code):
    os.makedirs(CACHE_DIR, exist_ok=True)

    cache_path = os.path.join(
        CACHE_DIR, f"{ins_code}.json"
    )

    try:
        with open(cache_path, "r", encoding="utf-8") as file:
            cache = json.load(file)

        if not isinstance(cache, dict):
            cache = {}

    except (OSError, ValueError):
        cache = {}

    daily_url = (
        "https://cdn.tsetmc.com/api/ClosingPrice/"
        f"GetClosingPriceDailyList/{ins_code}/0"
    )

    response = SESSION.get(daily_url, timeout=15)
    response.raise_for_status()

    data = response.json()

    daily_rows = (
        data.get("closingPriceDaily", [])
        if isinstance(data, dict)
        else []
    )

    dates = sorted({
        str(x.get("dEven", "")).strip()
        for x in daily_rows
        if isinstance(x, dict)
        and str(x.get("dEven", "")).strip().isdigit()
    }, reverse=True)[:HISTORY_DAYS]

    if not dates:
        return []

    for day in dates:

        if day in cache and day != dates[0]:
            continue

        url = (
            "https://cdn.tsetmc.com/api/Trade/"
            f"GetTradeHistory/{ins_code}/{day}/false"
        )

        try:
            response = SESSION.get(url, timeout=12)
            response.raise_for_status()

            result = response.json()

            trades = (
                result.get("tradeHistory", [])
                if isinstance(result, dict)
                else []
            )

        except Exception as error:
            print("Trade history error:", ins_code, day, error)

            if day not in cache:
                cache[day] = []

            continue

        buckets = {}

        for trade in trades:
            if not isinstance(trade, dict):
                continue

            try:
                t = int(trade.get("hEven", 0))
                hour = t // 10000
                price = float(trade.get("pTran", 0))

                if hour < 9 or hour > 12 or price <= 0:
                    continue

                if hour not in buckets:
                    buckets[hour] = {
                        "first": t,
                        "last": t,
                        "open": price,
                        "close": price,
                        "high": price,
                        "low": price
                    }

                else:
                    b = buckets[hour]

                    b["high"] = max(b["high"], price)
                    b["low"] = min(b["low"], price)

                    if t < b["first"]:
                        b["first"] = t
                        b["open"] = price

                    if t >= b["last"]:
                        b["last"] = t
                        b["close"] = price

            except (TypeError, ValueError):
                continue

        cache[day] = [
            {
                "hour": hour,
                "close": b["close"],
                "high": b["high"],
                "low": b["low"]
            }
            for hour, b in sorted(buckets.items())
        ]

        time.sleep(0.05)

    keep = sorted(cache.keys(), reverse=True)[:30]
    cache = {d: cache[d] for d in keep}

    try:
        with open(cache_path, "w", encoding="utf-8") as file:
            json.dump(cache, file, ensure_ascii=False)

    except OSError as error:
        print("Cache save error:", error)

    candles = []

    iran_now = datetime.now(timezone.utc) + timedelta(
        hours=3, minutes=30
    )

    today = iran_now.strftime("%Y%m%d")

    for day in sorted(dates):
        for candle in cache.get(day, []):

            hour = int(candle["hour"])

            if day == today and 9 <= iran_now.hour <= 12:
                if hour == iran_now.hour:
                    if hour != 12 or iran_now.minute < 30:
                        continue

            candles.append({
                "close": float(candle["close"]),
                "high": float(candle["high"]),
                "low": float(candle["low"])
            })

    print(f"{ins_code}: {len(candles)} hourly candles")

    return candles


def midpoint(candles, period, end_index):
    start = end_index - period + 1

    if start < 0:
        return None

    section = candles[start:end_index + 1]

    if len(section) != period:
        return None

    high = max(x["high"] for x in section)
    low = min(x["low"] for x in section)

    return (high + low) / 2


def ichimoku_analysis(candles):
    if len(candles) < SENKOU_B + KIJUN + 5:
        return False, "کندل کافی نیست", "insufficient"

    last = len(candles) - 1

    tenkan_values = []
    kijun_values = []
    span_a_values = []
    span_b_values = []

    for i in range(len(candles)):

        tenkan = midpoint(candles, TENKAN, i)
        kijun = midpoint(candles, KIJUN, i)
        span_b = midpoint(candles, SENKOU_B, i)

        tenkan_values.append(tenkan)
        kijun_values.append(kijun)

        if tenkan is not None and kijun is not None:
            span_a_values.append((tenkan + kijun) / 2)
        else:
            span_a_values.append(None)

        span_b_values.append(span_b)

    cloud_index = last - KIJUN

    if cloud_index < 0:
        return False, "ابر در دسترس نیست", "insufficient"

    span_a = span_a_values[cloud_index]
    span_b = span_b_values[cloud_index]

    if span_a is None or span_b is None:
        return False, "ابر در دسترس نیست", "insufficient"

    cloud_top = max(span_a, span_b)

    price = candles[last]["close"]
    above_cloud = price > cloud_top

    tenkan_now = tenkan_values[last]
    kijun_now = kijun_values[last]

    if tenkan_now is None or kijun_now is None:
        return False, "محاسبه ناموفق", "insufficient"

    bullish = tenkan_now > kijun_now

    cross_found = False
    cross_index = None

    first = max(
        KIJUN + 1,
        last - RECENT_CROSS_BARS + 1
    )

    for i in range(first, last + 1):

        values = (
            tenkan_values[i - 1],
            kijun_values[i - 1],
            tenkan_values[i],
            kijun_values[i]
        )

        if any(v is None for v in values):
            continue

        if values[0] <= values[1] and values[2] > values[3]:
            cross_found = True
            cross_index = i

    if above_cloud and bullish and cross_found:

        details = (
            f"قیمت: {price:.2f}\n"
            f"تنکان: {tenkan_now:.2f}\n"
            f"کیجون: {kijun_now:.2f}\n"
            f"فاصله کراس: {last - cross_index} کندل"
        )

        return True, details, "buy"

    if above_cloud and bullish:
        return False, "بالای ابر و موقعیت صعودی", "bullish_no_cross"

    if above_cloud:
        return False, "بالای ابر", "above_cloud"

    if bullish:
        return False, "تنکان بالای کیجون", "bullish_position"

    return False, "شرایط خرید برقرار نیست", "none"


def main():
    now = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    send_telegram(
        "🤖 ATI BOURSE BOT\n"
        "ربات فعال شد.\n"
        "تایم‌فریم: یک‌ساعته از معاملات TSETMC\n"
        "استراتژی: ایچیموکو\n"
        "حالت: فقط سیگنال خرید\n"
        "معامله خودکار: خاموش\n"
        f"زمان: {now}"
    )

    try:
        markets = get_market_list()

        send_telegram(
            "🔎 ATI BOURSE BOT\n"
            "اسکن بازار شروع شد.\n"
            f"نمادهای انتخاب‌شده: {len(markets)}\n"
            "تایم‌فریم: یک‌ساعته"
        )

        signals = []
        checked = 0
        errors = 0
        insufficient = 0
        above = 0
        bullish = 0
        crosses = 0

        for item in markets:

            code = extract_code(item)

            if not code:
                continue

            checked += 1

            try:
                candles = get_hourly_candles(code)

                signal, details, status = ichimoku_analysis(
                    candles
                )

                if status == "insufficient":
                    insufficient += 1

                elif status == "above_cloud":
                    above += 1

                elif status == "bullish_position":
                    bullish += 1

                elif status == "bullish_no_cross":
                    above += 1
                    bullish += 1

                elif status == "buy":
                    above += 1
                    bullish += 1
                    crosses += 1

                if signal:

                    name = (
                        item.get("lVal18AFC")
                        or item.get("instrumentName")
                        or code
                    )

                    signals.append(
                        "🟢 سیگنال خرید ایچیموکو\n"
                        f"نماد: {name}\n"
                        f"کد: {code}\n"
                        "تایم‌فریم: یک‌ساعته\n"
                        f"{details}"
                    )

            except Exception as error:
                errors += 1
                print("Symbol error:", code, error)

            if checked % 2 == 0 or checked == len(markets):
                send_telegram(
                    "⏳ گزارش پیشرفت ATI\n"
                    f"بررسی‌شده: {checked} از {len(markets)}\n"
                    f"سیگنال خرید: {len(signals)}\n"
                    f"خطاها: {errors}"
                )

        print(
            f"Markets: {len(markets)} | "
            f"Checked: {checked} | "
            f"Signals: {len(signals)} | "
            f"Errors: {errors}"
        )

        summary = (
            "📊 گزارش نهایی ATI BOURSE BOT\n"
            f"نمادهای بررسی‌شده: {checked} از {len(markets)}\n"
            f"سیگنال خرید: {len(signals)}\n"
            f"بالای ابر: {above}\n"
            f"موقعیت صعودی: {bullish}\n"
            f"کراس اخیر: {crosses}\n"
            f"کندل ناکافی: {insufficient}\n"
            f"خطاها: {errors}\n"
            "معامله خودکار: خاموش"
        )

        if not signals:
            summary += "\nدر این اجرا سیگنال خرید پیدا نشد."

        send_telegram(summary)

        for signal in signals[:5]:
            send_telegram(signal)

    except Exception:
        error = traceback.format_exc()
        print(error)

        send_telegram(
            "⚠️ خطای ربات ATI\n" + error[-2500:]
        )


if __name__ == "__main__":
    main()
