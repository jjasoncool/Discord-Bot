#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DIRS=(
  "$ROOT_DIR/logs"
  "$ROOT_DIR/vector_data"
)

echo "[init] Creating local volume directories..."
for dir in "${DIRS[@]}"; do
  mkdir -p "$dir"
  echo "  - ensured: $dir"
done

echo "[init] pgvector uses bind mount directory: $ROOT_DIR/vector_data"
echo "[init] Done. You can now run: docker compose up -d"
