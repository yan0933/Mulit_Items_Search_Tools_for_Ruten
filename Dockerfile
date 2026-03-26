# 使用官方 Playwright Python 鏡像，省去自行安裝瀏覽器的麻煩
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

# 設定工作目錄
WORKDIR /app

# 複製需求文件並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案原始碼
COPY . .

# 環境變數設定
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

# 暴露 FastAPI 預設埠
EXPOSE 8000

# 啟動指令 (使用 0.0.0.0 綁定埠號)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]