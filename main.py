import os
import sys
import time
import traceback
from datetime import datetime, timezone

from tabdeal.future import Future


# ============================================================
# ATI FUTURES - TABDEAL
# VERSION: V5.0 BASE / PAPER
# ============================================================

API_KEY = os.getenv("TABDEAL_API_KEY", "").strip()
API_SECRET = os.getenv("TABDEAL_API_SECRET", "").strip()

MAX_MARKETS = int(os.getenv("MAX_MARKETS", "30"))
TIMEOUT = 15

MODE = "PAPER"


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def fail(message):
    print(f"❌ {message}")
    sys.exit(1)


def make_client():
    if not API_KEY or not API_SECRET:
        fail(
            "TABDEAL_API_KEY یا TABDEAL_API_SECRET در GitHub Secrets وجود ندارد."
        )

    return Future(
        api_key=API_KEY,
        api_secret=API_SECRET,
        timeout=TIMEOUT,
        receive_window=60000,
    )


def get_symbols(client):
    data = client.exchange_info()

    if not isinstance(data, dict):
        raise RuntimeError("exchangeInfo پاسخ JSON معتبر برنگرداند.")

    symbols = data.get("symbols", [])

    if not isinstance(symbols, list):
        raise RuntimeError("فیلد symbols در exchangeInfo پیدا نشد.")

    result = []

    for item in symbols:
        if not isinstance(item, dict):
            continue

        symbol = str(item.get("symbol", "")).upper()
        status = str(item.get("status", "")).upper()
        quote = str(item.get("quoteAsset", "")).upper()

        if not symbol:
            continue

        if status and status != "TRADING":
            continue

        if quote and quote != "USDT":
            continue

        if symbol.endswith("USDT"):
            result.append(symbol)

    return sorted(set(result))


def check_market(client, symbol):
    try:
        depth = client.depth(symbol=symbol, limit=5)

        if not isinstance(depth, dict):
            return False, "invalid depth response"

        bids = depth.get("bids", [])
        asks = depth.get("asks", [])

        if not bids or not asks:
            return False, "empty orderbook"

        bid = float(bids[0][0])
        ask = float(asks[0][0])

        if bid <= 0 or ask <= 0:
            return False, "invalid price"

        return True, {
            "bid": bid,
            "ask": ask,
            "spread": ask - bid,
        }

    except Exception as exc:
        return False, str(exc)


def main():
    started = time.time()

    print("==============================================")
    print("🤖 ATI FUTURES V5.0")
    print("==============================================")
    print(f"Mode: 🟢 {MODE}")
    print("Exchange: Tabdeal Futures")
    print("Strategy: CONNECTION / MARKET DATA TEST")
    print(f"Time: {utc_now()}")
    print()

    print("🔌 Connecting to Tabdeal Futures...")

    try:
        client = make_client()

        ping = client.ping()

        print(f"✅ Futures ping: OK")
        print(f"   Response: {ping}")

    except Exception as exc:
        print("❌ Futures connection failed")
        print(f"Error: {exc}")
        traceback.print_exc()
        sys.exit(1)

    print()
    print("📋 Reading Futures exchangeInfo...")

    try:
        symbols = get_symbols(client)
    except Exception as exc:
        print("❌ exchangeInfo failed")
        print(f"Error: {exc}")
        traceback.print_exc()
        sys.exit(1)

    print(f"✅ USDT Futures markets found: {len(symbols)}")

    if not symbols:
        fail("هیچ بازار USDT Futures پیدا نشد.")

    selected = symbols[:MAX_MARKETS]

    print()
    print(f"📡 Testing orderbook for {len(selected)} markets...")
    print()

    ok_count = 0
    error_count = 0

    for symbol in selected:
        ok, result = check_market(client, symbol)

        if ok:
            ok_count += 1
            print(
                f"🟢 {symbol:<14} "
                f"Bid={result['bid']} "
                f"Ask={result['ask']} "
                f"Spread={result['spread']}"
            )
        else:
            error_count += 1
            print(f"🔴 {symbol:<14} ERROR: {result}")

    runtime = time.time() - started

    print()
    print("==============================================")
    print("📊 ATI FUTURES REPORT")
    print("==============================================")
    print(f"Markets available : {len(symbols)}")
    print(f"Markets tested    : {len(selected)}")
    print(f"Orderbook OK      : {ok_count}")
    print(f"Errors            : {error_count}")
    print(f"Real orders       : DISABLED")
    print(f"Runtime           : {runtime:.1f}s")
    print(f"Time              : {utc_now()}")
    print("==============================================")


if __name__ == "__main__":
    main()
