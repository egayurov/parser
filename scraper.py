import time
import random
import re
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ================= КОНФИГУРАЦИЯ =================
N8N_WEBHOOK_URL = "https://n8n-lolcfinance-n8n.ov4co6.easypanel.host/webhook-test/somon-parser" # Если внутри одной сети Easypanel, можно слать на внутреннее имя контейнера

PROXY_SERVER = "http://ip:port"
PROXY_USERNAME = "user"
PROXY_PASSWORD = "password"

BASE_URL = "https://somon.tj"
TARGET_URL = "https://somon.tj/nedvuzhimost/kvartiry/"
# =================================================

def random_delay(min_sec=2.0, max_sec=5.0):
    time.sleep(random.uniform(min_sec, max_sec))

def clean_price(price_str):
    if not price_str:
        return 0
    digits = re.sub(r'[^\d]', '', price_str)
    return int(digits) if digits else 0

def extract_platform_id(url):
    match = re.search(r'-(\d+)/?$', url)
    if match:
        return f"somon_{match.group(1)}"
    return f"somon_{random.randint(100000, 999999)}"

def main():
    results = []

    with sync_playwright() as p:
        proxy_settings = {
            "server": PROXY_SERVER,
            "username": PROXY_USERNAME,
            "password": PROXY_PASSWORD
        } if PROXY_SERVER and PROXY_SERVER != "http://ip:port" else None

        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            proxy=proxy_settings,
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print(f"[*] Открываем главную страницу: {TARGET_URL}")
        try:
            page.goto(TARGET_URL, timeout=60000)
            page.wait_for_load_state('networkidle')
        except Exception as e:
            print(f"[!] Ошибка загрузки главной страницы: {e}")
            browser.close()
            return

        random_delay(3, 6)

        print("[*] Собираем ссылки на квартиры...")
        links_locators = page.locator('a[href^="/adv/"]').all()
        
        ad_urls = set()
        for link in links_locators:
            href = link.get_attribute('href')
            if href and re.search(r'-(\d+)/?$', href):
                full_url = BASE_URL + href if href.startswith('/') else href
                ad_urls.add(full_url)

        ad_urls = list(ad_urls)[:20] 
        print(f"[*] Найдено уникальных объявлений: {len(ad_urls)}")

        for idx, url in enumerate(ad_urls, 1):
            print(f"\n[{idx}/{len(ad_urls)}] Обработка: {url}")
            random_delay()
            
            try:
                page.goto(url, timeout=45000)
                page.wait_for_load_state('domcontentloaded')
            except Exception as e:
                print(f"[!] Не удалось загрузить объявление: {e}")
                continue

            item_data = {
                "platform_id": extract_platform_id(url),
                "url": url,
                "title": "",
                "price_tjs": 0,
                "description": "",
                "phone": "",
                "main_image": "",
                "rooms": None,
                "area_sqm": None,
                "floor": None
            }

            try:
                item_data["title"] = page.locator('h1').first.inner_text(timeout=5000).strip()
            except: pass

            try:
                price_text = page.locator('.announcement-price, .item-price, [data-meta-id="price"]').first.inner_text(timeout=3000)
                item_data["price_tjs"] = clean_price(price_text)
            except: pass

            try:
                item_data["description"] = page.locator('.announcement-description, .item-description, #description-text').first.inner_text(timeout=3000).strip()
            except: pass

            try:
                item_data["main_image"] = page.locator('.announcement-image img, .slider-main img, .gallery-image img').first.get_attribute('src', timeout=3000)
            except: pass

            # --- УМНЫЙ ПАРСИНГ ХАРАКТЕРИСТИК (Комнаты, Площадь, Этаж) ---
            try:
                chars_blocks = page.locator('ul.chars-list li, .characteristics-item').all()
                for char in chars_blocks:
                    text = char.inner_text().lower()
                    if 'количество комнат' in text or 'комнат' in text:
                        val = re.sub(r'[^\d]', '', text)
                        item_data["rooms"] = int(val) if val else None
                    elif 'площадь' in text or 'кв.м' in text or 'м²' in text:
                        val = re.findall(r'\d+\.?\d*', text)
                        item_data["area_sqm"] = float(val[0]) if val else None
                    elif 'этаж' in text:
                        # Логика для формата "Этаж: 4" или "4/12"
                        val = re.findall(r'\d+', text)
                        if val:
                            item_data["floor"] = int(val[0])
            except Exception as e:
                print(f"[-] Ошибка парсинга характеристик: {e}")

            # --- КЛИК ПО ТЕЛЕФОНУ ---
            page.mouse.wheel(0, 400)
            random_delay(1, 2)

            try:
                phone_btn = page.locator('text="Показать", text="Телефон", .js-item-phone-button, .phone-button').first
                if phone_btn.is_visible():
                    phone_btn.click()
                    random_delay(2, 4) 
                    
                    phone_link = page.locator('a[href^="tel:"]').first
                    if phone_link.is_visible():
                        phone_raw = phone_link.get_attribute('href').replace('tel:', '')
                    else:
                        phone_raw = page.locator('.phone-number, .js-phone-number').first.inner_text(timeout=2000)
                    
                    item_data["phone"] = re.sub(r'[^\d+]', '', phone_raw)
            except PlaywrightTimeout:
                print("[-] Кнопка телефона не подгрузилась.")
            except Exception as e:
                print(f"[-] Ошибка при получении телефона: {e}")

            print(f"[+] Собрано: {item_data['rooms']}-комн, {item_data['area_sqm']} м² | {item_data['price_tjs']} TJS")
            results.append(item_data)

        browser.close()

    if results:
        print(f"\n[*] Отправка {len(results)} записей на Webhook n8n...")
        try:
            response = requests.post(N8N_WEBHOOK_URL, json=results, timeout=15)
            response.raise_for_status()
            print("[+] Успешно отправлено в n8n! Статус:", response.status_code)
        except Exception as e:
            print(f"[!] Ошибка отправки на Webhook: {e}")
    else:
        print("[-] Нет данных для отправки.")

if __name__ == "__main__":
    main()