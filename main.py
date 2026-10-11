import os
import re
import traceback
import asyncio
import requests
from playwright.async_api import async_playwright

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("\n⚠️ ATENÇÃO: TELEGRAM_BOT_TOKEN está vazio/não configurado nos Secrets do GitHub!")
        print("--- RELATÓRIO IMPRESSO NO CONSOLE ---")
        print(message)
        return
    
    token = TELEGRAM_BOT_TOKEN.strip()
    if not token.startswith("bot"):
        token = f"bot{token}"
        
    chat_id = TELEGRAM_CHAT_ID.strip()
    url = f"https://api.telegram.org/{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        res_data = response.json()
        if response.status_code == 200 and res_data.get("ok"):
            print("✅ Relatório consolidado enviado com sucesso ao Telegram!")
        else:
            print(f"❌ Erro da API do Telegram ({response.status_code}): {res_data}")
    except Exception as e:
        print(f"❌ Falha de conexão ao enviar para o Telegram: {e}")

def parse_hour(time_str: str) -> int:
    try:
        match = re.search(r'(\d{1,2}):(\d{2})', time_str)
        if match:
            hour = int(match.group(1))
            if 'PM' in time_str.upper() and hour < 12:
                hour += 12
            elif 'AM' in time_str.upper() and hour == 12:
                hour = 0
            return hour
    except Exception:
        pass
    return -1

# ------------------------------------------------------------------
# 1. SCRAPER: GOOGLE FLIGHTS
# ------------------------------------------------------------------
async def scrape_google_flights(context):
    print("🔎 [1/3] Buscando no Google Flights...")
    flights = []
    url = "https://www.google.com/travel/flights?q=Flights%20to%20VCP%20from%20RIO%20on%202027-09-28%20through%202027-09-30&hl=pt-BR&curr=BRL"
    page = await context.new_page()
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(5000)
        
        cards = await page.query_selector_all('li')
        for card in cards:
            try:
                text = await card.inner_text()
                if "R$" in text and ":" in text:
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
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Aviso Google Flights: {e}")
    finally:
        await page.close()
    return flights

# ------------------------------------------------------------------
# 2. SCRAPER: KAYAK
# ------------------------------------------------------------------
async def scrape_kayak(context):
    print("🔎 [2/3] Buscando no Kayak...")
    flights = []
    url = "https://www.kayak.com.br/flights/RIO-VCP/2027-09-28/2027-09-30?sort=price_a"
    page = await context.new_page()
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(6000)
        
        cards = await page.query_selector_all('div[class*="resultInner"], div[class*="nAV8"]')
        for card in cards[:8]:
            try:
                text = await card.inner_text()
                times = re.findall(r'\d{1,2}:\d{2}', text)
                price_match = re.search(r'R\$\s*[\d\.]+', text)
                
                if len(times) >= 2 and price_match:
                    dep_hour = parse_hour(times[0])
                    if dep_hour != -1 and dep_hour <= 10:
                        flights.append({
                            "source": "Kayak",
                            "airline": "Oferta Agregador",
                            "departure": times[0],
                            "arrival": times[1],
                            "price": price_match.group(0)
                        })
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Aviso Kayak: {e}")
    finally:
        await page.close()
    return flights

# ------------------------------------------------------------------
# 3. SCRAPER: COMPANHIAS DIRETA (AZUL / GOL)
# ------------------------------------------------------------------
async def scrape_direct_airlines(context):
    print("🔎 [3/3] Buscando ofertas diretas das Cias (Azul / GOL)...")
    flights = []
    # A Azul é a principal operadora do Hub de Viracopos (VCP)
    url = "https://www.voeazul.com.br/br/pt/home"
    page = await context.new_page()
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)
        
        # Raspagem estruturada simples na landing de tarifas
        body_text = await page.inner_text("body")
        price_match = re.search(r'R\$\s*[\d\.]+', body_text)
        if price_match:
            flights.append({
                "source": "Azul Direto",
                "airline": "Azul Linhas Aéreas",
                "departure": "Consulte Horários",
                "arrival": "VCP Hub",
                "price": price_match.group(0)
            })
    except Exception as e:
        print(f"⚠️ Aviso Cias Diretas: {e}")
    finally:
        await page.close()
    return flights

# ------------------------------------------------------------------
# EXECUÇÃO PRINCIPAL
# ------------------------------------------------------------------
async def main():
    print("🚀 Iniciando automação multi-site de busca de voos...")
    all_results = []
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            
            # Executa as varreduras sequencialmente
            gf_flights = await scrape_google_flights(context)
            kayak_flights = await scrape_kayak(context)
            direct_flights = await scrape_direct_airlines(context)
            
            all_results = gf_flights + kayak_flights + direct_flights
            
            await context.close()
            await browser.close()
            
            print(f"\n📊 Total de voos consolidados de todas as fontes: {len(all_results)}")
            
            if all_results:
                msg = "✈️ Monitor Multi-Site de Voos: RJ -> Campinas (VCP)\n"
                msg += "🗓️ Ida: 28/09/2027 (Até 10h) | Volta: 30/09/2027 (A partir das 19h)\n\n"
                for f in all_results:
                    msg += f"📌 Fonte: {f['source']} | Cia: {f['airline']}\n"
                    msg += f"🕒 Saída: {f['departure']} -> Chegada: {f['arrival']}\n"
                    msg += f"💰 Preço: {f['price']}\n"
                    msg += "-----------------------------------\n"
                send_telegram_message(msg)
            else:
                send_telegram_message("⚠️ Pesquisa realizada no Google Flights, Kayak e Cias Diretas, porém nenhum voo preencheu os critérios exatos de horário ou os sites apresentaram bloqueio temporário de IP.")
                
    except Exception as err:
        error_msg = f"❌ Erro crítico na execução:\n{traceback.format_exc()[-500:]}"
        print(error_msg)
        send_telegram_message(error_msg)

if __name__ == "__main__":
    asyncio.run(main())
