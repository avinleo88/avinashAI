"""
Stock Market Agent — Indian Markets (NSE/BSE)
Uses Claude AI + yfinance for live data and investment suggestions.
"""

import os
import json
import anthropic
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from colorama import Fore, Style, init

init(autoreset=True)

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE")

# Popular Indian stocks (yfinance uses .NS for NSE, .BO for BSE)
POPULAR_STOCKS = {
    "Reliance":    "RELIANCE.NS",
    "TCS":         "TCS.NS",
    "Infosys":     "INFY.NS",
    "HDFC Bank":   "HDFCBANK.NS",
    "ICICI Bank":  "ICICIBANK.NS",
    "Wipro":       "WIPRO.NS",
    "HUL":         "HINDUNILVR.NS",
    "Bajaj Finance": "BAJFINANCE.NS",
    "SBI":         "SBIN.NS",
    "Adani Ports": "ADANIPORTS.NS",
    "Nifty 50":    "^NSEI",
    "Sensex":      "^BSESN",
}

# ── Tools ─────────────────────────────────────────────────────────────────────
def get_stock_price(symbol: str, period: str = "1mo") -> dict:
    """Fetch current price, change, and OHLCV data."""
    try:
        # Auto-append .NS if no suffix given
        if "." not in symbol and "^" not in symbol:
            symbol = symbol.upper() + ".NS"

        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period=period)

        if hist.empty:
            return {"error": f"No data found for {symbol}. Try adding .NS or .BO suffix."}

        info    = ticker.info
        current = round(hist["Close"].iloc[-1], 2)
        prev    = round(hist["Close"].iloc[-2], 2) if len(hist) > 1 else current
        change  = round(current - prev, 2)
        pct     = round((change / prev) * 100, 2) if prev else 0

        # Simple moving averages
        sma20  = round(hist["Close"].rolling(20).mean().iloc[-1], 2) if len(hist) >= 20 else None
        sma50  = round(hist["Close"].rolling(50).mean().iloc[-1], 2) if len(hist) >= 50 else None

        # RSI (14-day)
        delta  = hist["Close"].diff()
        gain   = delta.clip(lower=0).rolling(14).mean()
        loss   = (-delta.clip(upper=0)).rolling(14).mean()
        rs     = gain / loss
        rsi    = round((100 - (100 / (1 + rs))).iloc[-1], 2) if not rs.empty else None

        # 52-week high/low
        year_hist = ticker.history(period="1y")
        week52_high = round(year_hist["Close"].max(), 2) if not year_hist.empty else None
        week52_low  = round(year_hist["Close"].min(), 2) if not year_hist.empty else None

        return {
            "symbol":       symbol,
            "name":         info.get("longName", symbol),
            "current_price": current,
            "prev_close":   prev,
            "change":       change,
            "change_pct":   pct,
            "volume":       int(hist["Volume"].iloc[-1]),
            "sma_20":       sma20,
            "sma_50":       sma50,
            "rsi":          rsi,
            "week52_high":  week52_high,
            "week52_low":   week52_low,
            "sector":       info.get("sector", "N/A"),
            "market_cap":   info.get("marketCap", "N/A"),
            "pe_ratio":     info.get("trailingPE", "N/A"),
            "period":       period,
        }

    except Exception as e:
        return {"error": str(e)}


def compare_stocks(symbols: list) -> dict:
    """Compare multiple stocks side by side."""
    results = {}
    for sym in symbols:
        data = get_stock_price(sym, period="3mo")
        if "error" not in data:
            results[sym] = data
    return results


def get_market_overview() -> dict:
    """Get Nifty 50 and Sensex overview."""
    nifty  = get_stock_price("^NSEI",  "1mo")
    sensex = get_stock_price("^BSESN", "1mo")
    return {
        "nifty50": nifty,
        "sensex":  sensex,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_sector_stocks(sector: str) -> dict:
    """Get stocks for a given sector."""
    sector_map = {
        "it":      ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS"],
        "banking": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"],
        "pharma":  ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS"],
        "auto":    ["MARUTI.NS", "TATAMOTORS.NS", "M&M.NS", "BAJAJ-AUTO.NS"],
        "fmcg":    ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS"],
        "energy":  ["RELIANCE.NS", "ONGC.NS", "NTPC.NS", "POWERGRID.NS"],
    }
    key     = sector.lower().replace(" ", "")
    symbols = sector_map.get(key, sector_map.get("it"))
    return compare_stocks(symbols)


# ── Tool definitions for Claude ───────────────────────────────────────────────
TOOLS = [
    {
        "name": "get_stock_price",
        "description": "Fetch current price, technical indicators (RSI, SMA), 52-week range, P/E ratio, and recent performance for an Indian stock. Use .NS suffix for NSE stocks (e.g. TCS.NS) or .BO for BSE.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock symbol e.g. TCS.NS, RELIANCE.NS, ^NSEI"},
                "period": {"type": "string", "description": "Data period: 1d, 5d, 1mo, 3mo, 6mo, 1y", "default": "1mo"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "compare_stocks",
        "description": "Compare multiple Indian stocks side by side with price, RSI, SMA and performance metrics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of stock symbols e.g. [TCS.NS, INFY.NS, WIPRO.NS]",
                }
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "get_market_overview",
        "description": "Get current Nifty 50 and Sensex index overview — use at the start of any analysis.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_sector_stocks",
        "description": "Analyze all major stocks in a sector. Sectors: IT, Banking, Pharma, Auto, FMCG, Energy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {"type": "string", "description": "Sector name: IT, Banking, Pharma, Auto, FMCG, Energy"}
            },
            "required": ["sector"],
        },
    },
]

