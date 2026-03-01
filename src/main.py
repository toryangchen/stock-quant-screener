from __future__ import annotations

import argparse
import logging
import os
import sys
from importlib import import_module
from pathlib import Path

from src.config import AppConfig, load_config
from src.output.logger import setup_logger


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
    parser.add_argument("command", choices=["etf", "breakout", "all"])
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
    run_etf_rotation = import_module("src.logic.etf_rotation").run_etf_rotation
    writer = import_module("src.output.writer")
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
    filter_stock_pool = import_module("src.logic.filters").filter_stock_pool
    run_trend_breakout = import_module("src.logic.trend_breakout").run_trend_breakout
    writer = import_module("src.output.writer")
    try:
        spot = ds.get_a_spot()
        pool = filter_stock_pool(spot, cfg)
        candidates = run_trend_breakout(
            ds=ds, stock_pool_df=pool, cfg=cfg, logger=logger, pause_note=pause_note
        )
    except Exception as exc:
        logger.warning("趋势突破股票池拉取失败，降级为空结果: %s", exc)
        import pandas as pd

        candidates = pd.DataFrame(
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
    writer.write_dataframe(
        candidates,
        cfg.output_dir / "trend_breakout_candidates.csv",
        cfg.output_dir / "trend_breakout_candidates.xlsx",
        "Candidates",
    )
    logger.info("趋势突破完成: 候选 %s 只", len(candidates))
    return candidates


def run_all(ds, cfg: AppConfig, logger: logging.Logger) -> None:
    performance = import_module("src.logic.performance")
    equity_curve = import_module("src.logic.equity_curve")
    writer = import_module("src.output.writer")

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
        import_module("src.output.writer").ensure_output_dir(cfg.output_dir)
    except Exception as exc:
        logger.error("配置或输出目录初始化失败: %s", exc)
        return 1

    try:
        ts_token = os.getenv("TUSHARE_TOKEN", "").strip()
        if ts_token:
            try:
                ds = import_module("src.data_source.tushare_impl").TushareDataSource(token=ts_token)
                logger.info("DataSource 使用 Tushare(日线) + AkShare(ETF备用)")
            except Exception as exc:
                logger.warning("Tushare 初始化失败，回退 AkShare: %s", exc)
                ds = import_module("src.data_source.akshare_impl").AkShareDataSource()
                logger.info("DataSource 使用 AkShare")
        else:
            ds = import_module("src.data_source.akshare_impl").AkShareDataSource()
            logger.info("未检测到 TUSHARE_TOKEN，DataSource 使用 AkShare")
    except Exception as exc:
        logger.error("DataSource 初始化失败: %s", exc)
        return 2

    try:
        if args.command == "etf":
            run_etf_module(ds, cfg, logger)
        elif args.command == "breakout":
            run_breakout_module(ds, cfg, logger, pause_note="")
        else:
            run_all(ds, cfg, logger)
        return 0
    except Exception as exc:
        logger.error("执行失败: %s", exc)
        return 3


if __name__ == "__main__":
    sys.exit(main())
