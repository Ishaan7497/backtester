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

TICKER = "TSLA"            # the stock symbol, e.g. "AAPL", "NVDA", "XOM"

START_DATE = "2023-01-01"  # when to start testing (YYYY-MM-DD)
END_DATE = "2026-01-01"    # when to stop testing  (YYYY-MM-DD)

FAST_MA = 20               # fast (short) moving average, in days
SLOW_MA = 50               # slow (long) moving average, in days

COST_PER_TRADE = 0.001     # fee per trade (0.001 = 0.1%)

# Risk management: exit a position early if it hits these (0 = disabled)
STOP_LOSS_PCT = 0.05       # exit if down 5% from entry (0.05 = 5%), or 0 to disable
TAKE_PROFIT_PCT = 0.10     # exit if up 10% from entry (0.10 = 10%), or 0 to disable

# What to run:
#   "single"       -> test one FAST_MA / SLOW_MA combo (and draw the chart)
#   "sweep"        -> test many combos below, rank them, and draw a heatmap
#   "multi_stock"  -> test the same params across many tickers below
MODE = "sweep"
SWEEP_FAST = [5, 10, 20, 50]      # fast windows to try in sweep mode
SWEEP_SLOW = [50, 100, 150, 200]  # slow windows to try in sweep mode

# For multi_stock mode: test the strategy on these tickers
TICKERS_TO_TEST = [ "MSFT", "NVDA", "TSLA", "AAPL"]

# ============================================================
#   (you don't need to touch anything below this line)
# ============================================================


def get_prices(ticker, start, end):
    """Download daily closing prices from Yahoo Finance."""
    data = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if data.empty:
        raise SystemExit(
            f"No data came back for '{ticker}'.\n"
            f"This usually isn't a bad symbol — it's almost always one of:\n"
            f"  1) Yahoo Finance temporarily rate-limited you (too many requests"
            f" in a short time). Wait ~30-60 seconds and try again.\n"
            f"  2) yfinance is out of date. Try: pip install --upgrade yfinance\n"
            f"  3) The symbol or date range really is wrong — double check it."
        )
    # yfinance sometimes returns columns with two levels; flatten to just "Close".
    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.to_frame("Close")


def run_backtest(data, short_window, long_window, cost_per_trade,
                 stop_loss_pct=0, take_profit_pct=0):
    """Apply the crossover rule with optional stop-loss and take-profit."""

    # 1) The two moving averages.
    data["ma_short"] = data["Close"].rolling(short_window).mean()
    data["ma_long"] = data["Close"].rolling(long_window).mean()

    # 2) The signal from the crossover.
    signal = (data["ma_short"] > data["ma_long"]).astype(int)
    target = signal.shift(1).fillna(0)

    # 3) Apply stop-loss and take-profit on top of the MA signal.
    #    position[i] is what we hold DURING day i (yesterday's close -> today's
    #    close), so it may only use prices up to yesterday's close. Using
    #    today's close here would let a stop-loss "see" a drop and dodge it.
    close = data["Close"].values
    position = np.zeros(len(data))
    entry_price = None

    for i in range(1, len(data)):
        last_close = close[i - 1]

        if position[i-1] == 0 and target.iloc[i] == 1:
            # Entering the market at yesterday's close.
            position[i] = 1
            entry_price = last_close
        elif position[i-1] == 1:
            # Already in the market — check stop/profit before checking MA signal.
            price_change = (last_close - entry_price) / entry_price
            
            hit_stop = stop_loss_pct > 0 and price_change <= -stop_loss_pct
            hit_profit = take_profit_pct > 0 and price_change >= take_profit_pct
            
            if hit_stop or hit_profit:
                # Exit due to stop-loss or take-profit (override MA signal).
                position[i] = 0
                entry_price = None
            elif target.iloc[i] == 0:
                # Exit due to MA signal crossing.
                position[i] = 0
                entry_price = None
            else:
                # Stay in position.
                position[i] = 1
        # else: position[i-1] == 0 and target.iloc[i] == 0, so stay in cash.
    
    data["position"] = position

    # 4) The stock's daily percentage change.
    data["mkt_ret"] = data["Close"].pct_change().fillna(0)

    # 5) We only earn the stock's return on days we actually held it.
    data["strat_ret"] = data["position"] * data["mkt_ret"]

    # 6) Every time the position changes, a trade happened — subtract a cost.
    turnover = data["position"].diff().abs().fillna(0)
    data["strat_ret"] = data["strat_ret"] - turnover * cost_per_trade

    # 7) Turn the stream of daily returns into a growing account balance.
    data["strat_equity"] = (1 + data["strat_ret"]).cumprod()
    data["hold_equity"] = (1 + data["mkt_ret"]).cumprod()

    # Count a "trade" as moving in or out of the market.
    in_market = (data["position"] > 0).astype(int)
    n_trades = int(in_market.diff().abs().fillna(0).sum())

    return data, n_trades


