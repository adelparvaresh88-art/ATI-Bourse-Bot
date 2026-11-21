
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
TENKAN = 9
KIJUN = 26
CACHE_DIR = "hourly_cache"
STATE_FILE = os.path.join(CACHE_DIR, "cross_state.json")

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
        print("Telegram:", response.status_code, response.text[:200])
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

    cache_path = os.path.join(CACHE_DIR, f"{ins_code}.json")

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

            # کندل ساعت جاری تا بسته‌شدن کامل وارد محاسبه نشود
            if day == today:
                if hour == iran_now.hour and 9 <= iran_now.hour <= 12:
                    if not (hour == 12 and iran_now.hour == 12
                            and iran_now.minute >= 30):
                        continue

            candles.append({
                "date": day,
                "hour": hour,
                "close": float(candle["close"]),
                "high": float(candle["high"]),
                "low": float(candle["low"])
            })

    print(f"{ins_code}: {len(candles)} closed hourly candles")
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


def check_tenkan_kijun_cross(candles):
    # برای بررسی کراس در دو کندل بسته‌شده، حداقل 27 کندل لازم است
    if len(candles) < KIJUN + 1:
        return None

    last = len(candles) - 1
    previous = last - 1

    tenkan_previous = midpoint(candles, TENKAN, previous)
    kijun_previous = midpoint(candles, KIJUN, previous)

    tenkan_now = midpoint(candles, TENKAN, last)
    kijun_now = midpoint(candles, KIJUN, last)

    values = (
        tenkan_previous,
        kijun_previous,
        tenkan_now,
        kijun_now
    )

    if any(value is None for value in values):
        return None

    # تنها شرط خرید: کراس صعودی تنکانسن و کیجونسن
    if (
        tenkan_previous <= kijun_previous
        and tenkan_now > kijun_now
    ):
        candle = candles[last]

        return {
            "tenkan": tenkan_now,
            "kijun": kijun_now,
            "price": candle["close"],
            "cross_id": f"{candle['date']}_{candle['hour']}"
        }

    return None


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            state = json.load(file)
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(CACHE_DIR, exist_ok=True)

    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False)


def main():
    now = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    send_telegram(
        "🤖 ATI BOURSE BOT\n"
        "ربات فعال شد.\n"
        "تایم‌فریم: یک‌ساعته TSETMC\n"
        "استراتژی: فقط کراس تنکانسن و کیجونسن\n"
        "شرط خرید: کراس صعودی\n"
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

        state = load_state()
        signals = []
        checked = 0
        errors = 0
        insufficient = 0

        for item in markets:
            code = extract_code(item)

            if not code:
                continue

            checked += 1

            try:
                candles = get_hourly_candles(code)

                cross = check_tenkan_kijun_cross(candles)

                if len(candles) < KIJUN + 1:
                    insufficient += 1

                if cross:
                    cross_id = cross["cross_id"]

                    # جلوگیری از ارسال دوباره همان کراس
                    if state.get(code) == cross_id:
                        continue

                    name = (
                        item.get("lVal18AFC")
                        or item.get("instrumentName")
                        or code
                    )

                    message = (
                        "🟢 ATI BOURSE BUY\n"
                        f"نماد: {name}\n"
                        f"کد: {code}\n"
                        "تایم‌فریم: یک‌ساعته\n"
                        "سیگنال: کراس صعودی تنکانسن و کیجونسن\n"
                        f"تنکانسن: {cross['tenkan']:.2f}\n"
                        f"کیجونسن: {cross['kijun']:.2f}\n"
                        f"قیمت: {cross['price']:.2f}\n"
                        "معامله خودکار: خاموش"
                    )

                    if send_telegram(message):
                        state[code] = cross_id
                        save_state(state)
                        signals.append(name)

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

        summary = (
            "📊 گزارش نهایی ATI BOURSE BOT\n"
            f"نمادهای بررسی‌شده: {checked} از {len(markets)}\n"
            f"سیگنال خرید جدید: {len(signals)}\n"
            f"کندل ناکافی: {insufficient}\n"
            f"خطاها: {errors}\n"
            "استراتژی: فقط کراس تنکانسن و کیجونسن\n"
            "معامله خودکار: خاموش"
        )

        if not signals:
            summary += "\nدر این اجرا کراس صعودی جدید پیدا نشد."

        send_telegram(summary)

    except Exception:
        error = traceback.format_exc()
        print(error)

        send_telegram(
            "⚠️ خطای ربات ATI\n" + error[-2500:]
        )


if __name__ == "__main__":
    main()
