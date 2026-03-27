# Mulit_Items_Search_Tools_for_Ruten

## Render.com 部署

### 推薦方式：使用 Dockerfile（自動化部署）

1. 建立 Github 代碼庫，並 push 本專案全集檔案。
2. 進入 Render 控制台，新增一個 `Web Service`，選擇 `GitHub repository`。
3. 連接你的 repo，Render 會自動偵測 `Dockerfile` 並執行：
   - Build 階段：`docker build`（包含 `playwright install --with-deps chromium`）
   - Runtime：`uvicorn app:app --host 0.0.0.0 --port 8000`

**優勢**：
- Dockerfile 中明確安裝 Playwright 瀏覽器（無需每次檢查）
- 啟動速度快（瀏覽器已預備）
- 穩定可靠

### 備選方式：使用 render.yaml

如果 Render 未自動使用 Dockerfile，可用：
- `buildCommand`: `pip install -r requirements.txt && playwright install --with-deps chromium`
- `startCommand`: `uvicorn app:app --host 0.0.0.0 --port $PORT`

## 本地測試

```bash
pip install -r requirements.txt
playwright install --with-deps
uvicorn app:app --reload
# 訪問 http://localhost:8000
```

## 注意

- 本專案依賴 Playwright 的 Chromium
- Dockerfile 已明確安裝瀏覽器，Render 部署無需額外配置
- 若流量大或超時，可考慮限制輸入商品數上限或改寫成 queue 方式

