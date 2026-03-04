from __future__ import annotations

import math
from dataclasses import dataclass

from scripts.config import AppConfig


@dataclass
class PositionSizingResult:
    risk_budget: float
    risk_per_share: float
    suggested_shares: int
    suggested_position_value: float
    note: str = ""


def calc_position_size(entry_price: float, stop_price: float, cfg: AppConfig) -> PositionSizingResult:
    risk_budget = cfg.account_capital * cfg.risk_per_trade_pct
    risk_per_share = float(entry_price - stop_price)

    if risk_per_share <= 0:
        return PositionSizingResult(
            risk_budget=risk_budget,
            risk_per_share=risk_per_share,
            suggested_shares=0,
            suggested_position_value=0.0,
            note="无效止损",
        )

    raw_shares = math.floor(risk_budget / risk_per_share)
    suggested_shares = math.floor(raw_shares / cfg.round_lot) * cfg.round_lot
    suggested_position_value = suggested_shares * entry_price

    return PositionSizingResult(
        risk_budget=risk_budget,
        risk_per_share=risk_per_share,
        suggested_shares=max(0, suggested_shares),
        suggested_position_value=max(0.0, suggested_position_value),
    )
