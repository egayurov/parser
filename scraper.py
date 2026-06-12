import time
import random
import re
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ================= КОНФИГУРАЦИЯ =================
N8N_WEBHOOK_URL = "https://n8n-lolcfinance-n8n.ov4co6.easypanel.host/webhook/somon-parser"

PROXY_SERVER = "http://pool.proxy.market:10005"  # Оставляем рабочий порт
PROXY_USERNAME = "caVdrQpUyf"
PROXY_PASSWORD = "20AKQfSLTR"

BASE_URL = "https://somon.tj"
TARGET_URL = "https://somon.tj/nedvizhimost/prodazha-kvartir/"
# =================================================

def random_delay(min_sec=3.0, max_sec=6.0):
    time.sleep(random.uniform(min_sec, max_sec))

def clean_price(price_str):
    if not price_str: return 0
    digits = re.sub(r'[^\d]', '', price_str)
    return int(digits) if digits else 0

def extract_platform_id(url):
    match = re.search(r'-(\d+)/?$', url)
    return f"somon_{match.group(1)}" if match else f"somon_{random.randint(100000, 999999)}"

def main():
    results = []

    with sync_playwright() as p:
        proxy_settings = {"server": PROXY_SERVER, "username": PROXY_USERNAME, "password": PROXY_PASSWORD}

        browser = p.chromium.launch(
            headless=True,
            args=[f"--proxy-server={PROXY_SERVER}"]
        )
        context = browser.new_context(
            proxy=proxy_settings,
            ignore_https_errors=True,
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()

        print(f"[*] Открываем раздел продажа квартир...")
        
        max_retries = 3
        page_loaded = False
        
        for attempt in range(max_retries):
            try:
                page.goto(TARGET_URL, timeout=90000)
                # ЖДЕМ появления хоть одной ссылки на квартиру
                page.wait_for_selector('a[href*="/adv/"]', timeout=30000)
                print(f"[*] УСПЕХ! ЗАГОЛОВОК: {page.title()}")
                page_loaded = True
                break
            except Exception as e:
                print(f"   [!] Ошибка загрузки главной (Попытка {attempt+1}): {e}")
                time.sleep(5)

        if not page_loaded:
            print("[-] Не смогли пробить главную страницу.")
            browser.close()
            return

        print("[*] Собираем ссылки...")
        links_locators = page.locator('a[href*="/adv/"]').all()
        
        ad_urls = set()
        for link in links_locators:
            href = link.get_attribute('href')
            if href and re.search(r'-(\d+)/?$', href):
                ad_urls.add(BASE_URL + href if href.startswith('/') else href)

        ad_urls = list(ad_urls)[:5] 
        print(f"[*] Найдено квартир для парсинга: {len(ad_urls)}")

        for idx, url in enumerate(ad_urls, 1):
            print(f"\n[{idx}/{len(ad_urls)}] Заходим: {url}")
            
            try:
                page.goto(url, timeout=60000)
                # ЖЕСТКО ЖДЕМ появления заголовка и цены
                page.wait_for_selector('h1', timeout=20000)
                time.sleep(3) # Даем еще 3 секунды на подгрузку скриптов Сомона
            except:
                print("   [!] Страница квартиры не прогрузилась, пропускаем.")
                continue

            item_data = {
                "platform_id": extract_platform_id(url), "url": url, "title": "",
                "price_tjs": 0, "description": "", "phone": "", "main_image": "",
                "rooms": None, "area_sqm": None, "floor": None
            }

            try: item_data["title"] = page.locator('h1').first.inner_text().strip()
            except: pass

            try: item_data["price_tjs"] = clean_price(page.locator('.announcement-price, .item-price, [data-meta-id="price"]').first.inner_text())
            except: pass

            try: item_data["description"] = page.locator('.announcement-description, .item-description').first.inner_text().strip()
            except: pass

            try:
                chars_blocks = page.locator('ul.chars-list li, .characteristics-item').all()
                for char in chars_blocks:
                    text = char.inner_text().lower()
                    if 'комнат' in text: item_data["rooms"] = int(re.sub(r'[^\d]', '', text) or 0)
                    elif 'кв.м' in text or 'м²' in text: 
                        val = re.findall(r'\d+\.?\d*', text)
                        if val: item_data["area_sqm"] = float(val[0])
                    elif 'этаж' in text:
                        val = re.findall(r'\d+', text)
                        if val: item_data["floor"] = int(val[0])
            except: pass

            # КЛИК ПО ТЕЛЕФОНУ
            page.mouse.wheel(0, 500)
            random_delay(2, 4)

            try:
                phone_btn = page.locator('text="Показать", text="Телефон", .js-item-phone-button, .phone-button').first
                if phone_btn.is_visible():
                    phone_btn.click()
                    print("   [*] Нажали кнопку телефона, ждем загрузки номера...")
                    # Ждем, пока ссылка tel: появится в DOM-дереве
                    page.wait_for_selector('a[href^="tel:"], .phone-number', timeout=15000)
                    random_delay(1, 2)
                    
                    phone_link = page.locator('a[href^="tel:"]').first
                    if phone_link.is_visible():
                        item_data["phone"] = re.sub(r'[^\d+]', '', phone_link.get_attribute('href').replace('tel:', ''))
                    else:
                        item_data["phone"] = re.sub(r'[^\d+]', '', page.locator('.phone-number, .js-phone-number').first.inner_text())
            except:
                print("   [-] Кнопка телефона не найдена или номер не подгрузился.")

            print(f"   [+] Собран: {item_data['rooms']}-комн | {item_data['area_sqm']}м² | Этаж: {item_data['floor']} | Тел: {item_data['phone']}")
            results.append(item_data)

        browser.close()

    if results:
        print(f"\n[*] Отправка {len(results)} записей на Webhook n8n...")
        try:
            response = requests.post(N8N_WEBHOOK_URL, json=results, timeout=15)
            print("[+] УСПЕХ! Статус:", response.status_code)
        except Exception as e:
            print(f"[!] Ошибка отправки: {e}")

if __name__ == "__main__":
    main()
