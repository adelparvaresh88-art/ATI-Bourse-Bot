
import os
import json
import time
import requests
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

# ================= SETTINGS =================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

MAX_MARKETS = 300
BATCH_SIZE = 30
HISTORY_DAYS = 35

TENKAN = 9
KIJUN = 26

TEHRAN = ZoneInfo("Asia/Tehran")

# شنبه تا چهارشنبه
MARKET_DAYS = {5, 6, 0, 1, 2}

MARKET_OPEN = (9, 0)
MARKET_CLOSE = (12, 30)

CACHE_DIR = "hourly_cache"
STATE_FILE = os.path.join(CACHE_DIR, "cross_state.json")
SCAN_STATE_FILE = os.path.join(CACHE_DIR, "scan_state.json")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tsetmc.com/"
})


# ================= MARKET TIME =================

def tehran_now():
    return datetime.now(TEHRAN)


def market_is_open():
    now = tehran_now()

    if now.weekday() not in MARKET_DAYS:
        return False

    current = (now.hour, now.minute)

    return MARKET_OPEN <= current < MARKET_CLOSE


# ================= TELEGRAM =================

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram secrets missing")
        return False

    try:
        response = SESSION.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=20
        )

        print("Telegram:", response.status_code)
        return response.ok

    except Exception as error:
        print("Telegram error:", error)
        return False


# ================= MARKET DATA =================

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


def parse_old_marketwatch(content):
    rows = []

    if not content or "@" not in content:
        return rows

    parts = content.split("@")

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
                timeout=25
            )

            response.raise_for_status()

            rows = (
                extract_rows(response.json())
                if is_json
                else parse_old_marketwatch(response.text)
            )

            valid = []
            seen = set()

            for item in rows:
                code = extract_code(item)

                if code and code not in seen:
                    seen.add(code)
                    valid.append(item)

            if valid:
                print("Market source:", url)
                print("Available markets:", len(valid))
                return valid[:MAX_MARKETS]

        except Exception as error:
            errors.append(str(error))
            print("Market source error:", error)

    raise RuntimeError(
        "دریافت فهرست نمادها ناموفق بود: " + str(errors)
    )


# ================= CACHE =================

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(CACHE_DIR, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False)


def load_state():
    data = load_json(STATE_FILE, {})
    return data if isinstance(data, dict) else {}


def save_state(state):
    save_json(STATE_FILE, state)


def load_scan_offset():
    data = load_json(SCAN_STATE_FILE, {})

    try:
        return max(0, int(data.get("offset", 0)))
    except (TypeError, ValueError, AttributeError):
        return 0


def save_scan_offset(offset):
    save_json(SCAN_STATE_FILE, {"offset": offset})


# ================= HOURLY CANDLES =================

