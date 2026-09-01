"""
Stock Agent — Free Version (No API Key)
Pure technical analysis using yfinance + rule-based signals.
"""

import os, json, time
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

from flask import Flask, request, Response, send_from_directory
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__, static_folder=".")
CORS(app)

# ── Stock data ────────────────────────────────────────────────────────────────
def get_stock_data(symbol: str, period: str = "3mo") -> dict:
    try:
        if "." not in symbol and "^" not in symbol:
            symbol = symbol.upper() + ".NS"
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period=period)
        if hist.empty:
            return {"error": f"No data for {symbol}"}
        info    = ticker.info
        current = round(hist["Close"].iloc[-1], 2)
        prev    = round(hist["Close"].iloc[-2], 2) if len(hist) > 1 else current
        change  = round(current - prev, 2)
        pct     = round((change / prev) * 100, 2) if prev else 0

        sma20 = round(hist["Close"].rolling(20).mean().iloc[-1], 2) if len(hist) >= 20 else current
        sma50 = round(hist["Close"].rolling(50).mean().iloc[-1], 2) if len(hist) >= 50 else current

        delta  = hist["Close"].diff()
        gain   = delta.clip(lower=0).rolling(14).mean()
        loss   = (-delta.clip(upper=0)).rolling(14).mean()
        rs     = gain / loss
        rsi    = round((100 - (100 / (1 + rs))).iloc[-1], 2) if not rs.empty else 50

        year_h = ticker.history(period="1y")
        w52_hi = round(year_h["Close"].max(), 2) if not year_h.empty else current
        w52_lo = round(year_h["Close"].min(), 2) if not year_h.empty else current
        w52_pct = round(((current - w52_lo) / (w52_hi - w52_lo)) * 100, 1) if (w52_hi - w52_lo) else 50

        # MACD
        ema12 = hist["Close"].ewm(span=12).mean()
        ema26 = hist["Close"].ewm(span=26).mean()
        macd  = round((ema12 - ema26).iloc[-1], 2)

        # Volume trend
        avg_vol  = int(hist["Volume"].tail(20).mean())
        cur_vol  = int(hist["Volume"].iloc[-1])
        vol_ratio = round(cur_vol / avg_vol, 2) if avg_vol else 1

        # 1-week, 1-month returns
        ret_1w = round(((current - hist["Close"].iloc[-5])  / hist["Close"].iloc[-5])  * 100, 2) if len(hist) >= 5  else 0
        ret_1m = round(((current - hist["Close"].iloc[-22]) / hist["Close"].iloc[-22]) * 100, 2) if len(hist) >= 22 else 0

        return {
            "symbol": symbol,
            "name": info.get("longName", symbol),
            "sector": info.get("sector", "N/A"),
            "current": current, "prev": prev,
            "change": change, "change_pct": pct,
            "sma20": sma20, "sma50": sma50,
            "rsi": rsi, "macd": macd,
            "w52_hi": w52_hi, "w52_lo": w52_lo, "w52_pct": w52_pct,
            "volume": cur_vol, "avg_volume": avg_vol, "vol_ratio": vol_ratio,
            "ret_1w": ret_1w, "ret_1m": ret_1m,
            "pe": info.get("trailingPE"),
            "mktcap": info.get("marketCap"),
        }
    except Exception as e:
        return {"error": str(e)}


SECTOR_STOCKS = {
    "it":      ["TCS.NS","INFY.NS","WIPRO.NS","HCLTECH.NS","TECHM.NS"],
    "banking": ["HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","KOTAKBANK.NS","AXISBANK.NS"],
    "pharma":  ["SUNPHARMA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS"],
    "auto":    ["MARUTI.NS","TATAMOTORS.NS","M&M.NS","BAJAJ-AUTO.NS"],
    "fmcg":    ["HINDUNILVR.NS","ITC.NS","NESTLEIND.NS","BRITANNIA.NS"],
    "energy":  ["RELIANCE.NS","ONGC.NS","NTPC.NS","POWERGRID.NS"],
}

