import os
import sys
import time
import traceback
from datetime import datetime, timezone
from io import BytesIO

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TOP = max(1, min(10, int(os.getenv("TOP_SIGNALS", "5"))))
MIN_SCORE = max(30, min(90, int(os.getenv("MIN_SCORE", "55"))))
TIMEOUT = 25
CDN = "https://cdn.tsetmc.com/api"
OLD_DATA = "https://old.tsetmc.com/tsev2/data"
OLD_EXCEL = "https://old.tsetmc.com/tsev2/excel/MarketWatchPlus.aspx"

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept": "application/json,text/plain,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
    "Referer": "https://www.tsetmc.com/",
    "Origin": "https://www.tsetmc.com",
})
retry = Retry(
    total=2,
    connect=2,
    read=2,
    backoff_factor=0.7,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET", "POST"]),
    raise_on_status=False,
)
S.mount("https://", HTTPAdapter(max_retries=retry))


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def num(v):
    try:
        if v is None or v == "":
            return 0.0
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def first(row, *keys):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize(row, allow_no_ins=False):
    # Some TSETMC responses nest quote fields under an instrument object.
    if isinstance(row.get("instrument"), dict):
        merged = dict(row["instrument"])
        merged.update({k: v for k, v in row.items() if k != "instrument"})
        row = merged

    symbol = str(first(row, "lVal18AFC", "l18", "symbol", "instrumentName", "instrument_Name") or "").strip()
    name = str(first(row, "lVal30", "l30", "name", "companyNamePersian") or symbol).strip()
    ins = str(first(row, "insCode", "inscode", "ins_code") or "").strip()
    flow = int(num(first(row, "flow", "flowCode", "flowId")))
    last = num(first(row, "pDrCotVal", "pl", "lastPrice", "lastprice"))
    close = num(first(row, "pClosing", "pc", "closePrice", "closingPrice"))
    prev = num(first(row, "priceYesterday", "py", "yesterdayPrice"))
    low = num(first(row, "priceMin", "pmin", "minValue", "lowValue"))
    high = num(first(row, "priceMax", "pmax", "maxValue", "highValue"))
    vol = num(first(row, "qTotTran5J", "tvol", "volume", "tradeVolume"))
    value = num(first(row, "qTotCap", "tval", "value", "tradeValue"))
    trades = num(first(row, "zTotTran", "tno", "tradeCount", "tradeCount"))
    base = num(first(row, "baseVol", "bvol", "baseVolume"))

    if not symbol or last <= 0 or prev <= 0 or vol <= 0:
        return None
    if not allow_no_ins and (not ins or flow not in (1, 2)):
        return None
    if flow not in (0, 1, 2):
        flow = 0

    excluded = ("صندوق", "اختیار", "حق تقدم", "اوراق", "اسناد", "گواهی", "تسهیلات", "اجاره")
    if any(word in name for word in excluded) or any(word in symbol for word in ("اختیار", "ح", "ض")):
        # Avoid broad filtering on single Persian letters; the name-based filter is primary.
        if any(word in name for word in excluded) or "اختیار" in symbol:
            return None

    return {
        "symbol": symbol,
        "name": name,
        "flow": flow,
        "last": last,
        "close": close,
        "prev": prev,
        "low": low,
        "high": high,
        "vol": vol,
        "value": value,
        "trades": trades,
        "base": base,
        "change": (last - prev) / prev * 100.0,
    }


