from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def build_equity_curve(closed_trades: pd.DataFrame, initial_capital: float) -> tuple[pd.DataFrame, float]:
    if closed_trades.empty:
        eq = pd.DataFrame(
            [{"date": pd.Timestamp.today().normalize(), "equity": initial_capital, "drawdown": 0.0}]
        )
        return eq, 0.0

    pnl_by_date = (
        closed_trades.groupby(closed_trades["date_close"].dt.date)["pnl_amount"].sum().sort_index().reset_index()
    )
    pnl_by_date.columns = ["date", "pnl_amount"]

    equity = initial_capital
    rows: list[dict] = []
    peak = initial_capital
    max_drawdown = 0.0

    for _, row in pnl_by_date.iterrows():
        equity += float(row["pnl_amount"])
        peak = max(peak, equity)
        drawdown = (equity - peak) / peak if peak > 0 else 0.0
        max_drawdown = min(max_drawdown, drawdown)
        rows.append({"date": pd.to_datetime(row["date"]), "equity": equity, "drawdown": drawdown})

    eq_df = pd.DataFrame(rows)
    return eq_df, float(max_drawdown)


def save_equity_curve_png(eq_df: pd.DataFrame, png_path: Path) -> None:
    plt.figure(figsize=(10, 4.8))
    plt.plot(eq_df["date"], eq_df["equity"], linewidth=2)
    plt.title("Equity Curve")
    plt.xlabel("Date")
    plt.ylabel("Equity")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(png_path, dpi=150)
    plt.close()