def get_hourly_candles(ins_code):

    os.makedirs(CACHE_DIR, exist_ok=True)

    cache_path = os.path.join(
        CACHE_DIR,
        f"{ins_code}.json"
    )

    cache = load_json(cache_path, {})

    if not isinstance(cache, dict):
        cache = {}

    daily_url = (
        "https://cdn.tsetmc.com/api/ClosingPrice/"
        f"GetClosingPriceDailyList/{ins_code}/0"
    )

    response = SESSION.get(daily_url, timeout=20)
    response.raise_for_status()

    data = response.json()

    daily_rows = (
        data.get("closingPriceDaily", [])
        if isinstance(data, dict)
        else []
    )

    dates = sorted({
        str(item.get("dEven", "")).strip()
        for item in daily_rows
        if isinstance(item, dict)
        and str(item.get("dEven", "")).strip().isdigit()
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
            response = SESSION.get(url, timeout=15)
            response.raise_for_status()

            result = response.json()

            trades = (
                result.get("tradeHistory", [])
                if isinstance(result, dict)
                else []
            )

        except Exception as error:
            print("Trade history error:", error)
            continue

        buckets = {}

        for trade in trades:

            if not isinstance(trade, dict):
                continue

            try:
                trade_time = int(trade.get("hEven", 0))
                hour = trade_time // 10000
                price = float(trade.get("pTran", 0))

                if hour < 9 or hour > 12 or price <= 0:
                    continue

                # حذف معاملات بعد از 12:30
                if hour == 12 and trade_time >= 123000:
                    continue

                if hour not in buckets:
                    buckets[hour] = {
                        "first": trade_time,
                        "last": trade_time,
                        "open": price,
                        "close": price,
                        "high": price,
                        "low": price
                    }

                else:
                    candle = buckets[hour]

                    candle["high"] = max(
                        candle["high"], price
                    )

                    candle["low"] = min(
                        candle["low"], price
                    )

                    if trade_time < candle["first"]:
                        candle["first"] = trade_time
                        candle["open"] = price

                    if trade_time >= candle["last"]:
                        candle["last"] = trade_time
                        candle["close"] = price

            except (TypeError, ValueError):
                continue

        cache[day] = [
            {
                "hour": hour,
                "close": candle["close"],
                "high": candle["high"],
                "low": candle["low"]
            }
            for hour, candle in sorted(buckets.items())
        ]

        time.sleep(0.05)

    keep = sorted(cache.keys(), reverse=True)[:40]

    cache = {
        day: cache[day]
        for day in keep
    }

    save_json(cache_path, cache)

    candles = []

    now = tehran_now()
    today = now.strftime("%Y%m%d")

    for day in sorted(dates):

        for candle in cache.get(day, []):

            hour = int(candle["hour"])

            # کندل جاری کامل نشده است
            if day == today and hour == now.hour:
                if 9 <= hour <= 12:
                    if not (
                        hour == 12 and now.minute >= 30
                    ):
                        continue

            candles.append({
                "date": day,
                "hour": hour,
                "close": float(candle["close"]),
                "high": float(candle["high"]),
                "low": float(candle["low"])
            })

    print(ins_code, "closed candles:", len(candles))

    return candles


# ================= ICHIMOKU =================

def midpoint(candles, period, end_index):

    start = end_index - period + 1

    if start < 0:
        return None

    section = candles[start:end_index + 1]

    if len(section) != period:
        return None

    high = max(item["high"] for item in section)
    low = min(item["low"] for item in section)

    return (high + low) / 2


def check_tenkan_kijun_cross(candles):

    if len(candles) < KIJUN + 1:
        return None

    last = len(candles) - 1
    previous = last - 1

    tenkan_previous = midpoint(
        candles, TENKAN, previous
    )

    kijun_previous = midpoint(
        candles, KIJUN, previous
    )

    tenkan_now = midpoint(
        candles, TENKAN, last
    )

    kijun_now = midpoint(
        candles, KIJUN, last
    )

    values = (
        tenkan_previous,
        kijun_previous,
        tenkan_now,
        kijun_now
    )

    if any(value is None for value in values):
        return None

    if (
        tenkan_previous <= kijun_previous
        and tenkan_now > kijun_now
    ):

        candle = candles[last]

        return {
            "tenkan": tenkan_now,
            "kijun": kijun_now,
            "price": candle["close"],
            "cross_id": (
                f"{candle['date']}_{candle['hour']}"
            )
        }

    return None


# ================= MAIN =================

def main():

    now = tehran_now()

    print("Tehran time:", now.strftime("%Y-%m-%d %H:%M"))

    # توقف کامل خارج از ساعات بازار
    if not market_is_open():

        print("MARKET CLOSED - NO SCAN")

        return

    send_telegram(
        "🤖 ATI BOURSE BOT\n"
        "ربات فعال شد.\n"
        "تایم‌فریم: یک‌ساعته TSETMC\n"
        "استراتژی: کراس صعودی تنکانسن 9 و کیجونسن 26\n"
        "تعداد نماد هدف: 300\n"
        "بررسی چرخشی: هر اجرا 30 نماد\n"
        "ساعات فعالیت: 09:00 تا 12:30 تهران\n"
        "معامله خودکار: خاموش\n"
        f"زمان: {now.strftime('%Y-%m-%d %H:%M')}"
    )

    try:

        all_markets = get_market_list()
        total_markets = len(all_markets)

        if total_markets == 0:
            raise RuntimeError("فهرست نمادها خالی است.")

        offset = load_scan_offset() % total_markets
        end = offset + BATCH_SIZE

        if end <= total_markets:
            markets = all_markets[offset:end]
        else:
            markets = (
                all_markets[offset:]
                + all_markets[:end - total_markets]
            )

        next_offset = (
            offset + len(markets)
        ) % total_markets

        save_scan_offset(next_offset)

        send_telegram(
            "🔎 ATI BOURSE BOT\n"
            "اسکن بازار شروع شد.\n"
            f"کل نمادهای هدف: {total_markets}\n"
            f"بررسی در این اجرا: {len(markets)}\n"
            "تایم‌فریم: یک‌ساعته"
        )

        state = load_state()

        signals = []
        checked = 0
        errors = 0
        insufficient = 0

        for item in markets:

            # در صورت رسیدن به پایان بازار، اسکن متوقف شود
            if not market_is_open():
                print("Market closed during scan.")
                break

            code = extract_code(item)

            if not code:
                continue

            checked += 1

            try:

                candles = get_hourly_candles(code)

                cross = check_tenkan_kijun_cross(candles)

                if len(candles) < KIJUN + 1:
                    insufficient += 1

                # کنترل مجدد ساعت قبل از ارسال سیگنال
                if cross and market_is_open():

                    cross_id = cross["cross_id"]

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

                    if market_is_open() and send_telegram(message):

                        state[code] = cross_id
                        save_state(state)

                        signals.append(name)

            except Exception as error:

                errors += 1

                print("Symbol error:", code, error)

            if checked % 10 == 0 or checked == len(markets):

                send_telegram(
                    "⏳ گزارش پیشرفت ATI\n"
                    f"بررسی‌شده: {checked} از {len(markets)}\n"
                    f"سیگنال خرید: {len(signals)}\n"
                    f"خطاها: {errors}"
                )

        summary = (
            "📊 گزارش نهایی ATI BOURSE BOT\n"
            f"نمادهای بررسی‌شده این اجرا: {checked} از {len(markets)}\n"
            f"کل نمادهای هدف: {total_markets}\n"
            f"سیگنال خرید جدید: {len(signals)}\n"
            f"کندل ناکافی: {insufficient}\n"
            f"خطاها: {errors}\n"
            "استراتژی: کراس صعودی تنکانسن 9 و کیجونسن 26\n"
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