def fetch_cdn():
    # Try both traded-only and full-watch modes; pre-market responses can be empty.
    attempts = []
    for show_traded in ("false", "true"):
        params = [
            ("market", "0"),
            ("industrialGroup", ""),
            ("showTraded", show_traded),
            ("withBestLimits", "false"),
            ("hEven", "0"),
            ("RefID", "0"),
        ]
        params += [(f"paperTypes[{i}]", str(i + 1)) for i in range(9)]
        response = S.get(CDN + "/ClosingPrice/GetMarketWatch", params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        rows = data.get("marketwatch", []) if isinstance(data, dict) else []
        valid = [normalize(item) for item in rows if isinstance(item, dict)]
        valid = [item for item in valid if item]
        attempts.append(f"showTraded={show_traded}: raw={len(rows)} valid={len(valid)}")
        if valid:
            return valid
    raise RuntimeError("CDN no usable rows (" + "; ".join(attempts) + ")")


def fetch_old_init():
    response = S.get(OLD_DATA + "/MarketWatchInit.aspx", params={"h": "0", "r": "0"}, timeout=TIMEOUT)
    response.raise_for_status()
    parts = response.text.split("@")
    if len(parts) < 3:
        raise RuntimeError("Legacy MarketWatchInit response format changed")
    out = []
    for line in parts[2].split(";"):
        cols = line.split(",")
        if len(cols) < 26:
            continue
        row = {
            "insCode": cols[0], "l18": cols[2], "l30": cols[3],
            "pc": cols[6], "pl": cols[7], "tno": cols[8],
            "tvol": cols[9], "tval": cols[10], "pmin": cols[11],
            "pmax": cols[12], "py": cols[13], "bvol": cols[15], "flow": cols[17],
        }
        item = normalize(row)
        if item:
            out.append(item)
    if not out:
        raise RuntimeError("Legacy MarketWatchInit returned no valid stock rows")
    return out


def fetch_old_excel():
    # TSETMC documents this Excel export as a full-market fallback.
    response = S.get(OLD_EXCEL, params={"d": "0"}, timeout=60)
    response.raise_for_status()
    if not response.content.startswith(b"PK"):
        raise RuntimeError("MarketWatchPlus did not return an XLSX file")

    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("openpyxl is missing; add openpyxl to requirements.txt") from exc

    workbook = load_workbook(BytesIO(response.content), read_only=True, data_only=True)
    sheet = workbook.active
    all_rows = list(sheet.iter_rows(values_only=True))
    workbook.close()
    out = []

    # Documented export order: symbol, name, trades, volume, value, yesterday,
    # first, last, last change, last %, close, close change, close %, low, high.
    for values in all_rows:
        if not values or len(values) < 15:
            continue
        symbol = str(values[0] or "").strip()
        name = str(values[1] or symbol).strip()
        if not symbol or symbol in ("نماد", "Symbol"):
            continue
        row = {
            "symbol": symbol, "name": name,
            "tno": values[2], "tvol": values[3], "tval": values[4],
            "py": values[5], "pl": values[7], "pc": values[10],
            "pmin": values[13], "pmax": values[14],
        }
        item = normalize(row, allow_no_ins=True)
        if item:
            out.append(item)
    if not out:
        raise RuntimeError("MarketWatchPlus XLSX parsed but contained no valid stock rows")
    return out


def analyze(item):
    """Score only facts available in the live market-watch snapshot."""
    change = item["change"]
    points = 0
    tags = []
    details = []

    # Positive price difference / daily momentum.
    if change > 0:
        points += 15
        tags.append("اختلاف قیمت مثبت")
    if 0.8 <= change <= 4.5:
        points += 10
        details.append("رشد روزانه متعادل")
    elif 4.5 < change <= 6.5:
        points += 4
        details.append("رشد تند؛ ریسک تعقیب قیمت")
    elif change > 6.5:
        details.append("رشد بیش از حد؛ حذف از فهرست")
    else:
        details.append("قیمت منفی؛ حذف از فهرست")

    # Last trade at/above closing price is a simple strength confirmation.
    if item["close"] > 0 and item["last"] >= item["close"]:
        points += 12
        tags.append("قدرت قیمت")

    # Daily traded volume relative to the symbol's base volume.
    ratio = item["vol"] / item["base"] if item["base"] > 0 else 0
    if ratio >= 2:
        points += 20
        tags.append("حجم بسیار بالا نسبت به حجم مبنا")
    elif ratio >= 1:
        points += 14
        tags.append("حجم بالاتر از حجم مبنا")
    elif ratio >= 0.5:
        points += 7
        tags.append("حجم قابل توجه")

    # Liquidity / participation.
    if item["value"] >= 100_000_000_000:
        points += 16
        tags.append("ارزش معاملات بالا")
    elif item["value"] >= 30_000_000_000:
        points += 12
    elif item["value"] >= 10_000_000_000:
        points += 7

    if item["trades"] >= 1500:
        points += 12
        tags.append("تعداد معاملات بالا")
    elif item["trades"] >= 500:
        points += 8
    elif item["trades"] >= 150:
        points += 4

    # Position inside today's range. This is NOT a confirmed support/resistance level.
    position = None
    if item["high"] > item["low"] > 0:
        position = (item["last"] - item["low"]) / (item["high"] - item["low"])
        if position >= 0.85:
            points += 16
            tags.append("نزدیک سقف روز")
        elif position >= 0.65:
            points += 10
        elif position >= 0.45:
            points += 5
        if position <= 0.20:
            details.append("نزدیک کف روز؛ نیازمند احتیاط")

    # Hard filters prevent negative or overheated names from being promoted.
    if change < 0.4 or change > 6.5:
        points = 0

    item["score"] = min(100, int(points))
    item["volume_ratio"] = ratio
    item["day_position"] = position
    item["tags"] = tags
    item["details"] = details
    return item["score"]

def telegram(message):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing in GitHub Secrets")
    response = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": message, "disable_web_page_preview": True},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError("Telegram error: " + response.text[:400])


def main():
    started = time.time()
    print("ATI BOURSE BOT V1.2 | SIGNAL ONLY | REAL TRADING OFF")
    errors, rows, source = [], [], "NONE"

    sources = [
        ("TSETMC CDN JSON", fetch_cdn),
        ("TSETMC MarketWatchPlus XLSX", fetch_old_excel),
        ("TSETMC Legacy MarketWatchInit", fetch_old_init),
    ]
    for label, function in sources:
        try:
            rows = function()
            source = label
            break
        except Exception as exc:
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
            print(errors[-1])

    if not rows:
        message = (
            "🤖 ATI BOURSE BOT V1.2\n"
            "دریافت اطلاعات بازار ناموفق بود؛ هیچ سیگنال ساختگی ارسال نشد.\n"
            f"زمان: {now()}\n\n" + "\n".join(errors)
        )[:3900]
        telegram(message)
        raise RuntimeError("No market data from all configured sources")

    unique = {}
    for item in rows:
        if item["symbol"] in unique:
            continue
        analyze(item)
        if item["score"] >= MIN_SCORE:
            unique[item["symbol"]] = item

    signals = sorted(
        unique.values(),
        key=lambda item: (item["score"], item["value"], item["trades"]),
        reverse=True,
    )[:TOP]

    lines = [
        "🤖 ATI BOURSE BOT V1.2",
        "حالت: فقط سیگنال | معامله واقعی: خاموش",
        f"زمان: {now()}",
        f"منبع: {source}",
        f"نمادهای معتبر: {len(rows)}",
        f"حداقل امتیاز: {MIN_SCORE}/100",
        f"مدت اجرا: {time.time() - started:.1f} ثانیه",
        "فیلترهای قابل سنجش: اختلاف قیمت، قدرت قیمت، حجم مبنا، ارزش و تعداد معاملات، جایگاه قیمت در دامنه روز",
        "فیلترهای نیازمند داده تاریخی/لحظه‌ای جداگانه: واگرایی، پولبک، حمایت و مقاومت معتبر، تغییر صف خرید/فروش و اطلاعیه افزایش سرمایه",
        "",
        "",
    ]
    if not signals:
        lines.append("⚠️ این نوبت سهمی با شرایط تعیین‌شده پیدا نشد؛ خریدی پیشنهاد نمی‌شود.")

    for index, item in enumerate(signals, 1):
        if item["flow"] == 1:
            market = "بورس"
        elif item["flow"] == 2:
            market = "فرابورس"
        else:
            market = "بازار نقدی؛ نوع بازار در منبع جایگزین مشخص نبود"
        lines.extend([
            f"{index}) {item['symbol']} - {item['name']}",
            f"{market} | امتیاز {item['score']}/100 | تغییر {item['change']:+.2f}%",
            f"قیمت آخرین معامله: {item['last']:,.0f}",
            f"حد ضرر محاسباتی ۳٪: {item['last'] * 0.97:,.0f}",
            f"هدف اول ۵٪: {item['last'] * 1.05:,.0f} | هدف دوم ۸٪: {item['last'] * 1.08:,.0f}",
            f"ارزش معاملات: {item['value']:,.0f} | تعداد معاملات: {int(item['trades']):,}",
            f"نسبت حجم به حجم مبنا: {item['volume_ratio']:.2f} برابر",
            "نشانه‌ها: " + ("، ".join(item["tags"]) if item["tags"] else "تأیید محدود"),
            "توضیح: " + ("؛ ".join(item["details"]) if item["details"] else "—"),
            "",
        ])

    lines.append("⚠️ این رتبه‌بندی غربالگری ماشینی است؛ سود تضمین نمی‌شود. «حجم مشکوک» فقط نسبت به حجم مبناست و به‌تنهایی نشانه ورود پول هوشمند نیست.")
    lines.append("⚠️ واگرایی، پولبک، صف‌ها و افزایش سرمایه در این نسخه تأیید نمی‌شوند؛ برای آن‌ها داده کندلی، سفارش‌ها و اطلاعیه‌های جداگانه لازم است.")
    message = "\n".join(lines)
    print(message)
    telegram(message)
    print("Telegram report sent.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("BOT ERROR:", exc)
        traceback.print_exc()
        sys.exit(1)
