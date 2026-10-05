# ============================================================
# ATI BOURSE BOT V1.0
# Tehran Stock Exchange / Farabourse
# SIGNAL ONLY - NO REAL TRADING
# ============================================================

import os
import time
import math
import statistics
from datetime import datetime, timezone

import requests


# ============================================================
# CONFIG
# ============================================================

BOT_VERSION = "ATI-BOURSE-V1.0"

TSETMC_BASE = "https://cdn.tsetmc.com"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# فعلاً خرید واقعی کاملاً خاموش است
REAL_TRADING = False

REQUEST_TIMEOUT = 20

# حداقل امتیاز برای ارسال BUY
MIN_SCORE = 65

# حداکثر تعداد سیگنال در هر اجرا
MAX_SIGNALS = 10

# نمادهای منتخب اولیه
# اگر خالی باشد، از Market Watch استفاده می‌شود
WATCHLIST = [
    "فملی",
    "فولاد",
    "شستا",
    "خودرو",
    "خساپا",
    "وبملت",
    "وتجارت",
    "ذوب",
    "شپنا",
    "شبندر",
    "نوری",
    "پارس",
    "شتران",
    "کگل",
    "کچاد",
]


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }
)


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ TELEGRAM SECRETS NOT SET")
        print(message)
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
        response = SESSION.post(
            url,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )

        if response.ok:
            return True

        print(
            "❌ TELEGRAM ERROR:",
            response.status_code,
            response.text[:500],
        )

    except Exception as exc:
        print("❌ TELEGRAM CONNECTION ERROR:", exc)

    return False


# ============================================================
# GENERAL HELPERS
# ============================================================

def safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        if isinstance(value, str):
            value = value.replace(",", "").strip()

        return float(value)

    except Exception:
        return default


def clamp(value, low, high):
    return max(low, min(high, value))


def pct_change(old, new):
    old = safe_float(old)
    new = safe_float(new)

    if old == 0:
        return 0.0

    return ((new - old) / old) * 100.0


def fmt_price(value):
    value = safe_float(value)

    if value == 0:
        return "0"

    if value >= 1000:
        return f"{value:,.0f}"

    if value >= 100:
        return f"{value:,.1f}"

    if value >= 10:
        return f"{value:,.2f}"

    return f"{value:,.4f}"


def now_text():
    return datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


# ============================================================
# TSETMC REQUEST
# ============================================================

def tsetmc_get(path, params=None):
    url = TSETMC_BASE + path

    try:
        response = SESSION.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        return response.json()

    except Exception as exc:
        print("❌ TSETMC ERROR")
        print(url)
        print(exc)
        return None


# ============================================================
# MARKET WATCH
# ============================================================

def get_market_watch():
    """
    دریافت دیده‌بان بازار.

    مسیر:
    /api/ClosingPrice/GetMarketWatch
    """

    params = {
        "market": 0,
        "paperTypes[0]": 1,
        "paperTypes[1]": 2,
        "paperTypes[2]": 3,
        "paperTypes[3]": 4,
        "paperTypes[4]": 5,
        "paperTypes[5]": 6,
        "paperTypes[6]": 7,
        "paperTypes[7]": 8,
        "paperTypes[8]": 9,
        "withBestLimits": "false",
        "hEven": 0,
        "RefID": 0,
    }

    data = tsetmc_get(
        "/api/ClosingPrice/GetMarketWatch",
        params=params,
    )

    if not data:
        return []

    marketwatch = data.get("marketwatch", [])

    if isinstance(marketwatch, dict):
        for key in (
            "marketWatch",
            "data",
            "items",
            "rows",
        ):
            if isinstance(marketwatch.get(key), list):
                marketwatch = marketwatch[key]
                break

    if not isinstance(marketwatch, list):
        return []

    return marketwatch


# ============================================================
# EXTRACT MARKET ROW
# ============================================================

