from __future__ import annotations

from typing import Any


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_points(series: list[dict[str, Any]], run_date: str) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for item in series:
        point_date = str(item.get("date", "")).strip()
        close = to_float(item.get("close"))
        if not point_date or close is None or point_date < run_date:
            continue
        points.append({"date": point_date, "close": round(close, 2)})
    points.sort(key=lambda item: item["date"])
    return points
