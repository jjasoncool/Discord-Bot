# 爬蟲專案說明

## 專案結構

```
src/scraper/
├── main.py                 # 主程式入口點
├── config.py              # 設定檔
├── container.py           # 依賴注入容器
├── requirements.txt       # Python 套件依賴
├── alembic.ini            # Alembic 設定檔
├── .env.example           # 環境變數範例檔
├── db/                    # 資料庫層
│   ├── __init__.py
│   ├── models.py          # 資料庫模型
│   ├── database.py        # 資料庫管理器
│   └── migrations/        # Alembic 遷移檔案
│       ├── env.py         # Alembic 環境設定
│       └── script.py.mako # 遷移腳本模板
├── services/              # 服務層
│   ├── __init__.py
│   ├── api_service.py     # API 請求服務
│   ├── file_service.py    # 檔案處理服務
│   └── scraper_service.py # 爬蟲核心服務
└── utils/                 # 工具函式
    ├── __init__.py
    ├── datetime_utils.py  # 日期時間工具
    └── logger.py          # 日誌工具
```

## 架構設計

### 分層架構
- **資料層 (Database)**: `db/` 資料夾，包含資料庫操作和 ORM 模型
- **服務層 (Services)**: `services/` 資料夾，處理具體業務邏輯
- **工具層 (Utils)**: `utils/` 資料夾，共用工具函式
- **設定層 (Config)**: 設定管理

### 設計模式
- **依賴注入**: 使用 `ServiceContainer` 管理依賴
- **單一職責**: 每個類別都有明確的職責
- **開放封閉**: 易於擴展新功能

## 使用方式

### 1. 安裝依賴
```bash
pip install -r requirements.txt
```

### 2. 設定環境變數
複製範例檔案並修改設定：
```bash
cp .env.example .env
```

編輯 `.env` 檔案：
```env
# 資料庫連線設定
DATABASE_URL=sqlite:///./articles.db

# 輸出目錄設定
OUTPUT_DIR=data

# 日誌設定
LOG_LEVEL=INFO
LOG_FILE=/logs/scraper.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5
```

**資料庫連線範例**：
- SQLite: `sqlite:///./articles.db`
- PostgreSQL: `postgresql://user:pass@localhost:5432/dbname`
- MySQL: `mysql+pymysql://user:pass@localhost:3306/dbname`

**日誌設定說明**：
- `LOG_LEVEL`: 日誌級別 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `LOG_FILE`: 日誌檔案路徑
- `LOG_MAX_BYTES`: 單個日誌檔案最大大小（預設 10MB）
- `LOG_BACKUP_COUNT`: 保留的舊日誌檔案數量（預設 5 個）

### 3. 執行程式
```bash
python main.py
```

### 4. Docker 部署
```bash
# 建立映像
docker build -t scraper .

# 執行容器（基本設定）
docker run -e DATABASE_URL="sqlite:///./articles.db" -e OUTPUT_DIR="data" scraper

# 執行容器（完整設定含日誌）
docker run \
  -e DATABASE_URL="sqlite:///./articles.db" \
  -e OUTPUT_DIR="data" \
  -e LOG_LEVEL="INFO" \
  -e LOG_FILE="/logs/scraper.log" \
  -v /host/logs:/logs \
  -v /host/data:/app/data \
  scraper
```

## 主要功能

1. **增量抓取**: 只抓取新增的文章，避免重複
2. **錯誤處理**: 完善的錯誤處理機制
3. **定時執行**: 每小時自動執行一次
4. **資料備份**: 同時支援資料庫和 JSON 檔案儲存
5. **延遲控制**: 避免被網站封鎖
6. **效能優化**: JSON 檔案支援 ID 過濾和增量追加

## 維護指南

### 添加新功能
1. 在 `services/` 目錄新增服務類別
2. 在 `container.py` 註冊新服務
3. 在主要服務中注入使用

### 修改設定
編輯 `config.py` 檔案中的相關設定

### 資料庫遷移
使用 Alembic 進行資料庫版本控制：

#### 常用 Alembic 指令說明

- **建立遷移檔案**：
  ```bash
  python -m alembic revision --autogenerate -m "描述變更內容"
  ```
  這個指令會自動比較當前資料庫模型與實際資料庫結構的差異，生成遷移檔案。

- **執行遷移**：
  ```bash
  python -m alembic upgrade head
  ```
  將所有未執行的遷移套用到資料庫。

- **查看遷移歷史**：
  ```bash
  python -m alembic history
  ```
  顯示所有遷移檔案的歷史記錄。

- **回退遷移**：
  ```bash
  python -m alembic downgrade -1
  ```
  回退到前一個遷移版本。

- **標記當前版本**：
  ```bash
  python -m alembic stamp <revision_id>
  ```
  將資料庫標記為指定的遷移版本（不執行遷移）。

#### 遷移檔案位置
遷移檔案會自動生成在 `db/migrations/versions/` 目錄下，每個檔案都包含：
- 版本號（時間戳）
- 升級函式（upgrade）
- 降級函式（downgrade）

#### 注意事項
- 遷移檔案一旦執行後不應手動修改
- 如果需要修改資料庫結構，應建立新的遷移檔案
- 在生產環境執行遷移前，務必先在測試環境驗證

### 錯誤排查
1. 查看程式日誌輸出，大部分錯誤都有詳細的上下文資訊
2. 檢查日誌檔案：`/logs/scraper.log`（預設位置）
3. 調整日誌級別為 `DEBUG` 以獲得更詳細的資訊
4. 確認環境變數設定是否正確

### 日誌管理
- 日誌會同時輸出到控制台和檔案
- 支援日誌輪替，避免檔案過大
- 可透過環境變數調整日誌級別和檔案位置
- 建議在生產環境使用 `INFO` 級別，開發時使用 `DEBUG`

## 效能優化

### JSON 檔案處理
- 使用 `load_json_with_filter()` 按 ID 過濾載入
- 使用 `append_to_json()` 增量追加避免重複
- 使用 `get_file_size_mb()` 監控檔案大小

### 資料庫查詢
- 利用索引提升查詢效能
- 使用批次操作減少資料庫連線次數

## 最佳實踐

- ✅ 職責分離
- ✅ 依賴注入
- ✅ 錯誤處理
- ✅ 統一日誌記錄
- ✅ 資源管理
- ✅ 型別提示
- ✅ 文件註解
- ✅ 環境變數管理
- ✅ 容器化部署
- ✅ 日誌輪替與管理