def normalize_market_row(row):
    """
    تلاش می‌کند ساختارهای مختلف TSETMC را به یک ساختار واحد تبدیل کند.
    """

    if not isinstance(row, dict):
        return None

    def pick(*names):
        for name in names:
            if name in row:
                return row[name]
        return None

    symbol = pick(
        "lVal18AFC",
        "l18",
        "symbol",
        "shortName",
        "short_name",
    )

    full_name = pick(
        "lVal30",
        "l30",
        "fullName",
        "full_name",
    )

    ins_code = pick(
        "insCode",
        "inscode",
        "ins_code",
        "id",
    )

    close = pick(
        "pClosing",
        "pc",
        "close",
        "closingPrice",
    )

    last = pick(
        "pDrCotVal",
        "pl",
        "last",
        "lastPrice",
    )

    yesterday = pick(
        "priceYesterday",
        "py",
        "yesterday",
    )

    high = pick(
        "priceMax",
        "pmax",
        "high",
    )

    low = pick(
        "priceMin",
        "pmin",
        "low",
    )

    volume = pick(
        "qTotTran5J",
        "tvol",
        "volume",
    )

    value = pick(
        "qTotCap",
        "tval",
        "value",
    )

    trades = pick(
        "zTotTran",
        "tno",
        "count",
        "trades",
    )

    base_volume = pick(
        "baseVol",
        "bvol",
        "base_volume",
    )

    if not symbol:
        return None

    return {
        "symbol": str(symbol).strip(),
        "name": str(full_name or symbol).strip(),
        "ins_code": str(ins_code or "").strip(),
        "close": safe_float(close),
        "last": safe_float(last),
        "yesterday": safe_float(yesterday),
        "high": safe_float(high),
        "low": safe_float(low),
        "volume": safe_float(volume),
        "value": safe_float(value),
        "trades": safe_float(trades),
        "base_volume": safe_float(base_volume),
    }


# ============================================================
# DAILY HISTORY
# ============================================================

def get_history(ins_code, limit=120):
    """
    دریافت سابقه قیمت روزانه.
    """

    if not ins_code:
        return []

    path = (
        f"/api/ClosingPrice/"
        f"GetClosingPriceDailyList/"
        f"{ins_code}/0"
    )

    data = tsetmc_get(path)

    if not data:
        return []

    rows = data.get("closingPriceDaily", [])

    if not isinstance(rows, list):
        return []

    history = []

    for row in rows:

        if not isinstance(row, dict):
            continue

        close = safe_float(
            row.get("pClosing", row.get("pClosingPrice"))
        )

        last = safe_float(
            row.get("pDrCotVal", row.get("last"))
        )

        high = safe_float(
            row.get("priceMax", row.get("pMax"))
        )

        low = safe_float(
            row.get("priceMin", row.get("pMin"))
        )

        yesterday = safe_float(
            row.get("priceYesterday", row.get("pYest"))
        )

        volume = safe_float(
            row.get("qTotTran5J", row.get("volume"))
        )

        if close <= 0:
            continue

        history.append(
            {
                "date": row.get("dEven"),
                "close": close,
                "last": last,
                "high": high if high > 0 else close,
                "low": low if low > 0 else close,
                "yesterday": yesterday,
                "volume": volume,
            }
        )

    # قدیمی → جدید
    history.sort(
        key=lambda x: str(x.get("date", ""))
    )

    return history[-limit:]


# ============================================================
# TECHNICAL CALCULATIONS
# ============================================================

def simple_average(values):
    values = [
        safe_float(x)
        for x in values
        if safe_float(x) > 0
    ]

    if not values:
        return 0.0

    return sum(values) / len(values)


def calculate_returns(closes):
    returns = []

    for i in range(1, len(closes)):
        previous = safe_float(closes[i - 1])
        current = safe_float(closes[i])

        if previous <= 0:
            continue

        returns.append(
            ((current - previous) / previous) * 100
        )

    return returns


def volatility(values):
    if len(values) < 2:
        return 0.0

    try:
        return statistics.pstdev(values)
    except Exception:
        return 0.0


def trend_score(closes):
    """
    روند کوتاه‌مدت و میان‌مدت.
    """

    if len(closes) < 20:
        return 0

    current = closes[-1]

    ma5 = simple_average(closes[-5:])
    ma10 = simple_average(closes[-10:])
    ma20 = simple_average(closes[-20:])

    score = 0

    if current > ma5:
        score += 10

    if current > ma10:
        score += 10

    if current > ma20:
        score += 10

    if ma5 > ma10:
        score += 8

    if ma10 > ma20:
        score += 7

    return score


def momentum_score(closes):
    if len(closes) < 15:
        return 0

    score = 0

    r3 = pct_change(closes[-4], closes[-1])
    r5 = pct_change(closes[-6], closes[-1])
    r10 = pct_change(closes[-11], closes[-1])

    if r3 > 0:
        score += 8

    if r5 > 0:
        score += 7

    if r10 > 0:
        score += 5

    if r5 >= 2:
        score += 5

    if r10 >= 5:
        score += 5

    return score


