import requests
from bs4 import BeautifulSoup
import csv
import time
import re
from urllib.parse import urljoin

# ================= КОНФИГУРАЦИЯ =================
BASE_URL = "https://eprocurement.gov.tj/ru/searchanno?binname=&methodz=&Uname=&numberAnno=&statuses=&years=&titleAnno=&date_start=&purch=&region_supply=&date_end=&filter_anno=Y"
DOMAIN = "https://eprocurement.gov.tj"
PAGES_TO_SCRAPE = 2        # Ограничим 2 страницами для теста (так как глубокий парсинг требует времени)
OUTPUT_FILE = "tenders_detailed.csv"
DELAY_BETWEEN_REQUESTS = 1.0  # Пауза в секундах между запросами (важно для обхода блокировок)
# =================================================

def extract_field_by_label(soup, label_text):
    """Ищет на странице текст метки (например, 'Телефон') и извлекает соседнее значение."""
    try:
        # Ищем элемент, содержащий искомый текст (без учета регистра)
        element = soup.find(string=re.compile(label_text, re.IGNORECASE))
        if not element:
            return ""
        
        parent = element.parent
        
        # Если метка внутри ячейки таблицы (td или th), берем следующую ячейку
        if parent.name in ['td', 'th']:
            next_sibling = parent.find_next_sibling(['td', 'th'])
            if next_sibling:
                return next_sibling.get_text(strip=True)
                
        # Если метка в блоке описания (dt/dd или bootstrap-сетке)
        next_sibling = parent.find_next_sibling()
        if next_sibling:
            return next_sibling.get_text(strip=True)
            
        return ""
    except Exception:
        return ""

def parse_detail_page(url, headers):
    """Заходит на страницу тендера и извлекает контактные данные."""
    contacts = {"fio": "", "phone": "", "email": ""}
    if not url:
        return contacts
        
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Извлекаем контакты по ключевым словам
            contacts["fio"] = extract_field_by_label(soup, r"ФИО|Контактное лицо|Ответственный")
            contacts["phone"] = extract_field_by_label(soup, r"Телефон|Контакты")
            contacts["email"] = extract_field_by_label(soup, r"E-mail|Электронная почта|Почта")
            
    except Exception as e:
        print(f"      [!] Ошибка при парсинге детальной страницы {url}: {e}")
        
    return contacts

def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    fieldnames = [
        "number", "organizer", "purchaser", "title", "url", 
        "method", "subject_type", "start_date", "end_date", 
        "lots_count", "status", "contact_fio", "contact_phone", "contact_email"
    ]

    print(f"[*] Запуск глубокого парсинга. Собираем список и заходим внутрь каждого объявления...")

    # Создаем файл и записываем заголовок
    try:
        with open(OUTPUT_FILE, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
    except Exception as e:
        print(f"[!] Ошибка создания файла: {e}")
        return

    total_saved = 0

    for page in range(1, PAGES_TO_SCRAPE + 1):
        url = f"{BASE_URL}&page={page}"
        print(f"\n[*] Сканируем страницу списка {page}...")
        
        try:
            time.sleep(DELAY_BETWEEN_REQUESTS)
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                print(f"   [!] Ошибка {response.status_code} при загрузке страницы {page}")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table')
            if not table:
                print(f"   [-] Таблица на странице {page} не найдена.")
                break
                
            rows = table.find_all('tr')
            page_results = []
            
            for row in rows[1:]:
                cols = row.find_all('td')
                if len(cols) >= 10:
                    anno_link_element = cols[3].find('a', href=True)
                    anno_title = anno_link_element.text.strip() if anno_link_element else cols[3].text.strip()
                    anno_url = urljoin(DOMAIN, anno_link_element['href']) if anno_link_element else ""
                    
                    print(f"   [*] Сбор деталей для тендера № {cols[0].text.strip()}...")
                    
                    # Делаем паузу перед запросом внутрь тендера
                    time.sleep(DELAY_BETWEEN_REQUESTS)
                    # Заходим внутрь страницы объявления и забираем контакты
                    detail_contacts = parse_detail_page(anno_url, headers)
                    
                    item = {
                        "number": cols[0].text.strip(),
                        "organizer": cols[1].text.strip(),
                        "purchaser": cols[2].text.strip(),
                        "title": anno_title,
                        "url": anno_url,
                        "method": cols[4].text.strip(),
                        "subject_type": cols[5].text.strip(),
                        "start_date": cols[6].text.strip(),
                        "end_date": cols[7].text.strip(),
                        "lots_count": cols[8].text.strip(),
                        "status": cols[9].text.strip(),
                        "contact_fio": detail_contacts["fio"],
                        "contact_phone": detail_contacts["phone"],
                        "contact_email": detail_contacts["email"]
                    }
                    page_results.append(item)
            
            # Записываем результаты страницы в файл
            if page_results:
                with open(OUTPUT_FILE, mode="a", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
                    writer.writerows(page_results)
                total_saved += len(page_results)
                print(f"[+] Страница {page} обработана. Сохранено тендеров: {len(page_results)}")
                
        except Exception as e:
            print(f"   [!] Ошибка обработки страницы {page}: {e}")

    print(f"\n[+] Глубокий сбор завершен. Всего сохранено: {total_saved}. Файл: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
