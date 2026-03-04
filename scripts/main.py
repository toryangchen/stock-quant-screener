from __future__ import annotations

import argparse
import logging
import os
import sys
from importlib import import_module
from pathlib import Path

from scripts.config import AppConfig, load_config
from scripts.output.logger import setup_logger


def _get_hs300_ret20(ds, logger: logging.Logger) -> float | None:
    import pandas as pd

    try:
        hs300 = ds.get_etf_daily("510300")
        if hs300 is None or hs300.empty or len(hs300) < 21:
            return None
        close = pd.to_numeric(hs300["close"], errors="coerce")
        close_t = float(close.iloc[-1])
        close_t_20 = float(close.iloc[-21])
        if close_t_20 <= 0:
            return None
        return close_t / close_t_20 - 1.0
    except Exception as exc:
        logger.warning("相对强度过滤跳过：无法获取沪深300近20日涨幅: %s", exc)
        return None


def apply_secondary_breakout_filter(ds, cfg: AppConfig, candidates, logger: logging.Logger):
    import pandas as pd

    df2 = candidates.copy()
    original_count = len(df2)
    if df2.empty:
        return df2

    df2["vol_ratio"] = pd.to_numeric(df2.get("vol_ratio"), errors="coerce")
    df2["entry_price"] = pd.to_numeric(df2.get("entry_price"), errors="coerce")
    df2["stop_price"] = pd.to_numeric(df2.get("stop_price"), errors="coerce")
    df2["risk_pct"] = pd.to_numeric(df2.get("risk_pct"), errors="coerce")
    df2["close"] = pd.to_numeric(df2.get("close"), errors="coerce")
    df2["ma20_price"] = pd.to_numeric(df2.get("ma20_price"), errors="coerce")

    # 1) 量能过滤
    df2 = df2[(df2["vol_ratio"] >= cfg.secondary_vol_min) & (df2["vol_ratio"] <= cfg.secondary_vol_max)]

    # 2) 止损空间过滤
    missing_risk = df2["risk_pct"].isna()
    if missing_risk.any():
        df2.loc[missing_risk, "risk_pct"] = (
            (df2.loc[missing_risk, "entry_price"] - df2.loc[missing_risk, "stop_price"])
            / df2.loc[missing_risk, "entry_price"]
        )
    df2 = df2[(df2["risk_pct"] >= cfg.secondary_risk_min) & (df2["risk_pct"] <= cfg.secondary_risk_max)]

    # 3) 涨幅过滤（如果有）
    if "pct_chg" in df2.columns:
        df2["pct_chg"] = pd.to_numeric(df2["pct_chg"], errors="coerce")
        df2 = df2[df2["pct_chg"] >= cfg.pct_chg_min]

    # 4) 市值过滤（如果有）
    if "mkt_cap" in df2.columns:
        df2["mkt_cap"] = pd.to_numeric(df2["mkt_cap"], errors="coerce")
        mkt_cap_valid = df2["mkt_cap"].notna() & (df2["mkt_cap"] >= 100e8) & (df2["mkt_cap"] <= 600e8)
        if cfg.secondary_mkt_cap_missing_policy == "exclude":
            df2 = df2[mkt_cap_valid]
        elif cfg.secondary_mkt_cap_missing_policy == "keep_with_penalty":
            df2 = df2[mkt_cap_valid | df2["mkt_cap"].isna()]
        else:
            df2 = df2[mkt_cap_valid | df2["mkt_cap"].isna()]

    # 5) 价格与乖离过滤
    df2 = df2[df2["close"] <= cfg.secondary_close_max]
    df2["ma20_gap"] = (df2["close"] - df2["ma20_price"]) / df2["ma20_price"]
    df2 = df2[df2["ma20_gap"] <= cfg.secondary_ma20_gap_max]

    # 6) 可选：相对强度（强于沪深300近20日）
    if cfg.secondary_require_relative_strength and "ret_20_stock" in df2.columns:
        df2["ret_20_stock"] = pd.to_numeric(df2["ret_20_stock"], errors="coerce")
        hs300_ret20 = _get_hs300_ret20(ds, logger)
        if hs300_ret20 is not None:
            df2 = df2[df2["ret_20_stock"] > hs300_ret20]

    # 7) 质量评分排序
    df2["score"] = (
        (df2["vol_ratio"] - cfg.vol_target).abs() * cfg.secondary_score_w1_vol
        + (df2["risk_pct"] - 0.06).abs() * cfg.secondary_score_w2_risk
        + df2["ma20_gap"] * cfg.secondary_score_w3_gap
    )
    if cfg.secondary_mkt_cap_missing_policy == "keep_with_penalty" and "mkt_cap" in df2.columns:
        df2.loc[df2["mkt_cap"].isna(), "score"] = (
            df2.loc[df2["mkt_cap"].isna(), "score"] + cfg.secondary_mkt_cap_missing_penalty
        )

    df2 = df2.sort_values(["score", "code"], ascending=[True, True]).reset_index(drop=True)
    if cfg.secondary_take_top_n > 0:
        df2 = df2.head(cfg.secondary_take_top_n).reset_index(drop=True)

    logger.info("二次筛选已执行(恒定触发): 初筛 %s 只 -> 二筛 %s 只", original_count, len(df2))
    return df2


