from fastapi import FastAPI, Request, Body
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

def search_ruten(keyword, target_seller=None):
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
        )

        url = f"https://www.ruten.com.tw/find/?q={quote(keyword)}"
        productSelector = ".product-item"
        waittime = 8000
        priceSelector = "div.price-range-container span.rt-text-price.rt-text-bold.text-price-dollar"

        if target_seller:
            url = f"https://www.ruten.com.tw/store/{target_seller}/find?q={quote(keyword)}"
            productSelector = ".quint-goods"
            waittime = 2000
            priceSelector = "div.price-range-container span.rt-text-price.text-price-dollar"

        page.goto(url)
        page.wait_for_timeout(waittime)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

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
        browser.close()
    return results

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """渲染主要頁面模板"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/search")
def api_search(
    items: str = Body(..., embed=True), 
    seller: str = Body(None, embed=True)
):
    """接收 JSON 請求並回傳搜尋結果 JSON"""
    item_list = [i.strip() for i in items.split("\n") if i.strip()]
    item_list = list(dict.fromkeys(item_list))

    all_results = []
    for item in item_list:
        results = search_ruten(item, target_seller=seller)
        all_results.extend(results)
        time.sleep(1)

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

    return {"results": {k: v for k, v in sorted_sellers}}