def volume_score(volumes):
    if len(volumes) < 20:
        return 0

    current = volumes[-1]

    avg20 = simple_average(volumes[-20:])

    if avg20 <= 0:
        return 0

    ratio = current / avg20

    if ratio >= 2.0:
        return 20

    if ratio >= 1.5:
        return 16

    if ratio >= 1.2:
        return 12

    if ratio >= 1.0:
        return 7

    return 0


def price_structure_score(history):
    if len(history) < 20:
        return 0

    recent = history[-20:]

    closes = [
        x["close"]
        for x in recent
        if x["close"] > 0
    ]

    highs = [
        x["high"]
        for x in recent
        if x["high"] > 0
    ]

    lows = [
        x["low"]
        for x in recent
        if x["low"] > 0
    ]

    if not closes:
        return 0

    current = closes[-1]

    resistance = max(highs[:-2]) if len(highs) > 2 else max(highs)
    support = min(lows[:-2]) if len(lows) > 2 else min(lows)

    score = 0

    if resistance > 0:
        distance = ((resistance - current) / current) * 100

        # نزدیک مقاومت
        if 0 <= distance <= 3:
            score += 10

        # شکست مقاومت
        if current > resistance:
            score += 20

    if support > 0:
        support_distance = (
            (current - support) / current
        ) * 100

        if 0 < support_distance <= 5:
            score += 5

    return score


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def calculate_levels(history):
    if len(history) < 15:
        return None

    recent = history[-30:]

    highs = [
        x["high"]
        for x in recent
        if x["high"] > 0
    ]

    lows = [
        x["low"]
        for x in recent
        if x["low"] > 0
    ]

    closes = [
        x["close"]
        for x in recent
        if x["close"] > 0
    ]

    if not closes:
        return None

    current = closes[-1]

    resistance = max(highs[:-2]) if len(highs) > 2 else max(highs)
    support = min(lows[:-2]) if len(lows) > 2 else min(lows)

    # اگر حمایت غیرواقعی بود
    if support <= 0 or support >= current:
        support = min(lows)

    if resistance <= 0:
        resistance = max(highs)

    return {
        "current": current,
        "support": support,
        "resistance": resistance,
    }


# ============================================================
# SIGNAL ENGINE
# ============================================================

