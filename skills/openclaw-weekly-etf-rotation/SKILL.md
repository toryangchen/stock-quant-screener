---
name: openclaw-weekly-etf-rotation
description: From local OpenClaw, SSH into the cloud server to run the weekly ETF rotation pipeline in background, then verify ETF cache/history output and rerun once if verification fails.
---

# OpenClaw Weekly ETF Rotation

Use this skill when the user asks local OpenClaw to trigger the ETF weekly rotation automation on the cloud server.

## Preconditions

- Local machine can SSH to the cloud server.
- Remote SSH config comes from local `.env`.
- Required vars: `REMOTE_HOST`, `REMOTE_USER`
- Optional vars: `REMOTE_PORT`, `REMOTE_KEY`, `REMOTE_REPO`
- Remote `.env` contains valid `MONGO_URI` and runtime config.

## Workflow

Run the local launcher:

```bash
bash skills/openclaw-weekly-etf-rotation/scripts/run_remote_etf_rotation_with_recheck.sh
```

Configurable env vars:

```bash
REMOTE_HOST=your_server_ip
REMOTE_USER=your_server_user
REMOTE_PORT=22
REMOTE_KEY=/absolute/path/to/your_ssh_key.pem
REMOTE_REPO=~/apps/stock-quant-screener
WAIT_SECONDS=1800
RUN_DATE=YYYY-MM-DD
```

The launcher does:

1. SSH to the server and start the ETF pipeline in background.
2. Wait `WAIT_SECONDS`.
3. SSH again and verify:
- `etf_cache` has at least 1 document
- `etf_history` has documents for `RUN_DATE`
- `outputs/etf_rotation_rank.xlsx` exists
4. If verification fails, rerun once in background.

## Remote Commands

Foreground:

```bash
bash skills/openclaw-weekly-etf-rotation/scripts/run_etf_rotation_pipeline.sh
```

Background:

```bash
bash skills/openclaw-weekly-etf-rotation/scripts/run_etf_rotation_pipeline_bg.sh
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

- If SSH fails, stop immediately.
- If post-check fails, rerun once.
- If rerun still fails, return failure and keep remote logs for inspection.

## Background Job Ops

```bash
ssh -i "$REMOTE_KEY" "$REMOTE_USER@$REMOTE_HOST" 'cd ~/apps/stock-quant-screener && tail -f outputs/logs/etf_rotation_*.log'
ssh -i "$REMOTE_KEY" "$REMOTE_USER@$REMOTE_HOST" 'cd ~/apps/stock-quant-screener && cat outputs/logs/etf_rotation.pid'
ssh -i "$REMOTE_KEY" "$REMOTE_USER@$REMOTE_HOST" 'cd ~/apps/stock-quant-screener && kill "$(cat outputs/logs/etf_rotation.pid)"'
```
