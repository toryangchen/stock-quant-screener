from __future__ import annotations

from fastapi import APIRouter, Query

from services import QuantReadService


service = QuantReadService()
router = APIRouter()


@router.get("/health")
def health():
    return service.health()


@router.get("/screening/dates")
def screening_dates():
    return service.get_screening_dates()


@router.get("/screening")
def screening_by_date(run_date: str = Query(..., description="YYYY-MM-DD")):
    return service.get_screening_by_date(run_date)


@router.get("/etf/dates")
def etf_dates():
    return service.get_etf_dates()


@router.get("/etf")
def etf_by_date(run_date: str = Query(..., description="YYYY-MM-DD")):
    return service.get_etf_by_date(run_date)


@router.get("/analysis/dates")
def analysis_dates():
    return service.get_analysis_dates()


@router.get("/analysis")
def analysis_by_date(run_date: str = Query(..., description="YYYY-MM-DD")):
    return service.get_analysis_by_date(run_date)
