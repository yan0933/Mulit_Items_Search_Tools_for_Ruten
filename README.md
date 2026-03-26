# Mulit_Items_Search_Tools_for_Ruten

## Render.com 部署

1. 建立 Github 代碼庫，並 push 本專案全集檔案。
2. 進入 Render 控制台，新增一個 `Web Service`，選擇 `Python`。
3. 取用 `render.yaml` 管理部署；render 會從此檔讀取：
   - `buildCommand`: `pip install -r requirements.txt && playwright install --with-deps`
   - `startCommand`: `uvicorn app:app --host 0.0.0.0 --port $PORT`
4. 若要自行測試，先本地執行：
   - `pip install -r requirements.txt`
   - `playwright install --with-deps`
   - `uvicorn app:app --host 0.0.0.0 --port 8000`

## 注意

- 本專案依賴 Playwright 的 Chromium，因此在 Render 運行時，`playwright install --with-deps` 一定要執行。
- 若流量大、或超時問題可考慮限制輸入商品數上限，或改寫成 queue + scheduling 方式。

