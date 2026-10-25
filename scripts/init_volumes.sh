#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# compose 的資料掛載都設了 create_host_path: false：目錄不存在就啟動失敗，不讓 Docker 以 root 建一個容器寫不進去的目錄，
# 所以新機器第一次 up 之前先用部署帳號（uid 1000）跑這支。分層：data/ 要備份、cache/ 可重建、run/ 執行期暫存、logs/ 日誌
DIRS=(
  "$ROOT_DIR/logs"
  "$ROOT_DIR/data/pgvector"
  "$ROOT_DIR/data/hermes"
  "$ROOT_DIR/cache/search-mcp"
  "$ROOT_DIR/run/gpu_lock"
)

echo "[init] Creating local volume directories..."
for dir in "${DIRS[@]}"; do
  mkdir -p "$dir"
  echo "  - ensured: $dir"
done

echo "[init] pgvector uses bind mount directory: $ROOT_DIR/data/pgvector (an empty directory means a fresh, empty cluster)"
echo "[init] Done. You can now run: docker compose up -d"
