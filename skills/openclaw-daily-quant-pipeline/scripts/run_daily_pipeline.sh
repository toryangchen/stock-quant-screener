#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT_DIR"

PY_BIN=".venv/bin/python"
if [[ ! -x "$PY_BIN" ]]; then
  echo "ERROR: missing python env at $PY_BIN"
  exit 1
fi

if [[ ! -f ".env" ]]; then
  echo "ERROR: missing .env"
  exit 1
fi

TRADE_DATE="${TRADE_DATE:-$(date +%Y%m%d)}"

ensure_mongo_running() {
  if mongosh --quiet --eval 'db.adminCommand({ping:1}).ok' >/dev/null 2>&1; then
    return 0
  fi

  echo "MongoDB not reachable, trying to start service..."
  local cmds=(
    "systemctl start mongod"
    "service mongod start"
    "service mongodb start"
    "brew services start mongodb-community@7.0"
  )

  for cmd in "${cmds[@]}"; do
    bash -lc "$cmd" >/dev/null 2>&1 || true
    if command -v sudo >/dev/null 2>&1; then
      sudo -n bash -lc "$cmd" >/dev/null 2>&1 || true
    fi
    if mongosh --quiet --eval 'db.adminCommand({ping:1}).ok' >/dev/null 2>&1; then
      echo "MongoDB started successfully."
      return 0
    fi
  done

  echo "ERROR: MongoDB is not running and auto-start failed."
  exit 2
}

count_missing_non_bj_mktcap() {
  "$PY_BIN" - <<'PY'
import json
from pathlib import Path
from datetime import datetime
import os

trade_date = os.environ.get("TRADE_DATE") or datetime.now().strftime("%Y%m%d")
path = Path("outputs/snapshots") / f"market_daily_{trade_date}.json"
if not path.exists():
    print("0")
    raise SystemExit(0)

obj = json.loads(path.read_text(encoding="utf-8"))
rows = obj.get("data", [])
if not isinstance(rows, list):
    print("0")
    raise SystemExit(0)

missing = 0
for r in rows:
    ex = str(r.get("exchange") or "").upper()
    if ex == "BJ":
        continue
    mv = r.get("mktcap", None)
    if mv is None or (isinstance(mv, str) and not mv.strip()):
        missing += 1
print(str(missing))
PY
}

ensure_mongo_running

echo "[1/4] ingest-daily"
"$PY_BIN" -m scripts.main ingest-daily

echo "[2/4] ingest-mktcap (trade_date=$TRADE_DATE)"
"$PY_BIN" -m scripts.main ingest-mktcap --trade-date "$TRADE_DATE"

MISSING_NON_BJ="$(TRADE_DATE="$TRADE_DATE" count_missing_non_bj_mktcap)"
if [[ "${MISSING_NON_BJ:-0}" -gt 0 ]]; then
  echo "mktcap missing for non-BJ stocks: $MISSING_NON_BJ, rerun full ingest once."
  echo "[3/4] ingest (retry path)"
  "$PY_BIN" -m scripts.main ingest
else
  echo "[3/4] breakout"
  "$PY_BIN" -m scripts.main breakout
fi

echo "[4/4] mongo post-check"
mongosh --quiet --eval '
const dbx = db.getSiblingDB("quant_screener");
const nonStock = dbx.market_cache.countDocuments({_id: {$not: /^\\d{6}$/}});
if (nonStock > 0) {
  printjson({ok: 0, non_stock_docs: nonStock});
  quit(2);
}
const today = new Date().toISOString().slice(0, 10);
const screening = dbx.screening_history.countDocuments({run_date: today});
printjson({ok: 1, non_stock_docs: nonStock, screening_today: screening});
'

echo "DONE"
