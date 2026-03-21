#!/bin/sh
set -eu

# Telethon session 預設檔案路徑（對應 main.py 的 session/telegram_scraper）
SESSION_FILE="/app/session/telegram_scraper.session"

if [ -f "$SESSION_FILE" ]; then
    echo "[telegram-scraper] 偵測到 session，直接啟動 main.py"
    exec python /app/main.py
fi

echo "[telegram-scraper] 尚未偵測到 session"

# 若有互動式終端，直接啟動 main.py 讓使用者輸入電話/驗證碼
if [ -t 0 ]; then
    echo "[telegram-scraper] 進入首次登入流程，請依提示輸入電話/驗證碼"
    exec python /app/main.py
fi

# 若無互動終端（例如 detached 啟動），容器待命避免 EOFError
echo "[telegram-scraper] 目前無互動終端，容器將待命（sleep infinity）"
echo "[telegram-scraper] 之後可用 docker compose exec -it telegram-scraper python /app/main.py 手動登入"
exec sleep infinity
