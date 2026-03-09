from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class AppConfig:
    run_date: date = field(default_factory=date.today)
    output_dir: Path = Path("outputs")

    etf_pool: list[dict[str, str]] = field(
        default_factory=lambda: [
            {"name": "沪深300", "code": "510300"},
            {"name": "创业板", "code": "159915"},
            {"name": "科创50", "code": "588000"},
            {"name": "券商", "code": "512000"},
            {"name": "半导体", "code": "512760"},
            {"name": "军工", "code": "512660"},
        ]
    )
    etf_ret_window: int = 20
    etf_ma_window: int = 20
    etf_history_min_days: int = 120

    lookback_high: int = 60
    vol_avg_window: int = 20
    vol_multiplier: float = 1.8
    vol_target: float = 3.0
    min_history_days: int = 60
    pct_chg_min: float = 0.04
    require_ma_bullish_stack: bool = False
    exclude_st: bool = True

    mkt_cap_filter_enabled: bool = False
    mkt_cap_min: float = 100e8
    mkt_cap_max: float = 800e8

    scan_limit: int = 0
    sleep_seconds: float = 0.0

    secondary_vol_min: float = 2.0
    secondary_vol_max: float = 6.0
    secondary_risk_min: float = 0.04
    secondary_risk_max: float = 0.08
    secondary_close_max: float = 60.0
    secondary_ma20_gap_max: float = 0.10
    secondary_take_top_n: int = 0
    secondary_score_w1_vol: float = 1.0
    secondary_score_w2_risk: float = 20.0
    secondary_score_w3_gap: float = 10.0
    secondary_require_relative_strength: bool = False
    secondary_mkt_cap_missing_policy: str = "exclude"
    secondary_mkt_cap_missing_penalty: float = 1.0

    account_capital: float = 20000
    risk_per_trade_pct: float = 0.02
    default_stop_loss_pct: float = 0.08
    round_lot: int = 100

    max_consecutive_losses: int = 3
    pause_days_after_max_loss: int = 5


def load_config() -> AppConfig:
    return AppConfig()
