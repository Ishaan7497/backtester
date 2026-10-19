# 📈 mini-backtester

**A beginner-friendly stock backtester: test a moving-average crossover strategy on real prices and see if it beats buy-and-hold.**

[![tests](https://github.com/Ishaan7497/mini-backtester/actions/workflows/tests.yml/badge.svg)](https://github.com/Ishaan7497/mini-backtester/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![pandas](https://img.shields.io/badge/pandas-yfinance-150458)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

![Example run on TSLA](docs/example_results.png)

## About

A small tool I built to learn how backtesting works. It runs a moving-average
crossover strategy on a single stock and compares it against just buying and
holding.

The strategy never deals in fixed dollar amounts; everything is a fraction of
the account, so the results are percentages that apply to any starting balance.
On trending large-caps it usually loses to buy-and-hold: it trades on noise,
pays a fee each time, and sits in cash through part of the climb. Seeing that
for myself was the point.

The one thing the code is careful about is lookahead bias — the trading signal
is shifted a day before returns are applied, so the strategy can only act on
information it would actually have had at the time. Skipping that is the
easiest way to get fake results.

That applies to the optional stop-loss and take-profit too: they only look at
the previous day's close. An earlier version checked the same day's close, which
let a stop-loss "see" a drop and dodge it. On MSFT 2019–2024 that bug turned a
46% return into an apparent 129%. The test suite now rewrites future prices and
checks that no earlier trading decision changes.

## Why I built this

## Setup

    pip install -r requirements.txt

## Running it

Open `backtest.py` and edit the settings block near the top, then run:

    python backtest.py

| Setting | What it controls |
|---|---|
| `TICKER` | The stock symbol to test, e.g. `"MSFT"`, `"NVDA"` |
| `START_DATE`, `END_DATE` | The date range to test, in `"YYYY-MM-DD"` format |
| `FAST_MA` | The short moving-average window, in days |
| `SLOW_MA` | The long moving-average window, in days |
| `COST_PER_TRADE` | The fee per trade, as a fraction (`0.001` = 0.1%) |
| `STOP_LOSS_PCT` | Exit early if the trade is down this much (`0.05` = 5%), `0` to turn off |
| `TAKE_PROFIT_PCT` | Exit early if the trade is up this much (`0.10` = 10%), `0` to turn off |
| `MODE` | `"single"` to test one fast/slow combo, `"sweep"` to test many at once, or `"multi_stock"` to test several tickers |
| `SWEEP_FAST`, `SWEEP_SLOW` | The lists of windows to try when `MODE = "sweep"` |
| `TICKERS_TO_TEST` | The tickers to compare when `MODE = "multi_stock"` |

Any of the main settings can also be overridden from the command line:

    python backtest.py --ticker NVDA --short 10 --long 30
    python backtest.py --mode sweep --stop-loss 0.05 --take-profit 0
    python backtest.py --help

Settings that don't make sense (a short window that isn't shorter than the long
one, negative fees, a start date after the end date, an unknown mode) are
rejected with a clear message.

**Single mode** prints a results summary in the terminal and saves
`results.png` — a two-panel chart showing the price with both moving averages
and every buy/sell mark, plus the strategy's equity curve next to buy-and-hold.

**Sweep mode** tests every combination of `SWEEP_FAST` and `SWEEP_SLOW`, prints
a table ranked by return with a buy-and-hold row for comparison, and saves
`sweep.png` — a heatmap where greener cells mean better returns, so you can see
at a glance whether a combo's success is a real pattern or a lucky coincidence.

![Example parameter sweep on TSLA](docs/example_sweep.png)

**Multi-stock mode** runs the same settings on every ticker in
`TICKERS_TO_TEST` and ranks them, to check whether a result holds up beyond one
stock.

## What the terms mean

**Moving average** — the average price over the last *N* days. A 20-day
moving average smooths out daily noise so you can see the underlying trend.

**Crossover** — the moment the fast (short-window) average crosses above or
below the slow (long-window) average. The strategy buys on a cross up and
sells on a cross down.

**Total return** — how much the starting balance grew (or shrank) by the end
of the test period.

**Sharpe ratio** — reward per unit of risk. Roughly: average return divided by
how much the returns bounce around, annualized. Higher is better; above 1 is
generally considered decent.

**Max drawdown** — the worst drop from a previous peak to a later low during
the test. It's not the buy price to the lowest point, and not simply the
highest value to the lowest value overall — it's the single worst peak-to-valley
fall along the way, which is what you'd have actually felt holding through it.

**Win rate** — of all the completed round-trip trades (one buy followed by one
sell), the percentage that ended up profitable after fees. A high win rate
doesn't guarantee a good total return — a few large losses can still outweigh
many small wins.

**Trades made** — how many times the strategy moved between being in the stock
and in cash. Every trade pays the fee set by `COST_PER_TRADE`.

**Buy and hold** — the comparison baseline: buy once at the start, do nothing,
sell at the end. The strategy is only interesting if it can beat this.

## Testing

    pip install pytest
    pytest

The tests use made-up price series, so they don't need an internet connection.
They cover lookahead bias, trading costs, matching each buy to its sell,
the summary numbers, missing or oddly shaped downloads, and every command-line
mode. They run on every push with GitHub Actions.

## License

[MIT](LICENSE). Nothing here is investment advice. It's a learning tool.
