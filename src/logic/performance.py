from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import AppConfig


TRADE_COLUMNS = [
    "trade_id",
    "date_open",
    "date_close",
    "symbol",
    "name",
    "side",
    "entry_price",
    "exit_price",
    "shares",
    "fees",
]

TRADE_COL_MAP = {
    "交易ID": "trade_id",
    "开仓日期": "date_open",
    "平仓日期": "date_close",
    "代码": "symbol",
    "名称": "name",
    "方向": "side",
    "开仓价": "entry_price",
    "平仓价": "exit_price",
    "股数": "shares",
    "手续费": "fees",
}


@dataclass
class PerformanceReport:
    total_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float | None = None
    expectancy: float = 0.0
    max_consecutive_losses: int = 0
    current_consecutive_losses: int = 0
    trade_paused: bool = False
    pause_until_date: str | None = None
    max_drawdown: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def ensure_trades_template(trades_path: Path) -> None:
    if trades_path.exists():
        return
    df = pd.DataFrame(columns=TRADE_COLUMNS)
    with pd.ExcelWriter(trades_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Trades")


def _normalize_trades_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    df = raw_df.rename(columns=TRADE_COL_MAP).copy()
    for col in TRADE_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    df = df[TRADE_COLUMNS]
    df["date_open"] = pd.to_datetime(df["date_open"], errors="coerce")
    df["date_close"] = pd.to_datetime(df["date_close"], errors="coerce")

    for col in ["entry_price", "exit_price", "shares", "fees"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["fees"] = df["fees"].fillna(0.0)
    return df


def load_trades(trades_path: Path) -> pd.DataFrame:
    raw = pd.read_excel(trades_path, sheet_name="Trades")
    return _normalize_trades_df(raw)


def get_closed_trades(trades_df: pd.DataFrame) -> pd.DataFrame:
    closed = trades_df[
        trades_df["date_close"].notna()
        & trades_df["exit_price"].notna()
        & trades_df["entry_price"].notna()
        & trades_df["shares"].notna()
    ].copy()

    if closed.empty:
        closed["pnl_amount"] = []
        closed["pnl_pct"] = []
        closed["is_win"] = []
        return closed

    closed["pnl_amount"] = (closed["exit_price"] - closed["entry_price"]) * closed["shares"] - closed["fees"]
    closed["pnl_pct"] = (closed["exit_price"] - closed["entry_price"]) / closed["entry_price"]
    closed["is_win"] = closed["pnl_amount"] > 0
    closed = closed.sort_values("date_close").reset_index(drop=True)
    return closed


def _calc_loss_streaks(pnls: list[float]) -> tuple[int, int]:
    max_streak = 0
    current = 0
    for pnl in pnls:
        if pnl < 0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak, current


def calc_performance_report(closed_trades: pd.DataFrame, cfg: AppConfig) -> PerformanceReport:
    report = PerformanceReport()
    if closed_trades.empty:
        return report

    pnls = closed_trades["pnl_amount"].tolist()
    wins = closed_trades[closed_trades["pnl_amount"] > 0]["pnl_amount"]
    losses = closed_trades[closed_trades["pnl_amount"] < 0]["pnl_amount"]

    total = len(closed_trades)
    win_rate = float(len(wins) / total) if total > 0 else 0.0
    avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
    avg_loss = float(losses.mean()) if len(losses) > 0 else 0.0

    profit_factor = None
    if len(losses) == 0 and len(wins) > 0:
        profit_factor = 999.0
    elif len(losses) > 0:
        profit_factor = float(wins.sum() / abs(losses.sum())) if abs(losses.sum()) > 0 else None

    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
    max_loss_streak, cur_loss_streak = _calc_loss_streaks(pnls)

    paused = cur_loss_streak >= cfg.max_consecutive_losses
    pause_until = None
    if paused:
        pause_until = (cfg.run_date + timedelta(days=cfg.pause_days_after_max_loss)).isoformat()

    report = PerformanceReport(
        total_trades=total,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=profit_factor,
        expectancy=expectancy,
        max_consecutive_losses=max_loss_streak,
        current_consecutive_losses=cur_loss_streak,
        trade_paused=paused,
        pause_until_date=pause_until,
    )
    return report