def trade_breakdown(data, cost_per_trade):
    """Pair each buy with its sell to see which round-trips made money.

    A "round-trip" is one full buy-then-sell cycle. For each one we check the
    price we bought at vs. the price we sold at (minus the two fees) and call it
    a win if it ended positive, a loss otherwise. If we're still holding at the
    end, we close that final trade at the last price.
    """
    position = data["position"].values
    price = data["Close"].values
    results = []
    entry_price = None

    # A position that starts (or ends) on day i was traded at day i-1's close.
    for i in range(1, len(position)):
        bought = position[i] > 0 and position[i - 1] == 0
        sold = position[i] == 0 and position[i - 1] > 0

        if bought:
            entry_price = price[i - 1]
        elif sold and entry_price is not None:
            net = price[i - 1] / entry_price - 1 - 2 * cost_per_trade
            results.append(net)
            entry_price = None

    # Still holding when the test ended? Close it at the last price.
    if entry_price is not None:
        results.append(price[-1] / entry_price - 1 - 2 * cost_per_trade)

    wins = sum(1 for r in results if r > 0)
    losses = len(results) - wins
    return wins, losses


def summarize(equity, returns):
    """Three headline numbers for a result."""
    total_return = equity.iloc[-1] - 1
    # Sharpe ratio = reward per unit of wobble, annualized (252 trading days).
    sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0
    # Max drawdown = the worst peak-to-valley drop you'd have lived through.
    peak = equity.cummax()
    max_drawdown = ((equity - peak) / peak).min()
    return total_return, sharpe, max_drawdown


def settings_header(title, start, end, cost, stop_loss, take_profit, width):
    """Print a header showing exactly what settings produced the results below."""
    sl = f"{stop_loss * 100:.0f}%" if stop_loss > 0 else "off"
    tp = f"{take_profit * 100:.0f}%" if take_profit > 0 else "off"
    print("\n" + "=" * width)
    print(f"  {title}")
    print(f"  {start} to {end}  |  cost {cost * 100:.2f}%  "
          f"|  stop-loss {sl}  |  take-profit {tp}")
    print("=" * width)


def print_single_result(ticker, fast, slow, data, n_trades, cost,
                        start, end, stop_loss, take_profit):
    """Print the summary table for one backtest."""
    strat = summarize(data["strat_equity"], data["strat_ret"])
    hold = summarize(data["hold_equity"], data["mkt_ret"])
    wins, losses = trade_breakdown(data, cost)
    round_trips = wins + losses
    win_rate = wins / round_trips if round_trips else 0
    beat = strat[0] - hold[0]

    settings_header(f"{ticker}  —  {fast}/{slow}-day crossover",
                    start, end, cost, stop_loss, take_profit, 52)
    print(f"  {'':16}{'Strategy':>11}{'Buy & Hold':>13}")
    print(f"  {'Total return':16}{strat[0]:>10.1%}{hold[0]:>13.1%}")
    print(f"  {'Sharpe ratio':16}{strat[1]:>10.2f}{hold[1]:>13.2f}")
    print(f"  {'Max drawdown':16}{strat[2]:>10.1%}{hold[2]:>13.1%}")
    print(f"  {'Trades':16}{n_trades:>10}")
    print(f"  {'Win rate':16}{win_rate:>10.0%}    ({wins} W / {losses} L)")
    print("-" * 52)
    if beat > 0:
        print(f"  Strategy BEAT buy & hold by {beat:+.1%}")
    else:
        print(f"  Strategy lost to buy & hold by {beat:.1%}")
    print("=" * 52)


