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
    "debug_mode": False,  # 除錯模式
}

# Facebook 抓取設定
FACEBOOK_CONFIG = {
    "target_url": "https://www.facebook.com/WutheringWaves.ZH/",
    "max_links": 3,
    "headless": True,
    "scroll_rounds": 6,
    "human_delay_min": (0.35, 0.9),  # 隨機延遲範圍
    "debug_mode": FEATURES["debug_mode"],  # 從功能設定讀取除錯模式
    "json_output_file": "data/fb_posts.json",  # FB 貼文 JSON 檔案名稱 (相對 data 目錄)
    "html_log_dir": "./logs",  # HTML 日誌目錄
    "data_dir": "./data",  # 資料檔案目錄
    "max_scraping_sessions": 3,  # 保留幾次擷取結果 (會根據 max_links 計算最大 HTML 檔案數)
}

# PTT 抓取設定（先做可連線與可抓頁面驗證）
PTT_CONFIG = {
    "target_search_url": "https://www.ptt.cc/bbs/C_Chat/search?page=2&q=%E9%B3%B4%E6%BD%AE",
    "over18_cookie": {"over18": "1"},
    "timeout": 20,
    "search_pages": 3,
}
