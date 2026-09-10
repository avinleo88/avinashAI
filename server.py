"""
Stock Agent — Free Version (No API Key)
Pure technical analysis using yfinance + rule-based signals.
"""

import os, json, time, csv, io, threading
import requests
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

from flask import Flask, request, Response, send_from_directory
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__, static_folder=".")
CORS(app)

# ── NSE symbol search index ───────────────────────────────────────────────────
_NSE_INDEX = {}   # lowercase name/symbol -> "SYMBOL.NS"
_NSE_NAMES = {}   # "SYMBOL.NS" -> "Company Full Name"

def _load_nse_list():
    import requests as req
    try:
        r = req.get(
            "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            timeout=20
        )
        reader = csv.DictReader(io.StringIO(r.text))
        count = 0
        for row in reader:
            sym  = row.get("SYMBOL", "").strip()
            name = row.get("NAME OF COMPANY", "").strip()
            if not sym or not name:
                continue
            full = sym + ".NS"
            _NSE_NAMES[full] = name.title()
            _NSE_INDEX[sym.lower()]  = full
            _NSE_INDEX[name.lower()] = full
            count += 1
        print(f"NSE list loaded: {count} stocks")
    except Exception as e:
        print(f"NSE list unavailable: {e}")

threading.Thread(target=_load_nse_list, daemon=True).start()

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
    "pharma":  ["SUNPHARMA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS","APOLLOHOSP.NS"],
    "auto":    ["MARUTI.NS","TATAMOTORS.NS","M&M.NS","BAJAJ-AUTO.NS","EICHERMOT.NS"],
    "fmcg":    ["HINDUNILVR.NS","ITC.NS","NESTLEIND.NS","BRITANNIA.NS","TATACONSUM.NS"],
    "energy":  ["RELIANCE.NS","ONGC.NS","NTPC.NS","POWERGRID.NS","BPCL.NS"],
    "metal":   ["TATASTEEL.NS","JSWSTEEL.NS","HINDALCO.NS","COALINDIA.NS","ADANIENT.NS"],
    "infra":   ["LT.NS","ADANIPORTS.NS","ULTRACEMCO.NS","GRASIM.NS","BHARTIARTL.NS"],
}

NIFTY50_SYMS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
    "HINDUNILVR.NS","ITC.NS","SBIN.NS","BHARTIARTL.NS","KOTAKBANK.NS",
    "LT.NS","AXISBANK.NS","ASIANPAINT.NS","MARUTI.NS","TITAN.NS",
    "SUNPHARMA.NS","ULTRACEMCO.NS","BAJFINANCE.NS","WIPRO.NS","NESTLEIND.NS",
    "POWERGRID.NS","NTPC.NS","TECHM.NS","HCLTECH.NS","ONGC.NS",
    "TATAMOTORS.NS","TATASTEEL.NS","ADANIENT.NS","ADANIPORTS.NS","BAJAJFINSV.NS",
    "COALINDIA.NS","DRREDDY.NS","EICHERMOT.NS","GRASIM.NS","HEROMOTOCO.NS",
    "INDUSINDBK.NS","JSWSTEEL.NS","M&M.NS","CIPLA.NS","DIVISLAB.NS",
    "APOLLOHOSP.NS","BPCL.NS","BRITANNIA.NS","HINDALCO.NS","TATACONSUM.NS",
]

NIFTY_NEXT50_SYMS = [
    "ADANIGREEN.NS","AMBUJACEM.NS","BAJAJHLDNG.NS","BANKBARODA.NS",
    "BERGEPAINT.NS","BEL.NS","CANBK.NS","CHOLAFIN.NS","COLPAL.NS",
    "DMART.NS","DLF.NS","GAIL.NS","GODREJCP.NS","GODREJPROP.NS",
    "HAL.NS","HAVELLS.NS","HDFCLIFE.NS","ICICIPRULI.NS","INDHOTEL.NS",
    "INDUSTOWER.NS","IOC.NS","IRCTC.NS","LUPIN.NS","MARICO.NS",
    "MUTHOOTFIN.NS","NAUKRI.NS","NHPC.NS","OBEROIRLTY.NS","OFSS.NS",
    "OIL.NS","PETRONET.NS","PFC.NS","PIDILITIND.NS","PNB.NS",
    "POLYCAB.NS","RECLTD.NS","SBICARD.NS","SBILIFE.NS","SHREECEM.NS",
    "SIEMENS.NS","SRF.NS","TATACOMM.NS","TORNTPHARM.NS","TRENT.NS",
    "UNIONBANK.NS","VBL.NS","VEDL.NS","ZOMATO.NS","PIIND.NS","PAYTM.NS",
]

NIFTY100_SYMS = NIFTY50_SYMS + NIFTY_NEXT50_SYMS

