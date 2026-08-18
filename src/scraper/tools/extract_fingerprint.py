"""
從容器內的 Firefox ESR 抓取真實 TLS / HTTP2 指紋（手動工具）。

此腳本會啟動容器內的 headless Firefox ESR，訪問 tls.peet.ws 指紋偵測站，
取得該瀏覽器的 JA3（TLS）與 Akamai（HTTP/2）真實指紋，儲存為本地指紋庫。
BaseScraperClient 啟動時會自動載入此指紋庫，作為 curl_cffi 內建指紋池的補充。

═══════════════════════════════════════════════════════
  用法（手動執行，非自動排程）
═══════════════════════════════════════════════════════

  1. 確保 scraper 容器正在運行
  2. 執行：

     docker exec scraper python tools/extract_fingerprint.py

  3. 指紋會自動儲存到 tools/fingerprints.json

═══════════════════════════════════════════════════════
  何時需要重跑
═══════════════════════════════════════════════════════

  - 容器更新 Firefox ESR 版本後（apt upgrade firefox-esr）
  - 覺得現有指紋可能被標記時
  - 指紋庫為空或被誤刪時

═══════════════════════════════════════════════════════
  注意事項
═══════════════════════════════════════════════════════

  - 會對外連線到 https://tls.peet.ws（僅抓取一次，非持續連線）
  - 該站只看到一次標準 Firefox TLS 握手，不涉及任何敏感資料
  - 同名指紋會覆蓋更新，不會重複新增
  - 若偵測站掛掉，不影響現有指紋庫，只是無法更新
"""
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service


FINGERPRINT_URL = "https://tls.peet.ws/api/all"
OUTPUT_FILE = Path(__file__).parent / "fingerprints.json"

# 全站時區的單一來源在 `sys_settings/time_settings.py` 的 APP_TZ，但 scraper 是獨立
# 容器（掛載 ./src/scraper → /app），根目錄看不到 sys_settings，只能保留這一份。
# 兩邊都吃 compose 的 TZ=Asia/Taipei，改動時請一起改。
TZ_UTC8 = timezone(timedelta(hours=8))


def extract_fingerprint() -> dict:
    """啟動 headless Firefox ESR，訪問指紋偵測站，回傳指紋資料。"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # 停用 Firefox 內建 JSON viewer，取得原始 JSON 文字
    options.set_preference("devtools.jsonview.enabled", False)
    # 減少不必要的連線
    options.set_preference("datareporting.policy.dataSubmissionEnabled", False)
    options.set_preference("toolkit.telemetry.enabled", False)

    service = Service(executable_path="/usr/local/bin/geckodriver")
    driver = webdriver.Firefox(options=options, service=service)

    try:
        driver.set_page_load_timeout(30)
        driver.get(FINGERPRINT_URL)
        time.sleep(3)
        # JSON viewer 已停用，body 內容就是原始 JSON
        body_text = driver.find_element("tag name", "body").text
        raw = json.loads(body_text)
    finally:
        driver.quit()

    # 取得 Firefox 版本
    firefox_version = ""
    ua = raw.get("user_agent", "")
    if "Firefox/" in ua:
        firefox_version = ua.split("Firefox/")[-1].split(" ")[0]

    # 組裝 JA3 string
    ja3_str = raw.get("tls", {}).get("ja3", "")
    ja3_hash = raw.get("tls", {}).get("ja3_hash", "")

    # 組裝 Akamai (HTTP/2) fingerprint
    akamai_str = raw.get("http2", {}).get("akamai_fingerprint", "")
    akamai_hash = raw.get("http2", {}).get("akamai_fingerprint_hash", "")

    result = {
        "name": f"firefox_esr_{firefox_version}" if firefox_version else "firefox_esr",
        "source": "local_firefox_esr",
        "extracted_at": datetime.now(TZ_UTC8).isoformat(),
        "user_agent": ua,
        "firefox_version": firefox_version,
        "ja3": ja3_str,
        "ja3_hash": ja3_hash,
        "akamai": akamai_str,
        "akamai_hash": akamai_hash,
        "tls_version": raw.get("tls", {}).get("version", ""),
        "http_version": raw.get("http_version", ""),
    }
    return result


def save_fingerprint(fp: dict):
    """追加寫入 fingerprints.json（不覆蓋舊資料）。"""
    existing = []
    if OUTPUT_FILE.exists():
        try:
            existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    # 如果已有同名指紋，更新而非重複加入
    updated = False
    for i, item in enumerate(existing):
        if item.get("name") == fp["name"]:
            existing[i] = fp
            updated = True
            break
    if not updated:
        existing.append(fp)

    OUTPUT_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已儲存到 {OUTPUT_FILE}（共 {len(existing)} 筆指紋）", file=sys.stderr)


def main():
    print("正在啟動 Firefox ESR 抓取指紋...", file=sys.stderr)
    fp = extract_fingerprint()
    print(json.dumps(fp, ensure_ascii=False, indent=2))
    save_fingerprint(fp)
    print("完成。", file=sys.stderr)


if __name__ == "__main__":
    main()