def save_chart(ticker, fast, slow, data):
    """Two-panel chart: price + moving averages with buy/sell marks, and equity."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    ax1.plot(data.index, data["Close"], label="Price", linewidth=1.5, alpha=0.7, color="gray")
    ax1.plot(data.index, data["ma_short"], label=f"Short MA ({fast}d)", linewidth=1.8, color="blue")
    ax1.plot(data.index, data["ma_long"], label=f"Long MA ({slow}d)", linewidth=1.8, color="orange")

    # Buy/sell marks = the closes we traded at (the day before the position changed).
    in_market = (data["position"] > 0).astype(int)
    moves = in_market.diff().shift(-1).fillna(0)
    buys = data.index[moves == 1]
    sells = data.index[moves == -1]
    ax1.scatter(buys, data.loc[buys, "Close"], marker="^", color="green", s=100, label="Buy", zorder=5)
    ax1.scatter(sells, data.loc[sells, "Close"], marker="v", color="red", s=100, label="Sell", zorder=5)

    ax1.set_ylabel("Price ($)")
    ax1.set_title(f"{ticker}: Moving Average Crossover ({fast}/{slow}-day)")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(alpha=0.3)

    ax2.plot(data.index, data["strat_equity"], label="Strategy", linewidth=1.8, color="blue")
    ax2.plot(data.index, data["hold_equity"], label="Buy & Hold", linewidth=1.8, alpha=0.7, color="gray")
    ax2.set_ylabel("Account value (started at $1)")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left", fontsize=9)
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig("results.png", dpi=120)
    print("\nChart saved to results.png (2 panels: strategy trades + equity curves)")


def run_multi_stock(tickers, fast, slow, start, end, cost, stop_loss, take_profit):
    """Test the same strategy on multiple stocks and rank by return."""
    rows = []

    for ticker in tickers:
        try:
            prices = get_prices(ticker, start, end)
        except SystemExit:
            print(f"  {ticker:>6} — no data")
            continue

        data, n_trades = run_backtest(prices, fast, slow, cost, stop_loss, take_profit)
        strat = summarize(data["strat_equity"], data["strat_ret"])
        hold = summarize(data["hold_equity"], data["mkt_ret"])
        wins, losses = trade_breakdown(data, cost)
        win_rate = wins / (wins + losses) if (wins + losses) else 0

        rows.append((ticker, strat[0], hold[0], strat[1], strat[2], n_trades, win_rate))

    rows.sort(key=lambda r: r[1], reverse=True)  # rank by strategy return

    W = 74
    settings_header(f"Multi-stock test  —  {fast}/{slow}-day crossover",
                    start, end, cost, stop_loss, take_profit, W)
    print(f"  {'Ticker':>7}{'Strategy':>11}{'Buy&Hold':>11}{'vs B&H':>10}"
          f"{'Sharpe':>8}{'MaxDD':>9}{'Win%':>7}")
    print("-" * W)
    beat_count = 0
    for ticker, strat_ret, hold_ret, sharpe, max_dd, n_trades, win_rate in rows:
        diff = strat_ret - hold_ret
        mark = " *" if diff > 0 else "  "
        if diff > 0:
            beat_count += 1
        print(f"  {ticker:>7}{strat_ret:>11.1%}{hold_ret:>11.1%}{diff:>+9.1%}{mark}"
              f"{sharpe:>7.2f}{max_dd:>9.1%}{win_rate:>7.0%}")
    print("-" * W)
    print(f"  ( * = beat buy & hold )")
    print("=" * W)

    print(f"\n  {beat_count} of {len(rows)} stocks beat buy & hold with this strategy.")
    if beat_count == len(rows) and rows:
        print("  It worked on every stock — that's a sign of something real, not luck.")
    elif beat_count <= 1:
        print("  It only worked on one (or none) — likely stock-specific luck.")



def run_sweep(prices, fast_list, slow_list, cost, ticker, stop_loss, take_profit,
              start, end):
    """Test many fast/slow combos, print a ranked table, and draw a heatmap."""
    rows = []
    for fast in fast_list:
        for slow in slow_list:
            if fast >= slow:
                continue  # fast must be shorter than slow
            d, n_trades = run_backtest(prices.copy(), fast, slow, cost, stop_loss, take_profit)
            total, sharpe, max_dd = summarize(d["strat_equity"], d["strat_ret"])
            rows.append((fast, slow, total, sharpe, max_dd, n_trades))

    rows.sort(key=lambda r: r[2], reverse=True)  # best total return first

    # Buy & hold baseline (same for every combo).
    mkt_ret = prices["Close"].pct_change().fillna(0)
    base = summarize((1 + mkt_ret).cumprod(), mkt_ret)

    W = 70
    settings_header(f"Parameter sweep  —  {ticker}",
                    start, end, cost, stop_loss, take_profit, W)
    print(f"  {'Fast':>5}{'Slow':>6}{'Return':>11}{'Sharpe':>8}"
          f"{'MaxDD':>9}{'Trades':>8}{'vs B&H':>13}")
    print("-" * W)
    beat_count = 0
    for fast, slow, total, sharpe, max_dd, n_trades in rows:
        diff = total - base[0]
        if diff > 0:
            beat_count += 1
        print(f"  {fast:>5}{slow:>6}{total:>11.1%}{sharpe:>8.2f}"
              f"{max_dd:>9.1%}{n_trades:>8}{diff:>+12.1%} ")
    print("-" * W)
    print(f"  {'Buy & Hold':>11}{base[0]:>11.1%}{base[1]:>8.2f}"
          f"{base[2]:>9.1%}{'—':>8}{'baseline':>13}")
    print("=" * W)

    best = rows[0]
    print(f"\n  Best combo: {best[0]}/{best[1]}-day  ->  {best[2]:.1%} return "
          f"({best[2] - base[0]:+.1%} vs buy & hold)")
    print(f"  {beat_count} of {len(rows)} combos beat buy & hold.")
    if beat_count <= 1:
        print("  Only one (or none) beating it is a warning sign — likely luck, not edge.")
    print("  Check sweep.png: a green CLUSTER is trustworthy, one lone green cell isn't.")

    save_sweep_heatmap(rows, fast_list, slow_list, ticker)




def save_sweep_heatmap(rows, fast_list, slow_list, ticker):
    """Draw a grid of returns: one cell per fast/slow combo, greener = better."""
    plt.close("all")  # clear any previous figures to avoid carryover
    
    # Build a grid (rows = fast windows, cols = slow windows).
    lookup = {(fast, slow): total for fast, slow, total, *_ in rows}
    grid = np.full((len(fast_list), len(slow_list)), np.nan)
    for i, fast in enumerate(fast_list):
        for j, slow in enumerate(slow_list):
            if (fast, slow) in lookup:
                grid[i, j] = lookup[(fast, slow)] * 100  # as a percent

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(grid, cmap="RdYlGn", aspect="auto")

    ax.set_xticks(range(len(slow_list)), labels=slow_list)
    ax.set_yticks(range(len(fast_list)), labels=fast_list)
    ax.set_xlabel("Slow MA (days)")
    ax.set_ylabel("Fast MA (days)")
    ax.set_title(f"{ticker}: total return by parameter combo (%)")

    # Write the return number inside each cell.
    for i in range(len(fast_list)):
        for j in range(len(slow_list)):
            if not np.isnan(grid[i, j]):
                ax.text(j, i, f"{grid[i, j]:.0f}%", ha="center", va="center", fontsize=10)

    fig.colorbar(im, ax=ax, label="Total return (%)")
    plt.tight_layout()
    plt.savefig("sweep.png", dpi=120)
    print("\nHeatmap saved to sweep.png")


def main():
    # Defaults come from the SETTINGS block at the top of this file.
    # The command-line flags below are optional and only override those.
    parser = argparse.ArgumentParser(description="Tiny moving-average backtester.")
    parser.add_argument("--ticker", default=TICKER, help="Stock symbol")
    parser.add_argument("--start", default=START_DATE, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=END_DATE, help="End date YYYY-MM-DD")
    parser.add_argument("--short", type=int, default=FAST_MA, help="Short MA window (days)")
    parser.add_argument("--long", type=int, default=SLOW_MA, help="Long MA window (days)")
    parser.add_argument("--cost", type=float, default=COST_PER_TRADE, help="Cost per trade")
    args = parser.parse_args()

    if MODE == "multi_stock":
        run_multi_stock(TICKERS_TO_TEST, args.short, args.long, args.start, args.end,
                        args.cost, STOP_LOSS_PCT, TAKE_PROFIT_PCT)
        return

    print(f"Downloading {args.ticker} from {args.start} to {args.end}...")
    prices = get_prices(args.ticker, args.start, args.end)

    if MODE == "sweep":
        run_sweep(prices, SWEEP_FAST, SWEEP_SLOW, args.cost, args.ticker,
                  STOP_LOSS_PCT, TAKE_PROFIT_PCT, args.start, args.end)
        return

    # Single mode
    data, n_trades = run_backtest(prices, args.short, args.long, args.cost,
                                  STOP_LOSS_PCT, TAKE_PROFIT_PCT)
    print_single_result(args.ticker, args.short, args.long, data, n_trades, args.cost,
                        args.start, args.end, STOP_LOSS_PCT, TAKE_PROFIT_PCT)
    save_chart(args.ticker, args.short, args.long, data)



if __name__ == "__main__":
    main()