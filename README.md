# Quant Screener Demo

面向 A 股小资金场景的命令行量化筛选 Demo（仅筛选与执行辅助，不含自动下单）。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果你有 Tushare Pro token（推荐），可放到本地 `.env`（已被 gitignore）：

```bash
cp .env.example .env
# 编辑 .env 填入真实 token
```

程序启动时会自动读取 `.env`，并优先使用 Tushare 的 A 股日线；ETF 数据仍由 AkShare 兜底。
程序内置 Tushare 限流（默认每分钟 50 次），可通过 `TUSHARE_RATE_LIMIT_PER_MINUTE` 调整。
程序支持 MongoDB 本地缓存（默认开启）：请求前先查缓存，命中则不再请求远端接口。

## 数据采集与筛选分离

- 数据采集：`python -m scripts.main ingest`
- 股票筛选：`python -m scripts.main breakout`

`ingest` 流程：

1. 用 Tushare（失败则回退 AkShare）拉当日全量日线；
2. 基于当日日线股票池，用 AkShare 逐只补充：`mktcap`；
4. 先写本地快照（`SNAPSHOT_DIR`），全部完成后再批量上传 Mongo。

说明：`breakout` 默认不自动在线同步（`BREAKOUT_AUTO_SYNC=false`），只使用数据库/缓存数据；如需恢复旧行为可设为 `true`。

## 可视化跟踪页面（新增）

- 前端：`apps/web`（React + TypeScript）
- 后端：`apps/api`（Python FastAPI，当前为 mock 接口）

启动方式见 [`apps/README.md`](/Users/yang/Documents/stock-quant-screener/apps/README.md)。

## 运行

```bash
python -m scripts.main etf
python -m scripts.main breakout
python -m scripts.main ingest-daily
python -m scripts.main ingest-mktcap --trade-date 20260305
python -m scripts.main ingest
python -m scripts.main all
```

可选参数：

```bash
python -m scripts.main all --output-dir ./outputs --scan-limit 300 --risk-per-trade 0.02 --sleep 0.1
```

## 输出文件

- `outputs/etf_rotation_rank.xlsx`
- `outputs/etf_rotation_rank.csv`
- `outputs/trend_breakout_candidates.xlsx`
- `outputs/trend_breakout_candidates.csv`
- `outputs/trades.xlsx`（首次自动生成模板）
- `outputs/report.xlsx`
- `outputs/report.json`
- `outputs/equity_curve.csv`
- `outputs/equity_curve.png`
