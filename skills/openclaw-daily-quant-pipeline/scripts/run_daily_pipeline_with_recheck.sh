#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT_DIR"

WAIT_SECONDS="${WAIT_SECONDS:-3600}"
TRADE_DATE="${TRADE_DATE:-$(date +%Y%m%d)}"

run_bg() {
  bash skills/openclaw-daily-quant-pipeline/scripts/run_daily_pipeline_bg.sh
}

check_snapshot() {
  local snap="outputs/snapshots/market_daily_${TRADE_DATE}.json"
  if [[ ! -f "$snap" ]]; then
    echo "snapshot_missing"
    return 10
  fi

  python3 - <<PY
import json
from pathlib import Path

p = Path("$snap")
obj = json.loads(p.read_text(encoding="utf-8"))
rows = obj.get("data", [])
if not isinstance(rows, list) or len(rows) < 1000:
    raise SystemExit(11)
expected = "${TRADE_DATE}"
expected_date = f"{expected[:4]}-{expected[4:6]}-{expected[6:8]}"
ok = any(str(r.get("date", "")).strip() == expected_date for r in rows if isinstance(r, dict))
if not ok:
    raise SystemExit(12)
print("snapshot_ok")
PY
}

echo "[1/4] start local background pipeline"
run_bg

echo "[2/4] wait ${WAIT_SECONDS}s"
sleep "$WAIT_SECONDS"

echo "[3/4] verify local snapshot for TRADE_DATE=${TRADE_DATE}"
if check_snapshot; then
  echo "snapshot verification passed"
  exit 0
fi

echo "[4/4] snapshot verification failed, rerun local background pipeline once"
run_bg
echo "rerun triggered"
