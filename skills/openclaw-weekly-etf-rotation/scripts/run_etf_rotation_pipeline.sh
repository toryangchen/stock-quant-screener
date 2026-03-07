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

set -a
# shellcheck disable=SC1091
source .env
set +a

MONGO_DB="${MONGO_DB:-quant_screener}"
RUN_DATE="${RUN_DATE:-$(date +%F)}"

mongo_ping() {
  if [[ -n "${MONGO_URI:-}" ]]; then
    mongosh --quiet "$MONGO_URI" --eval 'db.adminCommand({ping:1}).ok' >/dev/null 2>&1
  else
    mongosh --quiet --eval 'db.adminCommand({ping:1}).ok' >/dev/null 2>&1
  fi
}

ensure_mongo_running() {
  if mongo_ping; then
    return 0
  fi

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
    if mongo_ping; then
      return 0
    fi
  done

  echo "ERROR: MongoDB is not running and auto-start failed."
  exit 2
}

ensure_mongo_running

echo "[1/3] ingest-etf"
"$PY_BIN" -m scripts.main ingest-etf

echo "[2/3] etf-rotation"
"$PY_BIN" -m scripts.main etf-rotation

echo "[3/3] mongo post-check"
if [[ -n "${MONGO_URI:-}" ]]; then
  mongosh --quiet "$MONGO_URI" --eval "
const dbx = db.getSiblingDB(\"${MONGO_DB}\");
const cacheCount = dbx.etf_cache.countDocuments({});
const histCount = dbx.etf_history.countDocuments({run_date: \"${RUN_DATE}\"});
if (cacheCount <= 0 || histCount <= 0) {
  printjson({ok: 0, etf_cache: cacheCount, etf_history: histCount});
  quit(2);
}
printjson({ok: 1, etf_cache: cacheCount, etf_history: histCount});
"
else
  mongosh --quiet --eval "
const dbx = db.getSiblingDB(\"${MONGO_DB}\");
const cacheCount = dbx.etf_cache.countDocuments({});
const histCount = dbx.etf_history.countDocuments({run_date: \"${RUN_DATE}\"});
if (cacheCount <= 0 || histCount <= 0) {
  printjson({ok: 0, etf_cache: cacheCount, etf_history: histCount});
  quit(2);
}
printjson({ok: 1, etf_cache: cacheCount, etf_history: histCount});
"
fi

echo "DONE"