TOOL_FNS = {
    "get_stock_price":    lambda i: get_stock_price(i["symbol"], i.get("period", "1mo")),
    "compare_stocks":     lambda i: compare_stocks(i["symbols"]),
    "get_market_overview": lambda _: get_market_overview(),
    "get_sector_stocks":  lambda i: get_sector_stocks(i["sector"]),
}

# ── Agent loop ────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert Indian stock market analyst and investment advisor with deep knowledge of NSE and BSE markets.

Your role:
- Analyze live stock data fetched via tools
- Identify trends using RSI, SMA20, SMA50 indicators
- Provide clear BUY / HOLD / AVOID recommendations with reasoning
- Always check the market overview first before individual stocks
- Consider sector trends, P/E ratios, and 52-week position
- Give risk disclaimers — you are providing analysis, not guaranteed advice

Technical signal guidelines:
- RSI < 30 = oversold (potential buy opportunity)
- RSI > 70 = overbought (caution)
- Price > SMA20 > SMA50 = bullish trend
- Price < SMA20 < SMA50 = bearish trend
- Near 52-week high = momentum but risk of correction
- Near 52-week low = value opportunity but check fundamentals

Always structure your response with:
1. Market Overview
2. Stock Analysis (with data)
3. Recommendation (BUY / HOLD / AVOID)
4. Risk Note

Be concise, data-driven, and clear."""


def run_agent(client: anthropic.Anthropic, user_query: str):
    """Run the agentic loop."""
    messages = [{"role": "user", "content": user_query}]

    print(f"\n{Fore.CYAN}{'─'*60}")
    print(f"{Fore.CYAN}Agent thinking...{Style.RESET_ALL}\n")

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Collect all content
        tool_uses   = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        # Print any text
        for block in text_blocks:
            print(f"{Fore.WHITE}{block.text}")

        # No more tool calls — we're done
        if response.stop_reason == "end_turn" or not tool_uses:
            break

        # Execute tools
        tool_results = []
        for tool_use in tool_uses:
            print(f"{Fore.YELLOW}  → Calling tool: {tool_use.name}({json.dumps(tool_use.input)}){Style.RESET_ALL}")
            result = TOOL_FNS[tool_use.name](tool_use.input)
            print(f"{Fore.GREEN}  ✓ Got data for {tool_use.input}{Style.RESET_ALL}\n")
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tool_use.id,
                "content":     json.dumps(result),
            })

        # Add assistant response + tool results to messages
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user",      "content": tool_results})


# ── Main REPL ─────────────────────────────────────────────────────────────────
def main():
    if API_KEY == "YOUR_API_KEY_HERE":
        print(f"{Fore.RED}Error: Set your ANTHROPIC_API_KEY in the script or as an env variable.{Style.RESET_ALL}")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        return

    client = anthropic.Anthropic(api_key=API_KEY)

    print(f"""
{Fore.CYAN}╔══════════════════════════════════════════════════╗
║     Indian Stock Market AI Agent (NSE/BSE)       ║
║     Powered by Claude + Live yfinance Data       ║
╚══════════════════════════════════════════════════╝{Style.RESET_ALL}

{Fore.WHITE}Example queries you can ask:
  • "Should I invest in TCS or Infosys right now?"
  • "Analyze the IT sector"
  • "Give me a market overview for today"
  • "Is Reliance a good buy?"
  • "Compare HDFC Bank and ICICI Bank"
  • "What are the best banking stocks to invest in?"

{Fore.YELLOW}Disclaimer: This is for educational purposes only.
Not financial advice. Always do your own research.{Style.RESET_ALL}
""")

    while True:
        try:
            query = input(f"{Fore.CYAN}You: {Style.RESET_ALL}").strip()
            if not query:
                continue
            if query.lower() in ("exit", "quit", "bye"):
                print(f"{Fore.CYAN}Goodbye! Invest wisely.{Style.RESET_ALL}")
                break
            run_agent(client, query)
            print(f"\n{Fore.CYAN}{'─'*60}{Style.RESET_ALL}\n")

        except KeyboardInterrupt:
            print(f"\n{Fore.CYAN}Goodbye!{Style.RESET_ALL}")
            break
        except Exception as e:
            print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