def analyze_symbol(row, history):
    if not row or len(history) < 25:
        return None

    closes = [
        x["close"]
        for x in history
        if x["close"] > 0
    ]

    volumes = [
        x["volume"]
        for x in history
        if x["volume"] >= 0
    ]

    if len(closes) < 25:
        return None

    current = closes[-1]

    levels = calculate_levels(history)

    if not levels:
        return None

    support = levels["support"]
    resistance = levels["resistance"]

    score = 0
    reasons = []

    # -------------------------
    # Trend
    # -------------------------

    ts = trend_score(closes)

    score += ts

    if ts >= 25:
        reasons.append("روند صعودی کوتاه‌مدت و میان‌مدت")

    # -------------------------
    # Momentum
    # -------------------------

    ms = momentum_score(closes)

    score += ms

    if ms >= 15:
        reasons.append("مومنتوم مثبت")

    # -------------------------
    # Volume
    # -------------------------

    vs = volume_score(volumes)

    score += vs

    if vs >= 12:
        reasons.append("حجم معاملات بالاتر از میانگین")

    # -------------------------
    # Structure
    # -------------------------

    ps = price_structure_score(history)

    score += ps

    if ps >= 15:
        reasons.append("ساختار قیمت و شکست/نزدیکی مقاومت")

    # -------------------------
    # Current daily move
    # -------------------------

    yesterday = row.get("yesterday", 0)

    if yesterday <= 0:
        yesterday = closes[-2]

    daily_move = pct_change(
        yesterday,
        current,
    )

    # رشد بیش از حد روزانه = احتیاط
    if daily_move > 6:
        score -= 10
        reasons.append("رشد روزانه زیاد؛ ریسک تعقیب قیمت")

    elif daily_move > 0:
        score += 3

    # -------------------------
    # Price location
    # -------------------------

    if resistance > 0:
        distance_to_resistance = (
            (resistance - current)
            / current
        ) * 100

        # اگر خیلی بالای مقاومت باشد
        if distance_to_resistance < -8:
            score -= 8

    score = int(clamp(score, 0, 100))

    # -------------------------
    # Minimum score
    # -------------------------

    if score < MIN_SCORE:
        return None

    # -------------------------
    # Entry
    # -------------------------

    entry = current

    # اگر قیمت به مقاومت خیلی نزدیک است،
    # ورود پیشنهادی کمی بالاتر از مقاومت قرار می‌گیرد.
    if resistance > 0:
        resistance_distance = (
            (resistance - current)
            / current
        ) * 100

        if 0 <= resistance_distance <= 2:
            entry = resistance * 1.005

            reasons.append(
                "ورود پیشنهادی بعد از تأیید شکست مقاومت"
            )

    # -------------------------
    # Stop Loss
    # -------------------------

    # حد ضرر بین حمایت و حدود 4٪ زیر ورود
    if support > 0 and support < entry:
        support_stop = support * 0.985
    else:
        support_stop = entry * 0.96

    fixed_stop = entry * 0.96

    stop = max(
        support_stop,
        fixed_stop,
    )

    # جلوگیری از حد ضرر بالاتر از ورود
    if stop >= entry:
        stop = entry * 0.96

    risk = entry - stop

    if risk <= 0:
        return None

    # -------------------------
    # Targets
    # -------------------------

    target1 = entry + (risk * 1.5)
    target2 = entry + (risk * 2.5)
    target3 = entry + (risk * 4.0)

    # اگر مقاومت بالاتر است،
    # هدف اول را با ساختار بازار هماهنگ می‌کنیم.
    if resistance > entry:
        target1 = max(
            target1,
            resistance * 1.01,
        )

    reward3 = target3 - entry

    rr3 = reward3 / risk

    if rr3 < 1.5:
        return None

    # -------------------------
    # Reason fallback
    # -------------------------

    if not reasons:
        reasons.append("ترکیب روند، مومنتوم و ساختار قیمت")

    # حذف دلایل تکراری
    reasons = list(dict.fromkeys(reasons))

    return {
        "symbol": row["symbol"],
        "name": row["name"],
        "score": score,
        "entry": entry,
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "target3": target3,
        "rr": rr3,
        "daily_move": daily_move,
        "support": support,
        "resistance": resistance,
        "reasons": reasons,
    }


# ============================================================
# FORMAT SIGNAL
# ============================================================

def format_signal(signal):
    symbol = signal["symbol"]

    reasons = "\n".join(
        f"• {reason}"
        for reason in signal["reasons"]
    )

    return (
        f"🚨 ATI BOURSE SIGNAL\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 نماد: {symbol}\n"
        f"🏢 {signal['name']}\n\n"

        f"🟢 ورود پیشنهادی:\n"
        f"{fmt_price(signal['entry'])}\n\n"

        f"🛑 حد ضرر:\n"
        f"{fmt_price(signal['stop'])}\n\n"

        f"🎯 هدف 1:\n"
        f"{fmt_price(signal['target1'])}\n\n"

        f"🎯 هدف 2:\n"
        f"{fmt_price(signal['target2'])}\n\n"

        f"🎯 هدف 3:\n"
        f"{fmt_price(signal['target3'])}\n\n"

        f"⭐ امتیاز: {signal['score']}/100\n"
        f"📊 R/R: {signal['rr']:.2f}\n"
        f"📈 تغییر روزانه: {signal['daily_move']:.2f}%\n\n"

        f"🧠 دلیل انتخاب:\n"
        f"{reasons}\n\n"

        f"⚠️ این پیام سیگنال تحلیلی است؛ "
        f"خرید واقعی توسط ربات انجام نمی‌شود.\n"
        f"🕐 {now_text()}\n"
        f"⚡ {BOT_VERSION}"
    )


# ============================================================
# HEARTBEAT
# ============================================================

def send_start_message():
    message = (
        f"💓 ATI BOURSE ALIVE\n"
        f"⚡ {BOT_VERSION}\n"
        f"📊 بورس و فرابورس ایران\n"
        f"🔒 REAL TRADING: OFF\n"
        f"📡 TSETMC DATA\n"
        f"🕐 {now_text()}\n\n"
        f"🔎 شروع اسکن بازار..."
    )

    send_telegram(message)


