from __future__ import annotations

import logging

import pandas as pd

from src.config import AppConfig
from src.data_source.base import DataSource


def run_etf_rotation(ds: DataSource, cfg: AppConfig, logger: logging.Logger) -> tuple[pd.DataFrame, str]:
    rows: list[dict] = []

    for item in cfg.etf_pool:
        name = item["name"]
        code = item["code"]
        try:
            df = ds.get_etf_daily(code)
            if len(df) < cfg.etf_history_min_days:
                logger.warning("ETF %s(%s) 数据不足 %s 条，跳过", name, code, cfg.etf_history_min_days)
                continue

            tmp = df.copy()
            tmp["retN"] = tmp["close"] / tmp["close"].shift(cfg.etf_ret_window) - 1
            tmp["maN"] = tmp["close"].rolling(cfg.etf_ma_window).mean()
            tmp["above_ma"] = tmp["close"] > tmp["maN"]
            last = tmp.iloc[-1]
            if pd.isna(last["retN"]) or pd.isna(last["maN"]):
                logger.warning("ETF %s(%s) 指标不足，跳过", name, code)
                continue

            rows.append(
                {
                    "name": name,
                    "code": code,
                    "close": float(last["close"]),
                    "retN": float(last["retN"]),
                    "retN_pct": round(float(last["retN"]) * 100, 2),
                    "maN": float(last["maN"]),
                    "above_ma": bool(last["above_ma"]),
                }
            )
        except Exception as exc:
            logger.warning("ETF %s(%s) 拉取失败，已跳过: %s", name, code, exc)

    rank_df = pd.DataFrame(rows)
    if rank_df.empty:
        return rank_df, "CASH"

    rank_df = rank_df.sort_values("retN", ascending=False).reset_index(drop=True)
    rank_df["rank"] = rank_df.index + 1

    top = rank_df.iloc[0]
    if bool(top["above_ma"]):
        decision = f"BUY:{top['name']}({top['code']})"
    else:
        decision = "CASH"
    rank_df["decision"] = decision

    return rank_df, decision
