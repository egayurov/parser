import requests
from bs4 import BeautifulSoup
import csv
import time
from urllib.parse import urljoin

# ================= КОНФИГУРАЦИЯ =================
BASE_URL = "https://eprocurement.gov.tj/ru/searchanno?binname=&methodz=&Uname=&numberAnno=&statuses=&years=&titleAnno=&date_start=&purch=&region_supply=&date_end=&filter_anno=Y"
DOMAIN = "https://eprocurement.gov.tj"
OUTPUT_FILE = "all_tenders.csv"
DELAY_BETWEEN_PAGES = 1.2  # Задержка в секундах между страницами
MAX_RETRIES = 3            # Количество попыток при сбое сети

# Вставьте сюда ваш PRODUCTION URL из узла Webhook в n8n (без слова -test)
N8N_WEBHOOK_URL = "https://n8n-lolcfinance-n8n.ov4co6.easypanel.host/webhook/oxus-parser"
# =================================================

def fetch_page_with_retry(url, headers, retries=MAX_RETRIES):
    """Выполняет запрос к странице с поддержкой повторных попыток при ошибках сети."""
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code == 200:
                return response
            else:
                print(f"   [!] Сервер вернул код {response.status_code}. Попытка {attempt + 1} из {retries}...")
        except (requests.exceptions.RequestException, Exception) as e:
            print(f"   [!] Ошибка сети: {e}. Попытка {attempt + 1} из {retries}...")
        
        # Увеличиваем задержку перед следующей попыткой
        time.sleep(5 * (attempt + 1))
    return None

def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    fieldnames = [
        "number", "organizer", "purchaser", "title", "url", 
        "method", "subject_type", "start_date", "end_date", 
        "lots_count", "status"
    ]

    # Создаем файл и записываем заголовок
    try:
        with open(OUTPUT_FILE, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
        print(f"[+] Файл {OUTPUT_FILE} успешно создан. Начинаем сбор...")
    except Exception as e:
        print(f"[!] Не удалось создать файл для записи: {e}")
        return

    page = 1
    total_saved = 0

    while True:
        url = f"{BASE_URL}&page={page}"
        print(f"[*] Обработка страницы {page}...")
        
        response = fetch_page_with_retry(url, headers)
        if not response:
            print(f"[!] Не удалось загрузить страницу {page} после {MAX_RETRIES} попыток. Завершение работы.")
            break
            
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table')
        
        if not table:
            print(f"[+] Сбор завершен. На странице {page} таблица объявлений отсутствует.")
            break
            
        rows = table.find_all('tr')
        page_results = []
        
        for row in rows[1:]:
            cols = row.find_all('td')
            if len(cols) >= 10:
                anno_link_element = cols[3].find('a', href=True)
                anno_title = anno_link_element.text.strip() if anno_link_element else cols[3].text.strip()
                anno_url = urljoin(DOMAIN, anno_link_element['href']) if anno_link_element else ""
                
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
                    "status": cols[9].text.strip()
                }
                page_results.append(item)
        
        if not page_results:
            print(f"[+] Сбор завершен. На странице {page} нет новых объявлений.")
            break
            
        try:
            with open(OUTPUT_FILE, mode="a", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
                writer.writerows(page_results)
            
            total_saved += len(page_results)
            print(f"   [+] Успешно сохранено {len(page_results)} строк со страницы {page}. Всего в базе: {total_saved}")
        except Exception as e:
            print(f"   [!] Ошибка при записи данных страницы {page} в файл: {e}")
            
        page += 1
        time.sleep(DELAY_BETWEEN_PAGES)

    print(f"\n[+] Парсинг завершен. Всего собрано объявлений: {total_saved}. Файл: {OUTPUT_FILE}")

    # ОТПРАВКА ФАЙЛА В n8n ПОСЛЕ ЗАВЕРШЕНИЯ ВСЕГО СБОРА
    print("[*] Отправляем итоговый файл в n8n...")
    try:
        with open(OUTPUT_FILE, "rb") as f:
            # Увеличим тайм-аут до 60 секунд, так как файл может быть объемным
            response = requests.post(N8N_WEBHOOK_URL, files={"file": f}, timeout=60)
            if response.status_code == 200:
                print("[+] УСПЕХ! Полный файл успешно отправлен в n8n.")
            else:
                print(f"[-] n8n вернул код ответа: {response.status_code}")
    except Exception as e:
        print(f"[!] Ошибка отправки итогового файла в n8n: {e}")

if __name__ == "__main__":
    main()
