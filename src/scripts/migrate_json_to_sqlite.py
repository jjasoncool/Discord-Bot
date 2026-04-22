"""
手動遷移腳本：sent_articles.json → sent_articles.db

用法（在 discord-bot 容器內）：
    python scripts/migrate_json_to_sqlite.py

行為：
    1. 讀取 services/sent_articles.json
    2. 寫入 services/sent_articles.db
    3. 原檔改名為 sent_articles.json.bak
"""
import asyncio
import sys
from pathlib import Path

# 確保可以 import services 下的模組
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.state_db import StateDB


async def main():
    json_path = Path(__file__).parent / "sent_articles.json"
    db = StateDB()
    await db.connect()

    success = await db.migrate_from_json(json_path)
    if success:
        print("✅ 遷移完成，原檔已備份為 sent_articles.json.bak")
    else:
        if not json_path.exists():
            print("⚠️ sent_articles.json 不存在，無需遷移")
        else:
            print("⚠️ DB 已有資料，跳過遷移（若要強制重匯，請先刪除 sent_articles.db）")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