NAME_MAP = {
    "HDFCBANK.NS":"HDFC Bank", "ICICIBANK.NS":"ICICI Bank",
    "SBIN.NS":"State Bank of India", "KOTAKBANK.NS":"Kotak Mahindra Bank",
    "AXISBANK.NS":"Axis Bank", "TCS.NS":"Tata Consultancy Services",
    "INFY.NS":"Infosys", "WIPRO.NS":"Wipro", "HCLTECH.NS":"HCL Technologies",
    "TECHM.NS":"Tech Mahindra", "RELIANCE.NS":"Reliance Industries",
    "ONGC.NS":"ONGC", "NTPC.NS":"NTPC", "POWERGRID.NS":"Power Grid Corp",
    "SUNPHARMA.NS":"Sun Pharmaceutical", "DRREDDY.NS":"Dr. Reddy's Labs",
    "CIPLA.NS":"Cipla", "DIVISLAB.NS":"Divi's Laboratories",
    "MARUTI.NS":"Maruti Suzuki", "TATAMOTORS.NS":"Tata Motors",
    "M&M.NS":"Mahindra & Mahindra", "BAJAJ-AUTO.NS":"Bajaj Auto",
    "HEROMOTOCO.NS":"Hero MotoCorp", "EICHERMOT.NS":"Eicher Motors",
    "HINDUNILVR.NS":"Hindustan Unilever", "ITC.NS":"ITC",
    "NESTLEIND.NS":"Nestle India", "BRITANNIA.NS":"Britannia Industries",
    "TATASTEEL.NS":"Tata Steel", "JSWSTEEL.NS":"JSW Steel",
    "HINDALCO.NS":"Hindalco Industries", "BAJFINANCE.NS":"Bajaj Finance",
    "TITAN.NS":"Titan Company", "ASIANPAINT.NS":"Asian Paints",
    "ULTRACEMCO.NS":"UltraTech Cement", "LT.NS":"Larsen & Toubro",
    "TATAPOWER.NS":"Tata Power", "YESBANK.NS":"Yes Bank",
    "ZOMATO.NS":"Zomato", "BHARTIARTL.NS":"Bharti Airtel",
    "COALINDIA.NS":"Coal India", "APOLLOHOSP.NS":"Apollo Hospitals",
    "ADANIPORTS.NS":"Adani Ports", "PAYTM.NS":"Paytm",
    "LTIM.NS":"LTIMindtree", "TATACHEM.NS":"Tata Chemicals",
    "TATACONSUM.NS":"Tata Consumer", "TATAELXSI.NS":"Tata Elxsi",
    "TATACOMM.NS":"Tata Communications",
}


    "tcs":"TCS.NS","infosys":"INFY.NS","wipro":"WIPRO.NS",
    "reliance":"RELIANCE.NS","hdfc bank":"HDFCBANK.NS","hdfc":"HDFCBANK.NS",
    "icici bank":"ICICIBANK.NS","icici":"ICICIBANK.NS",
    "sbi":"SBIN.NS","state bank":"SBIN.NS","maruti":"MARUTI.NS",
    "bajaj finance":"BAJFINANCE.NS","bajaj":"BAJFINANCE.NS",
    "nifty":"^NSEI","sensex":"^BSESN","ongc":"ONGC.NS",
    "hcl":"HCLTECH.NS","kotak":"KOTAKBANK.NS","axis bank":"AXISBANK.NS","axis":"AXISBANK.NS",
    "sun pharma":"SUNPHARMA.NS","sunpharma":"SUNPHARMA.NS",
    "dr reddy":"DRREDDY.NS","drreddy":"DRREDDY.NS","cipla":"CIPLA.NS",
    "itc":"ITC.NS","tata motors":"TATAMOTORS.NS","tatamotors":"TATAMOTORS.NS",
    "adani":"ADANIPORTS.NS","yes bank":"YESBANK.NS","yesbank":"YESBANK.NS",
    "zomato":"ZOMATO.NS","paytm":"PAYTM.NS","ola":"OLA.NS",
    "infra":"INFRATEL.NS","airtel":"BHARTIARTL.NS","bharti":"BHARTIARTL.NS",
    "titan":"TITAN.NS","nestle":"NESTLEIND.NS","asian paints":"ASIANPAINT.NS",
    "asian":"ASIANPAINT.NS","ultratech":"ULTRACEMCO.NS","cement":"ULTRACEMCO.NS",
    "tata steel":"TATASTEEL.NS","jsw":"JSWSTEEL.NS","hindalco":"HINDALCO.NS",
    "power grid":"POWERGRID.NS","ntpc":"NTPC.NS","coal india":"COALINDIA.NS",
    "tech mahindra":"TECHM.NS","ltimindtree":"LTIM.NS","mphasis":"MPHASIS.NS",
    "divis":"DIVISLAB.NS","apollo":"APOLLOHOSP.NS","max health":"MAXHEALTH.NS",
}

