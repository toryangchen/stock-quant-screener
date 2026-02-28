from __future__ import annotations

import pandas as pd

from src.config import AppConfig


def filter_stock_pool(spot_df: pd.DataFrame, cfg: AppConfig) -> pd.DataFrame:
    df = spot_df.copy()

    if cfg.exclude_st:
        df = df[~df["name"].astype(str).str.contains("ST", na=False)]

    if cfg.mkt_cap_filter_enabled and "mktcap" in df.columns:
        mktcap = pd.to_numeric(df["mktcap"], errors="coerce")
        df = df[(mktcap >= cfg.mkt_cap_min) & (mktcap <= cfg.mkt_cap_max)]

    return df.head(cfg.scan_limit).reset_index(drop=True)
