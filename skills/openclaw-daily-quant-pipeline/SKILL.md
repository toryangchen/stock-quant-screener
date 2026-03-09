---
name: openclaw-daily-quant-pipeline
description: Run the daily A-share pipeline directly on the server via OpenClaw, keep it in background, recheck snapshot JSON after 1 hour, and rerun once if snapshot is invalid.
---

# OpenClaw Daily Quant Pipeline

Use this skill when OpenClaw is already running on the cloud server and needs to execute the daily stock pipeline with delayed verification.

Default rule: OpenClaw should call only the background launcher. Do not use the foreground script unless you are debugging interactively.

## Preconditions

- OpenClaw is running on the target server.
- The repo is already checked out on that server.
- Server-side `.env` contains valid Mongo and Tushare config.
- The current working directory is the repo root.

## Required Invariants

- `market_cache` must contain only stock-code `_id` (`^\\d{6}$`).
- Breakout must not modify `market_cache`.
- Screening results are written to `screening_history`.

## Workflow

Run the server-local launcher script:

```bash
bash skills/openclaw-daily-quant-pipeline/scripts/run_daily_pipeline_with_recheck.sh
```

Configurable env vars:

```bash
TRADE_DATE=YYYYMMDD
WAIT_SECONDS=3600
```

The script executes:

1. Start `run_daily_pipeline.sh` in background.
2. Wait 1 hour (`WAIT_SECONDS`).
3. Verify `outputs/snapshots/market_daily_YYYYMMDD.json`:
- file exists
- `data` is a non-empty list (>=1000 rows)
- contains at least one row whose `date` equals trade date
4. If verification fails, rerun the background pipeline once.

## Outputs

- Remote snapshot JSON: `outputs/snapshots/market_daily_YYYYMMDD.json`
- Remote logs: `outputs/logs/daily_pipeline_*.log`
- Remote PID file: `outputs/logs/daily_pipeline.pid`

## Failure Handling

- If 1-hour snapshot verification fails, rerun once automatically.
- If rerun also fails, stop and return failure details.

## Manual Retry Commands

```bash
bash skills/openclaw-daily-quant-pipeline/scripts/run_daily_pipeline_bg.sh
bash skills/openclaw-daily-quant-pipeline/scripts/run_daily_pipeline_with_recheck.sh
```

## Background Job Ops

```bash
tail -f outputs/logs/daily_pipeline_*.log
cat outputs/logs/daily_pipeline.pid
kill "$(cat outputs/logs/daily_pipeline.pid)"
```
