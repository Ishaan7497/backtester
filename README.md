# 📈 mini-backtester

**A beginner-friendly stock backtester: test a moving-average crossover strategy on real prices and see if it beats buy-and-hold.**

[![tests](https://github.com/Ishaan7497/mini-backtester/actions/workflows/tests.yml/badge.svg)](https://github.com/Ishaan7497/mini-backtester/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![pandas](https://img.shields.io/badge/pandas-yfinance-150458)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

![20/50-day crossover on META, 2021–2023: the strategy sidesteps the 2022 crash and ends at +180% vs +32% for buy-and-hold](docs/example_results.png)

## About

A small tool I built to learn how backtesting works. It runs a moving-average
crossover strategy on a single stock and compares it against just buying and
holding.

The strategy never deals in fixed dollar amounts; everything is a fraction of
the account, so the results are percentages that apply to any starting balance.
On trending large-caps it usually loses to buy-and-hold: it trades on noise,
pays a fee each time, and sits in cash through part of the climb. Where it does
win is a long crash followed by a recovery — see
[where it works, and where it doesn't](#where-it-works-and-where-it-doesnt).
Seeing both for myself was the point.

The one thing the code is careful about is lookahead bias — the trading signal
is shifted a day before returns are applied, so the strategy can only act on
information it would actually have had at the time. Skipping that is the
easiest way to get fake results.

That applies to the optional stop-loss and take-profit too: they only look at
the previous day's close. An earlier version checked the same day's close, which
let a stop-loss "see" a drop and dodge it. On MSFT 2019–2024 that bug turned a
46% return into an apparent 129%. The test suite now rewrites future prices and
checks that no earlier trading decision changes.

## Where it works, and where it doesn't

A crossover strategy is a bet on long trends. It shines when a stock crashes and
recovers, and falls behind when a stock just keeps climbing. The same stock shows
both.

### Where it works: META, 2021–2023

    python backtest.py --ticker META --start 2021-01-01 --end 2023-12-31 --short 20 --long 50 --stop-loss 0 --take-profit 0 --mode single

META fell 77% from its 2021 peak to its late-2022 low, then nearly tripled in
2023. The 20/50-day crossover sold on the way down, sat in cash through most of
the slide, and bought back in soon after the bottom (the chart at the top of
this page).

| META, 2021–2023 | Strategy (20/50) | Buy & hold |
|---|---|---|
| Total return | **+180%** | +32% |
| Sharpe ratio | **1.29** | 0.44 |
| Max drawdown | **−35%** | −77% |
| Trades | 13 | — |

Only 3 of its 7 round trips made money (a 43% win rate), but the wins were big
and the losses small. With the default 5% stop-loss and 10% take-profit turned
on, it still returns +134%.

One good result could be luck, so the sweep tests all 15 fast/slow combos.
Every one of them beats buy-and-hold, from +54% to +180%, and shifting the start
and end dates anywhere between mid-2020 and mid-2024 still leaves 14 or 15 of the
15 ahead.

    python backtest.py --ticker META --start 2021-01-01 --end 2023-12-31 --stop-loss 0 --take-profit 0 --mode sweep

![Sweep on META, 2021–2023: all 15 combos beat buy-and-hold](docs/example_sweep.png)

### Where it doesn't: META, 2023–2026

From January 2023 to October 2026 META climbed steadily, returning +474%. Not
one of the 15 combos came close; the best managed +160%. With no crash to
avoid, every exit just meant missing part of the climb.

    python backtest.py --ticker META --start 2023-01-01 --end 2026-10-17 --stop-loss 0 --take-profit 0 --mode sweep

![Sweep on META, 2023–2026: none of the 15 combos beat buy-and-hold](docs/example_sweep_bull.png)

NVDA, MSFT, AAPL and SPY over 2023–2026 tell the same story: 0 of 15 combos beat
buy-and-hold on any of them.

The 2021–2023 window was picked *because* it has a crash and a recovery. It shows
the kind of market the strategy is built for; it says nothing about whether the
next crash will come.

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
| `OPEN_CHARTS` | Open the saved chart automatically when the run finishes (`True` / `False`) |

Any of the main settings can also be overridden from the command line:

    python backtest.py --ticker NVDA --short 10 --long 30
    python backtest.py --mode sweep --stop-loss 0.05 --take-profit 0
    python backtest.py --no-open        # don't open the chart when done
    python backtest.py --help

Settings that don't make sense (a short window that isn't shorter than the long
one, negative fees, a start date after the end date, an unknown mode) are
rejected with a clear message.

**Single mode** prints a results summary in the terminal and saves (and opens)
`results.png` — a two-panel chart showing the price with both moving averages
and every buy/sell mark, plus the strategy's equity curve next to buy-and-hold.

**Sweep mode** tests every combination of `SWEEP_FAST` and `SWEEP_SLOW`, prints
a table ranked by return with a buy-and-hold row for comparison, and saves
`sweep.png` — a heatmap whose colors are centered on buy-and-hold: green cells
beat it, red cells lost to it. A green cluster suggests a real pattern; one lone
green cell is more likely luck. (See the two META heatmaps above.)

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
