#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT_DIR"

LOG_DIR="${LOG_DIR:-outputs/logs}"
mkdir -p "$LOG_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_FILE:-$LOG_DIR/etf_rotation_${TS}.log}"
PID_FILE="${PID_FILE:-$LOG_DIR/etf_rotation.pid}"

nohup bash skills/openclaw-weekly-etf-rotation/scripts/run_etf_rotation_pipeline.sh >"$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"

echo "started"
echo "pid=$PID"
echo "pid_file=$PID_FILE"
echo "log_file=$LOG_FILE"
