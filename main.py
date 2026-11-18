import os, sys, time, traceback
from datetime import datetime, timezone
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TOP = int(os.getenv("TOP_SIGNALS", "5"))
MIN_SCORE = int(os.getenv("MIN_SCORE", "55"))
TIMEOUT = 25
CDN = "https://cdn.tsetmc.com/api"
OLD = "https://old.tsetmc.com/tsev2/data"
S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tsetmc.com/"
})

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def num(v):
    try: return float(str(v or 0).replace(",", ""))
    except (TypeError, ValueError): return 0.0

def get(row, *keys):
    for k in keys:
        if row.get(k) not in (None, ""): return row[k]
    return None

def normalize(r):
    symbol = str(get(r, "lVal18AFC", "symbol", "l18") or "").strip()
    name = str(get(r, "lVal30", "name", "l30") or symbol).strip()
    ins = str(get(r, "insCode", "inscode", "ins_code") or "").strip()
    flow = int(num(get(r, "flow", "flowCode")))
    last = num(get(r, "pDrCotVal", "pl", "lastPrice"))
    close = num(get(r, "pClosing", "pc", "closePrice"))
    prev = num(get(r, "priceYesterday", "py", "yesterdayPrice"))
    low = num(get(r, "priceMin", "pmin"))
    high = num(get(r, "priceMax", "pmax"))
    vol = num(get(r, "qTotTran5J", "tvol", "volume"))
    value = num(get(r, "qTotCap", "tval", "value"))
    trades = num(get(r, "zTotTran", "tno", "tradeCount"))
    base = num(get(r, "baseVol", "bvol", "baseVolume"))
    if not symbol or not ins or flow not in (1, 2) or last <= 0 or prev <= 0 or vol <= 0:
        return None
    if any(w in name for w in ("صندوق", "اختیار", "حق تقدم", "اوراق", "اسناد", "گواهی")):
        return None
    return dict(symbol=symbol, name=name, flow=flow, last=last, close=close,
                prev=prev, low=low, high=high, vol=vol, value=value,
                trades=trades, base=base, change=(last-prev)/prev*100)

def fetch_cdn():
    p = [("market","0"),("industrialGroup",""),("showTraded","true"),
         ("withBestLimits","false"),("hEven","0"),("RefID","0")]
    p += [(f"paperTypes[{i}]", str(i+1)) for i in range(9)]
    r = S.get(CDN + "/ClosingPrice/GetMarketWatch", params=p, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    rows = data.get("marketwatch", []) if isinstance(data, dict) else []
    out = [normalize(x) for x in rows if isinstance(x, dict)]
    out = [x for x in out if x]
    if not out: raise RuntimeError("CDN returned no valid stock rows")
    return out

def fetch_old():
    r = S.get(OLD + "/MarketWatchInit.aspx", params={"h":"0","r":"0"}, timeout=TIMEOUT)
    r.raise_for_status()
    parts = r.text.split("@")
    if len(parts) < 3: raise RuntimeError("Legacy response format changed")
    out = []
    for line in parts[2].split(";"):
        c = line.split(",")
        if len(c) < 26: continue
        row = dict(insCode=c[0], l18=c[2], l30=c[3], pc=c[6], pl=c[7],
                   tno=c[8], tvol=c[9], tval=c[10], pmin=c[11],
                   pmax=c[12], py=c[13], bvol=c[15], flow=c[17])
        x = normalize(row)
        if x: out.append(x)
    if not out: raise RuntimeError("Legacy source returned no valid stocks")
    return out

def score(x):
    c = x["change"]
    if c < 0.4 or c > 6.5: return 0
    s = 24 if 0.8 <= c <= 4.5 else 14
    if x["close"] > 0 and x["last"] >= x["close"]: s += 12
    if x["base"] > 0:
        q = x["vol"]/x["base"]
        s += 20 if q >= 2 else 14 if q >= 1 else 7 if q >= .5 else 0
    v = x["value"]
    s += 16 if v >= 100_000_000_000 else 12 if v >= 30_000_000_000 else 7 if v >= 10_000_000_000 else 0
    n = x["trades"]
    s += 12 if n >= 1500 else 8 if n >= 500 else 4 if n >= 150 else 0
    if x["high"] > x["low"] > 0:
        pos = (x["last"]-x["low"])/(x["high"]-x["low"])
        s += 16 if pos >= .85 else 10 if pos >= .65 else 5 if pos >= .45 else 0
    return min(100, int(s))

def telegram(msg):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing in GitHub Secrets")
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id":CHAT_ID,"text":msg,"disable_web_page_preview":True}, timeout=TIMEOUT)
    r.raise_for_status()
    if not r.json().get("ok"): raise RuntimeError(f"Telegram error: {r.text[:400]}")

def main():
    start = time.time()
    print("ATI BOURSE BOT V1.0 | SIGNAL ONLY | REAL TRADING OFF")
    errors, rows, source = [], [], "NONE"
    try:
        rows, source = fetch_cdn(), "TSETMC CDN JSON"
    except Exception as e:
        errors.append("CDN: " + str(e))
        print(errors[-1])
    if not rows:
        try: rows, source = fetch_old(), "TSETMC Legacy MarketWatch"
        except Exception as e:
            errors.append("Legacy: " + str(e))
            print(errors[-1])
    if not rows:
        telegram("ATI BOURSE BOT\nدریافت اطلاعات بازار ناموفق بود.\n"+now()+"\n"+"\n".join(errors)[:2000])
        raise RuntimeError("No market data")
    best = {}
    for x in rows:
        if x["symbol"] in best: continue
        x["score"] = score(x)
        if x["score"] >= MIN_SCORE: best[x["symbol"]] = x
    signals = sorted(best.values(), key=lambda x:(x["score"],x["value"],x["trades"]), reverse=True)[:TOP]
    lines = ["🤖 ATI BOURSE BOT V1.0", "حالت: فقط سیگنال | معامله واقعی: خاموش",
             "زمان: "+now(), "منبع: "+source, f"نمادهای معتبر: {len(rows)}",
             f"مدت اجرا: {time.time()-start:.1f} ثانیه", ""]
    if not signals: lines += ["⚠️ این نوبت سیگنال واجد شرایط پیدا نشد."]
    for i,x in enumerate(signals,1):
        market = "بورس" if x["flow"] == 1 else "فرابورس"
        lines += [f"{i}) {x['symbol']} - {x['name']}",
          f"{market} | امتیاز {x['score']}/100 | تغییر {x['change']:+.2f}%",
          f"ورود محاسباتی: {x['last']:,.0f}",
          f"حد ضرر ۳٪: {x['last']*.97:,.0f}",
          f"هدف اول ۵٪: {x['last']*1.05:,.0f} | هدف دوم ۸٪: {x['last']*1.08:,.0f}",
          f"ارزش معاملات: {x['value']:,.0f} | تعداد معاملات: {int(x['trades']):,}", ""]
    lines.append("⚠️ سیگنال ماشینی تضمین سود یا توصیه قطعی خرید نیست.")
    msg = "\n".join(lines)
    print(msg)
    telegram(msg)
    print("Telegram report sent.")

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print("BOT ERROR:", e)
        traceback.print_exc()
        sys.exit(1)
