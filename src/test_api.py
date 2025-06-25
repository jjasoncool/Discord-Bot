"""
測試 Scraper API 連接
"""
import asyncio
import aiohttp
import json
import os

async def test_api_connection():
    """測試 API 連接"""
    # 根據環境選擇 URL

    # 如果在 Docker 環境中，使用容器名稱
    # 如果在本地環境，使用 localhost
    if os.path.exists('/.dockerenv'):
        base_url = "http://scraper:8000"
        print("🐳 在 Docker 環境中，使用容器網路")
    else:
        base_url = "http://localhost:8000"
        print("💻 在本地環境中，使用 localhost")

    print(f"🔗 API URL: {base_url}")

    # 測試健康檢查
    try:
        async with aiohttp.ClientSession() as session:
            print("🔍 測試健康檢查端點...")
            async with session.get(f"{base_url}/health", timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ 健康檢查成功: {data}")
                else:
                    print(f"❌ 健康檢查失敗，狀態碼: {response.status}")

    except Exception as e:
        print(f"❌ 健康檢查請求失敗: {e}")

    # 測試文章 API
    try:
        async with aiohttp.ClientSession() as session:
            print("\n🔍 測試文章 API...")
            params = {"days": 3, "limit": 10}
            async with session.get(f"{base_url}/api/articles/recent", params=params, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('success'):
                        print(f"✅ 文章 API 成功，取得 {len(data['articles'])} 篇文章")

                        # 顯示前3篇文章
                        for i, article in enumerate(data['articles'][:3]):
                            print(f"  {i+1}. ID: {article['article_id']} - {article['article_title'][:50]}...")
                    else:
                        print(f"❌ 文章 API 回應失敗: {data.get('message')}")
                else:
                    print(f"❌ 文章 API 請求失敗，狀態碼: {response.status}")
                    response_text = await response.text()
                    print(f"    回應內容: {response_text[:200]}...")

    except Exception as e:
        print(f"❌ 文章 API 請求失敗: {e}")

    # 測試 Discord 專用 API
    try:
        async with aiohttp.ClientSession() as session:
            print("\n🔍 測試 Discord 專用 API...")
            params = {"days": 3, "limit": 10}
            async with session.get(f"{base_url}/api/articles/discord", params=params, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('success'):
                        print(f"✅ Discord API 成功，取得 {len(data['articles'])} 篇有完整內容的文章")

                        # 顯示前3篇文章的詳細資訊
                        for i, article in enumerate(data['articles'][:3]):
                            print(f"  {i+1}. ID: {article['article_id']} - {article['article_title'][:50]}...")
                            if article.get('article_content_full'):
                                print(f"     ✅ 有完整內容 ({len(article['article_content_full'])} 字)")
                            if article.get('article_type_name'):
                                print(f"     📂 類型: {article['article_type_name']}")
                    else:
                        print(f"❌ Discord API 回應失敗: {data.get('message')}")
                else:
                    print(f"❌ Discord API 請求失敗，狀態碼: {response.status}")
                    response_text = await response.text()
                    print(f"    回應內容: {response_text[:200]}...")

    except Exception as e:
        print(f"❌ Discord API 請求失敗: {e}")

    # 測試調試端點
    try:
        async with aiohttp.ClientSession() as session:
            print("\n🔍 測試調試端點...")
            async with session.get(f"{base_url}/api/debug/tables", timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ 調試端點成功")
                    print(f"   📊 主表文章數: {data['table_counts']['article_menus']}")
                    print(f"   📊 副表文章數: {data['table_counts']['article_details']}")
                    print(f"   📊 有完整內容的文章數: {data['table_counts']['joined_records']}")

                    if data.get('latest_main_article'):
                        latest = data['latest_main_article']
                        print(f"   📄 最新主表文章: ID {latest['id']} - {latest.get('title', 'N/A')[:30]}...")

                    if data.get('latest_detail_article'):
                        latest = data['latest_detail_article']
                        print(f"   📄 最新副表文章: ID {latest['id']} - {latest.get('title', 'N/A')[:30]}...")
                else:
                    print(f"❌ 調試端點失敗，狀態碼: {response.status}")

    except Exception as e:
        print(f"❌ 調試端點請求失敗: {e}")

if __name__ == "__main__":
    print("🚀 開始測試 Scraper API 連接...\n")
    asyncio.run(test_api_connection())
    print("\n✅ 測試完成")
