import os
import sys

import matplotlib
matplotlib.use("Agg")  # no windows during tests

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest as bt  # noqa: E402


def prices(values):
    idx = pd.bdate_range("2020-01-01", periods=len(values))
    return pd.DataFrame({"Close": np.asarray(values, dtype=float)}, index=idx)


def random_walk(n=400, seed=0):
    rng = np.random.default_rng(seed)
    return prices(100 * np.cumprod(1 + rng.normal(0.0005, 0.02, n)))


# ── no lookahead ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("stop,take", [(0, 0), (0.05, 0), (0, 0.10), (0.05, 0.10)])
def test_positions_never_depend_on_future_prices(stop, take):
    base = random_walk()
    full, _ = bt.run_backtest(base.copy(), 10, 30, 0.001, stop, take)
    pos = full["position"].values
    holding = [i for i in range(1, len(pos)) if pos[i] and pos[i - 1]]
    assert len(holding) > 20
    for cut in holding[::max(1, len(holding) // 8)]:
        for jump in (0.3, 3.0):                      # a crash or a spike from day `cut` on
            changed = base.copy()
            changed.iloc[cut:, 0] *= jump
            other, _ = bt.run_backtest(changed, 10, 30, 0.001, stop, take)
            # Positions up to and including day `cut` may only use closes before it.
            np.testing.assert_array_equal(pos[:cut + 1], other["position"].values[:cut + 1])


def test_stop_loss_cannot_dodge_the_drop_that_triggers_it():
    # Rise to switch the strategy on, then one big drop.
    up = list(np.linspace(100, 160, 60))
    p = prices(up + [100.0] + [100.0] * 5)
    d, _ = bt.run_backtest(p, 5, 20, 0.0, stop_loss_pct=0.05)
    crash_day = 60
    assert d["position"].iloc[crash_day] == 1          # still holding through the crash
    assert d["strat_ret"].iloc[crash_day] < -0.3        # and takes the loss
    assert d["position"].iloc[crash_day + 1] == 0      # stop fires the next day


def test_signal_is_acted_on_the_day_after_the_crossover():
    p = prices([10] * 30 + list(np.linspace(10, 30, 30)))
    d, _ = bt.run_backtest(p, 3, 10, 0.0)
    cross = int(np.argmax((d["ma_short"] > d["ma_long"]).values))
    assert d["position"].iloc[cross] == 0
    assert d["position"].iloc[cross + 1] == 1


# ── returns, costs and trades ────────────────────────────────────────────────

def test_flat_prices_never_trade():
    d, n = bt.run_backtest(prices([50] * 100), 5, 20, 0.001)
    assert n == 0
    assert d["strat_equity"].iloc[-1] == pytest.approx(1.0)


def test_buy_and_hold_equity_matches_price_change():
    p = random_walk()
    d, _ = bt.run_backtest(p.copy(), 10, 30, 0.0)
    assert d["hold_equity"].iloc[-1] == pytest.approx(p["Close"].iloc[-1] / p["Close"].iloc[0])


def test_costs_are_charged_per_trade():
    p = random_walk(seed=3)
    free, n = bt.run_backtest(p.copy(), 5, 20, 0.0)
    paid, n2 = bt.run_backtest(p.copy(), 5, 20, 0.01)
    assert n == n2 > 0
    assert paid["strat_equity"].iloc[-1] < free["strat_equity"].iloc[-1]
    np.testing.assert_allclose(free["strat_ret"] - paid["strat_ret"],
                               paid["position"].diff().abs().fillna(0) * 0.01)


def test_trade_breakdown_matches_equity_curve():
    """With no fees, compounding the round-trips must equal the final equity."""
    p = random_walk(seed=7)
    d, _ = bt.run_backtest(p.copy(), 5, 20, 0.0)
    pos, close = d["position"].values, d["Close"].values
    growth, entry = 1.0, None
    for i in range(1, len(pos)):
        if pos[i] and not pos[i - 1]:
            entry = close[i - 1]
        elif not pos[i] and pos[i - 1]:
            growth *= close[i - 1] / entry
            entry = None
    if entry is not None:
        growth *= close[-1] / entry
    assert d["strat_equity"].iloc[-1] == pytest.approx(growth)
    wins, losses = bt.trade_breakdown(d, 0.0)
    assert wins + losses > 0


def test_take_profit_exits_after_target_reached():
    up = list(np.linspace(100, 101, 25)) + list(np.linspace(101, 140, 40))
    d, _ = bt.run_backtest(prices(up), 3, 10, 0.0, take_profit_pct=0.10)
    entered = int(np.argmax(d["position"].values))
    entry = d["Close"].iloc[entered - 1]
    first_exit = entered + int(np.argmax(d["position"].values[entered:] == 0))
    assert d["Close"].iloc[first_exit - 1] / entry - 1 >= 0.10


def test_data_shorter_than_long_window():
    d, n = bt.run_backtest(prices(range(1, 20)), 5, 50, 0.001)
    assert n == 0
    assert d["strat_equity"].iloc[-1] == pytest.approx(1.0)


# ── summary numbers ──────────────────────────────────────────────────────────

def test_summarize_known_values():
    equity = pd.Series([1.0, 1.2, 0.9, 1.5])
    total, sharpe, dd = bt.summarize(equity, equity.pct_change().fillna(0))
    assert total == pytest.approx(0.5)
    assert dd == pytest.approx(0.9 / 1.2 - 1)
    assert sharpe > 0


def test_summarize_with_zero_volatility():
    flat = pd.Series([1.0] * 10)
    assert bt.summarize(flat, flat.pct_change().fillna(0)) == (0.0, 0, 0.0)


# ── downloading ──────────────────────────────────────────────────────────────

def test_empty_download_gives_a_helpful_error(monkeypatch):
    monkeypatch.setattr(bt.yf, "download", lambda *a, **k: pd.DataFrame())
    with pytest.raises(SystemExit, match="No data came back for 'FAKE'"):
        bt.get_prices("FAKE", "2020-01-01", "2021-01-01")


def test_two_level_columns_are_flattened(monkeypatch):
    idx = pd.bdate_range("2020-01-01", periods=3)
    cols = pd.MultiIndex.from_tuples([("Close", "MSFT"), ("Open", "MSFT")])
    raw = pd.DataFrame([[1, 1], [2, 2], [3, 3]], index=idx, columns=cols)
    monkeypatch.setattr(bt.yf, "download", lambda *a, **k: raw)
    out = bt.get_prices("MSFT", "2020-01-01", "2021-01-01")
    assert list(out.columns) == ["Close"]
    assert out["Close"].tolist() == [1, 2, 3]


# ── command line ─────────────────────────────────────────────────────────────

@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(bt, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(bt, "get_prices", lambda t, s, e: random_walk(seed=len(t)))
    monkeypatch.setattr(bt, "open_file", lambda path: None)
    return tmp_path


@pytest.fixture
def opened(offline, monkeypatch):
    """Records the charts main() would have opened, instead of opening them."""
    paths = []
    monkeypatch.setattr(bt, "open_file", paths.append)
    return paths


@pytest.mark.parametrize("args", [
    ["--short", "50", "--long", "20"],
    ["--short", "0"],
    ["--cost", "-0.1"],
    ["--stop-loss", "-1"],
    ["--start", "2024-01-01", "--end", "2020-01-01"],
    ["--mode", "banana"],
])
def test_bad_settings_are_rejected(offline, args, capsys):
    with pytest.raises(SystemExit) as e:
        bt.main(args)
    assert e.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_single_mode_prints_results_and_saves_chart(offline, opened, capsys):
    bt.main(["--mode", "single", "--short", "10", "--long", "30"])
    out = capsys.readouterr().out
    assert "Total return" in out and "Win rate" in out
    assert (offline / "results.png").exists()
    assert opened == [str(offline / "results.png")]


def test_sweep_mode_ranks_combos_and_saves_heatmap(offline, opened, capsys):
    bt.main(["--mode", "sweep"])
    out = capsys.readouterr().out
    assert "Parameter sweep" in out and "Best combo" in out
    assert (offline / "sweep.png").exists()
    assert opened == [str(offline / "sweep.png")]


def test_no_open_flag_skips_opening_chart(opened):
    bt.main(["--mode", "sweep", "--no-open"])
    assert opened == []


def test_sweep_with_no_valid_combos(offline, capsys):
    bt.run_sweep(random_walk(), [50, 100], [10, 20], 0.001, "X", 0, 0, "a", "b")
    assert "No valid combos" in capsys.readouterr().out


def test_multi_stock_mode_skips_missing_tickers(offline, monkeypatch, capsys):
    def fake(t, s, e):
        if t == "NVDA":
            raise SystemExit("no data")
        return random_walk(seed=len(t))
    monkeypatch.setattr(bt, "get_prices", fake)
    bt.main(["--mode", "multi_stock"])
    out = capsys.readouterr().out
    assert "NVDA — no data" in out
    assert "of 3 stocks beat buy & hold" in out


def test_single_mode_warns_when_not_enough_data(offline, monkeypatch, capsys):
    monkeypatch.setattr(bt, "get_prices", lambda t, s, e: prices(range(1, 30)))
    bt.main(["--mode", "single", "--short", "5", "--long", "50"])
    assert "will never trade" in capsys.readouterr().out
