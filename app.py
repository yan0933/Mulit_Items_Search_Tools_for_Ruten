from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from playwright.sync_api import sync_playwright
from urllib.parse import quote
from collections import defaultdict
import re
import time

app = FastAPI()
templates = Jinja2Templates(directory="templates")
# ---- 讀取前置符號檔 ----
symbol_pairs = []
with open("prefix_symbols.txt", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if len(line) >= 2:
            symbol_pairs.append(line)

start_chars = "".join([p[0] for p in symbol_pairs])
end_chars = "".join([p[1] for p in symbol_pairs])
prefix_pattern = rf"^[{re.escape(start_chars)}](.+?)[{re.escape(end_chars)}]+"

def search_ruten(keyword, target_seller=None):
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu"
            ]
        )
        page = browser.new_page(
            viewport={"width":1280, "height":800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
        )


        # 一般多產品搜尋
        url = f"https://www.ruten.com.tw/find/?q={quote(keyword)}"
        productSelector = ".product-item"
        waittime = 10000
        priceSelector = "div.price-range-container span.rt-text-price.rt-text-bold.text-price-dollar"

        # 如果指定賣家，使用賣家專屬搜尋 URL
        if target_seller:
            url = f"https://www.ruten.com.tw/store/{target_seller}/find?q={quote(keyword)}"
            productSelector = ".quint-goods"
            waittime = 1000
            priceSelector = "div.price-range-container span.rt-text-price.text-price-dollar"

        page.goto(url)

        # 等待整頁渲染完成
        print(f"搜尋 {keyword}，等待頁面渲染 {waittime} 毫秒...")
        page.wait_for_timeout(waittime)

        # 抓商品卡片
        cards = page.query_selector_all(productSelector)
        if not cards:
            print(f"{keyword} 商品卡片沒出現")
            browser.close()
            return []

        print(f"搜尋 '{keyword}' 抓到商品數量: {len(cards)}")

        for card in cards:
            try:
                # 商品名稱
                title_el = card.query_selector("p.rt-product-card-name")
                title_full = ""
                for i in range(15):  # 最多等待 7.5 秒
                    title_full = title_el.inner_text().strip()
                    if title_full:
                        break
                if not title_full:
                    continue

                # 價格
                price_el = card.query_selector(priceSelector)
                price_text = price_el.inner_text().strip() if price_el else "0"
                price = int("".join(filter(str.isdigit, price_text))) if price_text else 0
                if price >= 99999:
                    continue
                
                # 賣場名稱
                # seller = target_seller if target_seller else "未知賣家"
                match = re.match(prefix_pattern, title_full)
                if match:
                    seller = match.group(1)
                    title = re.sub(prefix_pattern, "", title_full).strip()  # 去掉前置字
                else:
                    seller = target_seller if target_seller else "未知賣家"
                    title = title_full.strip()

                # 商品連結
                link_el = card.query_selector("a.rt-product-card-name-wrap")
                link = link_el.get_attribute("href") if link_el else "#"

                # 去掉賣場前綴
                # title = re.sub(r"^【.+?】", "", title_full).strip()
                title = title_full

                # print(f"商品: {title} | 價格: {price} | 賣場: {seller}")

                results.append({
                    "title": title,
                    "price": price,
                    "seller": seller,
                    "link": link
                })
            except Exception as e:
                print("抓取商品錯誤:", e)
                continue

        browser.close()
    return results

# ---- FastAPI 前端 ----
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "results": None})

@app.post("/", response_class=HTMLResponse)
def search(request: Request, items: str = Form(...), seller: str = Form(None)):
    # 取得商品清單，去重
    item_list = [i.strip() for i in items.split("\n") if i.strip()]
    item_list = list(dict.fromkeys(item_list))  # 保留順序

    all_results = []

    # 抓取每個商品
    for item in item_list:
        results = search_ruten(item, target_seller=seller)
        all_results.extend(results)
        time.sleep(2)

    # 依賣場分類
    seller_data = defaultdict(list)
    for product in all_results:
        seller_name = product["seller"]
        seller_data[seller_name].append({
            "title": product["title"],
            "price": product["price"],
            "link": product["link"]
        })

    # 排序：未知賣家放最後，其他依商品數量降序
    sorted_sellers = sorted(
        seller_data.items(),
        key=lambda x: (x[0] == "未知賣家", -len(x[1]))
    )

    # 將排序結果轉成 dict，方便模板使用
    sorted_seller_data = {seller: items for seller, items in sorted_sellers}

    return templates.TemplateResponse("index.html", {
        "request": request,
        "results": sorted_seller_data
    })