# Words to ignore when extracting symbols from free text
STOPWORDS = {
    "BUY","SELL","HOLD","GOOD","BAD","BEST","TOP","NOW","TODAY","STOCK",
    "SHOULD","INVEST","MARKET","SHARE","PRICE","GIVE","TELL","SHOW","WHAT",
    "WHICH","WHERE","WHEN","HOW","CAN","WILL","WOULD","COULD","IS","ARE",
    "THE","AND","FOR","WITH","INTO","ABOUT","ANALYSIS","ANALYSE","ANALYZE",
    "SECTOR","COMPARE","VS","OR","IN","AT","OF","TO","FROM","THIS","THAT",
    "DO","DOES","THINK","SUGGEST","RECOMMENDATION","RETURN","PROFIT","LOSS",
    "LONG","SHORT","TERM","HIGH","LOW","RISK","SAFE","WORTH","IT","ME",
    "MY","YOUR","THEIR","HIS","HER","WE","THEY","I","A","AN","BE","HAS",
    "HAVE","HAD","WAS","WERE","BEEN","BEING","GET","GOT","MAKE","MADE",
}

# ── Signal engine ─────────────────────────────────────────────────────────────
def analyse(d: dict) -> dict:
    score  = 0
    flags  = []
    warns  = []

    rsi = d.get("rsi", 50)
    if rsi < 30:   score += 2; flags.append(f"RSI {rsi} — oversold (buy zone)")
    elif rsi < 45: score += 1; flags.append(f"RSI {rsi} — slightly oversold")
    elif rsi > 70: score -= 2; warns.append(f"RSI {rsi} — overbought (risky entry)")
    elif rsi > 60: score -= 1; warns.append(f"RSI {rsi} — approaching overbought")
    else:          flags.append(f"RSI {rsi} — neutral zone")

    c, s20, s50 = d["current"], d["sma20"], d["sma50"]
    if c > s20 > s50:  score += 2; flags.append("Price > SMA20 > SMA50 — bullish trend")
    elif c > s20:      score += 1; flags.append("Price above SMA20 — short-term bullish")
    elif c < s20 < s50: score -= 2; warns.append("Price < SMA20 < SMA50 — bearish trend")
    elif c < s20:       score -= 1; warns.append("Price below SMA20 — short-term bearish")

    macd = d.get("macd", 0)
    if macd > 0:   score += 1; flags.append(f"MACD positive ({macd}) — bullish momentum")
    else:          score -= 1; warns.append(f"MACD negative ({macd}) — bearish momentum")

    w52p = d.get("w52_pct", 50)
    if w52p < 20:   score += 1; flags.append(f"Near 52-week low ({w52p:.0f}% range) — value zone")
    elif w52p > 85: score -= 1; warns.append(f"Near 52-week high ({w52p:.0f}% range) — correction risk")
    else:           flags.append(f"52-week position: {w52p:.0f}% of range")

    vr = d.get("vol_ratio", 1)
    if vr > 1.5:   score += 1; flags.append(f"Volume {vr}x above average — strong interest")
    elif vr < 0.5: score -= 1; warns.append(f"Volume {vr}x below average — low interest")

    ret1m = d.get("ret_1m", 0)
    if ret1m > 10:  score += 1; flags.append(f"1-month return: +{ret1m}% — momentum")
    elif ret1m < -10: score -= 1; warns.append(f"1-month return: {ret1m}% — weak performance")

    if   score >= 4:  verdict, emoji = "STRONG BUY",  "🟢"
    elif score >= 2:  verdict, emoji = "BUY",          "🟢"
    elif score >= 0:  verdict, emoji = "HOLD",         "🟡"
    elif score >= -2: verdict, emoji = "AVOID",        "🔴"
    else:             verdict, emoji = "STRONG AVOID", "🔴"

    return {"score": score, "verdict": verdict, "emoji": emoji,
            "flags": flags, "warns": warns}


