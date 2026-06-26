# Mini Backtester

A tiny, beginner-friendly stock backtester in Python. It tests one simple
trading rule on one stock using real historical prices, then compares it
against simply buying and holding.

This is a learning project, not investment advice.

## The strategy

A **moving-average crossover**:

- Be **in the stock** when the short-term average price is above the
  long-term average price (the stock is trending up).
- Be in **cash** otherwise.

## What it measures

- **Total return** — how much $1 grew into.
- **Sharpe ratio** — reward per unit of risk (higher is better).
- **Max drawdown** — the worst peak-to-valley drop along the way.
- **Trades made** — how often it bought/sold (each trade costs money).

It also saves a chart (`results.png`) of the strategy vs. buy-and-hold.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
python backtest.py                                  # defaults: AAPL, 20/50-day
python backtest.py --ticker MSFT                    # a different stock
python backtest.py --short 10 --long 30             # different averages
python backtest.py --ticker NVDA --start 2018-01-01 --end 2024-01-01
```

## A note on honesty

The most important line in the code shifts the trading signal forward one day,
so the strategy can only act on yesterday's information. Without that, a
backtest can secretly "peek" at the future and show fake profits. This is the
single most common beginner mistake, and avoiding it is the whole point of
building your own engine.

## Ideas to extend it

- Try the strategy across many stocks and average the results.
- Add a second rule and compare.
- Test more parameter combinations to see how fragile the "edge" is.
- Add a stop-loss.
