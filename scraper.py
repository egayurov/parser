import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import re

# ================= КОНФИГУРАЦИЯ =================
BASE_URL = "https://oxus.tj/index.php/ru/"
DOMAIN = urlparse(BASE_URL).netloc
OUTPUT_FILE = "oxus_full_content.txt"
# =================================================

def clean_text(soup):
    """Очищает HTML от мусора (скрипты, стили, меню навигации) и возвращает чистый текст."""
    # Удаляем служебные теги
    for element in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        element.decompose()
        
    # Извлекаем текст
    text = soup.get_text(separator='\n')
    
    # Очищаем от лишних пустых строк
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)

def main():
    visited = set()
    to_visit = [BASE_URL]
    
    print(f"[*] Начало парсинга сайта {BASE_URL}...")
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        while to_visit:
            url = to_visit.pop(0)
            if url in visited:
                continue
                
            print(f"[*] Сканируем: {url}")
            try:
                # Небольшая задержка между запросами
                time.sleep(1)
                
                response = requests.get(url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                })
                
                if response.status_code != 200:
                    print(f"   [-] Ошибка {response.status_code} для {url}")
                    continue
                    
                visited.add(url)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Извлекаем заголовок и контент
                title = soup.title.string.strip() if soup.title else "Без заголовка"
                content_text = clean_text(soup)
                
                # Записываем в файл в читаемом виде
                f.write(f"\n\n{'='*60}\n")
                f.write(f"URL: {url}\n")
                f.write(f"ЗАГОЛОВОК: {title}\n")
                f.write(f"{'='*60}\n\n")
                f.write(content_text)
                f.write("\n")
                
                # Поиск новых внутренних ссылок только для русской версии
                for link in soup.find_all('a', href=True):
                    next_url = urljoin(url, link['href'])
                    parsed_next = urlparse(next_url)
                    
                    # Проверяем, что ссылка ведет на тот же домен и содержит '/ru/'
                    if DOMAIN in parsed_next.netloc and "/ru/" in parsed_next.path:
                        # Исключаем файлы, которые не нужно парсить
                        if not any(ext in next_url.lower() for ext in ['.pdf', '.jpg', '.png', '.doc', '.docx', '.zip', '.xls', '.xlsx']):
                            # Убираем якоря типа #content
                            clean_next_url = next_url.split('#')[0]
                            if clean_next_url not in visited and clean_next_url not in to_visit:
                                to_visit.append(clean_next_url)
                                
            except Exception as e:
                print(f"   [!] Ошибка при обработке {url}: {e}")
                
    print(f"\n[+] Сбор завершен. Все данные сохранены в файл: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
