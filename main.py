import os
import time
import requests
from datetime import datetime, timezone

# =========================================================
# ATI BOURSE BOT V2.8 - BRSAPI DATA
# =========================================================

VERSION = "ATI-BOURSE-V2.8-BRSAPI-TOP5"

REAL_TRADING = False

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

BRS_API_KEY = os.getenv("BRS_API_KEY", "").strip()

API_URL = "https://Api.BrsApi.ir/Tsetmc/History.php"

TIMEOUT = 25

# نمادهای بزرگ و پرمعامله برای اسکن
SYMBOLS = [
    "فملی",
    "فولاد",
    "شستا",
    "خودرو",
    "خساپا",
    "وبملت",
    "وتجارت",
    "شبندر",
    "شپنا",
    "ذوب",
    "کگل",
    "کچاد",
    "نوری",
    "پارس",
    "تاپیکو",
    "وغدیر",
    "رمپنا",
    "شتران",
    "وبصادر",
    "خگستر",
    "کرمان",
    "وساپا",
    "ثبهساز",
    "فاذر",
    "آریا",
]


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM SECRETS MISSING")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }

    try:
        r = requests.post(
            url,
            json=payload,
            timeout=20
        )

        if r.ok:
            return True

        print("Telegram error:", r.text)
        return False

    except Exception as e:
        print("Telegram exception:", e)
        return False


# =========================================================
# BRSAPI
# =========================================================

