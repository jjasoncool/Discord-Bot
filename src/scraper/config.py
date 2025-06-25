import os
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# API 網址設定
API_URLS = {
    "api1": "https://hw-media-cdn-mingchao.kurogame.com/akiwebsite/website2.0/json/G152/zh-tw/ArticleMenu.json",
    # "api2": "https://hw-media-cdn-mingchao.kurogame.com/akiwebsite/website2.0/json/G152/zh-tw/article/[article_id].json",
    "api2": "https://hw-media-cdn-mingchao.kurogame.com/akiwebsite/website2.0/json/G152/zh-tw/article/"
}

# 輸出檔案名稱設定
OUTPUT_FILES = {
    "api1": "article_menu.json",
    "api2": "article_data.json"
}

# 資料庫設定 - 使用環境變數
DATABASE_CONFIG = {
    "filename": os.path.basename(os.getenv("DATABASE_URL", "sqlite:///./articles.db").split("///")[-1]),
    "url": os.getenv("DATABASE_URL", "sqlite:///./articles.db")
}

# 功能開關設定
FEATURES = {
    "save_to_json": True,  # 是否同時儲存 JSON 檔案
    "save_to_database": True,  # 是否儲存到資料庫
    "debug_mode": False  # 除錯模式
}
