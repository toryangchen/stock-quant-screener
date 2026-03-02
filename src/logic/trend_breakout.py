from __future__ import annotations

import logging
import re
import time

import pandas as pd

from src.config import AppConfig
from src.data_source.base import DataSource
from src.logic.risk import calc_position_size


def _format_scan_code(code: str) -> str:
    text = str(code).strip().lower()
    if text.startswith(("sh", "sz", "bj")):
        return text
    m = re.search(r"(\d{6})$", text)
    return m.group(1) if m else text


def _code_variants(code: str) -> list[str]:
    variants = [code]
    m = re.search(r"(\d{6})$", code)
    if m:
        d = m.group(1)
        if d not in variants:
            variants.append(d)
    return variants


def run_trend_breakout(
    ds: DataSource,
    stock_pool_df: pd.DataFrame,
    cfg: AppConfig,
    logger: logging.Logger,
    pause_note: str = "",
) -> pd.DataFrame:
    candidates: list[dict] = []
    bulk_daily_map: dict[str, pd.DataFrame] = {}

    if hasattr(ds, "get_stock_daily_bulk"):
        try:
            code_list = [_format_scan_code(str(c)) for c in stock_pool_df["code"].tolist()]
            bulk_daily_map = ds.get_stock_daily_bulk(code_list, min_days=cfg.min_history_days)
            logger.info("批量日线拉取完成: 请求 %s 只, 命中 %s 只", len(code_list), len(bulk_daily_map))
        except Exception as exc:
            logger.warning("批量日线拉取失败，回退逐只拉取: %s", exc)
            bulk_daily_map = {}

    for _, row in stock_pool_df.iterrows():
        code = _format_scan_code(str(row["code"]))
        name = str(row["name"])

        try:
            df = None
            for key in _code_variants(code):
                if key in bulk_daily_map:
                    df = bulk_daily_map[key]
                    break
            if df is None:
                df = ds.get_stock_daily(code)
            if len(df) < cfg.min_history_days:
                continue

            recent = df.tail(cfg.min_history_days).reset_index(drop=True)
            today_close = float(recent["close"].iloc[-1])

            high_window = recent["close"].iloc[-cfg.lookback_high - 1 : -1]
            prev_high = high_window.max()
            is_60d_high = bool(today_close > prev_high)

            vol_window = recent["volume"].iloc[-cfg.vol_avg_window - 1 : -1]
            avg_vol = float(vol_window.mean())
            vol_ratio = float(recent["volume"].iloc[-1] / avg_vol) if avg_vol > 0 else float("nan")
            vol_ok = bool(pd.notna(vol_ratio) and vol_ratio >= cfg.vol_multiplier)

            if not (is_60d_high and vol_ok):
                if cfg.sleep_seconds > 0:
                    time.sleep(cfg.sleep_seconds)
                continue

            entry_price = today_close
            stop_price = entry_price * (1 - cfg.default_stop_loss_pct)
            sizing = calc_position_size(entry_price=entry_price, stop_price=stop_price, cfg=cfg)

            note = sizing.note
            if pause_note:
                note = pause_note

            candidates.append(
                {
                    "code": code,
                    "name": name,
                    "close": round(today_close, 3),
                    "is_60d_high": is_60d_high,
                    "vol_ratio": round(vol_ratio, 2) if pd.notna(vol_ratio) else None,
                    "entry_price": round(entry_price, 3),
                    "stop_price": round(stop_price, 3),
                    "suggested_shares": sizing.suggested_shares,
                    "suggested_position_value": round(sizing.suggested_position_value, 2),
                    "note": note,
                }
            )
        except Exception as exc:
            logger.warning("股票 %s(%s) 拉取失败，已跳过: %s", name, code, exc)

        if cfg.sleep_seconds > 0:
            time.sleep(cfg.sleep_seconds)

    if not candidates:
        return pd.DataFrame(
            columns=[
                "code",
                "name",
                "close",
                "is_60d_high",
                "vol_ratio",
                "entry_price",
                "stop_price",
                "suggested_shares",
                "suggested_position_value",
                "note",
            ]
        )

    out = pd.DataFrame(candidates)
    out = out.sort_values(["vol_ratio", "code"], ascending=[False, True]).reset_index(drop=True)
    return out
