---
name: openclaw-daily-quant-pipeline
description: From local OpenClaw, SSH into cloud server to start daily A-share pipeline in background, recheck snapshot JSON after 1 hour, and rerun once if snapshot is invalid.
---

# OpenClaw Daily Quant Pipeline

Use this skill when the user asks local OpenClaw to SSH into cloud server and run the daily stock pipeline with delayed verification.

## Preconditions

- Local machine can SSH to cloud server.
- SSH key is available (default: `~/Ubantu_Server.pem`).
- Remote repo path is `~/apps/stock-quant-screener` (override if needed).
- Remote `.env` contains valid Mongo and Tushare config.

## Required Invariants

- `market_cache` must contain only stock-code `_id` (`^\\d{6}$`).
- Breakout must not modify `market_cache`.
- Screening results are written to `screening_history`.

## Workflow

Run the local launcher script:

```bash
bash skills/openclaw-daily-quant-pipeline/scripts/run_remote_pipeline_with_recheck.sh
```

Configurable env vars:

```bash
REMOTE_HOST=192.144.236.58
REMOTE_USER=ubuntu
REMOTE_PORT=22
REMOTE_KEY=~/Ubantu_Server.pem
REMOTE_REPO=~/apps/stock-quant-screener
TRADE_DATE=YYYYMMDD
WAIT_SECONDS=3600
```

The script executes:

1. SSH to remote server and run `run_daily_pipeline_bg.sh` in background.
2. Wait 1 hour (`WAIT_SECONDS`).
3. SSH again and verify `outputs/snapshots/market_daily_YYYYMMDD.json`:
- file exists
- `data` is a non-empty list (>=1000 rows)
- contains at least one row whose `date` equals trade date
4. If verification fails, SSH and rerun remote background pipeline once.

## Outputs

- Remote snapshot JSON: `outputs/snapshots/market_daily_YYYYMMDD.json`
- Remote logs: `outputs/logs/daily_pipeline_*.log`
- Remote PID file: `outputs/logs/daily_pipeline.pid`

## Failure Handling

- If SSH connection fails, stop immediately.
- If 1-hour snapshot verification fails, rerun once automatically.
- If rerun also fails, stop and return failure details.

## Manual Retry Commands

```bash
bash skills/openclaw-daily-quant-pipeline/scripts/run_remote_pipeline_with_recheck.sh
```

## Background Job Ops

```bash
ssh -i ~/Ubantu_Server.pem ubuntu@192.144.236.58 'cd ~/apps/stock-quant-screener && tail -f outputs/logs/daily_pipeline_*.log'
ssh -i ~/Ubantu_Server.pem ubuntu@192.144.236.58 'cd ~/apps/stock-quant-screener && cat outputs/logs/daily_pipeline.pid'
ssh -i ~/Ubantu_Server.pem ubuntu@192.144.236.58 'cd ~/apps/stock-quant-screener && kill "$(cat outputs/logs/daily_pipeline.pid)"'
```
