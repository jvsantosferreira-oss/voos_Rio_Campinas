import os
import re
import asyncio
import requests
from playwright.async_api import async_playwright

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("--- RELATÓRIO DE VOOS (CONSOLE) ---")
        print(message)
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro ao enviar Telegram: {e}")

def parse_hour(time_str: str) -> int:
    """Extrai a hora (0-23) de strings de tempo variadas."""
    match = re.search(r'(\d{1,2}):(\d{2})', time_str)
    if match:
        hour = int(match.group(1))
        if 'PM' in time_str.upper() and hour < 12:
            hour += 12
        elif 'AM' in time_str.upper() and hour == 12:
            hour = 0
        return hour
    return -1

async def scrape_google_flights(browser):
    """Scraper para o Google Flights."""
    print("🔎 Buscando no Google Flights...")
    flights = []
    url = "https://www.google.com/travel/flights?q=Flights%20to%20VCP%20from%20RIO%20on%202027-09-28%20through%202027-09-30&hl=pt-BR&curr=BRL"
    
    context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    page = await context.new_page()
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)
        
        cards = await page.query_selector_all('li.pI13d')
        for card in cards[:10]:
            text = await card.inner_text()
            times = re.findall(r'\d{1,2}:\d{2}', text)
            price_match = re.search(r'R\$\s*[\d\.]+', text)
            
            if len(times) >= 2 and price_match:
                dep_hour = parse_hour(times[0])
                if dep_hour != -1 and dep_hour <= 10:
                    airline = "Azul/GOL/LATAM"
                    for name in ["Azul", "GOL", "LATAM"]:
                        if name in text:
                            airline = name
                            break
                    flights.append({
                        "source": "Google Flights",
                        "airline": airline,
                        "departure": times[0],
                        "arrival": times[1],
                        "price": price_match.group(0)
                    })
    except Exception as e:
        print(f"Erro Google Flights: {e}")
    finally:
        await context.close()
    return flights

async def scrape_kayak(browser):
    """Scraper para o Kayak."""
    print("🔎 Buscando no Kayak...")
    flights = []
    url = "https://www.kayak.com.br/flights/RIO-VCP/2027-09-28/2027-09-30?sort=price_a"
    
    context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    page = await context.new_page()
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=35000)
        await page.wait_for_timeout(5000)
        
        cards = await page.query_selector_all('div.nAV8')
        for card in cards[:8]:
            text = await card.inner_text()
            times = re.findall(r'\d{1,2}:\d{2}', text)
            price_match = re.search(r'R\$\s*[\d\.]+', text)
            
            if len(times) >= 2 and price_match:
                dep_hour = parse_hour(times[0])
                if dep_hour != -1 and dep_hour <= 10:
                    flights.append({
                        "source": "Kayak",
                        "airline": "Oferta Kayak",
                        "departure": times[0],
                        "arrival": times[1],
                        "price": price_match.group(0)
                    })
    except Exception as e:
        print(f"Erro Kayak: {e}")
    finally:
        await context.close()
    return flights

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # Executa as raspagens
        gf_results = await scrape_google_flights(browser)
        kayak_results = await scrape_kayak(browser)
        
        await browser.close()
        
        all_results = gf_results + kayak_results
        
        if all_results:
            msg = "✈️ *Monitor de Voos: RJ ➔ Campinas (VCP)*\n"
            msg += "🗓️ *Ida:* 28/09/2027 (Saída até 10h)\n"
            msg += "🗓️ *Volta:* 30/09/2027 (Retorno a partir das 19h)\n\n"
            
            for f in all_results:
                msg += f"📌 *{f['source']}* | Cia: {f['airline']}\n"
                msg += f"🕒 Saída: {f['departure']} ➔ Chegada: {f['arrival']}\n"
                msg += f"💰 *Preço:* {f['price']}\n"
                msg += "-----------------------------------\n"
            
            send_telegram_message(msg)
        else:
            send_telegram_message("⚠️ Nenhum voo encontrado dentro dos critérios em nenhum dos portais.")

if __name__ == "__main__":
    asyncio.run(main())