NAME_MAP = {
    "HDFCBANK.NS":"HDFC Bank","ICICIBANK.NS":"ICICI Bank",
    "SBIN.NS":"State Bank of India","KOTAKBANK.NS":"Kotak Mahindra Bank",
    "AXISBANK.NS":"Axis Bank","INDUSINDBK.NS":"IndusInd Bank",
    "PNB.NS":"Punjab National Bank","BANKBARODA.NS":"Bank of Baroda",
    "CANBK.NS":"Canara Bank","UNIONBANK.NS":"Union Bank",
    "FEDERALBNK.NS":"Federal Bank","YESBANK.NS":"Yes Bank",
    "TCS.NS":"Tata Consultancy Services","INFY.NS":"Infosys",
    "WIPRO.NS":"Wipro","HCLTECH.NS":"HCL Technologies",
    "TECHM.NS":"Tech Mahindra","LTIM.NS":"LTIMindtree",
    "MPHASIS.NS":"Mphasis","PERSISTENT.NS":"Persistent Systems",
    "COFORGE.NS":"Coforge","LTTS.NS":"L&T Technology Services",
    "KPIT.NS":"KPIT Technologies",
    "RELIANCE.NS":"Reliance Industries","ONGC.NS":"ONGC",
    "NTPC.NS":"NTPC","POWERGRID.NS":"Power Grid Corp",
    "COALINDIA.NS":"Coal India","TATAPOWER.NS":"Tata Power",
    "ADANIGREEN.NS":"Adani Green Energy","ADANIENT.NS":"Adani Enterprises",
    "ADANIPORTS.NS":"Adani Ports","JSWENERGY.NS":"JSW Energy",
    "TORNTPOWER.NS":"Torrent Power","NHPC.NS":"NHPC","SJVN.NS":"SJVN",
    "SUNPHARMA.NS":"Sun Pharmaceutical","DRREDDY.NS":"Dr. Reddy's Labs",
    "CIPLA.NS":"Cipla","DIVISLAB.NS":"Divi's Laboratories",
    "LUPIN.NS":"Lupin","BIOCON.NS":"Biocon","ALKEM.NS":"Alkem Labs",
    "TORNTPHARM.NS":"Torrent Pharma","GLENMARK.NS":"Glenmark",
    "LAURUSLABS.NS":"Laurus Labs","ZYDUSLIFE.NS":"Zydus Lifesciences",
    "MANKIND.NS":"Mankind Pharma",
    "MARUTI.NS":"Maruti Suzuki","TATAMOTORS.NS":"Tata Motors",
    "M&M.NS":"Mahindra & Mahindra","HEROMOTOCO.NS":"Hero MotoCorp",
    "BAJAJ-AUTO.NS":"Bajaj Auto","EICHERMOT.NS":"Eicher Motors",
    "TVSMOTOR.NS":"TVS Motor","ASHOKLEY.NS":"Ashok Leyland",
    "BHARATFORG.NS":"Bharat Forge","MRF.NS":"MRF","CEATLTD.NS":"CEAT",
    "HINDUNILVR.NS":"Hindustan Unilever","ITC.NS":"ITC",
    "NESTLEIND.NS":"Nestle India","BRITANNIA.NS":"Britannia Industries",
    "DABUR.NS":"Dabur","MARICO.NS":"Marico","GODREJCP.NS":"Godrej Consumer",
    "COLPAL.NS":"Colgate-Palmolive","EMAMILTD.NS":"Emami",
    "TATACONSUM.NS":"Tata Consumer","VBL.NS":"Varun Beverages",
    "DMART.NS":"DMart (Avenue Supermarts)","TRENT.NS":"Trent",
    "ZOMATO.NS":"Zomato","PAYTM.NS":"Paytm","FSN.NS":"Nykaa",
    "NAUKRI.NS":"Info Edge (Naukri)","POLICYBZR.NS":"PB Fintech",
    "BAJFINANCE.NS":"Bajaj Finance","BAJAJFINSV.NS":"Bajaj Finserv",
    "MUTHOOTFIN.NS":"Muthoot Finance","SHRIRAMFIN.NS":"Shriram Finance",
    "CHOLAFIN.NS":"Cholamandalam Finance","LICHSGFIN.NS":"LIC Housing Finance",
    "HDFCLIFE.NS":"HDFC Life","SBILIFE.NS":"SBI Life","ICICIPRULI.NS":"ICICI Prudential",
    "TATASTEEL.NS":"Tata Steel","JSWSTEEL.NS":"JSW Steel",
    "HINDALCO.NS":"Hindalco","VEDL.NS":"Vedanta","SAIL.NS":"SAIL",
    "NMDC.NS":"NMDC","JINDALSTEL.NS":"Jindal Steel",
    "LT.NS":"Larsen & Toubro","SIEMENS.NS":"Siemens","ABB.NS":"ABB",
    "BHEL.NS":"BHEL","THERMAX.NS":"Thermax","CUMMINSIND.NS":"Cummins India",
    "VOLTAS.NS":"Voltas","BLUESTARCO.NS":"Blue Star","HAVELLS.NS":"Havells",
    "POLYCAB.NS":"Polycab","DIXON.NS":"Dixon Technologies",
    "HAL.NS":"HAL","BEL.NS":"Bharat Electronics",
    "MAZDOCK.NS":"Mazagon Dock","COCHINSHIP.NS":"Cochin Shipyard",
    "IRCTC.NS":"IRCTC","IRFC.NS":"IRFC","CONCOR.NS":"Container Corp",
    "ASIANPAINT.NS":"Asian Paints","BERGEPAINT.NS":"Berger Paints",
    "PIDILITIND.NS":"Pidilite Industries","SRF.NS":"SRF",
    "PIIND.NS":"PI Industries","TATACHEM.NS":"Tata Chemicals",
    "GODREJPROP.NS":"Godrej Properties","DLF.NS":"DLF",
    "INDHOTEL.NS":"Indian Hotels (Taj)","LEMONTREE.NS":"Lemon Tree Hotels",
    "INDIGO.NS":"IndiGo (InterGlobe)","SPICEJET.NS":"SpiceJet",
    "ULTRACEMCO.NS":"UltraTech Cement","SHREECEM.NS":"Shree Cement",
    "AMBUJACEM.NS":"Ambuja Cements","ACC.NS":"ACC",
    "BHARTIARTL.NS":"Bharti Airtel","IDEA.NS":"Vodafone Idea",
    "TITAN.NS":"Titan Company","TATAELXSI.NS":"Tata Elxsi",
    "TATACOMM.NS":"Tata Communications","SUZLON.NS":"Suzlon Energy",
    "APOLLOHOSP.NS":"Apollo Hospitals","MAXHEALTH.NS":"Max Healthcare",
    "FORTIS.NS":"Fortis Healthcare",
    "HINDPETRO.NS":"HPCL","BPCL.NS":"BPCL","IOC.NS":"Indian Oil","GAIL.NS":"GAIL","PETRONET.NS":"Petronet LNG","OIL.NS":"Oil India",
}


