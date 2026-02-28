from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class DataSource(ABC):
    @abstractmethod
    def get_a_spot(self) -> pd.DataFrame:
        """Return columns: code(str), name(str), mktcap(float, optional)."""

    @abstractmethod
    def get_stock_daily(self, code: str) -> pd.DataFrame:
        """Return columns: date, close, volume. Must be sorted by date asc."""

    @abstractmethod
    def get_etf_daily(self, code: str) -> pd.DataFrame:
        """Return columns: date, close, volume(optional). Must be sorted by date asc."""
