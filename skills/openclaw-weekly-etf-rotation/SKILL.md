---
name: openclaw-weekly-etf-rotation
description: Run the weekly ETF rotation pipeline directly on the server via OpenClaw, then verify ETF cache/history output and rerun once if verification fails.
---

# OpenClaw Weekly ETF Rotation

Use this skill when OpenClaw is already running on the server and needs to trigger the ETF weekly rotation automation.

Default rule: OpenClaw should call only the background launcher. Do not use the foreground script unless you are debugging interactively.

## Preconditions

- OpenClaw is running on the target server.
- The repo is already checked out on that server.
- Server-side `.env` contains valid `MONGO_URI` and runtime config.
- The current working directory is the repo root.

## Workflow

Run the server-local launcher:

```bash
bash skills/openclaw-weekly-etf-rotation/scripts/run_etf_rotation_with_recheck.sh
```

Configurable env vars:

```bash
WAIT_SECONDS=1800
RUN_DATE=YYYY-MM-DD
```

The launcher does:

1. Start the ETF pipeline in background on the current server.
2. Wait `WAIT_SECONDS`.
3. Verify:
- `etf_cache` has at least 1 document
- `etf_history` has documents for `RUN_DATE`
- `outputs/etf_rotation_rank.xlsx` exists
4. If verification fails, rerun once in background.

## Local Commands

Background:

```bash
bash skills/openclaw-weekly-etf-rotation/scripts/run_etf_rotation_pipeline_bg.sh
bash skills/openclaw-weekly-etf-rotation/scripts/run_etf_rotation_with_recheck.sh
```

## Outputs

- Remote Mongo collections:
- `etf_cache`
- `etf_history`
- Remote files:
- `outputs/etf_rotation_rank.csv`
- `outputs/etf_rotation_rank.xlsx`
- Remote logs:
- `outputs/logs/etf_rotation_*.log`
- `outputs/logs/etf_rotation.pid`

## Failure Handling

- If post-check fails, rerun once.
- If rerun still fails, return failure and keep remote logs for inspection.

## Background Job Ops

```bash
tail -f outputs/logs/etf_rotation_*.log
cat outputs/logs/etf_rotation.pid
kill "$(cat outputs/logs/etf_rotation.pid)"
```
