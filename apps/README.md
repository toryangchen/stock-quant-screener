# Web + API

## API (mock)

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