def get_history(symbol):

    params = {
        "key": BRS_API_KEY,
        "type": 0,
        "l18": symbol,
    }

    try:

        r = requests.get(
            API_URL,
            params=params,
            timeout=TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        print(
            f"📡 {symbol} HTTP {r.status_code}"
        )

        if not r.ok:
            return []

        data = r.json()

        if isinstance(data, list):
            return data

        if isinstance(data, dict):

            # چند حالت متداول
            for key in [
                "data",
                "result",
                "history",
                "History",
                "items",
            ]:

                if key in data and isinstance(
                    data[key], list
                ):
                    return data[key]

        return []

    except Exception as e:

        print(
            f"❌ {symbol} DATA ERROR: {e}"
        )

        return []


# =========================================================
# NUMBER
# =========================================================

def num(value):

    try:
        if value is None:
            return 0.0

        if isinstance(value, str):
            value = value.replace(",", "").strip()

        return float(value)

    except Exception:
        return 0.0


# =========================================================
# NORMALIZE
# =========================================================

def normalize_row(row):

    if not isinstance(row, dict):
        return None

    close = num(
        row.get("pf")
        or row.get("close")
        or row.get("pClosing")
        or row.get("pc")
    )

    previous = num(
        row.get("py")
        or row.get("previous")
        or row.get("priceYesterday")
    )

    high = num(
        row.get("pmax")
        or row.get("high")
        or row.get("priceMax")
    )

    low = num(
        row.get("pmin")
        or row.get("low")
        or row.get("priceMin")
    )

    volume = num(
        row.get("tvol")
        or row.get("volume")
        or row.get("qTotTran5J")
    )

    trades = num(
        row.get("tno")
        or row.get("trades")
        or row.get("zTotTran")
    )

    value = num(
        row.get("tval")
        or row.get("value")
        or row.get("qTotCap")
    )

    if close <= 0:
        return None

    if previous <= 0:
        return None

    change = (
        (close - previous)
        / previous
    ) * 100

    return {
        "close": close,
        "previous": previous,
        "high": high,
        "low": low,
        "volume": volume,
        "trades": trades,
        "value": value,
        "change": change,
    }


# =========================================================
# SCORE
# =========================================================

def calculate_score(d):

    score = 0

    change = d["change"]
    volume = d["volume"]
    trades = d["trades"]
    value = d["value"]

    # تغییر قیمت
    if change >= 4:
        score += 35
    elif change >= 3:
        score += 30
    elif change >= 2:
        score += 25
    elif change >= 1:
        score += 18
    elif change >= 0.5:
        score += 10
    elif change > 0:
        score += 5

    # حجم
    if volume >= 10_000_000:
        score += 25
    elif volume >= 5_000_000:
        score += 22
    elif volume >= 1_000_000:
        score += 18
    elif volume >= 300_000:
        score += 12
    elif volume >= 100_000:
        score += 7

    # تعداد معاملات
    if trades >= 5000:
        score += 20
    elif trades >= 2000:
        score += 17
    elif trades >= 1000:
        score += 14
    elif trades >= 500:
        score += 10
    elif trades >= 200:
        score += 5

    # ارزش معاملات
    if value >= 100_000_000_000:
        score += 20
    elif value >= 50_000_000_000:
        score += 17
    elif value >= 10_000_000_000:
        score += 14
    elif value >= 2_000_000_000:
        score += 10
    elif value >= 500_000_000:
        score += 5

    # شتاب مثبت
    if change >= 2:
        score += 5

    return score


# =========================================================
# ANALYZE
# =========================================================

def analyze_symbol(symbol):

    history = get_history(symbol)

    if not history:
        return None

    # آخرین رکورد معتبر
    rows = []

    for row in history:

        normalized = normalize_row(row)

        if normalized:
            rows.append(normalized)

    if not rows:
        return None

    # معمولاً آخرین رکورد آخر لیست است
    d = rows[-1]

    # اگر چند روز داده داریم، تغییر حجم را هم بررسی کنیم
    volume_boost = False

    if len(rows) >= 2:

        previous_volume = rows[-2]["volume"]

        if previous_volume > 0:
            if d["volume"] >= previous_volume * 1.5:
                volume_boost = True
                d["score_bonus"] = 10
            else:
                d["score_bonus"] = 0
        else:
            d["score_bonus"] = 0

    else:
        d["score_bonus"] = 0

    score = calculate_score(d)

    score += d["score_bonus"]

    d["score"] = score
    d["volume_boost"] = volume_boost

    return d


# =========================================================
# TOP 5
# =========================================================

def get_top5():

    results = []

    print(
        f"🔎 SCANNING {len(SYMBOLS)} SYMBOLS..."
    )

    for symbol in SYMBOLS:

        data = analyze_symbol(symbol)

        if data is None:
            print(
                f"⚠️ {symbol}: NO VALID DATA"
            )
            continue

        # فقط نمادهای مثبت
        if data["change"] <= 0:
            print(
                f"⚪ {symbol}: NEGATIVE"
            )
            continue

        results.append({
            "symbol": symbol,
            **data
        })

        print(
            f"✅ {symbol} "
            f"| +{data['change']:.2f}% "
            f"| SCORE {data['score']}"
        )

        # فشار روی API کمتر شود
        time.sleep(0.25)

    results.sort(
        key=lambda x: (
            x["score"],
            x["change"],
            x["value"],
            x["volume"]
        ),
        reverse=True
    )

    return results[:5]


# =========================================================
# SIGNAL
# =========================================================

def create_signal(item, rank):

    symbol = item["symbol"]
    price = item["close"]

    # مدیریت ریسک
    stop = price * 0.97

    target1 = price * 1.05

    target2 = price * 1.08

    reason = []

    if item["change"] >= 2:
        reason.append(
            f"رشد قیمت +{item['change']:.2f}%"
        )

    if item["volume_boost"]:
        reason.append(
            "افزایش حجم معاملات"
        )

    if item["trades"] >= 1000:
        reason.append(
            "تعداد معاملات مناسب"
        )

    if item["value"] >= 10_000_000_000:
        reason.append(
            "ارزش معاملات بالا"
        )

    if not reason:
        reason.append(
            "امتیاز مناسب در اسکن بازار"
        )

    reason_text = " + ".join(reason)

    return (
        f"🏆 سهم شماره {rank}\n"
        f"📌 نماد: {symbol}\n\n"

        f"📊 تغییر: "
        f"+{item['change']:.2f}%\n"

        f"⭐ امتیاز: "
        f"{item['score']}\n\n"

        f"🟢 ورود پیشنهادی:\n"
        f"{price:,.0f} ریال\n\n"

        f"🛑 حد ضرر:\n"
        f"{stop:,.0f} ریال "
        f"(-3%)\n\n"

        f"🎯 هدف 1:\n"
        f"{target1:,.0f} ریال "
        f"(+5%)\n\n"

        f"🎯 هدف 2:\n"
        f"{target2:,.0f} ریال "
        f"(+8%)\n\n"

        f"📦 حجم: "
        f"{item['volume']:,.0f}\n"

        f"🔄 معاملات: "
        f"{item['trades']:,.0f}\n\n"

        f"🧠 دلیل انتخاب:\n"
        f"{reason_text}\n\n"

        f"⚠️ این قیمت‌ها سیگنال تحلیلی هستند؛ "
        f"خرید واقعی توسط ربات انجام نمی‌شود."
    )


# =========================================================
# MAIN
# =========================================================

def main():

    now = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    print(
        f"💓 ATI BOURSE ALIVE\n"
        f"⚡ {VERSION}\n"
        f"📊 بورس و فرابورس ایران\n"
        f"🔒 REAL TRADING: "
        f"{'ON' if REAL_TRADING else 'OFF'}\n"
        f"🕐 {now}"
    )

    if not BRS_API_KEY:

        message = (
            "❌ ATI BOURSE ERROR\n\n"
            "🔑 BRS_API_KEY در GitHub Secrets "
            "وجود ندارد.\n\n"
            "🚫 اسکن بازار انجام نشد.\n"
            "🔒 REAL TRADING: OFF"
        )

        print(message)
        send_telegram(message)
        return

    send_telegram(
        f"💓 ATI BOURSE ALIVE\n"
        f"⚡ {VERSION}\n"
        f"📊 بورس و فرابورس ایران\n"
        f"🔒 REAL TRADING: OFF\n"
        f"📡 DATA: BrsApi\n"
        f"🕐 {now}"
    )

    top5 = get_top5()

    if not top5:

        message = (
            "❌ ATI BOURSE ERROR\n\n"
            "هیچ سهم معتبر و مثبتی از "
            "منبع داده دریافت نشد.\n\n"
            "📡 DATA SOURCE: BrsApi\n"
            "🚫 هیچ سهمی انتخاب نشد.\n"
            "🔒 REAL TRADING: OFF\n"
            f"🕐 {now}"
        )

        print(message)
        send_telegram(message)
        return

    header = (
        "🚀 ATI BOURSE TOP 5\n"
        f"⚡ {VERSION}\n"
        "📡 DATA: BrsApi / TSETMC\n"
        "🔒 REAL TRADING: OFF\n\n"
        "📋 5 سهم برتر امروز:"
    )

    send_telegram(header)

    for i, item in enumerate(
        top5,
        start=1
    ):

        message = create_signal(
            item,
            i
        )

        print("\n" + message)

        send_telegram(message)

        time.sleep(1)

    send_telegram(
        "✅ ATI BOURSE SCAN COMPLETE\n"
        f"🏆 {len(top5)} سهم انتخاب شد.\n"
        "🔒 REAL TRADING: OFF"
    )


if __name__ == "__main__":
    main()
