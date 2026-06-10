import time
import random
import re
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ================= КОНФИГУРАЦИЯ =================
N8N_WEBHOOK_URL = "https://n8n-lolcfinance-n8n.ov4co6.easypanel.host/webhook-test/somon-parser"

# Настройки бесплатного ScraperAPI
PROXY_SERVER = "http://proxy-server.scraperapi.com:8001" 
PROXY_USERNAME = "scraperapi.country_code=ru"
PROXY_PASSWORD = "7bcaf0b4733c9417fab59fbe5fa8e711"

BASE_URL = "https://somon.tj"
TARGET_URL = "https://somon.tj/nedvuzhimost/kvartiry/"
# =================================================

def random_delay(min_sec=3.0, max_sec=6.0):
    time.sleep(random.uniform(min_sec, max_sec))

def extract_platform_id(url):
    match = re.search(r'-(\d+)/?$', url)
    return f"somon_{match.group(1)}" if match else f"somon_{random.randint(100000, 999999)}"

def clean_price(price_str):
    digits = re.sub(r'[^\d]', '', price_str) if price_str else ""
    return int(digits) if digits else 0

def main():
    results = []

    with sync_playwright() as p:
        # Запускаем браузер
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print(f"[*] Открываем главную страницу: {TARGET_URL}")
        try:
            # Изменили логику ожидания
            page.goto(TARGET_URL, timeout=60000)
            page.wait_for_load_state('domcontentloaded')
            print("[*] Страница загрузилась. Ждем 5 секунд для подгрузки скриптов Сомона...")
            time.sleep(5) 
            
            # ВЫВОДИМ ЗАГОЛОВОК СТРАНИЦЫ (чтобы понять, не капча ли там)
            page_title = page.title()
            print(f"[*] ЗАГОЛОВОК СТРАНИЦЫ: {page_title}")
            
        except Exception as e:
            print(f"[!] Ошибка загрузки: {e}")
            browser.close()
            return

        print("[*] Ищем ссылки на квартиры...")
        # Улучшенный поиск ссылок
        links_locators = page.locator('a[href*="/adv/"]').all()
        
        ad_urls = set()
        for link in links_locators:
            href = link.get_attribute('href')
            if href and re.search(r'-(\d+)/?$', href):
                full_url = BASE_URL + href if href.startswith('/') else href
                ad_urls.add(full_url)

        ad_urls = list(ad_urls)[:3] # СОБЕРЕМ ПОКА ТОЛЬКО 3 КВАРТИРЫ ДЛЯ ТЕСТА
        print(f"[*] Найдено уникальных объявлений: {len(ad_urls)}")

        for idx, url in enumerate(ad_urls, 1):
            print(f"\n[{idx}/{len(ad_urls)}] Обработка: {url}")
            try:
                page.goto(url, timeout=45000)
                time.sleep(3)
            except:
                continue

            item_data = {
                "platform_id": extract_platform_id(url),
                "url": url,
                "title": "", "price_tjs": 0, "description": "", "phone": ""
            }

            try: item_data["title"] = page.locator('h1').first.inner_text().strip()
            except: pass

            try: item_data["price_tjs"] = clean_price(page.locator('.announcement-price, .item-price, [data-meta-id="price"]').first.inner_text())
            except: pass

            print(f"[+] Собрано: {item_data['title']} | {item_data['price_tjs']} TJS")
            results.append(item_data)

        browser.close()

    if results:
        print(f"\n[*] Отправка {len(results)} записей на Webhook n8n...")
        try:
            res = requests.post(N8N_WEBHOOK_URL, json=results, timeout=15)
            print("[+] Успешно отправлено! Статус:", res.status_code)
        except Exception as e:
            print(f"[!] Ошибка отправки: {e}")
    else:
        print("[-] Нет данных для отправки.")

if __name__ == "__main__":
    main()
