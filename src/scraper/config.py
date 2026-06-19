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

# Bahamut 抓取設定（第一版：主文 + 主文留言）
BAHAMUT_CONFIG = {
    "target_board_url": "https://forum.gamer.com.tw/B.php?bsn=74934",
    "subbsn": "13",         # 子看板 ID，空字串=不帶（預設公開看板），多個用 _ 分隔（如 "12_13"）
    "timeout": 20,
    "board_start_page": 1,
    "board_end_page": 2,
    "max_articles_per_page": 30,
    "gate_max_hops": 3,
    "human_delay_min": (0.35, 0.9),
    "page_delay_range": (2, 5),
    "sample_output_dir": "data/bahamut_samples",
    "export_sample_json": False,
}

# HKEPC 抓取設定（系統設備 / 硬體新知）
# tags：要抓的 tag 清單，未來要新增類型直接在這加一個字串即可，例如 "顯示卡"、"處理器"、"AI"。
#       同一篇文章可能同時掛多個 tag，跨 tag 重複會在 scraper 內以 hkepc_id 去重。
HKEPC_CONFIG = {
    "base_url": "https://www.hkepc.com",
    "tags": ["IT快訊"],          # 要抓的 tag（可擴充）
    "pages_per_tag": 3,          # 定期每個 tag 抓幾頁（每頁約 5 篇）
    "first_run_limit": 50,       # 首次（DB 空）種子抓滿幾篇後停
    "timeout": 20,
    "human_delay_min": (0.35, 0.9),  # 抓內頁之間的隨機延遲
    # UA 不寫死：HkepcScraperService 繼承 BaseScraperClient，
    # 由 curl_cffi impersonate 輪換池自動帶（TLS 指紋 + UA + HTTP/2 一致）。
}

# 個別 Logger 的 log level 覆蓋（不設定的 logger 使用預設 LOG_LEVEL）
# 可用值：DEBUG, INFO, WARNING, ERROR
LOGGER_LEVELS = {
    "bahamut_scraper": "WARNING",
    "fb_scraper": "INFO",
    "ptt_scraper": "INFO",
    "hkepc_scraper": "INFO",
}