def fmt_inr(n):
    if not n: return "N/A"
    if n >= 1e12: return f"₹{n/1e12:.1f}T"
    if n >= 1e9:  return f"₹{n/1e9:.1f}B"
    if n >= 1e7:  return f"₹{n/1e7:.1f}Cr"
    return f"₹{n:,.0f}"


# ── Response builder ──────────────────────────────────────────────────────────
def build_response(query: str):
    q    = query.lower()
    now  = datetime.now().strftime("%d %b %Y, %I:%M %p")
    lines = []

    def emit(text=""):
        lines.append(text)

    # Detect intent
    sector_key = next((k for k in SECTOR_STOCKS if k in q), None)
    symbols_found = []

    # 1. Match multi-word names first (e.g. "yes bank", "tata motors")
    for name, sym in sorted(POPULAR.items(), key=lambda x: -len(x[0])):
        if name in q and sym not in symbols_found:
            symbols_found.append(sym)

    # 2. Only extract raw .NS/.BO symbols — ignore plain words
    import re
    raw = re.findall(r'\b([A-Z0-9]{2,12}\.(?:NS|BO))\b', query.upper())
    for r in raw:
        if r not in symbols_found:
            symbols_found.append(r)

    is_market = any(w in q for w in ["market","nifty","sensex","overview","index"])
    is_compare = any(w in q for w in ["compare","vs","versus","better","between"])

    emit(f"**📅 Analysis as of {now}**")
    emit()

    # ── Market overview ──
    if is_market or (not sector_key and not symbols_found):
        emit("## 📊 Market Overview")
        emit()
        for name, sym in [("Nifty 50","^NSEI"),("Sensex","^BSESN")]:
            d = get_stock_data(sym, "1mo")
            if "error" not in d:
                arrow = "▲" if d["change"] >= 0 else "▼"
                color = "+" if d["change"] >= 0 else ""
                emit(f"**{name}:** ₹{d['current']:,.2f}  {arrow} {color}{d['change_pct']}% today")
        emit()

    # ── Sector analysis ──
    if sector_key:
        emit(f"## 🏭 {sector_key.upper()} Sector Analysis")
        emit()
        results = []
        for sym in SECTOR_STOCKS[sector_key]:
            d = get_stock_data(sym)
            if "error" not in d:
                sig = analyse(d)
                results.append((d, sig))

        results.sort(key=lambda x: x[1]["score"], reverse=True)

        for d, sig in results:
            emit(f"**{d['name']}** ({d['symbol']})")
            emit(f"₹{d['current']:,}  |  {sig['emoji']} **{sig['verdict']}**  |  Score: {sig['score']:+d}")
            emit(f"RSI: {d['rsi']} | SMA20: ₹{d['sma20']:,} | 1M: {d['ret_1m']:+.1f}%")
            emit()

        best = results[0][0] if results else None
        if best:
            emit(f"---")
            emit(f"**🏆 Top Pick:** {best['name']} — strongest technical setup in the sector.")

    # ── Individual / compare stocks ──
    elif symbols_found:
        unique = list(dict.fromkeys(symbols_found))[:5]
        if len(unique) > 1:
            emit(f"## 🔍 Comparison: {' vs '.join(s.replace('.NS','').replace('.BO','') for s in unique)}")
        else:
            emit(f"## 🔍 Stock Analysis")
        emit()

        all_results = []
        for sym in unique:
            d = get_stock_data(sym)
            if "error" in d:
                emit(f"⚠️ Could not fetch data for **{sym}**: {d['error']}")
                emit()
                continue

            sig = analyse(d)
            all_results.append((d, sig))

            change_arrow = "▲" if d["change"] >= 0 else "▼"
            change_sign  = "+" if d["change"] >= 0 else ""

            emit(f"### {d['name']} ({d['symbol']})")
            emit(f"**Price:** ₹{d['current']:,}  {change_arrow} {change_sign}{d['change']} ({change_sign}{d['change_pct']}%)")
            emit()
            emit(f"| Indicator | Value | Signal |")
            emit(f"|---|---|---|")
            emit(f"| RSI (14) | {d['rsi']} | {'Oversold 🟢' if d['rsi']<30 else 'Overbought 🔴' if d['rsi']>70 else 'Neutral 🟡'} |")
            emit(f"| SMA 20 | ₹{d['sma20']:,} | {'Above ✅' if d['current']>d['sma20'] else 'Below ❌'} |")
            emit(f"| SMA 50 | ₹{d['sma50']:,} | {'Above ✅' if d['current']>d['sma50'] else 'Below ❌'} |")
            emit(f"| MACD | {d['macd']} | {'Bullish ✅' if d['macd']>0 else 'Bearish ❌'} |")
            emit(f"| 52W Position | {d['w52_pct']:.0f}% of range | ₹{d['w52_lo']:,} — ₹{d['w52_hi']:,} |")
            emit(f"| Volume | {d['vol_ratio']}x avg | {'High 🟢' if d['vol_ratio']>1.3 else 'Low 🔴' if d['vol_ratio']<0.7 else 'Normal 🟡'} |")
            emit(f"| 1W Return | {d['ret_1w']:+.1f}% | |")
            emit(f"| 1M Return | {d['ret_1m']:+.1f}% | |")
            if d.get("pe"):  emit(f"| P/E Ratio | {d['pe']:.1f}x | |")
            if d.get("mktcap"): emit(f"| Market Cap | {fmt_inr(d['mktcap'])} | |")
            emit()

            emit(f"**Verdict: {sig['emoji']} {sig['verdict']}** (Score: {sig['score']:+d}/8)")
            emit()
            if sig["flags"]:
                emit("✅ **Positives:**")
                for f in sig["flags"]: emit(f"- {f}")
            if sig["warns"]:
                emit("⚠️ **Cautions:**")
                for w in sig["warns"]: emit(f"- {w}")
            emit()
            emit("---")
            emit()

        if len(all_results) > 1:
            best = max(all_results, key=lambda x: x[1]["score"])
            emit(f"**🏆 Recommendation:** Go with **{best[0]['name']}** — highest score ({best[1]['score']:+d}) and strongest technical setup.")
            emit()

    emit("---")
    emit("⚠️ *This is rule-based technical analysis only — not financial advice. Past performance doesn't guarantee future results. Always do your own research.*")

    return "\n".join(lines)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/proxy")
