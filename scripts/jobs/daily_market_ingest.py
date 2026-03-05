from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from pymongo import MongoClient, UpdateOne


@dataclass
class IngestResult:
    trade_date: str
    stock_list_count: int
    daily_rows: int
    mktcap_filled: int
    mongo_upserts: int
    snapshot_file: str


def _load_env_file(env_path: Path = Path(".env")) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"").strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _norm_code(code: str) -> str:
    s = str(code).strip().upper()
    m = re.search(r"(\d{6})", s)
    return m.group(1) if m else s


def _to_em_symbol(code6: str) -> str:
    d = _norm_code(code6)
    if d.startswith(("6", "5", "9")):
        return f"SH{d}"
    if d.startswith("8"):
        return f"BJ{d}"
    return f"SZ{d}"


def _fetch_daily_tushare(trade_date: str, logger: logging.Logger) -> pd.DataFrame:
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("缺少 TUSHARE_TOKEN")

    import tushare as ts  # type: ignore

    ts.set_token(token)
    pro = ts.pro_api(token)

    daily = pro.daily(trade_date=trade_date)
    if daily is None or daily.empty:
        raise RuntimeError(f"Tushare daily({trade_date}) 返回空")

    need_daily = ["ts_code", "trade_date", "close", "vol", "low", "pre_close", "open", "amount"]
    for col in need_daily:
        if col not in daily.columns:
            raise ValueError(f"Tushare daily 缺少字段: {col}")

    daily = daily[need_daily].copy()
    daily["code"] = daily["ts_code"].astype(str).str.split(".").str[0].map(_norm_code)
    daily = daily.rename(columns={"vol": "volume", "amount": "turnover"})

    # 不使用 daily_basic（当前权限不可用）。
    out = daily.copy()
    out["date"] = pd.to_datetime(out["trade_date"], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")

    numeric_cols = ["close", "volume", "low", "pre_close", "open", "turnover"]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    # Tushare daily.amount 单位是千元，这里统一转成元，和 AkShare 保持一致。
    out["turnover"] = out["turnover"] * 1000.0

    out = out[
        [
            "code",
            "date",
            "close",
            "volume",
            "low",
            "pre_close",
            "open",
            "turnover",
        ]
    ]
    out = out.dropna(subset=["code", "date", "close", "volume", "low"]).reset_index(drop=True)
    logger.info("Tushare 日线拉取完成: %s", len(out))
    return out


def _fetch_daily_akshare(logger: logging.Logger) -> pd.DataFrame:
    import akshare as ak  # type: ignore

    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        raise RuntimeError("AkShare stock_zh_a_spot_em 返回空")

    for col in ["代码", "最新价", "成交量", "最低", "昨收", "今开", "成交额"]:
        if col not in df.columns:
            raise ValueError(f"AkShare 实时接口缺少字段: {col}")

    today = datetime.now().strftime("%Y-%m-%d")
    out = pd.DataFrame(
        {
            "code": df["代码"].astype(str).map(_norm_code),
            "date": today,
            "close": pd.to_numeric(df["最新价"], errors="coerce"),
            "volume": pd.to_numeric(df["成交量"], errors="coerce"),
            "low": pd.to_numeric(df["最低"], errors="coerce"),
            "pre_close": pd.to_numeric(df["昨收"], errors="coerce"),
            "open": pd.to_numeric(df["今开"], errors="coerce"),
            "turnover": pd.to_numeric(df["成交额"], errors="coerce"),
        }
    )
    out = out.dropna(subset=["code", "close", "volume", "low"]).reset_index(drop=True)
    logger.info("AkShare 日线拉取完成: %s", len(out))
    return out


def fetch_daily_core(trade_date: str, logger: logging.Logger) -> tuple[pd.DataFrame, str]:
    try:
        df = _fetch_daily_tushare(trade_date=trade_date, logger=logger)
        return df, "tushare"
    except Exception as exc:
        logger.warning("Tushare 拉取失败，回退 AkShare: %s", exc)
        return _fetch_daily_akshare(logger=logger), "akshare"


def write_local_snapshot(df: pd.DataFrame, trade_date: str, logger: logging.Logger) -> Path:
    out_dir = Path(os.getenv("SNAPSHOT_DIR", "outputs/snapshots"))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"market_daily_{trade_date}.json"

    payload = {
        "trade_date": trade_date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rows": len(df),
        "data": df.to_dict(orient="records"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    logger.info("本地快照已写入: %s", path)
    return path


def _snapshot_path(trade_date: str) -> Path:
    out_dir = Path(os.getenv("SNAPSHOT_DIR", "outputs/snapshots"))
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"market_daily_{trade_date}.json"


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _load_local_snapshot(trade_date: str) -> tuple[Path, dict, pd.DataFrame]:
    path = _snapshot_path(trade_date)
    if not path.exists():
        raise RuntimeError(f"未找到本地快照: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload.get("data", [])
    if not isinstance(data, list):
        raise RuntimeError(f"本地快照 data 格式异常: {path}")
    df = pd.DataFrame(data)
    return path, payload, df


def _merge_history(existing_data: list[dict] | None, new_row: dict) -> list[dict]:
    rows = [x for x in (existing_data or []) if isinstance(x, dict)]
    rows = [x for x in rows if x.get("date") != new_row.get("date")]
    rows.append(new_row)
    rows.sort(key=lambda x: str(x.get("date", "")))
    return rows[-60:]


def upload_snapshot_to_mongo(df: pd.DataFrame, trade_date: str, source_tag: str, logger: logging.Logger) -> int:
    uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip()
    db_name = os.getenv("MONGO_DB", "quant_screener").strip() or "quant_screener"
    coll_name = os.getenv("MONGO_COLLECTION", "market_cache").strip() or "market_cache"

    coll = MongoClient(uri)[db_name][coll_name]

    codes = df["code"].astype(str).tolist()
    existed = {
        doc["_id"]: doc
        for doc in coll.find({"_id": {"$in": codes}}, {"_id": 1, "data": 1, "name": 1, "exchange": 1, "mktcap": 1})
    }

    ops: list[UpdateOne] = []
    now = datetime.utcnow()

    for _, r in df.iterrows():
        code = _norm_code(str(r["code"]))
        old = existed.get(code, {})
        daily_row = {
            "date": str(r["date"]),
            "close": None if pd.isna(r["close"]) else float(r["close"]),
            "volume": None if pd.isna(r["volume"]) else float(r["volume"]),
            "low": None if pd.isna(r["low"]) else float(r["low"]),
            "pre_close": None if pd.isna(r.get("pre_close")) else float(r.get("pre_close")),
            "open": None if pd.isna(r.get("open")) else float(r.get("open")),
            "turnover": None if pd.isna(r.get("turnover")) else float(r.get("turnover")),
        }
        merged_data = _merge_history(old.get("data", []), daily_row)

        payload = {
            "_id": code,
            "source": source_tag,
            "updated_at": now,
            "cached_at": now,
            "expires_at": None,
            "name": str(r.get("name") or old.get("name") or ""),
            "exchange": str(r.get("exchange") or old.get("exchange") or ""),
            "mktcap": None if pd.isna(r.get("mktcap")) else float(r.get("mktcap")),
            "data": merged_data,
        }
        ops.append(UpdateOne({"_id": code}, {"$set": payload}, upsert=True))

    # 快照和同步元信息
    snap_doc = {
        "_id": f"ingest:daily_snapshot:{trade_date}",
        "source": source_tag,
        "updated_at": now,
        "cached_at": now,
        "expires_at": None,
        "data": df.to_dict(orient="records"),
    }
    meta_doc = {
        "_id": "ingest:sync_meta",
        "source": source_tag,
        "updated_at": now,
        "cached_at": now,
        "expires_at": None,
        "data": [{"sync_date": trade_date, "total": int(len(df)), "ok": int(len(df)), "failed": 0}],
    }
    ops.append(UpdateOne({"_id": snap_doc["_id"]}, {"$set": snap_doc}, upsert=True))
    ops.append(UpdateOne({"_id": meta_doc["_id"]}, {"$set": meta_doc}, upsert=True))

    if ops:
        coll.bulk_write(ops, ordered=False)

    logger.info("Mongo 批量上传完成: upserts=%s", len(ops))
    return len(ops)


def run_daily_ingest_step1(logger: logging.Logger, trade_date: str | None = None) -> IngestResult:
    _load_env_file(Path(".env"))
    trade_date = trade_date or datetime.now().strftime("%Y%m%d")
    existing_path = _snapshot_path(trade_date)
    if existing_path.exists():
        try:
            _, _, existing_df = _load_local_snapshot(trade_date)
            if not existing_df.empty:
                logger.info("检测到当日本地快照已存在，跳过 step1 拉取: %s", existing_path)
                return IngestResult(
                    trade_date=trade_date,
                    stock_list_count=int(len(existing_df)),
                    daily_rows=int(len(existing_df)),
                    mktcap_filled=int(pd.to_numeric(existing_df.get("mktcap"), errors="coerce").notna().sum()),
                    mongo_upserts=0,
                    snapshot_file=str(existing_path),
                )
        except Exception:
            pass

    daily_df, daily_source = fetch_daily_core(trade_date=trade_date, logger=logger)
    merged = daily_df.dropna(subset=["close", "volume", "low"]).reset_index(drop=True)
    merged["mktcap"] = pd.NA
    logger.info("当日全量股票池(来自日线): %s", len(merged))

    snapshot_file = write_local_snapshot(merged, trade_date=trade_date, logger=logger)
    mongo_upserts = upload_snapshot_to_mongo(
        merged,
        trade_date=trade_date,
        source_tag=f"daily_ingest_step1:{daily_source}",
        logger=logger,
    )
    return IngestResult(
        trade_date=trade_date,
        stock_list_count=int(len(merged)),
        daily_rows=int(len(merged)),
        mktcap_filled=0,
        mongo_upserts=int(mongo_upserts),
        snapshot_file=str(snapshot_file),
    )


def run_mktcap_enrich_step2(logger: logging.Logger, trade_date: str | None = None) -> IngestResult:
    _load_env_file(Path(".env"))
    trade_date = trade_date or datetime.now().strftime("%Y%m%d")
    path, payload, df = _load_local_snapshot(trade_date)
    if df.empty or "code" not in df.columns:
        raise RuntimeError(f"本地快照为空或缺少 code 字段: {path}")

    import akshare as ak  # type: ignore

    sleep_sec = float(os.getenv("AK_ENRICH_SLEEP_SECONDS", "0.25"))
    max_retries = int(os.getenv("AK_ENRICH_RETRIES", "2"))
    limit = int(os.getenv("AK_ENRICH_CODES_LIMIT", "0"))
    if "mktcap" in df.columns:
        pending_df = df[df["mktcap"].isna()]
    else:
        pending_df = df
    codes = pending_df["code"].astype(str).map(_norm_code).tolist()
    if limit > 0:
        codes = codes[:limit]

    code_idx = {str(_norm_code(c)): i for i, c in enumerate(df["code"].astype(str).tolist())}
    for idx, code in enumerate(codes, start=1):
        em_symbol = _to_em_symbol(code)
        mktcap = None
        if not em_symbol.startswith("BJ"):
            for _ in range(max_retries + 1):
                try:
                    scale_df = ak.stock_zh_scale_comparison_em(symbol=em_symbol)
                    if scale_df is not None and not scale_df.empty and {"代码", "总市值"}.issubset(scale_df.columns):
                        hit = scale_df[scale_df["代码"].astype(str).str.zfill(6) == code]
                        if not hit.empty:
                            mv = pd.to_numeric(hit.iloc[0]["总市值"], errors="coerce")
                            if pd.notna(mv):
                                mktcap = float(mv)
                    break
                except Exception:
                    time.sleep(0.2)

        # 每拉一只都落本地（用户要求）
        row_idx = code_idx.get(code)
        if row_idx is not None:
            payload["data"][row_idx]["mktcap"] = mktcap
            _write_json_atomic(path, payload)

        if idx % 200 == 0:
            logger.info("step2 进度: %s/%s", idx, len(codes))
        if sleep_sec > 0:
            time.sleep(sleep_sec)

    # 统一落库
    df2 = pd.DataFrame(payload.get("data", []))
    mkt_filled = int(pd.to_numeric(df2.get("mktcap"), errors="coerce").notna().sum())
    mongo_upserts = upload_snapshot_to_mongo(
        df2,
        trade_date=trade_date,
        source_tag="daily_ingest_step2:ak_scale_local_then_db",
        logger=logger,
    )

    return IngestResult(
        trade_date=trade_date,
        stock_list_count=int(len(df2)),
        daily_rows=int(len(df2)),
        mktcap_filled=mkt_filled,
        mongo_upserts=int(mongo_upserts),
        snapshot_file=str(path),
    )


def run_daily_market_ingest(logger: logging.Logger) -> IngestResult:
    step1 = run_daily_ingest_step1(logger=logger)
    step2 = run_mktcap_enrich_step2(logger=logger, trade_date=step1.trade_date)
    return step2
