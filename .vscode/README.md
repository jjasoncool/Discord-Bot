# VSCode 配置說明

## 解決 Pylance 無法解析容器中安裝的套件問題

### 問題描述
當你在 Docker 容器中開發時，VSCode 的 Pylance 可能無法識別容器環境中已經安裝的 Python 套件。

### 解決方案

#### 方法 1: 在 Discord Bot 容器中開發（推薦）

1. **安裝擴展**：`ms-vscode-remote.remote-containers`

2. **啟動容器**：
   - 重新開啟專案資料夾
   - 點擊 "Reopen in Container"
   - VSCode 會連接到 `discord-bot` 容器

**適用於**：開發 Discord bot 相關功能，可以調用 scraper API

#### 方法 2: 手動連接容器

如果你已經啟動了容器，也可以直接連接：

1. Ctrl+Shift+P → "Remote-Containers: Attach to Running Container"
2. 選擇你的容器（`discord-bot`）
3. 選擇工作目錄：`/app`

### 開發不同服務的建議

#### Discord Bot 開發
- 使用 Dev Containers 自動連接
- 在 `/app` 工作目錄下工作
- 可以發送 HTTP 請求到 `http://scraper:8000`

#### Scraper 開發
- 用 `Remote-Containers: Open Folder Locally` 打開 `src/scraper/` 文件進行編輯
- 或使用 Scraper Dev Container：點擊 "Reopen in Container" 選取 Scraper 環境
- 使用 Docker Compose 運行和測試

### 配置說明

專案支援兩個 Dev Container 環境，分別對應不同的服務。你可以根據開發需求選擇連接的容器：

#### `discord-bot` 開發環境
- **位置**：`.devcontainer/discord-bot/devcontainer.json`
- **用途**：專為 Discord Bot 開發優化，可以調用 Scraper API
- **配置**：
  ```json
  {
    "name": "Discord Bot",
    "dockerComposeFile": "../../docker-compose.yaml",
    "service": "discord-bot",
    "workspaceFolder": "/app"
  }
  ```

#### `scraper` 開發環境
- **位置**：`.devcontainer/scraper/devcontainer.json`
- **用途**：專為 Scraper API 開發優化
- **配置**：
  ```json
  {
    "name": "Scraper",
    "dockerComposeFile": "../../docker-compose.yaml",
    "service": "scraper",
    "workspaceFolder": "/app",
    "forwardPorts": [8000]
  }
  ```

#### `.vscode/settings.json`
```json
{
  "python.defaultInterpreterPath": "/usr/local/bin/python"
}
```

### 重要提醒

- **確保容器正在運行**：使用 `docker-compose ps` 檢查
- **兩個服務可同時運行**：Docker Compose 會自動管理網路連接
- **Scraper 服務不會被 Dev Containers 直接影響**

### 故障排除

如果仍然無法識別套件：

1. **檢查 Python 環境**：
   ```bash
   docker-compose exec discord-bot which python  # 應顯示 /usr/local/bin/python
   docker-compose exec discord-bot pip list      # 檢查已安裝套件
   ```

2. **重新載入 Pylance**：
   - Ctrl+Shift+P → "Python: Restart Language Server"

3. **清除 Dev Containers 快取**：
   - Ctrl+Shift+P → "Dev Containers: Clean"

這樣就能在容器環境中獲得完整的 Python 智慧提示和錯誤檢查功能。
