from fastapi import FastAPI, Request, Body
from fastapi.responses import HTMLResponse
from playwright.sync_api import sync_playwright
from urllib.parse import quote
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import time
import datetime
import os
from pathlib import Path
app = FastAPI()

# 執行緒池 (預設 4 個執行緒，可根據 CPU 核心數調整)
executor = ThreadPoolExecutor(max_workers=1)

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
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage", # 解決 Docker 記憶體限制問題
                "--disable-blink-features=AutomationControlled"]
        )
        try:
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            # 加入這行：攔截不需要的資源（圖片、字體、CSS）
            page.route("**/*.{png,jpg,jpeg,gif,css,svg,woff}", lambda route: route.abort())
            
            # 執行搜尋
            results = search_ruten_on_page(page, item, target_seller=target_seller)
            
            page.close()
            context.close()
        except Exception as e:
            print(f"Thread error for {item}: {e}")
        finally:
            browser.close()
    
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
    html = """
    <!DOCTYPE html>
<html>

<head>
  <meta charset="UTF-8">
  <title>露天商品抓取測試</title>
  <style>
    body {
      font-family: sans-serif;
      padding: 20px;
      line-height: 1.6;
    }

    .loading {
      color: #007bff;
      display: none;
      font-weight: bold;
      margin: 10px 0;
    }

    .seller-block {
      border: 1px solid #ddd;
      padding: 15px;
      margin-bottom: 20px;
      border-radius: 8px;
    }

    .seller-name {
      color: #d32f2f;
      border-bottom: 2px solid #eee;
      padding-bottom: 5px;
    }

    ul {
      list-style-type: none;
      padding-left: 0;
    }

    li {
      margin-bottom: 8px;
    }

    a {
      text-decoration: none;
      color: #0056b3;
    }

    a:hover {
      text-decoration: underline;
    }

    /* 卡片容器：自動適應寬度，每列最少 250px */
    .results-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
      gap: 20px;
      padding: 20px 0;
    }

    /* 單個卡片樣式 */
    .product-card {
      background: #fff;
      border-radius: 8px;
      border: 1px solid #eee;
      overflow: hidden;
      transition: transform 0.2s, box-shadow 0.2s;
      display: flex;
      flex-direction: column;
    }

    .product-card:hover {
      transform: translateY(-5px);
      box-shadow: 0 10px 20px rgba(0, 0, 0, 0.1);
    }

    /* 圖片容器：固定比例 1:1 */
    .card-img-wrapper {
      width: 100%;
      height: 150px;
      /* 你可以根據需求調整固定高度 */
      background: #f8f8f8;
      /* 背景色，預防透明圖或尺寸不足 */
      display: flex;
      /* 使用 Flexbox */
      justify-content: center;
      /* 水平置中 */
      align-items: center;
      /* 垂直置中 */
      overflow: hidden;
    }

    .card-img-wrapper img {
      height: 100%;
      /* 高度撐滿容器 */
      width: auto;
      /* 寬度自動縮放，保持比例 */
      max-width: 100%;
      /* 預防圖片過寬超出容器 */
      display: block;
    }

    /* 卡片內容區 */
    .card-content {
      padding: 15px;
      display: flex;
      flex-direction: column;
      flex-grow: 1;
    }

    .card-title {
      font-size: 0.95rem;
      color: #333;
      text-decoration: none;
      margin-bottom: 10px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      /* 最多顯示兩行文字 */
      -webkit-box-orient: vertical;
      overflow: hidden;
      height: 2.8rem;
      line-height: 1.4;
    }

    .card-price {
      font-size: 1.2rem;
      color: #e62117;
      font-weight: bold;
      margin-top: auto;
      /* 將價格推到底部 */
    }

    .seller-badge {
      font-size: 0.8rem;
      color: #666;
      background: #f0f0f0;
      padding: 2px 8px;
      border-radius: 10px;
      display: inline-block;
      margin-top: 5px;
    }

    /* 條列式容器 */
    .results-list {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 10px 0;
    }

    /* 單個條列項目 */
    .product-item {
      display: flex;
      background: #fff;
      border: 1px solid #eee;
      border-radius: 4px;
      overflow: hidden;
      transition: background 0.2s;
      height: 120px;
      /* 固定高度，讓條列整齊 */
    }

    .product-item:hover {
      background: #f9f9f9;
      border-color: #ddd;
    }

    /* 左側圖片區域：固定 100px 寬度 */
    .item-img-wrapper {
      width: 100px;
      height: 100px;
      background: #f0f0f0;
      display: flex;
      justify-content: center;
      /* 水平置中 */
      align-items: center;
      /* 垂直置中 */
      flex-shrink: 0;
      /* 防止被壓縮 */
    }

    .item-img-wrapper img {
      width: auto;
      /* 高度撐滿 */
      max-height: 100%;
      /* 寬度隨比例 */
      max-width: 100%;
      /* 確保不超出 150px */
      display: block;
    }

    /* 右側資訊區域 */
    .item-info {
      padding: 12px 15px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      /* 讓標題在頂部，價格在底部 */
      flex-grow: 1;
      min-width: 0;
      /* 防止長文字撐破 Flex 容器 */
    }

    .item-title {
      font-size: 1rem;
      color: #333;
      text-decoration: none;
      font-weight: 500;
      line-height: 1.4;
      /* 多行截斷 */
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .item-detail {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
    }

    .item-price {
      font-size: 1.2rem;
      color: #d00;
      font-weight: bold;
    }

    .item-seller-tag {
      font-size: 0.8rem;
      color: #777;
      background: #eee;
      padding: 2px 8px;
      border-radius: 3px;
    }
  </style>
</head>

<body>
  <h1>露天多商品搜尋 (JSON 版, Multi-Threaded)</h1>
  <div>
    <textarea id="items" rows="5" placeholder="每行輸入一個商品名稱" style="width: 100%; max-width: 500px;"></textarea><br>
    <input type="text" id="seller" placeholder="指定賣家帳號 (可選)" style="width: 200px; margin: 10px 0;"><br>
    <button id="searchBtn" onclick="doSearch()">開始搜尋</button>
  </div>

  <div id="loadingStatus" class="loading">正在搜尋並處理資料，請稍候...</div>
  <div id="resultsContainer" style="margin-top: 20px;"></div>

  <script>
    async function doSearch() {
      const itemsVal = document.getElementById('items').value;
      const sellerVal = document.getElementById('seller').value;
      const btn = document.getElementById('searchBtn');
      const loading = document.getElementById('loadingStatus');
      const container = document.getElementById('resultsContainer');

      if (!itemsVal.trim()) return alert("請輸入商品名稱！");

      // UI 狀態切換
      btn.disabled = true;
      loading.style.display = 'block';
      container.innerHTML = '';

      try {
        const response = await fetch('/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: itemsVal, seller: sellerVal })
        });

        const data = await response.json();
        renderResults(data.results);
      } catch (err) {
        console.error(err);
        alert("搜尋失敗，請檢查後端連線。");
      } finally {
        btn.disabled = false;
        loading.style.display = 'none';
      }
    }

    function renderResults(results) {
      const container = document.getElementById('resultsContainer');
      const entries = Object.entries(results);

      if (entries.length === 0) {
        container.innerHTML = '<p>查無相關商品。</p>';
        return;
      }
      
      entries.forEach(([seller, items]) => {
        const sellerSection = document.createElement('div');
        sellerSection.style.marginBottom = '30px';

        // 賣家標題
        sellerSection.innerHTML = `
        <h2 style="font-size: 1.2rem; color: #444; border-bottom: 2px solid #0066cc; padding-bottom: 5px; margin-bottom: 15px;">
            ${seller} <span style="font-size: 0.9rem; color: #999; font-weight: normal;">(${items.length} 件商品)</span>
        </h2>
        <div class="results-list"></div>
    `;
        container.appendChild(sellerSection);

        const listContainer = sellerSection.querySelector('.results-list');

        // 產生條列 HTML
        listContainer.innerHTML = items.map(item => {
          const imgSrc = item.image || "https://via.placeholder.com/150?text=No+Image";

          return `
            <div class="product-item">
                <div class="item-img-wrapper">
                    <img src="${imgSrc}" alt="${item.title}" loading="lazy">
                </div>
                <div class="item-info">
                    <a href="${item.link}" target="_blank" class="item-title" title="${item.title}">
                        ${item.title}
                    </a>
                    <div class="item-detail">
                        <span class="item-price">$${item.price}</span>
                    </div>
                </div>
            </div>
        `;
        }).join('');
      });
    }
  </script>
</body>

</html>
    """
    return HTMLResponse(content=html)

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