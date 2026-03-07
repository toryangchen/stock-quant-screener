#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_USER="${REMOTE_USER:-}"
REMOTE_PORT="${REMOTE_PORT:-22}"
REMOTE_KEY="${REMOTE_KEY:-}"
REMOTE_REPO="${REMOTE_REPO:-~/apps/stock-quant-screener}"
WAIT_SECONDS="${WAIT_SECONDS:-1800}"
RUN_DATE="${RUN_DATE:-$(date +%F)}"

if [[ -z "$REMOTE_HOST" || -z "$REMOTE_USER" ]]; then
  echo "ERROR: REMOTE_HOST and REMOTE_USER must be set in .env or environment."
  exit 1
fi

SSH_OPTS=(
  -p "$REMOTE_PORT"
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/dev/null
  -o ConnectTimeout=10
)

if [[ -n "${REMOTE_KEY:-}" ]]; then
  SSH_OPTS+=(-i "$REMOTE_KEY")
fi

run_remote_bg() {
  ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" \
    "cd ${REMOTE_REPO} && RUN_DATE=${RUN_DATE} bash skills/openclaw-weekly-etf-rotation/scripts/run_etf_rotation_pipeline_bg.sh"
}

check_remote_result() {
  ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" bash -lc "
set -euo pipefail
cd ${REMOTE_REPO}
if [[ ! -f outputs/etf_rotation_rank.xlsx ]]; then
  echo 'xlsx_missing'
  exit 10
fi
set -a
source .env
set +a
mongosh --quiet \"\$MONGO_URI\" --eval '
const dbx = db.getSiblingDB(\"quant_screener\");
const cacheCount = dbx.etf_cache.countDocuments({});
const histCount = dbx.etf_history.countDocuments({run_date: \"${RUN_DATE}\"});
if (cacheCount <= 0 || histCount <= 0) { quit(11); }
printjson({ok: 1, etf_cache: cacheCount, etf_history: histCount});
'
"
}

echo "[1/4] start remote ETF rotation pipeline"
run_remote_bg

echo "[2/4] wait ${WAIT_SECONDS}s"
sleep "$WAIT_SECONDS"

echo "[3/4] verify remote ETF outputs for RUN_DATE=${RUN_DATE}"
if check_remote_result; then
  echo "verification passed"
  exit 0
fi

echo "[4/4] verification failed, rerun remote ETF rotation once"
run_remote_bg
echo "rerun triggered"