def load_env_file(env_path: Path = Path(".env")) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A-share quant screener demo")
    parser.add_argument("command", choices=["etf", "breakout", "sync", "ingest", "all"])
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--scan-limit", type=int, default=None)
    parser.add_argument("--risk-per-trade", type=float, default=None)
    parser.add_argument("--sleep", type=float, default=None)
    return parser.parse_args()


def apply_overrides(cfg: AppConfig, args: argparse.Namespace) -> AppConfig:
    if args.output_dir:
        cfg.output_dir = Path(args.output_dir)
    if args.scan_limit is not None:
        cfg.scan_limit = args.scan_limit
    if args.risk_per_trade is not None:
        cfg.risk_per_trade_pct = args.risk_per_trade
    if args.sleep is not None:
        cfg.sleep_seconds = args.sleep
    return cfg


def run_etf_module(ds, cfg: AppConfig, logger: logging.Logger) -> None:
    run_etf_rotation = import_module("scripts.logic.etf_rotation").run_etf_rotation
    writer = import_module("scripts.output.writer")
    etf_df, decision = run_etf_rotation(ds=ds, cfg=cfg, logger=logger)
    writer.write_dataframe(
        etf_df,
        cfg.output_dir / "etf_rotation_rank.csv",
        cfg.output_dir / "etf_rotation_rank.xlsx",
        "Rank",
    )
    logger.info("ETF 轮动完成: %s, 输出 %s", decision, cfg.output_dir / "etf_rotation_rank.xlsx")


def run_breakout_module(
    ds,
    cfg: AppConfig,
    logger: logging.Logger,
    pause_note: str = "",
):
    filter_stock_pool = import_module("scripts.logic.filters").filter_stock_pool
    run_trend_breakout = import_module("scripts.logic.trend_breakout").run_trend_breakout
    writer = import_module("scripts.output.writer")
    history_store = import_module("scripts.output.mongo_history").MongoScreeningHistory()
    try:
        # 默认关闭筛选内自动同步，采集与筛选分离。
        auto_sync = os.getenv("BREAKOUT_AUTO_SYNC", "false").lower() in {"1", "true", "yes", "on"}
        if auto_sync and hasattr(ds, "sync_market_daily"):
            need_sync = True
            if hasattr(ds, "has_today_snapshot"):
                try:
                    need_sync = not bool(ds.has_today_snapshot())
                except Exception:
                    need_sync = True

            if need_sync:
                try:
                    sync_stats = ds.sync_market_daily()
                    logger.info(
                        "筛选前同步完成: total=%s, ok=%s, failed=%s",
                        sync_stats.get("total", 0),
                        sync_stats.get("ok", 0),
                        sync_stats.get("failed", 0),
                    )
                except Exception as exc:
                    logger.warning("筛选前同步失败，继续使用当前缓存数据: %s", exc)
            else:
                logger.info("检测到当日交易快照已存在，跳过全量同步")
        else:
            logger.info("筛选流程未启用自动同步，直接使用数据库/缓存数据")

        spot = ds.get_a_spot()
        pool = filter_stock_pool(spot, cfg)
        primary_candidates = run_trend_breakout(
            ds=ds, stock_pool_df=pool, cfg=cfg, logger=logger, pause_note=pause_note
        )
        candidates = apply_secondary_breakout_filter(ds, cfg, primary_candidates, logger)
    except Exception as exc:
        logger.warning("趋势突破股票池拉取失败，降级为空结果: %s", exc)
        import pandas as pd

        primary_candidates = pd.DataFrame(
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
        candidates = pd.DataFrame(
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
                "ma20_gap",
                "score",
                "entry_price",
                "stop_price",
                "suggested_shares",
                "suggested_position_value",
                "note",
            ]
        )

    run_date = cfg.run_date.strftime("%Y-%m-%d")
    saved_primary, saved_secondary = history_store.save_daily(
        run_date=run_date,
        primary_df=primary_candidates,
        secondary_df=candidates,
    )
    logger.info(
        "Mongo 筛选记录已保存(单表去重): date=%s, total=%s, secondary=%s",
        run_date,
        saved_primary,
        saved_secondary,
    )
    writer.write_dataframe(
        candidates,
        cfg.output_dir / "trend_breakout_candidates.csv",
        cfg.output_dir / "trend_breakout_candidates.xlsx",
        "Candidates",
    )
    logger.info("趋势突破完成: 候选 %s 只", len(candidates))
    return candidates


