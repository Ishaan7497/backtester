"""
backtest.py — a tiny, beginner-friendly stock backtester.

What it does:
  Tests one simple trading rule on one stock using real historical prices,
  then compares it against just buying and holding the stock.

The rule (a "moving-average crossover"):
  - Be IN the stock when the recent average price (short window) is above the
    slower average price (long window) -> the stock is trending up.
  - Be in CASH otherwise.

Run it:
  Edit the SETTINGS block below (ticker, dates, moving averages), then:
  python backtest.py

  Or override any setting from the command line:
  python backtest.py --ticker NVDA --short 10 --long 30

Nothing here is investment advice. It's a learning tool.
"""

import argparse
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt


# ============================================================
#   SETTINGS  --  edit these, then just run the file
# ============================================================

TICKER = "MSFT"            # the stock symbol, e.g. "AAPL", "NVDA", "XOM"

START_DATE = "2019-01-01"  # when to start testing (YYYY-MM-DD)
END_DATE = "2024-01-01"    # when to stop testing  (YYYY-MM-DD)

FAST_MA = 20               # fast (short) moving average, in days
SLOW_MA = 50               # slow (long) moving average, in days

COST_PER_TRADE = 0.001     # fee per trade (0.001 = 0.1%)

# ============================================================
#   (you don't need to touch anything below this line)
# ============================================================


def get_prices(ticker, start, end):
    """Download daily closing prices from Yahoo Finance."""
    data = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if data.empty:
        raise SystemExit(f"No data found for '{ticker}'. Check the symbol and dates.")
    # yfinance sometimes returns columns with two levels; flatten to just "Close".
    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.to_frame("Close")


def run_backtest(data, short_window, long_window, cost_per_trade):
    """Apply the crossover rule and compute day-by-day results."""

    # 1) The two moving averages.
    data["ma_short"] = data["Close"].rolling(short_window).mean()
    data["ma_long"] = data["Close"].rolling(long_window).mean()

    # 2) The signal: 1 = "we want to be in the stock", 0 = "we want cash".
    data["signal"] = (data["ma_short"] > data["ma_long"]).astype(int)

    # 3) THE MOST IMPORTANT LINE.
    #    We act on YESTERDAY'S signal, not today's. In real life you can't see
    #    today's closing price and trade at that same close — so we shift the
    #    signal forward one day. Skipping this is the #1 way beginners fool
    #    themselves into fake profits ("lookahead bias").
    data["position"] = data["signal"].shift(1).fillna(0)

    # 4) The stock's daily percentage change.
    data["mkt_ret"] = data["Close"].pct_change().fillna(0)

    # 5) We only earn the stock's return on days we actually held it.
    data["strat_ret"] = data["position"] * data["mkt_ret"]

    # 6) Every time the position changes, a trade happened — subtract a cost.
    trades = data["position"].diff().abs().fillna(0)
    data["strat_ret"] = data["strat_ret"] - trades * cost_per_trade

    # 7) Turn the stream of daily returns into a growing account balance,
    #    starting from $1. This is what we plot.
    data["strat_equity"] = (1 + data["strat_ret"]).cumprod()
    data["hold_equity"] = (1 + data["mkt_ret"]).cumprod()

    return data, int(trades.sum())


def summarize(equity, returns):
    """Three headline numbers for a result."""
    total_return = equity.iloc[-1] - 1
    # Sharpe ratio = reward per unit of wobble, annualized (252 trading days).
    sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0
    # Max drawdown = the worst peak-to-valley drop you'd have lived through.
    peak = equity.cummax()
    max_drawdown = ((equity - peak) / peak).min()
    return total_return, sharpe, max_drawdown


def main():
    # Defaults come from the SETTINGS block at the top of this file.
    # The command-line flags below are optional and only override those.
    parser = argparse.ArgumentParser(description="Tiny moving-average backtester.")
    parser.add_argument("--ticker", default=TICKER, help="Stock symbol")
    parser.add_argument("--start", default=START_DATE, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=END_DATE, help="End date YYYY-MM-DD")
    parser.add_argument("--short", type=int, default=FAST_MA, help="Short MA window (days)")
    parser.add_argument("--long", type=int, default=SLOW_MA, help="Long MA window (days)")
    parser.add_argument("--cost", type=float, default=COST_PER_TRADE, help="Cost per trade (0.001 = 0.1%)")
    args = parser.parse_args()

    print(f"Downloading {args.ticker} from {args.start} to {args.end}...")
    data = get_prices(args.ticker, args.start, args.end)

    data, n_trades = run_backtest(data, args.short, args.long, args.cost)

    strat = summarize(data["strat_equity"], data["strat_ret"])
    hold = summarize(data["hold_equity"], data["mkt_ret"])

    print("\n" + "=" * 52)
    print(f"  Results for {args.ticker}  ({args.short}/{args.long}-day crossover)")
    print("=" * 52)
    print(f"  {'':14}{'Strategy':>12}{'Buy & Hold':>14}")
    print(f"  {'Total return':14}{strat[0]:>11.1%}{hold[0]:>14.1%}")
    print(f"  {'Sharpe ratio':14}{strat[1]:>11.2f}{hold[1]:>14.2f}")
    print(f"  {'Max drawdown':14}{strat[2]:>11.1%}{hold[2]:>14.1%}")
    print(f"  {'Trades made':14}{n_trades:>11}")
    print("=" * 52)

    # Plot 1: Strategy chart with moving averages and buy/sell points.
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    # Top plot: Price and moving averages.
    ax1.plot(data.index, data["Close"], label="Price", linewidth=1.5, alpha=0.7, color="gray")
    ax1.plot(data.index, data["ma_short"], label=f"Short MA ({args.short}d)", linewidth=1.8, color="blue")
    ax1.plot(data.index, data["ma_long"], label=f"Long MA ({args.long}d)", linewidth=1.8, color="orange")
    
    # Mark the buy and sell points (where position changes).
    trades = data["position"].diff().fillna(0)
    buys = data.index[trades == 1]
    sells = data.index[trades == -1]
    ax1.scatter(buys, data.loc[buys, "Close"], marker="^", color="green", s=100, label="Buy", zorder=5)
    ax1.scatter(sells, data.loc[sells, "Close"], marker="v", color="red", s=100, label="Sell", zorder=5)
    
    ax1.set_ylabel("Price ($)")
    ax1.set_title(f"{args.ticker}: Moving Average Crossover Strategy ({args.short}/{args.long}-day)")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(alpha=0.3)
    
    # Bottom plot: Account equity over time.
    ax2.plot(data.index, data["strat_equity"], label="Strategy", linewidth=1.8, color="blue")
    ax2.plot(data.index, data["hold_equity"], label="Buy & Hold", linewidth=1.8, alpha=0.7, color="gray")
    ax2.set_ylabel("Account value (started at $1)")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left", fontsize=9)
    ax2.grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig("results.png", dpi=120)
    print("\nChart saved to results.png (2 panels: strategy trades + equity curves)")


if __name__ == "__main__":
    main()