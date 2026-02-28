from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import pandas as pd


def ensure_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def write_dataframe(df: pd.DataFrame, csv_path: Path, xlsx_path: Path, sheet_name: str) -> None:
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)


def write_report_json(report_obj: Any, path: Path) -> None:
    if is_dataclass(report_obj):
        payload = asdict(report_obj)
    elif isinstance(report_obj, dict):
        payload = report_obj
    else:
        payload = dict(report_obj)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_report_excel(report_obj: dict[str, Any], xlsx_path: Path) -> None:
    rows = [{"metric": k, "value": v} for k, v in report_obj.items()]
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Summary")
