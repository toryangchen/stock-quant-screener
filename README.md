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

## 运行

```bash
python -m src.main etf
python -m src.main breakout
python -m src.main all
```

可选参数：

```bash
python -m src.main all --output-dir ./outputs --scan-limit 300 --risk-per-trade 0.02 --sleep 0.1
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
