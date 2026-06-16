import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time

# ================= КОНФИГУРАЦИЯ =================
# Укажите языковые префиксы, которые есть на сайте
LANGUAGES = ["ru", "tj", "en"] 
DOMAIN = "oxus.tj"

# URL вашего вебхука в n8n
N8N_WEBHOOK_URL = "https://n8n-lolcfinance-n8n.ov4co6.easypanel.host/webhook-test/oxus-parser"
# =================================================

def clean_text(soup):
    for element in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        element.decompose()
    text = soup.get_text(separator='\n')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)

def crawl_language(lang):
    base_url = f"https://{DOMAIN}/index.php/{lang}/"
    output_file = f"oxus_{lang}_content.txt"
    visited = set()
    to_visit = [base_url]
    
    print(f"\n[*] Начинаем сбор версии для языка: {lang.upper()}")
    
    with open(output_file, "w", encoding="utf-8") as f:
        while to_visit:
            url = to_visit.pop(0)
            if url in visited:
                continue
                
            print(f"[{lang.upper()}] Сканируем: {url}")
            try:
                time.sleep(1)
                response = requests.get(url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                })
                
                if response.status_code != 200:
                    continue
                    
                visited.add(url)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                title = soup.title.string.strip() if soup.title else "No Title"
                content_text = clean_text(soup)
                
                f.write(f"\n\n{'='*60}\nURL: {url}\nЗАГОЛОВОК: {title}\n{'='*60}\n\n")
                f.write(content_text)
                f.write("\n")
                
                for link in soup.find_all('a', href=True):
                    next_url = urljoin(url, link['href'])
                    parsed_next = urlparse(next_url)
                    
                    # Ищем ссылки только для текущего языка (например, содержащие /ru/ или /tj/)
                    if DOMAIN in parsed_next.netloc and f"/{lang}/" in parsed_next.path:
                        if not any(ext in next_url.lower() for ext in ['.pdf', '.jpg', '.png', '.doc', '.docx', '.zip']):
                            clean_next_url = next_url.split('#')[0]
                            if clean_next_url not in visited and clean_next_url not in to_visit:
                                to_visit.append(clean_next_url)
                                
            except Exception as e:
                print(f"   [!] Ошибка {url}: {e}")
                
    print(f"[+] Сбор {lang.upper()} завершен. Файл: {output_file}")
    return output_file

def send_to_n8n(file_path):
    print(f"[*] Отправляем {file_path} в n8n...")
    try:
        with open(file_path, "rb") as f:
            response = requests.post(N8N_WEBHOOK_URL, files={"file": f}, timeout=30)
            print(f"[+] Ответ n8n для {file_path}: {response.status_code}")
    except Exception as e:
        print(f"[!] Ошибка отправки {file_path} в n8n: {e}")

def main():
    for lang in LANGUAGES:
        file_created = crawl_language(lang)
        send_to_n8n(file_created)
        time.sleep(2) # Пауза перед следующим языком

if __name__ == "__main__":
    main()
