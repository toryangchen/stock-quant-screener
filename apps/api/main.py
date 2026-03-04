from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from random import Random

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware


@dataclass(frozen=True)
class StockMeta:
    code: str
    name: str


STOCK_POOL = [
    StockMeta("000001.SZ", "平安银行"),
    StockMeta("000333.SZ", "美的集团"),
    StockMeta("000651.SZ", "格力电器"),
    StockMeta("000858.SZ", "五粮液"),
    StockMeta("002594.SZ", "比亚迪"),
    StockMeta("002475.SZ", "立讯精密"),
    StockMeta("300750.SZ", "宁德时代"),
    StockMeta("300308.SZ", "中际旭创"),
    StockMeta("300059.SZ", "东方财富"),
    StockMeta("600036.SH", "招商银行"),
    StockMeta("600519.SH", "贵州茅台"),
    StockMeta("600900.SH", "长江电力"),
    StockMeta("601318.SH", "中国平安"),
    StockMeta("601398.SH", "工商银行"),
    StockMeta("601899.SH", "紫金矿业"),
    StockMeta("688111.SH", "金山办公"),
]

app = FastAPI(title="Quant Screener Mock API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_seed(*parts: str) -> int:
    s = "|".join(parts)
    return int(sha256(s.encode("utf-8")).hexdigest()[:12], 16)


def _trading_dates(start: date, end: date) -> list[date]:
    out: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def _available_dates() -> list[str]:
    start = date(2026, 2, 1)
    today = datetime.now().date()
    return [d.strftime("%Y-%m-%d") for d in _trading_dates(start, today)]


def _pick_for_date(run_date: str) -> list[StockMeta]:
    rng = Random(_to_seed("pick", run_date))
    k = min(8, len(STOCK_POOL))
    picks = rng.sample(STOCK_POOL, k=k)
    picks.sort(key=lambda x: x.code)
    return picks


def _build_trend(run_date: str, code: str, base_price: float) -> list[dict]:
    start = datetime.strptime(run_date, "%Y-%m-%d").date()
    end = datetime.now().date()
    dates = _trading_dates(start, end)
    rng = Random(_to_seed("trend", run_date, code))

    price = base_price
    points: list[dict] = []
    for d in dates:
        drift = rng.uniform(-0.03, 0.035)
        price = max(0.5, price * (1.0 + drift))
        points.append({"date": d.strftime("%Y-%m-%d"), "close": round(price, 2)})
    return points


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/screening/dates")
def screening_dates() -> dict:
    dates = _available_dates()
    return {"dates": dates}


@app.get("/api/screening")
def screening_by_date(
    run_date: str = Query(..., description="YYYY-MM-DD"),
) -> dict:
    dates = set(_available_dates())
    if run_date not in dates:
        raise HTTPException(status_code=404, detail=f"date not found: {run_date}")

    picks = _pick_for_date(run_date)
    stocks = []
    trends = []

    for stock in picks:
        seed = _to_seed("entry", run_date, stock.code)
        rng = Random(seed)
        entry = round(rng.uniform(10, 280), 2)
        series = _build_trend(run_date, stock.code, entry)
        latest = series[-1]["close"] if series else entry
        ret = (latest - entry) / entry if entry > 0 else 0.0

        stocks.append(
            {
                "code": stock.code,
                "name": stock.name,
                "entry_price": entry,
                "latest_price": latest,
                "return_pct": round(ret * 100, 2),
            }
        )
        trends.append(
            {
                "code": stock.code,
                "name": stock.name,
                "points": series,
            }
        )

    stocks.sort(key=lambda x: x["return_pct"], reverse=True)

    return {
        "date": run_date,
        "today": datetime.now().strftime("%Y-%m-%d"),
        "stocks": stocks,
        "trends": trends,
    }
