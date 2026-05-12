#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Deploy the local JM AI design app to the JDCloud server.

Usage:
  scripts/deploy_jdcloud.sh

Environment overrides:
  DEPLOY_HOST          SSH host. Default: xy1-gcs.jdcloud.com
  DEPLOY_PORT          SSH port. Default: 20151
  DEPLOY_USER          SSH user. Default: root
  DEPLOY_ROOT          Remote app root. Default: /data/jm-ai-design-app
  DEPLOY_PYTHON        Remote Python. Default: /root/miniconda/envs/jm-ai-design-app/bin/python
  DEPLOY_RELEASE       Release directory name. Default: current timestamp
  DEPLOY_PUBLIC_URL    Public URL for smoke check. Default: JDCloud app URL
  RUN_TESTS            Run local pytest before packaging. Default: 1
  REQUIRE_CLEAN        Refuse dirty git worktree. Default: 0

The script does not upload .env, data/, .venv/, caches, local report output, or
other runtime artifacts. Remote config and task history are kept in shared/.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

APP_NAME="jm-ai-design-app"
LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_HOST="${DEPLOY_HOST:-xy1-gcs.jdcloud.com}"
DEPLOY_PORT="${DEPLOY_PORT:-20151}"
DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/data/jm-ai-design-app}"
DEPLOY_PYTHON="${DEPLOY_PYTHON:-/root/miniconda/envs/jm-ai-design-app/bin/python}"
DEPLOY_RELEASE="${DEPLOY_RELEASE:-$(date +%Y%m%d-%H%M%S)}"
DEPLOY_PUBLIC_URL="${DEPLOY_PUBLIC_URL:-http://224c75daaf6d45848a9d-udapp-3000.gcs-xy1a.jdcloud.com/}"
RUN_TESTS="${RUN_TESTS:-1}"
REQUIRE_CLEAN="${REQUIRE_CLEAN:-0}"

REMOTE="${DEPLOY_USER}@${DEPLOY_HOST}"
ARCHIVE="/tmp/${APP_NAME}-${DEPLOY_RELEASE}.tgz"
REMOTE_ARCHIVE="/tmp/${APP_NAME}-${DEPLOY_RELEASE}.tgz"
RELEASE_DIR="${DEPLOY_ROOT}/releases/${DEPLOY_RELEASE}"
SSH_OPTS=(-p "$DEPLOY_PORT" -o StrictHostKeyChecking=no)
SCP_OPTS=(-P "$DEPLOY_PORT" -o StrictHostKeyChecking=no)

run() {
  printf '\n==> %s\n' "$*"
  "$@"
}

if [[ -d "$LOCAL_ROOT/.git" ]]; then
  if [[ "$REQUIRE_CLEAN" == "1" ]]; then
    if ! git -C "$LOCAL_ROOT" diff --quiet || ! git -C "$LOCAL_ROOT" diff --cached --quiet; then
      echo "Dirty git worktree. Commit/stash changes or run with REQUIRE_CLEAN=0." >&2
      exit 1
    fi
  elif [[ -n "$(git -C "$LOCAL_ROOT" status --short)" ]]; then
    echo "Warning: deploying a dirty git worktree." >&2
  fi
fi

if [[ "$RUN_TESTS" == "1" ]]; then
  LOCAL_PYTHON="${LOCAL_PYTHON:-$LOCAL_ROOT/.venv/bin/python}"
  if [[ ! -x "$LOCAL_PYTHON" ]]; then
    echo "Local Python not found: $LOCAL_PYTHON" >&2
    echo "Set LOCAL_PYTHON or run with RUN_TESTS=0." >&2
    exit 1
  fi
  run env \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    PYTHONPATH="$LOCAL_ROOT" \
    "$LOCAL_PYTHON" -X faulthandler -m pytest -p no:capture -q
fi

echo "Packaging ${LOCAL_ROOT}"
rm -f "$ARCHIVE"
COPYFILE_DISABLE=1 tar \
  --exclude=.git \
  --exclude=.env \
  --exclude=.venv \
  --exclude=.pytest_cache \
  --exclude=data \
  --exclude=data-dev \
  --exclude=outpu \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='._*' \
  -czf "$ARCHIVE" \
  -C "$LOCAL_ROOT" .

run scp "${SCP_OPTS[@]}" "$ARCHIVE" "$REMOTE:$REMOTE_ARCHIVE"

run ssh "${SSH_OPTS[@]}" "$REMOTE" \
  "DEPLOY_ROOT='$DEPLOY_ROOT' RELEASE_DIR='$RELEASE_DIR' REMOTE_ARCHIVE='$REMOTE_ARCHIVE' DEPLOY_PYTHON='$DEPLOY_PYTHON' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

mkdir -p "$DEPLOY_ROOT/releases" "$DEPLOY_ROOT/shared" "$DEPLOY_ROOT/backups"
if [[ ! -f "$DEPLOY_ROOT/shared/.env" ]]; then
  echo "Missing remote shared config: $DEPLOY_ROOT/shared/.env" >&2
  exit 1
fi
if [[ ! -d "$DEPLOY_ROOT/shared/data" ]]; then
  echo "Missing remote shared data dir: $DEPLOY_ROOT/shared/data" >&2
  exit 1
fi

mkdir -p "$RELEASE_DIR"
tar -xzf "$REMOTE_ARCHIVE" -C "$RELEASE_DIR"
ln -sfn "$DEPLOY_ROOT/shared/.env" "$RELEASE_DIR/.env"
ln -sfn "$DEPLOY_ROOT/shared/data" "$RELEASE_DIR/data"

cd "$RELEASE_DIR"
"$DEPLOY_PYTHON" - <<'PY'
from app.main import create_app

app = create_app()
print("import-ok", app.title)
PY

ln -sfn "$RELEASE_DIR" "$DEPLOY_ROOT/current"
"$DEPLOY_ROOT/stop.sh" || true
"$DEPLOY_ROOT/start.sh"
"$DEPLOY_ROOT/status.sh"

if command -v curl >/dev/null 2>&1; then
  curl -fsS -o /dev/null --max-time 10 http://127.0.0.1:3000/ || {
    echo "Local remote smoke check failed" >&2
    exit 1
  }
fi
REMOTE_SCRIPT

if [[ -n "$DEPLOY_PUBLIC_URL" ]]; then
  run curl -fsSL -o /dev/null -w 'public_http_code=%{http_code}\n' "$DEPLOY_PUBLIC_URL"
fi

echo
echo "Deployed release: $RELEASE_DIR"
