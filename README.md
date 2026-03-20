# Stock Quant Screener

面向 A 股小资金场景的筛选项目。当前分成两条独立流程：

- A 股日筛：拉全量股票日线、补 `mktcap`、做初筛和二筛
- ETF 周轮动：拉 ETF 历史数据、做轮动排序、落库历史结果

项目不做自动下单，当前职责是数据采集、规则筛选、结果落库和可视化跟踪。

## 目录

- `scripts/`: Python 命令行脚本
- `apps/api`: FastAPI mock 服务
- `apps/web`: React + TypeScript 跟踪页面
- `outputs/`: 导出文件、快照和日志
- `skills/`: OpenClaw/OpenAI Agent 用的自动化技能

## 环境准备

Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

前端:

```bash
cd apps/web
npm install
```

环境变量建议从 `.env.example` 复制：

```bash
cp .env.example .env
```

至少需要：

- `TUSHARE_TOKEN`
- `MONGO_URI`
- `MONGO_DB=quant_screener`

当前仓库默认使用 MongoDB，且已经约束：

- `market_cache` 只存 A 股股票，`_id` 必须是 6 位股票代码
- `etf_cache` 单独存 ETF 历史数据

## Mongo 表设计

`market_cache`

- 用途：A 股个股近 60 交易日数据缓存
- `_id`: 6 位股票代码
- 顶层字段：`exchange`, `name`, `mktcap`, `updated_at`, `data`
- `data`: 日线数组，字段通常为 `date`, `close`, `volume`, `low`, `pre_close`, `open`, `turnover`

`screening_history`

- 用途：A 股日筛历史结果
- `_id`: `[code].[run_date]`
- 顶层字段保留 `code`, `run_date`，并带初筛/二筛结果字段

`etf_cache`

- 用途：ETF 历史日线缓存
- `_id`: ETF 代码
- 顶层字段：`code`, `name`, `updated_at`, `data`

`etf_history`

- 用途：ETF 周轮动排序结果
- `_id`: `[code].[run_date]`
- 顶层字段保留 `code`, `run_date`, `decision`, `rank` 等结果字段

`analysis_stock`

- 用途：盘中观察股票历史记录
- `_id`: `[code].[run_date]`
- 顶层字段保留 `code`, `run_date`, `name`, `entry_price`, `pct_chg`, `source_file`

## A 股日筛流程

### 1. 拉当日全量股票日线

```bash
.venv/bin/python -m scripts.main ingest-daily
```

行为：

- 优先用 Tushare `daily(trade_date=YYYYMMDD)` 拉全量
- 失败时回退 AkShare 实时接口
- 先写本地快照：`outputs/snapshots/market_daily_YYYYMMDD.json`
- 再落库到 `market_cache`

### 2. 补 `mktcap`

```bash
.venv/bin/python -m scripts.main ingest-mktcap --trade-date 20260307
```

行为：

- 从本地快照读取股票列表
- 用 AkShare `stock_zh_scale_comparison_em` 逐只补 `mktcap`
- 北交所股票跳过
- 每拉一只就回写本地快照，最后再统一更新 `market_cache`

### 3. 执行日筛

```bash
.venv/bin/python -m scripts.main breakout
```

行为：

- 只从 `market_cache` 读取数据
- 不直接请求外部接口
- 执行初筛和二筛
- 落库到 `screening_history`
- 导出：
  - `outputs/trend_breakout_candidates.csv`
  - `outputs/trend_breakout_candidates.xlsx`

### 4. 一键日流程

```bash
.venv/bin/python -m scripts.main ingest
```

行为：

- 先执行 `ingest-daily`
- 仅当快照里存在“今日日期”的交易数据时，才继续：
  - `ingest-mktcap`
  - `breakout`
- 如果快照不是今日交易数据，则跳过后续筛选

## ETF 周轮动流程

### 1. 拉 ETF 历史数据

```bash
.venv/bin/python -m scripts.main ingest-etf
```

行为：

- 按 ETF 池逐只拉历史日线
- 落库到 `etf_cache`
- 当前 ETF 池定义在 [config.py](./scripts/config.py)

### 2. 执行 ETF 轮动排序

```bash
.venv/bin/python -m scripts.main etf-rotation
```

行为：

- 只从 `etf_cache` 读取数据
- 计算：
  - 近 20 日涨幅
  - 是否站上 20 日均线
- 按近 20 日涨幅排序
- 结果落库到 `etf_history`
- 导出：
  - `outputs/etf_rotation_rank.csv`
  - `outputs/etf_rotation_rank.xlsx`

说明：

- `etf` 与 `etf-rotation` 当前都走同一套 ETF 排序逻辑
- `all` 命令已删除，ETF 和个股筛选不再混跑

## 当前命令清单

```bash
.venv/bin/python -m scripts.main ingest-daily
.venv/bin/python -m scripts.main ingest-mktcap --trade-date 20260307
.venv/bin/python -m scripts.main ingest
.venv/bin/python -m scripts.main breakout
.venv/bin/python -m scripts.main ingest-etf
.venv/bin/python -m scripts.main etf-rotation
.venv/bin/python -m scripts.main etf
.venv/bin/python -m scripts.main import-analysis-stock --source-dir outputs/analyse-stock-by-date
```

常用参数：

```bash
.venv/bin/python -m scripts.main breakout --scan-limit 300 --sleep 0
.venv/bin/python -m scripts.main ingest-mktcap --trade-date 20260307
```

## Web 跟踪页面

后端（API，部署在你自己的服务器）：

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

建议在服务器 `.env` 里配置跨域白名单：

```bash
API_CORS_ORIGINS=http://localhost:5173,https://stock.toryang.cc
```

生产环境域名约定：

```text
Web: https://stock.toryang.cc
API: https://api.toryang.cc/stock
```

前端：

```bash
cd apps/web
npm run dev
```

默认前端请求：

- `http://127.0.0.1:8000`

可通过环境变量覆盖：

```bash
VITE_API_BASE=http://127.0.0.1:8000 npm run dev
```

生产环境改为 Cloudflare Pages 部署：

1. 保留 API 的服务器部署流程，继续使用 `.github/workflows/deploy-api.yml`
2. 在 Cloudflare Pages 里连接这个 GitHub 仓库
3. 根目录设置为 `apps/web`
4. 构建命令使用 `npm run build:cloudflare`
5. 输出目录设置为 `dist`
6. 在 Cloudflare Pages 里把自定义域名设置为 `stock.toryang.cc`

说明：

- 前端构建时固定使用根路径 `/`，适配自定义域名 `https://stock.toryang.cc`
- API 地址已固定注入为 `https://api.toryang.cc/stock`
- 你的反向代理需要把 `https://api.toryang.cc/stock/...` 转发到 FastAPI 实际服务

新增接口：

- `GET /analysis/dates`
- `GET /analysis?run_date=2026-03-10`

更多说明见 [apps/README.md](./apps/README.md)。

## OpenClaw 自动化

自动化 skill 在：

- [SKILL.md](./skills/openclaw-daily-quant-pipeline/SKILL.md)

当前支持：

- 服务器上的 OpenClaw 直接后台执行日流程脚本
- 1 小时后复检服务器本地快照 JSON
- 若快照异常，自动再重跑一次

## 当前约束

- `breakout` 不允许修改 `market_cache`
- `market_cache` 不允许写入非股票 `_id`
- ETF 数据不再混入 `market_cache`
- ETF 和个股流程拆开执行
