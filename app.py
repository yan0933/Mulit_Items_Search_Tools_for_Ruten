from fastapi import FastAPI, Request, Body
from fastapi.responses import HTMLResponse, FileResponse
from urllib.parse import quote
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright
import re
import datetime
from pathlib import Path

app = FastAPI()

# 執行緒池 (預設 4 個執行緒，可根據 CPU 核心數調整)
executor = ThreadPoolExecutor(max_workers=1)

# ---- 啟動時簡單驗證 ----
@app.on_event("startup")
async def startup_event():
    print("[STARTUP] 應用程式已啟動")
    print("[STARTUP] Playwright 環境檢查...")
    try:
        with sync_playwright() as p:
            print("[STARTUP] ✓ Chromium 可用")
    except Exception as e:
        print(f"[STARTUP] ⚠ Playwright/Chromium 檢查失敗: {e}")

# ---- 讀取前置符號檔 ----
symbol_pairs = []
try:
    with open("prefix_symbols.txt", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if len(line) >= 2:
                symbol_pairs.append(line)
except FileNotFoundError:
    symbol_pairs = ["【】", "[]"]

start_chars = "".join([p[0] for p in symbol_pairs])
end_chars = "".join([p[1] for p in symbol_pairs])
prefix_pattern = rf"^[{re.escape(start_chars)}](.+?)[{re.escape(end_chars)}]+"

# ---- 工作函數：在單個執行緒中執行完整搜尋（包括創建瀏覽器) ----
def search_item_thread(item, target_seller=None):
    """在單個執行緒中為一個商品進行完整搜尋"""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] 開始處理商品: {item}")
    
    results = []
    
    # 每個執行緒創建自己的瀏覽器實例
    try:
        with sync_playwright() as p:
            print(f"[{now}] Playwright 已初始化，準備啟動 Chromium...")
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            print(f"[{now}] Chromium 已啟動")
            try:
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                
                # 攔截不需要的資源
                page.route("**/*.{png,jpg,jpeg,gif,css,svg,woff}", lambda route: route.abort())
                
                # 執行搜尋
                results = search_ruten_on_page(page, item, target_seller=target_seller)
                
                page.close()
                context.close()
            except Exception as e:
                print(f"[{now}] 搜尋出錯 {item}: {e}")
            finally:
                browser.close()
    except Exception as e:
        print(f"[{now}] Playwright 初始化失敗: {e}")
    
    end = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{end}] 完成處理商品: {item}")
    
    return results
def search_ruten_on_page(page, keyword, target_seller=None):
    results = []
    
    # 所有的選擇器與變數定義完全保留
    url = f"https://www.ruten.com.tw/find/?q={quote(keyword)}"
    productSelector = ".product-item"
    priceSelector = "div.price-range-container span.rt-text-price.rt-text-bold.text-price-dollar"

    if target_seller:
        url = f"https://www.ruten.com.tw/store/{target_seller}/find?q={quote(keyword)}"
        productSelector = ".quint-goods"        
        priceSelector = "div.price-range-container span.rt-text-price.text-price-dollar"

    try:
        # 1. 前往網頁
        page.goto(url, wait_until="domcontentloaded")

        # 2. 修改點：將 state 改為 "attached"
        # 這代表「只要 HTML 標籤出現就開工」，不管它現在是否在螢幕內或是否透明
        page.wait_for_selector(productSelector, state="attached", timeout=5000)
        
        # 3. 滾動以觸發後續的圖片加載
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        
        # 4. 滾動後給予 1-2 秒讓資料穩定（這段不能省，因為露天的價格有時是動態填入的）
        page.wait_for_timeout(1500)
        cards = page.query_selector_all(productSelector)
        for card in cards:
            try:                
                title_el = card.query_selector("p.rt-product-card-name")
                title_full = title_el.inner_text().strip() if title_el else ""
                if not title_full: continue

                img_el = card.query_selector("img.rt-product-card-img")
                img_url = img_el.get_attribute("src") if img_el else ""
                
                price_el = card.query_selector(priceSelector)
                price_text = price_el.inner_text().strip() if price_el else "0"
                price = int("".join(filter(str.isdigit, price_text))) if price_text else 0
                if price >= 99999: continue
                
                # 保留你原本的賣家名稱提取 logic
                match = re.match(prefix_pattern, title_full)
                if match:
                    seller = match.group(1)
                    title = re.sub(prefix_pattern, "", title_full).strip()
                else:
                    seller = target_seller if target_seller else "未知賣家"
                    title = title_full.strip()

                link_el = card.query_selector("a.rt-product-card-name-wrap")
                link = link_el.get_attribute("href") if link_el else "#"

                results.append({
                    "title": title,
                    "price": price,
                    "seller": seller,
                    "link": link,
                    "image": img_url
                })
            except:
                continue
    except Exception as e:
        print(f"Error searching {keyword}: {e}")

    return results

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    template_path = Path(__file__).parent / "index.html"
    return FileResponse(template_path, media_type="text/html")

# ---- 改為多執行緒 API 入口 (使用 ThreadPoolExecutor 並行搜尋) ----
@app.post("/search")
def api_search(
    items: str = Body(..., embed=True), 
    seller: str = Body(None, embed=True)
):
    item_list = [i.strip() for i in items.split("\n") if i.strip()]
    item_list = list(dict.fromkeys(item_list))

    all_results = []

    # 使用 ThreadPoolExecutor 並行執行搜尋
    futures = []
    for item in item_list:
        # 将每个搜索任务提交到执行线程池
        future = executor.submit(search_item_thread, item, target_seller=seller)
        futures.append(future)
    
    # 收集所有搜尋結果
    for future in as_completed(futures):
        try:
            results = future.result()
            all_results.extend(results)
        except Exception as e:
            print(f"Error in thread: {e}")

    # ---- 後續分類整理與排序邏輯 ----
    seller_data = defaultdict(list)
    for product in all_results:
        seller_data[product["seller"]].append({
            "title": product["title"],
            "price": product["price"],
            "link": product["link"],
            "image": product.get("image", "")
        })

    sorted_sellers = sorted(
        seller_data.items(),
        key=lambda x: (x[0] == "未知賣家", -len(x[1]))
    )

    try:
        # 直接使用 dict() 轉換 tuple list 是最安全的
        final_results = dict(sorted_sellers)
    except Exception as e:
        print(f"轉換字典失敗: {e}")
        # 如果失敗，至少回傳原始列表避免 ASGI 崩潰
        final_results = {str(k): v for k, v in sorted_sellers}

    return {"results": final_results}