def run_sync_module(ds, logger: logging.Logger) -> None:
    if not hasattr(ds, "sync_market_daily"):
        logger.warning("当前 DataSource 不支持 sync 命令，已跳过")
        return
    stats = ds.sync_market_daily()
    logger.info(
        "日度全量同步完成: total=%s, ok=%s, failed=%s",
        stats.get("total", 0),
        stats.get("ok", 0),
        stats.get("failed", 0),
    )


def run_ingest_module(logger: logging.Logger) -> None:
    ingest = import_module("scripts.jobs.daily_market_ingest")
    result = ingest.run_daily_market_ingest(logger=logger)
    logger.info(
        "数据采集完成: trade_date=%s, list=%s, daily=%s, mktcap_filled=%s, mongo_upserts=%s, snapshot=%s",
        result.trade_date,
        result.stock_list_count,
        result.daily_rows,
        result.mktcap_filled,
        result.mongo_upserts,
        result.snapshot_file,
    )


def run_all(ds, cfg: AppConfig, logger: logging.Logger) -> None:
    performance = import_module("scripts.logic.performance")
    equity_curve = import_module("scripts.logic.equity_curve")
    writer = import_module("scripts.output.writer")

    run_etf_module(ds, cfg, logger)
    candidates = run_breakout_module(ds, cfg, logger, pause_note="")

    trades_path = cfg.output_dir / "trades.xlsx"
    performance.ensure_trades_template(trades_path)

    trades_df = performance.load_trades(trades_path)
    closed = performance.get_closed_trades(trades_df)
    report = performance.calc_performance_report(closed, cfg)

    eq_df, max_drawdown = equity_curve.build_equity_curve(closed, cfg.account_capital)
    report.max_drawdown = max_drawdown

    eq_df.to_csv(cfg.output_dir / "equity_curve.csv", index=False, encoding="utf-8-sig")
    equity_curve.save_equity_curve_png(eq_df, cfg.output_dir / "equity_curve.png")

    if report.trade_paused and not candidates.empty:
        candidates = candidates.copy()
        candidates["note"] = "暂停交易"
        writer.write_dataframe(
            candidates,
            cfg.output_dir / "trend_breakout_candidates.csv",
            cfg.output_dir / "trend_breakout_candidates.xlsx",
            "Candidates",
        )

    report_dict = report.to_dict()
    writer.write_report_excel(report_dict, cfg.output_dir / "report.xlsx")
    writer.write_report_json(report_dict, cfg.output_dir / "report.json")

    logger.info("绩效统计完成: paused=%s, max_drawdown=%.4f", report.trade_paused, report.max_drawdown)
    logger.info("all 流程完成, 输出目录: %s", cfg.output_dir)


def main() -> int:
    load_env_file(Path(".env"))
    logger = setup_logger()
    args = parse_args()

    try:
        cfg = apply_overrides(load_config(), args)
        import_module("scripts.output.writer").ensure_output_dir(cfg.output_dir)
    except Exception as exc:
        logger.error("配置或输出目录初始化失败: %s", exc)
        return 1

    if args.command == "ingest":
        try:
            run_ingest_module(logger)
            return 0
        except Exception as exc:
            logger.error("执行失败: %s", exc)
            return 3

    try:
        ts_token = os.getenv("TUSHARE_TOKEN", "").strip()
        if ts_token:
            try:
                ds = import_module("scripts.data_source.tushare_impl").TushareDataSource(token=ts_token)
                logger.info("DataSource 使用 Tushare(日线) + AkShare(ETF备用)")
            except Exception as exc:
                logger.warning("Tushare 初始化失败，回退 AkShare: %s", exc)
                ds = import_module("scripts.data_source.akshare_impl").AkShareDataSource()
                logger.info("DataSource 使用 AkShare")
        else:
            ds = import_module("scripts.data_source.akshare_impl").AkShareDataSource()
            logger.info("未检测到 TUSHARE_TOKEN，DataSource 使用 AkShare")
    except Exception as exc:
        logger.error("DataSource 初始化失败: %s", exc)
        return 2

    try:
        if args.command == "etf":
            run_etf_module(ds, cfg, logger)
        elif args.command == "breakout":
            run_breakout_module(ds, cfg, logger, pause_note="")
        elif args.command == "sync":
            run_sync_module(ds, logger)
        elif args.command == "ingest":
            run_ingest_module(logger)
        else:
            run_all(ds, cfg, logger)
        return 0
    except Exception as exc:
        logger.error("执行失败: %s", exc)
        return 3


if __name__ == "__main__":
    sys.exit(main())