POPULAR = {
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
@app.route("/recommendations")
def recommendations():
    try:
        data = yf.download(NIFTY50_SYMS, period="3mo", progress=False, auto_adjust=True)
        closes_all = data["Close"]
        volumes_all = data["Volume"]
        if closes_all.empty:
            return json.dumps([]), 200, {"Access-Control-Allow-Origin": "*"}

        results = []
        for sym in closes_all.columns:
            closes  = closes_all[sym].dropna()
            volumes = volumes_all[sym].dropna() if sym in volumes_all.columns else None
            if len(closes) < 22:
                continue
            cur  = float(closes.iloc[-1])
            prev = float(closes.iloc[-2])

            # RSI
            delta = closes.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss
            rsi   = round(float((100 - 100 / (1 + rs)).iloc[-1]), 1)

            # SMA
            sma20 = round(float(closes.rolling(20).mean().iloc[-1]), 2)
            sma50 = round(float(closes.rolling(50).mean().iloc[-1]), 2) if len(closes) >= 50 else sma20

            # MACD
            ema12 = closes.ewm(span=12).mean()
            ema26 = closes.ewm(span=26).mean()
            macd  = round(float((ema12 - ema26).iloc[-1]), 2)

            # 52W position
            w52_hi = float(closes.max())
            w52_lo = float(closes.min())
            w52pct = round(((cur - w52_lo) / (w52_hi - w52_lo)) * 100, 1) if (w52_hi - w52_lo) else 50

            # Volume ratio
            vol_ratio = 1.0
            if volumes is not None and len(volumes) >= 20:
                avg_vol   = float(volumes.tail(20).mean())
                cur_vol   = float(volumes.iloc[-1])
                vol_ratio = round(cur_vol / avg_vol, 2) if avg_vol else 1

            # 1-month return
            ret_1m = round(((cur - float(closes.iloc[-22])) / float(closes.iloc[-22])) * 100, 2)

            # Score — same logic as frontend analyse()
            score, flags, warns = 0, [], []
            if rsi < 30:   score += 2; flags.append(f"RSI {rsi} — oversold (buy zone)")
            elif rsi < 45: score += 1; flags.append(f"RSI {rsi} — slightly oversold")
            elif rsi > 70: score -= 2; warns.append(f"RSI {rsi} — overbought")
            elif rsi > 60: score -= 1; warns.append(f"RSI {rsi} — approaching overbought")

            if cur > sma20 and sma20 > sma50:   score += 2; flags.append("Price > SMA20 > SMA50 — bullish trend")
            elif cur > sma20:                     score += 1; flags.append("Price above SMA20 — short-term bullish")
            elif cur < sma20 and sma20 < sma50: score -= 2; warns.append("Price < SMA20 < SMA50 — bearish trend")
            elif cur < sma20:                    score -= 1; warns.append("Price below SMA20 — bearish")

            if macd > 0: score += 1; flags.append(f"MACD +{macd} — bullish momentum")
            else:        score -= 1; warns.append(f"MACD {macd} — bearish momentum")

            if w52pct < 20:   score += 1; flags.append(f"Near 52W low ({w52pct}%) — value zone")
            elif w52pct > 85: score -= 1; warns.append(f"Near 52W high ({w52pct}%) — correction risk")

            if vol_ratio > 1.5:  score += 1; flags.append(f"Volume {vol_ratio}x avg — strong interest")
            elif vol_ratio < 0.5: score -= 1; warns.append(f"Volume {vol_ratio}x avg — low interest")

            if ret_1m > 10:   score += 1; flags.append(f"1M return +{ret_1m}% — momentum")
            elif ret_1m < -10: score -= 1; warns.append(f"1M return {ret_1m}% — weak")

            verdict = "STRONG BUY" if score >= 4 else "BUY" if score >= 2 else "HOLD" if score >= 0 else "AVOID" if score >= -2 else "STRONG AVOID"
            if score < 2:
                continue  # only return BUY and STRONG BUY

            results.append({
                "symbol":    sym,
                "name":      NAME_MAP.get(sym, sym.replace(".NS", "")),
                "price":     round(cur, 2),
                "change_pct": round(((cur - prev) / prev) * 100, 2) if prev else 0,
                "score":     score,
                "verdict":   verdict,
                "rsi":       rsi,
                "sma20":     sma20,
                "sma50":     sma50,
                "macd":      macd,
                "w52pct":    w52pct,
                "vol_ratio": vol_ratio,
                "ret_1m":    ret_1m,
                "flags":     flags,
                "warns":     warns,
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return Response(json.dumps(results[:10]), content_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return json.dumps({"error": str(e)}), 502, {"Access-Control-Allow-Origin": "*"}


@app.route("/avoid")
def avoid():
    try:
        data = yf.download(NIFTY50_SYMS, period="3mo", progress=False, auto_adjust=True)
        closes_all = data["Close"]
        volumes_all = data["Volume"]
        results = []
        for sym in NIFTY50_SYMS:
            try:
                closes = closes_all[sym].dropna()
                volumes = volumes_all[sym].dropna()
                if len(closes) < 52:
                    continue
                cur = float(closes.iloc[-1])
                prev = float(closes.iloc[-2]) if len(closes) > 1 else cur
                delta = closes.diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss.replace(0, 1e-9)
                rsi = round(float(100 - 100 / (1 + rs.iloc[-1])), 1)
                sma20 = round(float(closes.iloc[-20:].mean()), 2)
                sma50 = round(float(closes.iloc[-50:].mean()), 2)
                ema12 = closes.ewm(span=12, adjust=False).mean()
                ema26 = closes.ewm(span=26, adjust=False).mean()
                macd = round(float((ema12 - ema26).iloc[-1]), 2)
                high52 = float(closes.max())
                low52 = float(closes.min())
                w52pct = round((cur - low52) / (high52 - low52) * 100, 1) if high52 != low52 else 50
                vol_avg = float(volumes.mean()) if len(volumes) > 0 else 1
                vol_ratio = round(float(volumes.iloc[-1]) / vol_avg, 2) if vol_avg else 1
                ret_1m = round((cur / float(closes.iloc[-21]) - 1) * 100, 2) if len(closes) >= 21 else 0
                score = 0
                flags, warns = [], []
                if rsi > 70:   score -= 1; warns.append(f"RSI {rsi} — overbought")
                elif rsi < 30: score += 1; flags.append(f"RSI {rsi} — oversold entry")
                if cur < sma20 < sma50: score -= 2; warns.append("Price < SMA20 < SMA50 — bearish trend")
                elif cur < sma20:       score -= 1; warns.append("Price below SMA20 — short-term bearish")
                elif cur > sma20 > sma50: score += 2; flags.append("Price > SMA20 > SMA50 — bullish trend")
                elif cur > sma20:         score += 1; flags.append("Price above SMA20 — short-term bullish")
                if macd < 0:   score -= 1; warns.append(f"MACD {macd} — bearish momentum")
                elif macd > 0: score += 1; flags.append(f"MACD +{macd} — bullish momentum")
                if w52pct < 20:   score -= 1; warns.append(f"Near 52W low ({w52pct}%) — weak")
                elif w52pct > 80: score -= 1; warns.append(f"Near 52W high ({w52pct}%) — correction risk")
                if vol_ratio > 1.5: score += 1; flags.append(f"Volume {vol_ratio}x avg — strong interest")
                elif vol_ratio < 0.5: score -= 1; warns.append(f"Volume {vol_ratio}x avg — low interest")
                if ret_1m < -5:   score -= 1; warns.append(f"1M return {ret_1m}% — declining")
                elif ret_1m > 5:  score += 1; flags.append(f"1M return +{ret_1m}% — momentum")
                verdict = "STRONG BUY" if score >= 4 else "BUY" if score >= 2 else "HOLD" if score >= 0 else "AVOID" if score >= -3 else "STRONG AVOID"
                if score > -1:
                    continue
                results.append({
                    "symbol":    sym,
                    "name":      NAME_MAP.get(sym, sym.replace(".NS", "")),
                    "price":     round(cur, 2),
                    "change_pct": round(((cur - prev) / prev) * 100, 2) if prev else 0,
                    "score":     score,
                    "verdict":   verdict,
                    "rsi":       rsi,
                    "sma20":     sma20,
                    "sma50":     sma50,
                    "macd":      macd,
                    "w52pct":    w52pct,
                    "vol_ratio": vol_ratio,
                    "ret_1m":    ret_1m,
                    "flags":     flags,
                    "warns":     warns,
                })
            except Exception:
                continue
        results.sort(key=lambda x: x["score"])
        return Response(json.dumps(results[:10]), content_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return json.dumps({"error": str(e)}), 502, {"Access-Control-Allow-Origin": "*"}


@app.route("/top-movers")
def top_movers():
    try:
        data = yf.download(NIFTY50_SYMS, period="2d", progress=False, auto_adjust=True)
        closes = data["Close"]
        if closes.empty:
            return json.dumps({"gainers": [], "losers": []}), 200, {"Access-Control-Allow-Origin": "*"}
        changes = []
        for sym in closes.columns:
            col = closes[sym].dropna()
            if len(col) >= 2:
                cur  = float(col.iloc[-1])
                prev = float(col.iloc[-2])
                pct  = round(((cur - prev) / prev) * 100, 2) if prev else 0
                changes.append({
                    "symbol": sym,
                    "name": NAME_MAP.get(sym, sym.replace(".NS", "")),
                    "price": round(cur, 2),
                    "change_pct": pct,
                })
        changes.sort(key=lambda x: x["change_pct"], reverse=True)
        return Response(json.dumps({"gainers": changes[:5], "losers": list(reversed(changes[-5:]))}),
                        content_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return json.dumps({"error": str(e)}), 502, {"Access-Control-Allow-Origin": "*"}


@app.route("/sector-summary")
def sector_summary():
    try:
        all_syms = list({s for syms in SECTOR_STOCKS.values() for s in syms})
        data = yf.download(all_syms, period="2d", progress=False, auto_adjust=True)
        closes = data["Close"]
        result = []
        LABELS = {"it":"IT","banking":"Banking","pharma":"Pharma","auto":"Auto",
                  "fmcg":"FMCG","energy":"Energy","metal":"Metal","infra":"Infra"}
        for key, syms in SECTOR_STOCKS.items():
            pcts = []
            for sym in syms:
                if sym in closes.columns:
                    col = closes[sym].dropna()
                    if len(col) >= 2:
                        cur  = float(col.iloc[-1])
                        prev = float(col.iloc[-2])
                        if prev:
                            pcts.append(((cur - prev) / prev) * 100)
            if pcts:
                avg = round(sum(pcts) / len(pcts), 2)
                result.append({"sector": LABELS.get(key, key.title()), "change_pct": avg})
        result.sort(key=lambda x: x["change_pct"], reverse=True)
        return Response(json.dumps(result), content_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return json.dumps({"error": str(e)}), 502, {"Access-Control-Allow-Origin": "*"}


@app.route("/market-summary")
def market_summary():
    indices = [
        ("^NSEI",   "Nifty 50"),
        ("^BSESN",  "Sensex"),
        ("^NSEBANK","Nifty Bank"),
        ("^CNXIT",  "Nifty IT"),
        ("^NSMIDCP","Nifty Midcap"),
    ]
    result = []
    for symbol, label in indices:
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="2d")
            if hist.empty or len(hist) < 1:
                continue
            cur  = round(hist["Close"].iloc[-1], 2)
            prev = round(hist["Close"].iloc[-2], 2) if len(hist) > 1 else cur
            chg  = round(cur - prev, 2)
            pct  = round((chg / prev) * 100, 2) if prev else 0
            result.append({"symbol": symbol, "label": label, "price": cur, "change": chg, "change_pct": pct})
        except Exception:
            continue
    return Response(json.dumps(result), content_type="application/json",
                    headers={"Access-Control-Allow-Origin": "*"})


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/search")
def search():
    q = request.args.get("q", "").lower().strip()
    if not q or len(q) < 2:
        return Response(json.dumps([]), content_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*"})
    results = []
    # exact symbol match first
    if q.upper() + ".NS" in _NSE_NAMES:
        sym = q.upper() + ".NS"
        results.append({"symbol": sym, "name": NAME_MAP.get(sym) or _NSE_NAMES.get(sym, sym)})
    # exact name match
    if q in _NSE_INDEX and not results:
        sym = _NSE_INDEX[q]
        results.append({"symbol": sym, "name": NAME_MAP.get(sym) or _NSE_NAMES.get(sym, sym)})
    # partial matches
    if not results:
        for name, sym in _NSE_INDEX.items():
            if q in name:
                entry = {"symbol": sym, "name": NAME_MAP.get(sym) or _NSE_NAMES.get(sym, name.title())}
                if entry not in results:
                    results.append(entry)
            if len(results) >= 5:
                break
    return Response(json.dumps(results[:5]), content_type="application/json",
                    headers={"Access-Control-Allow-Origin": "*"})


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


@app.route("/sentiment")
def sentiment():
    """Compute overall Nifty 50 market sentiment score (0-100)."""
    try:
        data = yf.download(NIFTY50_SYMS, period="3mo", progress=False, auto_adjust=True)
        closes_all = data["Close"]
        bullish = bearish = neutral = 0
        top_bullish, top_bearish = [], []
        all_scores = []

        for sym in NIFTY50_SYMS:
            try:
                closes = closes_all[sym].dropna()
                if len(closes) < 22:
                    continue
                cur = float(closes.iloc[-1])
                delta = closes.diff()
                gain  = delta.clip(lower=0).rolling(14).mean()
                loss  = (-delta.clip(upper=0)).rolling(14).mean()
                rs    = gain / loss.replace(0, 1e-9)
                rsi   = float((100 - 100 / (1 + rs)).iloc[-1])
                sma20 = float(closes.rolling(20).mean().iloc[-1])
                sma50 = float(closes.rolling(50).mean().iloc[-1]) if len(closes) >= 50 else sma20
                ema12 = closes.ewm(span=12).mean()
                ema26 = closes.ewm(span=26).mean()
                macd  = float((ema12 - ema26).iloc[-1])

                score = 0
                if rsi < 30:   score += 2
                elif rsi < 45: score += 1
                elif rsi > 70: score -= 2
                elif rsi > 60: score -= 1
                if cur > sma20 and sma20 > sma50:    score += 2
                elif cur > sma20:                      score += 1
                elif cur < sma20 and sma20 < sma50:   score -= 2
                elif cur < sma20:                      score -= 1
                if macd > 0: score += 1
                else:        score -= 1

                all_scores.append(score)
                name = NAME_MAP.get(sym, sym.replace(".NS", ""))
                if score >= 2:
                    bullish += 1
                    if len(top_bullish) < 4:
                        top_bullish.append({"name": name, "score": score, "rsi": round(rsi, 1)})
                elif score <= -2:
                    bearish += 1
                    if len(top_bearish) < 4:
                        top_bearish.append({"name": name, "score": score, "rsi": round(rsi, 1)})
                else:
                    neutral += 1
            except Exception:
                continue

        total = bullish + bearish + neutral
        if total == 0:
            return json.dumps({"error": "no data"}), 502, {"Access-Control-Allow-Origin": "*"}

        score_pct = round((bullish / total) * 100)
        avg = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0

        if score_pct >= 70:   label = "Strongly Bullish"
        elif score_pct >= 55: label = "Bullish"
        elif score_pct >= 45: label = "Neutral"
        elif score_pct >= 30: label = "Bearish"
        else:                 label = "Strongly Bearish"

        return Response(json.dumps({
            "score": score_pct, "label": label, "avg_score": avg,
            "bullish": bullish, "bearish": bearish, "neutral": neutral, "total": total,
            "top_bullish": top_bullish, "top_bearish": top_bearish,
        }), content_type="application/json", headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return json.dumps({"error": str(e)}), 502, {"Access-Control-Allow-Origin": "*"}


@app.route("/screener")
def screener():
    """Filter Nifty 50 or Nifty 100 stocks by technical criteria."""
    try:
        min_rsi   = float(request.args.get("min_rsi", 0))
        max_rsi   = float(request.args.get("max_rsi", 100))
        above_sma20 = request.args.get("above_sma20", "").lower() == "true"
        above_sma50 = request.args.get("above_sma50", "").lower() == "true"
        below_sma20 = request.args.get("below_sma20", "").lower() == "true"
        macd_pos  = request.args.get("macd_positive", "").lower() == "true"
        macd_neg  = request.args.get("macd_negative", "").lower() == "true"
        min_score = int(request.args.get("min_score", -10))
        max_score = int(request.args.get("max_score", 10))
        universe  = request.args.get("universe", "nifty50").lower()

        syms = NIFTY100_SYMS if universe == "nifty100" else NIFTY50_SYMS
        data = yf.download(syms, period="3mo", progress=False, auto_adjust=True)
        closes_all = data["Close"]
        volumes_all = data.get("Volume", None)
        results = []

        for sym in syms:
            try:
                closes = closes_all[sym].dropna()
                if len(closes) < 22:
                    continue
                cur  = float(closes.iloc[-1])
                prev = float(closes.iloc[-2])

                delta = closes.diff()
                gain  = delta.clip(lower=0).rolling(14).mean()
                loss  = (-delta.clip(upper=0)).rolling(14).mean()
                rs    = gain / loss.replace(0, 1e-9)
                rsi   = round(float((100 - 100 / (1 + rs)).iloc[-1]), 1)
                sma20 = round(float(closes.rolling(20).mean().iloc[-1]), 2)
                sma50 = round(float(closes.rolling(50).mean().iloc[-1]), 2) if len(closes) >= 50 else sma20
                ema12 = closes.ewm(span=12).mean()
                ema26 = closes.ewm(span=26).mean()
                macd  = round(float((ema12 - ema26).iloc[-1]), 2)

                # Apply filters
                if rsi < min_rsi or rsi > max_rsi:   continue
                if above_sma20 and cur <= sma20:      continue
                if above_sma50 and cur <= sma50:      continue
                if below_sma20 and cur >= sma20:      continue
                if macd_pos and macd <= 0:            continue
                if macd_neg and macd >= 0:            continue

                # Score
                score = 0
                if rsi < 30:   score += 2
                elif rsi < 45: score += 1
                elif rsi > 70: score -= 2
                elif rsi > 60: score -= 1
                if cur > sma20 and sma20 > sma50:    score += 2
                elif cur > sma20:                      score += 1
                elif cur < sma20 and sma20 < sma50:   score -= 2
                elif cur < sma20:                      score -= 1
                if macd > 0: score += 1
                else:        score -= 1

                if score < min_score or score > max_score: continue

                verdict = ("STRONG BUY" if score >= 4 else "BUY" if score >= 2
                           else "HOLD" if score >= 0 else "AVOID" if score >= -2 else "STRONG AVOID")
                ret_1m = round(((cur - float(closes.iloc[-22])) / float(closes.iloc[-22])) * 100, 2)

                vol_ratio = 1.0
                if volumes_all is not None and sym in volumes_all.columns:
                    vols = volumes_all[sym].dropna()
                    if len(vols) >= 20:
                        avg_v = float(vols.tail(20).mean())
                        vol_ratio = round(float(vols.iloc[-1]) / avg_v, 2) if avg_v else 1

                results.append({
                    "symbol": sym, "name": NAME_MAP.get(sym, sym.replace(".NS", "")),
                    "price": round(cur, 2),
                    "change_pct": round(((cur - prev) / prev) * 100, 2) if prev else 0,
                    "score": score, "verdict": verdict,
                    "rsi": rsi, "sma20": sma20, "sma50": sma50, "macd": macd,
                    "ret_1m": ret_1m, "vol_ratio": vol_ratio,
                })
            except Exception:
                continue

        results.sort(key=lambda x: x["score"], reverse=True)
        return Response(json.dumps({"results": results[:20], "universe": universe, "total_scanned": len(syms)}),
                        content_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return json.dumps({"error": str(e)}), 502, {"Access-Control-Allow-Origin": "*"}


@app.route("/news")
def news():
    symbol = request.args.get("symbol", "").upper().strip()
    if not symbol:
        return Response(json.dumps([]), content_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*"})
    if "." not in symbol and "^" not in symbol:
        symbol += ".NS"
    try:
        ticker = yf.Ticker(symbol)
        raw = getattr(ticker, "news", None) or []
        items = []
        for n in raw[:5]:
            if not isinstance(n, dict):
                continue
            # yfinance 0.2.x: flat keys; newer versions may nest under "content"
            content = n.get("content", {}) or {}
            title   = n.get("title") or content.get("title", "")
            pub     = (n.get("publisher") or
                       content.get("provider", {}).get("displayName", ""))
            link    = (n.get("link") or
                       content.get("canonicalUrl", {}).get("url", ""))
            ts      = n.get("providerPublishTime") or 0
            if title:
                items.append({"title": title, "publisher": pub,
                               "link": link, "published": int(ts)})
        return Response(json.dumps(items), content_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return json.dumps({"error": str(e)}), 502, {"Access-Control-Allow-Origin": "*"}


# ── Mutual Fund helpers ───────────────────────────────────────────────────────
_MF_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

def _mf_fetch(code):
    r = requests.get(f"https://api.mfapi.in/mf/{code}", timeout=15, headers=_MF_HEADERS)
    return r.json()

def _mf_returns(data):
    if not data:
        return {}
    from datetime import timedelta
    entries = []
    for d in data:
        try:
            for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(d["date"], fmt)
                    entries.append((dt, float(d["nav"])))
                    break
                except ValueError:
                    pass
        except (KeyError, TypeError):
            pass
    if not entries:
        return {}
    entries.sort(key=lambda x: x[0], reverse=True)
    cur_date, cur_nav = entries[0]

    def nav_at(days):
        target = cur_date - timedelta(days=days)
        best, best_diff = None, float("inf")
        for dt, nav in entries:
            diff = abs((dt - target).days)
            if diff < best_diff:
                best_diff, best = diff, nav
            if dt < target - timedelta(days=15):
                break
        return best if best_diff <= 15 else None

    def ret(days):
        past = nav_at(days)
        if past and past > 0:
            return round(((cur_nav - past) / past) * 100, 2)
        return None

    def cagr(days, years):
        past = nav_at(days)
        if past and past > 0:
            return round(((cur_nav / past) ** (1 / years) - 1) * 100, 2)
        return None

    return {
        "1M":  ret(30),
        "3M":  ret(90),
        "6M":  ret(180),
        "1Y":  cagr(365, 1),
        "3Y":  cagr(365 * 3, 3),
        "5Y":  cagr(365 * 5, 5),
    }

def _mf_search_and_fetch(q):
    """Search MFAPI, prefer Direct Growth, return analysis dict or None."""
    r = requests.get(f"https://api.mfapi.in/mf/search?q={q}", timeout=10, headers=_MF_HEADERS)
    results = r.json()
    direct = [f for f in results
              if "direct" in f["schemeName"].lower() and "growth" in f["schemeName"].lower()]
    chosen = direct[0] if direct else (results[0] if results else None)
    if not chosen:
        return None
    code = str(chosen["schemeCode"])
    fund = _mf_fetch(code)
    meta = fund.get("meta", {})
    data = fund.get("data", [])
    if not data:
        return None
    prices = [float(d["nav"]) for d in reversed(data[:365])]
    return {
        "type": "mf",
        "code": code,
        "name": meta.get("scheme_name", ""),
        "category": meta.get("scheme_category", ""),
        "type_label": meta.get("scheme_type", ""),
        "fund_house": meta.get("fund_house", ""),
        "current_nav": round(float(data[0]["nav"]), 4),
        "nav_date": data[0].get("date", ""),
        "returns": _mf_returns(data),
        "prices": prices,
    }

def _stock_as_mf_format(q):
    """Fetch a stock and return it in MF-compatible returns format."""
    sym = q.strip().upper()
    for pop_name, pop_sym in POPULAR.items():
        if pop_name in q.lower():
            sym = pop_sym
            break
    else:
        if "." not in sym and "^" not in sym:
            sym += ".NS"
    try:
        ticker = yf.Ticker(sym)
        hist5y = ticker.history(period="5y")
        if hist5y.empty:
            return None
        prices = hist5y["Close"].tolist()
        cur = prices[-1]
        info = ticker.info

        def ret_at(n):
            if len(prices) > n and prices[-(n+1)]:
                return round(((cur - prices[-(n+1)]) / prices[-(n+1)]) * 100, 2)
            return None

        def cagr_at(n, yrs):
            if len(prices) > n and prices[-(n+1)] and yrs:
                return round(((cur / prices[-(n+1)]) ** (1/yrs) - 1) * 100, 2)
            return None

        return {
            "type": "stock",
            "code": sym,
            "name": info.get("longName") or NAME_MAP.get(sym, sym.replace(".NS", "")),
            "category": info.get("sector", "Equity"),
            "type_label": "Stock",
            "fund_house": "NSE",
            "current_nav": round(cur, 2),
            "nav_date": "",
            "returns": {
                "1M":  ret_at(22),
                "3M":  ret_at(66),
                "6M":  ret_at(130),
                "1Y":  cagr_at(252, 1),
                "3Y":  cagr_at(756, 3),
                "5Y":  cagr_at(1260, 5),
            },
            "prices": prices[-365:] if len(prices) > 365 else prices,
        }
    except Exception:
        return None


@app.route("/mf/search")
def mf_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return Response(json.dumps([]), content_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*"})
    try:
        r = requests.get(f"https://api.mfapi.in/mf/search?q={q}", timeout=10, headers=_MF_HEADERS)
        results = r.json()
        direct = [{"code": f["schemeCode"], "name": f["schemeName"]}
                  for f in results
                  if "direct" in f["schemeName"].lower() and "growth" in f["schemeName"].lower()]
        return Response(json.dumps(direct[:10]), content_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return json.dumps({"error": str(e)}), 502, {"Access-Control-Allow-Origin": "*"}


@app.route("/mf/analyze")
def mf_analyze():
    q = request.args.get("q", "").strip()
    if not q:
        return json.dumps({"error": "no query"}), 400, {"Access-Control-Allow-Origin": "*"}
    try:
        result = _mf_search_and_fetch(q)
        if not result:
            return json.dumps({"error": "not found"}), 404, {"Access-Control-Allow-Origin": "*"}
        return Response(json.dumps(result), content_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return json.dumps({"error": str(e)}), 502, {"Access-Control-Allow-Origin": "*"}


@app.route("/mf/compare")
def mf_compare():
    from concurrent.futures import ThreadPoolExecutor
    queries = [request.args.get(f"q{i}", "").strip() for i in range(1, 5)]
    queries = [q for q in queries if q][:4]
    if len(queries) < 2:
        return json.dumps({"error": "need at least q1 and q2"}), 400, {"Access-Control-Allow-Origin": "*"}

    def fetch_one(q):
        # Try MF first, then stock
        try:
            result = _mf_search_and_fetch(q)
            if result:
                return result
        except Exception:
            pass
        try:
            return _stock_as_mf_format(q)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(fetch_one, queries))

    results = [r for r in results if r]
    return Response(json.dumps(results), content_type="application/json",
                    headers={"Access-Control-Allow-Origin": "*"})


@app.route("/mf/top")
def mf_top():
    from concurrent.futures import ThreadPoolExecutor
    category = request.args.get("category", "large cap").lower().strip()
    search_map = {
        "large cap":  "large cap direct growth",
        "mid cap":    "mid cap direct growth",
        "small cap":  "small cap direct growth",
        "flexi cap":  "flexi cap direct growth",
        "elss":       "elss tax saver direct growth",
        "debt":       "short duration direct growth",
        "index":      "nifty 50 index direct",
        "hybrid":     "aggressive hybrid direct growth",
    }
    search_q = search_map.get(category, category + " direct growth")
    try:
        r = requests.get(f"https://api.mfapi.in/mf/search?q={search_q}",
                         timeout=10, headers=_MF_HEADERS)
        results = r.json()
        direct = [f for f in results
                  if "direct" in f["schemeName"].lower()
                  and "growth" in f["schemeName"].lower()][:14]
        if not direct:
            direct = results[:14]

        def fetch_one(fund_info):
            try:
                code = str(fund_info["schemeCode"])
                fund = _mf_fetch(code)
                meta = fund.get("meta", {})
                data = fund.get("data", [])
                if not data or len(data) < 30:
                    return None
                ret = _mf_returns(data)
                return {
                    "code": code,
                    "name": meta.get("scheme_name", ""),
                    "category": meta.get("scheme_category", ""),
                    "fund_house": meta.get("fund_house", ""),
                    "current_nav": round(float(data[0]["nav"]), 4),
                    "returns": ret,
                }
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=6) as ex:
            fetched = list(ex.map(fetch_one, direct))

        valid = [f for f in fetched if f and f["returns"].get("1Y") is not None]
        valid.sort(key=lambda x: x["returns"].get("1Y", 0), reverse=True)
        return Response(json.dumps(valid[:8]), content_type="application/json",
                        headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return json.dumps({"error": str(e)}), 502, {"Access-Control-Allow-Origin": "*"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"✓  Free Stock Agent — open http://localhost:{port} in your browser")
    app.run(host="0.0.0.0", port=port, debug=False)
