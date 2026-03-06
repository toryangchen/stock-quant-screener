#!/usr/bin/env bash
set -euo pipefail

# Local launcher: SSH to remote server, start remote background pipeline,
# wait 1 hour, then verify snapshot json; rerun once if invalid.

REMOTE_HOST="${REMOTE_HOST:-192.144.236.58}"
REMOTE_USER="${REMOTE_USER:-ubuntu}"
REMOTE_PORT="${REMOTE_PORT:-22}"
REMOTE_KEY="${REMOTE_KEY:-$HOME/Ubantu_Server.pem}"
REMOTE_REPO="${REMOTE_REPO:-~/apps/stock-quant-screener}"
WAIT_SECONDS="${WAIT_SECONDS:-3600}"
TRADE_DATE="${TRADE_DATE:-$(date +%Y%m%d)}"

SSH_OPTS=(
  -p "$REMOTE_PORT"
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/dev/null
  -o ConnectTimeout=10
)

if [[ -n "${REMOTE_KEY:-}" ]]; then
  SSH_OPTS+=( -i "$REMOTE_KEY" )
fi

run_remote_bg() {
  ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" \
    "cd ${REMOTE_REPO} && bash skills/openclaw-daily-quant-pipeline/scripts/run_daily_pipeline_bg.sh"
}

check_remote_snapshot() {
  ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" bash -lc "
set -euo pipefail
cd ${REMOTE_REPO}
SNAP=outputs/snapshots/market_daily_${TRADE_DATE}.json
if [[ ! -f \"\$SNAP\" ]]; then
  echo 'snapshot_missing'
  exit 10
fi
python3 - <<'PY'
import json
from pathlib import Path
p = Path('outputs/snapshots/market_daily_${TRADE_DATE}.json')
obj = json.loads(p.read_text(encoding='utf-8'))
rows = obj.get('data', [])
if not isinstance(rows, list) or len(rows) < 1000:
    raise SystemExit(11)
# valid if at least one row has today's date
expected = '${TRADE_DATE}'
expected_date = f'{expected[:4]}-{expected[4:6]}-{expected[6:8]}'
ok = any(str(r.get('date','')).strip() == expected_date for r in rows if isinstance(r, dict))
if not ok:
    raise SystemExit(12)
print('snapshot_ok')
PY
"
}

echo "[1/4] start remote background pipeline"
run_remote_bg

echo "[2/4] wait ${WAIT_SECONDS}s"
sleep "$WAIT_SECONDS"

echo "[3/4] verify remote snapshot for TRADE_DATE=${TRADE_DATE}"
if check_remote_snapshot; then
  echo "snapshot verification passed"
  exit 0
fi

echo "[4/4] snapshot verification failed, rerun remote background pipeline once"
run_remote_bg

echo "rerun triggered"
