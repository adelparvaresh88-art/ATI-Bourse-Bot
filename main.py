
import os
import time
import requests
import traceback
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

BASE_URL = "https://cdn.tsetmc.com/api/ClosingPrice"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

MAX_MARKETS = 80
TIMEFRAME = 60
TENKAN = 9
KIJUN = 26
SENKOU_B = 52


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram secrets are missing.")
        return False

    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        response = requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": message},
            timeout=20
        )
        print("Telegram:", response.status_code, response.text[:300])
        return response.ok
    except Exception as exc:
        print("Telegram error:", exc)
        return False


def get_market_list():
    urls = [
        "https://cdn.tsetmc.com/api/MarketData/GetMarketWatch",
        "https://old.tsetmc.com/tsev2/data/MarketWatchInit.aspx?h=0&r=0"
    ]

    for url in urls:
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            data = response.json()

            rows = (
                data.get("instrumentState")
                or data.get("marketWatch")
                or data.get("instrument")
                or []
            )

            if isinstance(rows, list) and rows:
                return rows[:MAX_MARKETS]

        except Exception as exc:
            print("Market source error:", url, exc)

    raise RuntimeError("No valid market data received from TSETMC.")


def extract_code(item):
    if not isinstance(item, dict):
        return None

    for key in (
        "insCode",
        "instrumentCode",
        "instrumentId",
        "InsCode"
    ):
        value = item.get(key)
        if value:
            return str(value)

    return None


def get_hourly_candles(ins_code):
    url = f"https://cdn.tsetmc.com/api/ClosingPrice/GetChartData/{ins_code}/{TIMEFRAME}"

    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    data = response.json()

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

        try:
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
    highest = max(c["high"] for c in recent)
    lowest = min(c["low"] for c in recent)
    return (highest + lowest) / 2


def ichimoku_buy_signal(candles):
    if len(candles) < SENKOU_B + 3:
        return False, "Not enough candles"

    # آخرین کندل ممکن است هنوز بسته نشده باشد؛ آن را کنار می‌گذاریم.
    closed = candles[:-1]

    if len(closed) < SENKOU_B + 2:
        return False, "Not enough closed candles"

    previous = closed[:-1]
    current = closed

    tenkan_now = midpoint(current, TENKAN)
    kijun_now = midpoint(current, KIJUN)
    tenkan_prev = midpoint(previous, TENKAN)
    kijun_prev = midpoint(previous, KIJUN)

    if None in (tenkan_now, kijun_now, tenkan_prev, kijun_prev):
        return False, "Ichimoku calculation unavailable"

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
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    send_telegram(
        "🤖 ATI BOURSE BOT\n"
        "ربات ایچیموکو فعال شد.\n"
        "تایم‌فریم: یک‌ساعته\n"
        "حالت: فقط سیگنال خرید\n"
        "معامله خودکار: خاموش\n"
        f"زمان: {now}"
    )

    print("ATI BOURSE BOT started.")

    try:
        markets = get_market_list()
        print("Markets received:", len(markets))

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
                signal, details = ichimoku_buy_signal(candles)

                if signal:
                    name = (
                        item.get("lVal18AFC")
                        or item.get("instrumentName")
                        or ins_code
                    )
                    signals.append(
                        f"🟢 سیگنال خرید ایچیموکو\n"
                        f"نماد: {name}\n"
                        f"کد: {ins_code}\n"
                        f"تایم‌فریم: ۱ ساعته\n"
                        f"{details}"
                    )

            except Exception as exc:
                errors += 1
                print("Symbol error:", ins_code, exc)

            time.sleep(0.15)

        print(
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
                "در این اجرا سیگنال خرید ایچیموکو پیدا نشد."
            )

    except Exception as exc:
        print("BOT ERROR:", traceback.format_exc())
        send_telegram(
            "⚠️ خطا در ربات بورس ATI\n"
            f"{str(exc)[:700]}"
        )


if __name__ == "__main__":
    main()
