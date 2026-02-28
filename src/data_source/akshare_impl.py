from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import pandas as pd

from .base import DataSource


class AkShareDataSource(DataSource):
    def __init__(self) -> None:
        try:
            import akshare as ak  # type: ignore
        except ImportError as exc:
            raise RuntimeError("akshare 未安装，请先执行: pip install -r requirements.txt") from exc
        self.ak = ak

    def _pick_col(self, df: pd.DataFrame, candidates: Iterable[str], target: str) -> str:
        for col in candidates:
            if col in df.columns:
                return col
        raise ValueError(f"缺少字段 '{target}'，接口字段可能变动，需更新映射。当前列: {list(df.columns)}")

    def _normalize_daily(self, df: pd.DataFrame) -> pd.DataFrame:
        date_col = self._pick_col(df, ["日期", "date", "Date", "交易日期"], "date")
        close_col = self._pick_col(df, ["收盘", "close", "Close"], "close")
        vol_col = self._pick_col(df, ["成交量", "volume", "Volume", "成交量(手)"], "volume")

        out = df[[date_col, close_col, vol_col]].copy()
        out.columns = ["date", "close", "volume"]
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out["close"] = pd.to_numeric(out["close"], errors="coerce")
        out["volume"] = pd.to_numeric(out["volume"], errors="coerce")
        out = out.dropna(subset=["date", "close", "volume"]).sort_values("date")
        out = out.reset_index(drop=True)
        return out

    def get_a_spot(self) -> pd.DataFrame:
        df = self.ak.stock_zh_a_spot_em()
        code_col = self._pick_col(df, ["代码", "code", "symbol"], "code")
        name_col = self._pick_col(df, ["名称", "name"], "name")

        keep_cols = [code_col, name_col]
        mktcap_col = None
        for candidate in ["总市值", "总市值(元)", "mktcap", "总市值-亿"]:
            if candidate in df.columns:
                mktcap_col = candidate
                keep_cols.append(mktcap_col)
                break

        out = df[keep_cols].copy()
        rename_map = {code_col: "code", name_col: "name"}
        if mktcap_col:
            rename_map[mktcap_col] = "mktcap"
        out = out.rename(columns=rename_map)

        out["code"] = out["code"].astype(str).str.zfill(6)
        out["name"] = out["name"].astype(str)
        if "mktcap" in out.columns:
            out["mktcap"] = pd.to_numeric(out["mktcap"], errors="coerce")

        return out

    def get_stock_daily(self, code: str) -> pd.DataFrame:
        try:
            df = self.ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date="",
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq",
            )
        except TypeError:
            df = self.ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        return self._normalize_daily(df)

    def get_etf_daily(self, code: str) -> pd.DataFrame:
        try:
            df = self.ak.fund_etf_hist_em(
                symbol=code,
                period="daily",
                start_date="",
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq",
            )
        except TypeError:
            df = self.ak.fund_etf_hist_em(symbol=code, period="daily", adjust="qfq")
        return self._normalize_daily(df)
