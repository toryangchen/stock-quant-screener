from __future__ import annotations

import os
import re
from datetime import datetime

import pandas as pd

from .base import DataSource


class TushareDataSource(DataSource):
    def __init__(self, token: str | None = None) -> None:
        try:
            import tushare as ts  # type: ignore
        except ImportError as exc:
            raise RuntimeError("tushare 未安装，请先执行: pip install -r requirements.txt") from exc

        self.token = token or os.getenv("TUSHARE_TOKEN", "").strip()
        if not self.token:
            raise RuntimeError("未提供 Tushare Token，请设置环境变量 TUSHARE_TOKEN")

        ts.set_token(self.token)
        self.pro = ts.pro_api(self.token)

        self.akshare_backup = None
        try:
            from .akshare_impl import AkShareDataSource

            self.akshare_backup = AkShareDataSource()
        except Exception:
            self.akshare_backup = None

    def _normalize_code(self, code: str) -> str:
        text = str(code).strip().lower()
        m = re.search(r"(\d{6})$", text)
        if m:
            return m.group(1)
        return text

    def _to_ts_code(self, code: str) -> str:
        text = str(code).strip().lower()
        if re.match(r"^\d{6}\.(sh|sz|bj)$", text):
            return text.upper()

        if text.startswith("sh") and len(text) >= 8:
            return f"{text[-6:]}.SH"
        if text.startswith("sz") and len(text) >= 8:
            return f"{text[-6:]}.SZ"
        if text.startswith("bj") and len(text) >= 8:
            return f"{text[-6:]}.BJ"

        m = re.search(r"(\d{6})$", text)
        digits = m.group(1) if m else text[-6:]

        if digits.startswith(("6", "5", "9")):
            return f"{digits}.SH"
        if digits.startswith("8"):
            return f"{digits}.BJ"
        return f"{digits}.SZ"

    def get_a_spot(self) -> pd.DataFrame:
        df = self.pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")
        if df is None or df.empty:
            raise RuntimeError("Tushare stock_basic 返回空数据")

        out = df.rename(columns={"ts_code": "code", "name": "name"}).copy()
        out["code"] = out["code"].astype(str).str.split(".").str[0].map(self._normalize_code)
        out["name"] = out["name"].astype(str)
        return out[["code", "name"]]

    def get_stock_daily(self, code: str) -> pd.DataFrame:
        ts_code = self._to_ts_code(code)
        end_date = datetime.now().strftime("%Y%m%d")
        df = self.pro.daily(ts_code=ts_code, start_date="19900101", end_date=end_date)

        if df is None or df.empty:
            raise RuntimeError(f"Tushare daily 返回空数据: {ts_code}")

        for col in ["trade_date", "close", "vol"]:
            if col not in df.columns:
                raise ValueError(
                    f"缺少字段 '{col}'，接口字段可能变动，需更新映射。当前列: {list(df.columns)}"
                )

        out = df[["trade_date", "close", "vol"]].rename(
            columns={"trade_date": "date", "close": "close", "vol": "volume"}
        )
        out["date"] = pd.to_datetime(out["date"], format="%Y%m%d", errors="coerce")
        out["close"] = pd.to_numeric(out["close"], errors="coerce")
        out["volume"] = pd.to_numeric(out["volume"], errors="coerce")
        out = out.dropna(subset=["date", "close", "volume"]).sort_values("date").reset_index(drop=True)
        return out

    def get_etf_daily(self, code: str) -> pd.DataFrame:
        if self.akshare_backup is None:
            raise RuntimeError("当前 Token 无 fund_daily 权限，且 AkShare 备用源不可用")
        return self.akshare_backup.get_etf_daily(code)
