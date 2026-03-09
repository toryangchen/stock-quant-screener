#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT_DIR"

WAIT_SECONDS="${WAIT_SECONDS:-1800}"
RUN_DATE="${RUN_DATE:-$(date +%F)}"

run_bg() {
  RUN_DATE="$RUN_DATE" bash skills/openclaw-weekly-etf-rotation/scripts/run_etf_rotation_pipeline_bg.sh
}

check_result() {
  if [[ ! -f outputs/etf_rotation_rank.xlsx ]]; then
    echo "xlsx_missing"
    return 10
  fi

  if [[ ! -f ".env" ]]; then
    echo "env_missing"
    return 11
  fi

  set -a
  # shellcheck disable=SC1091
  source .env
  set +a

  mongosh --quiet "$MONGO_URI" --eval "
const dbx = db.getSiblingDB(\"quant_screener\");
const cacheCount = dbx.etf_cache.countDocuments({});
const histCount = dbx.etf_history.countDocuments({run_date: \"${RUN_DATE}\"});
if (cacheCount <= 0 || histCount <= 0) { quit(12); }
printjson({ok: 1, etf_cache: cacheCount, etf_history: histCount});
"
}

echo "[1/4] start local ETF rotation pipeline"
run_bg

echo "[2/4] wait ${WAIT_SECONDS}s"
sleep "$WAIT_SECONDS"

echo "[3/4] verify local ETF outputs for RUN_DATE=${RUN_DATE}"
if check_result; then
  echo "verification passed"
  exit 0
fi

echo "[4/4] verification failed, rerun local ETF rotation once"
run_bg
echo "rerun triggered"
