---
name: openclaw-daily-quant-pipeline
description: Run the daily A-share automation on server: ingest daily full-market data into market_cache, enrich mktcap (skip BJ), run breakout screening, and verify market_cache remains stock-id-only.
---

# OpenClaw Daily Quant Pipeline

Use this skill when the user asks to run or schedule the daily stock pipeline on a server/OpenClaw.

## Preconditions

- Run in repo root: `/Users/yang/Documents/stock-quant-screener` (or deployed equivalent path).
- `.env` contains valid Mongo and Tushare config.
- Python env exists at `.venv`.
- MongoDB target db is `quant_screener`.

## Required Invariants

- `market_cache` must contain only stock-code `_id` (`^\\d{6}$`).
- Breakout must not modify `market_cache`.
- Screening results are written to `screening_history`.

## Workflow

Run the bundled script:

```bash
bash skills/openclaw-daily-quant-pipeline/scripts/run_daily_pipeline.sh
```

The script executes:

1. Pre-check Mongo service:
- ping Mongo before writing.
- if unavailable, auto-try start service (`systemctl/service/brew services`) and recheck.
2. `ingest-daily`: fetch current trading day full-market daily data and write to local snapshot + `market_cache`.
3. `ingest-mktcap`: fill `mktcap` from AkShare one-by-one (current code skips BJ).
4. Retry path:
- after first `ingest-mktcap`, count missing `mktcap` for non-BJ stocks in snapshot.
- if missing > 0, rerun `scripts.main ingest` once.
- if missing == 0, run `breakout` directly.
5. Post-checks on Mongo:
- `market_cache` has zero non-stock `_id` docs.
- print today `screening_history` count.

## Outputs

- Snapshot JSON: `outputs/snapshots/market_daily_YYYYMMDD.json`
- Candidate files:
- `outputs/trend_breakout_candidates.csv`
- `outputs/trend_breakout_candidates.xlsx`
- Mongo collections:
- `market_cache`
- `screening_history`

## Failure Handling

- If `ingest-daily` fails, stop immediately.
- If `ingest-mktcap` fails, stop and keep snapshot for retry.
- If post-check finds non-stock docs in `market_cache`, treat as failure.

## Manual Retry Commands

```bash
.venv/bin/python -m scripts.main ingest-daily
.venv/bin/python -m scripts.main ingest-mktcap --trade-date YYYYMMDD
.venv/bin/python -m scripts.main breakout
```
