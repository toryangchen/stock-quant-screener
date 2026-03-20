# Web + API

## API (MongoDB)

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

跨域白名单可通过环境变量配置：

```bash
API_CORS_ORIGINS=http://localhost:5173,https://stock.toryang.cc
```

- health: `GET /health`
- dates: `GET /screening/dates`
- screening by date: `GET /screening?run_date=2026-02-03`
- analysis dates: `GET /analysis/dates`
- analysis by date: `GET /analysis?run_date=2026-03-10`

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

GitHub Pages 发布：

1. 在仓库 Pages 设置中选择 `GitHub Actions`
2. 在仓库 Pages 设置里配置自定义域名 `stock.toryang.cc`
3. 推送 `main` 后，`deploy-web.yml` 会自动发布到 `https://stock.toryang.cc`

生产环境默认前端请求：

```text
https://api.toryang.cc/stock
```
