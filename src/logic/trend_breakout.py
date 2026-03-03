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
    use_bulk_mode = False
    skipped_missing_in_bulk = 0

    if hasattr(ds, "get_stock_daily_bulk"):
        try:
            code_list = [_format_scan_code(str(c)) for c in stock_pool_df["code"].tolist()]
            bulk_daily_map = ds.get_stock_daily_bulk(code_list, min_days=cfg.min_history_days)
            use_bulk_mode = True
            logger.info("批量日线拉取完成: 请求 %s 只, 命中 %s 只", len(code_list), len(bulk_daily_map))
        except Exception as exc:
            logger.warning("批量日线拉取失败，回退逐只拉取: %s", exc)
            bulk_daily_map = {}
            use_bulk_mode = False

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
                if use_bulk_mode:
                    skipped_missing_in_bulk += 1
                    continue
                df = ds.get_stock_daily(code)
            if len(df) < cfg.min_history_days:
                continue

            recent = df.tail(cfg.min_history_days).reset_index(drop=True)
            history = recent.iloc[:-1]
            if len(history) < max(cfg.vol_avg_window, 20):
                continue

            today_close = float(recent["close"].iloc[-1])
            prev_close = float(recent["close"].iloc[-2]) if len(recent) >= 2 else float("nan")
            pct_chg = (today_close - prev_close) / prev_close if prev_close > 0 else float("nan")
            close_t_20 = float(recent["close"].iloc[-21]) if len(recent) >= 21 else float("nan")
            ret_20_stock = (today_close / close_t_20 - 1.0) if close_t_20 > 0 else float("nan")
            low_t = pd.to_numeric(recent.get("low", pd.Series([pd.NA])).iloc[-1], errors="coerce")

            ma20_price = float(history["close"].tail(20).mean())
            ma10_price = float(history["close"].tail(10).mean())
            ma5_price = float(history["close"].tail(5).mean())
            above_ma20 = bool(pd.notna(ma20_price) and today_close > ma20_price)
            if not above_ma20:
                continue

            if cfg.require_ma_bullish_stack and not (ma5_price > ma10_price > ma20_price):
                continue

            high_window = recent["close"].iloc[-cfg.lookback_high - 1 : -1]
            prev_high = high_window.max()
            is_60d_high = bool(today_close > prev_high)

            vol_window = recent["volume"].iloc[-cfg.vol_avg_window - 1 : -1]
            avg_vol = float(vol_window.mean())
            vol_ratio = float(recent["volume"].iloc[-1] / avg_vol) if avg_vol > 0 else float("nan")
            vol_ok = bool(pd.notna(vol_ratio) and vol_ratio >= cfg.vol_multiplier)
            pct_chg_ok = bool(pd.notna(pct_chg) and pct_chg >= cfg.pct_chg_min)

            if not (is_60d_high and vol_ok and pct_chg_ok):
                if cfg.sleep_seconds > 0:
                    time.sleep(cfg.sleep_seconds)
                continue

            entry_price = today_close
            stop_candidates = []
            if pd.notna(low_t):
                stop_candidates.append(float(low_t))
            if pd.notna(ma10_price):
                stop_candidates.append(float(ma10_price))
            if not stop_candidates:
                continue

            stop_price = min(stop_candidates)
            if stop_price >= entry_price:
                continue

            risk_pct = (entry_price - stop_price) / entry_price
            sizing = calc_position_size(entry_price=entry_price, stop_price=stop_price, cfg=cfg)

            note = sizing.note
            if pause_note:
                note = pause_note

            mkt_cap = row.get("mktcap") if hasattr(row, "get") else None
            mkt_cap_value = pd.to_numeric(mkt_cap, errors="coerce")

            candidates.append(
                {
                    "code": code,
                    "name": name,
                    "close": round(today_close, 3),
                    "is_60d_high": is_60d_high,
                    "vol_ratio": round(vol_ratio, 2) if pd.notna(vol_ratio) else None,
                    "vol_score": round(abs(vol_ratio - cfg.vol_target), 4) if pd.notna(vol_ratio) else None,
                    "pct_chg": round(float(pct_chg), 4) if pd.notna(pct_chg) else None,
                    "ret_20_stock": round(float(ret_20_stock), 4) if pd.notna(ret_20_stock) else None,
                    "mkt_cap": float(mkt_cap_value) if pd.notna(mkt_cap_value) else None,
                    "ma20_price": round(ma20_price, 3) if pd.notna(ma20_price) else None,
                    "ma10_price": round(ma10_price, 3) if pd.notna(ma10_price) else None,
                    "low_t": round(float(low_t), 3) if pd.notna(low_t) else None,
                    "risk_pct": round(risk_pct, 6),
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

    if use_bulk_mode and skipped_missing_in_bulk > 0:
        logger.info("批量模式跳过未命中股票: %s 只", skipped_missing_in_bulk)

    if not candidates:
        return pd.DataFrame(
            columns=[
                "code",
                "name",
                "close",
                "is_60d_high",
                "vol_ratio",
                "vol_score",
                "pct_chg",
                "ret_20_stock",
                "mkt_cap",
                "ma20_price",
                "ma10_price",
                "low_t",
                "risk_pct",
                "entry_price",
                "stop_price",
                "suggested_shares",
                "suggested_position_value",
                "note",
            ]
        )

    out = pd.DataFrame(candidates)
    out = out.sort_values(["vol_score", "code"], ascending=[True, True]).reset_index(drop=True)
    return out
