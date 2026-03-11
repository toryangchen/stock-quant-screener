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
        open_price = to_float(item.get("open"))
        high_price = to_float(item.get("high"))
        low_price = to_float(item.get("low"))
        fallback_high = max(value for value in [high_price, open_price, close] if value is not None)
        fallback_low = min(value for value in [low_price, open_price, close] if value is not None)
        points.append(
            {
                "date": point_date,
                "open": round(open_price if open_price is not None else close, 2),
                "high": round(fallback_high, 2),
                "low": round(fallback_low, 2),
                "close": round(close, 2),
            }
        )
    points.sort(key=lambda item: item["date"])
    return points