def proxy():
    import re as _re
    url = request.args.get("url", "")
    # extract symbol and range from Yahoo Finance chart URL
    m = _re.search(r'/chart/([^?]+)\?.*range=([^&]+)', url)
    if not m:
        return json.dumps({"error": "bad url"}), 400, {"Access-Control-Allow-Origin": "*"}
    symbol, period = m.group(1), m.group(2)
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if hist.empty:
            return json.dumps({"chart":{"result":None,"error":"no data"}}), 200, {"Access-Control-Allow-Origin": "*"}
        closes  = hist["Close"].tolist()
        volumes = hist["Volume"].tolist()
        timestamps = [int(t.timestamp()) for t in hist.index]
        payload = {"chart":{"result":[{
            "meta": {
                "symbol": symbol,
                "currency": "INR",
                "longName": NAME_MAP.get(symbol, symbol.replace(".NS","").replace(".BO","")),
                "shortName": NAME_MAP.get(symbol, symbol.replace(".NS","").replace(".BO","")),
            },
            "timestamp": timestamps,
            "indicators": {"quote":[{"close": closes, "volume": volumes}]}
        }],"error":None}}
        return Response(json.dumps(payload), content_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return json.dumps({"error": str(e)}), 502, {"Access-Control-Allow-Origin": "*"}


@app.route("/ask", methods=["POST"])
def ask():
    data  = request.json or {}
    query = data.get("query", "").strip()
    if not query:
        return Response('data: {"error":"empty"}\n\n', mimetype="text/event-stream")

    def generate():
        yield f"data: {json.dumps({'type':'status','text':'Fetching live market data from NSE...'})}\n\n"

        try:
            result = build_response(query)
            yield f"data: {json.dumps({'type':'text','text':result})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type':'text','text':f'⚠️ Error: {str(e)}'})}\n\n"

        yield f"data: {json.dumps({'type':'done'})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"✓  Free Stock Agent — open http://localhost:{port} in your browser")
    app.run(host="0.0.0.0", port=port, debug=False)