def send_no_signal_message(count):
    message = (
        f"💓 ATI BOURSE RUN COMPLETED\n"
        f"⚡ {BOT_VERSION}\n"
        f"📊 نمادهای بررسی‌شده: {count}\n"
        f"👀 فعلاً شرایط BUY قوی پیدا نشد.\n"
        f"🔒 REAL TRADING: OFF\n"
        f"🕐 {now_text()}"
    )

    send_telegram(message)


# ============================================================
# MAIN SCANNER
# ============================================================

def scan_market():
    print("=" * 60)
    print(f"⚡ {BOT_VERSION}")
    print("📊 BOURSE / FARABOURSE")
    print("🔒 REAL TRADING: OFF")
    print(f"🕐 {now_text()}")
    print("=" * 60)

    send_start_message()

    market_rows = get_market_watch()

    print(
        f"📡 MARKET WATCH ROWS: {len(market_rows)}"
    )

    if not market_rows:
        send_telegram(
            "❌ ATI BOURSE ERROR\n\n"
            "داده Market Watch از TSETMC دریافت نشد.\n"
            "ربات هیچ معامله‌ای انجام نداد."
        )

        return

    normalized = []

    for raw in market_rows:

        row = normalize_market_row(raw)

        if not row:
            continue

        normalized.append(row)

    print(
        f"📊 NORMALIZED SYMBOLS: {len(normalized)}"
    )

    # --------------------------------------------------------
    # Filter selected symbols
    # --------------------------------------------------------

    if WATCHLIST:

        selected = []

        watch_set = {
            x.strip()
            for x in WATCHLIST
            if x.strip()
        }

        for row in normalized:

            symbol = row["symbol"]

            if symbol in watch_set:
                selected.append(row)

        # اگر نمادها در MarketWatch پیدا نشدند،
        # حداقل MarketWatch را نگه می‌داریم
        if not selected:
            print(
                "⚠️ WATCHLIST SYMBOLS NOT FOUND"
            )

            selected = normalized[:50]

    else:
        selected = normalized

    print(
        f"🔎 SYMBOLS TO ANALYZE: {len(selected)}"
    )

    signals = []

    # --------------------------------------------------------
    # Analyze
    # --------------------------------------------------------

    for index, row in enumerate(selected, start=1):

        symbol = row["symbol"]

        print(
            f"[{index}/{len(selected)}] "
            f"Analyzing {symbol}"
        )

        try:

            history = get_history(
                row["ins_code"],
                limit=120,
            )

            if len(history) < 25:
                print(
                    f"  ⚠️ insufficient history: "
                    f"{len(history)}"
                )
                continue

            signal = analyze_symbol(
                row,
                history,
            )

            if signal:
                signals.append(signal)

                print(
                    f"  ✅ SIGNAL "
                    f"score={signal['score']}"
                )

            else:
                print("  - no signal")

        except Exception as exc:

            print(
                f"  ❌ analysis error: {exc}"
            )

        # فشار کمتر روی API
        time.sleep(0.25)

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    signals.sort(
        key=lambda x: (
            x["score"],
            x["rr"],
        ),
        reverse=True,
    )

    signals = signals[:MAX_SIGNALS]

    print(
        f"🚨 FINAL SIGNALS: {len(signals)}"
    )

    # --------------------------------------------------------
    # Send
    # --------------------------------------------------------

    if not signals:

        send_no_signal_message(
            len(selected)
        )

        return

    for signal in signals:

        message = format_signal(signal)

        print()
        print(message)
        print()

        send_telegram(message)

        time.sleep(1)


# ============================================================
# ERROR REPORT
# ============================================================

def send_fatal_error(exc):
    message = (
        f"🚨 ATI BOURSE ERROR\n"
        f"⚡ {BOT_VERSION}\n\n"
        f"❌ {type(exc).__name__}\n"
        f"{str(exc)[:800]}\n\n"
        f"🔒 هیچ معامله‌ای انجام نشد.\n"
        f"🕐 {now_text()}"
    )

    send_telegram(message)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        print(
            f"\n🚀 STARTING {BOT_VERSION}\n"
        )

        scan_market()

        print(
            "\n✅ ATI BOURSE RUN COMPLETED\n"
        )

    except KeyboardInterrupt:

        print(
            "\n🛑 BOT STOPPED"
        )

    except Exception as exc:

        print(
            "\n🚨 FATAL ERROR:"
        )

        print(exc)

        send_fatal_error(exc)
