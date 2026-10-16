# 收工前的檢查都從這裡跑：`make check`＝lint＋完整測試。
# 測試要在容器裡跑（主機沒有 discord 等套件）；lint 與型別檢查在主機跑（工具在 requirements-dev.txt）。

CONTAINER ?= discord-bot
UNITTEST = python -m unittest discover -s test -t . -p 'test_*.py'

.PHONY: check test gate lint typecheck dev-tools

check: lint test

## 完整單元測試（容器內，約兩分鐘）
test:
	docker exec -w /app -e PYTHONDONTWRITEBYTECODE=1 $(CONTAINER) $(UNITTEST)

## 啟動 gate 跑的那一組（守衛、import 解析、設定載入，約 20 秒）
gate:
	docker exec -w /app -e APP_STARTUP_GATE=1 -e PYTHONDONTWRITEBYTECODE=1 $(CONTAINER) python -m test.gate

## lint（主機）：只開「一定是錯」的規則，設定在 pyproject.toml
lint:
	python3 -m ruff check src

## 型別檢查（主機；pyright 第一次執行會下載 node 執行檔）
typecheck:
	python3 -m pyright

## 裝開發工具到目前的 python 環境
dev-tools:
	python3 -m pip install -r requirements-dev.txt
