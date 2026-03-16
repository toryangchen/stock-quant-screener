# Web + API

## API (MongoDB)

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- health: `GET /health`
- dates: `GET /api/screening/dates`
- screening by date: `GET /api/screening?run_date=2026-02-03`
- analysis dates: `GET /api/analysis/dates`
- analysis by date: `GET /api/analysis?run_date=2026-03-10`

说明：

- API 直接读取 MongoDB 中的 `screening_history`、`analysis_stock` 和 `market_cache`
- `dates` 只返回有二筛结果的 `run_date`
- `screening` 返回真实入选股票，以及从 `run_date` 到最新缓存交易日的走势

## Web (React + TS)

```bash
cd apps/web
npm install
npm run dev
```

默认请求 `http://127.0.0.1:8000`。
如需修改：

```bash
VITE_API_BASE=http://127.0.0.1:8000 npm run dev
```
