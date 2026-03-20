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

Cloudflare Pages 发布：

1. 在 Cloudflare Pages 中连接这个 GitHub 仓库
2. 根目录填写 `apps/web`
3. 构建命令填写 `npm run build:cloudflare`
4. 输出目录填写 `dist`
5. 绑定自定义域名 `stock.toryang.cc`

生产环境默认前端请求：

```text
https://api.toryang.cc/stock
```
