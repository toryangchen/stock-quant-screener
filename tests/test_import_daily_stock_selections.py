from __future__ import annotations

from datetime import datetime
import unittest

from scripts.jobs.import_daily_stock_selections import build_analysis_rows


class DailyStockSelectionImportTests(unittest.TestCase):
    def test_build_analysis_rows_maps_selection_stocks_to_analysis_stock_docs(self) -> None:
        selection = {
            "_id": "source123",
            "date": "2026-05-15",
            "created_at": datetime(2026, 5, 15, 14, 31, 11),
            "stocks": [
                {"code": "600006", "name": "东风股份", "price": 6.87, "pct_chg": 3.3082706766917256},
                {"code": "SZ000551", "name": " 创元科技 ", "price": "17.09", "pct_chg": "4.143814747105422"},
            ],
        }

        rows = build_analysis_rows(selection, saved_at=datetime(2026, 5, 15, 15, 0, 0))

        self.assertEqual(
            rows,
            [
                {
                    "_id": "600006.2026-05-15",
                    "run_date": "2026-05-15",
                    "code": "600006",
                    "name": "东风股份",
                    "entry_price": 6.87,
                    "pct_chg": 3.31,
                    "source_file": "daily_stock_selections:source123",
                    "source_collection": "daily_stock_selections",
                    "source_id": "source123",
                    "source_created_at": datetime(2026, 5, 15, 14, 31, 11),
                    "saved_at": datetime(2026, 5, 15, 15, 0, 0),
                },
                {
                    "_id": "000551.2026-05-15",
                    "run_date": "2026-05-15",
                    "code": "000551",
                    "name": "创元科技",
                    "entry_price": 17.09,
                    "pct_chg": 4.14,
                    "source_file": "daily_stock_selections:source123",
                    "source_collection": "daily_stock_selections",
                    "source_id": "source123",
                    "source_created_at": datetime(2026, 5, 15, 14, 31, 11),
                    "saved_at": datetime(2026, 5, 15, 15, 0, 0),
                },
            ],
        )

    def test_build_analysis_rows_skips_rows_without_valid_code_or_price(self) -> None:
        selection = {
            "_id": "source456",
            "date": "2026-05-15",
            "stocks": [
                {"code": "", "name": "无代码", "price": 1.0, "pct_chg": 1.0},
                {"code": "600006", "name": "无价格", "price": None, "pct_chg": 1.0},
                {"code": "600078", "name": "澄星股份", "price": 15.46, "pct_chg": None},
            ],
        }

        rows = build_analysis_rows(selection, saved_at=datetime(2026, 5, 15, 15, 0, 0))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["_id"], "600078.2026-05-15")
        self.assertEqual(rows[0]["pct_chg"], 0.0)


if __name__ == "__main__":
    unittest.main()
