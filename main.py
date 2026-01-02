from playwright.sync_api import sync_playwright
import requests
import os
from dotenv import load_dotenv
from datetime import datetime
import pytz
import re
import sys

load_dotenv()

USUARIO = os.getenv('USUARIO_REDEBAN')
CONTRASEÑA = os.getenv('CONTRASEÑA_REDEBAN')
CUC_COMERCIO = os.getenv('CUC_COMERCIO')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
ZONA = pytz.timezone('America/Bogota')

def enviar_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
        print("[OK] Mensaje enviado a Telegram")
        return True
    except Exception as e:
        print(f"[ERROR] Telegram: {e}")
        return False

def ejecutar_redeban():
    print(f"\n[INICIO] {datetime.now(ZONA).strftime('%d/%m/%Y %H:%M:%S')}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print("[*] Abriendo Redeban...")
            page.goto('https://www.entrecuentasredeban.com.co/webcopi/#/login', timeout=60000)
            page.wait_for_timeout(5000)
            
            print("[*] Login...")
            inputs = page.query_selector_all('input')
            inputs[0].fill(USUARIO)
            inputs[1].fill(CONTRASEÑA)
            page.click('button:has-text("Ingresar")')
            page.wait_for_timeout(10000)
            
            print("[*] Seleccionando comercio...")
            page.click('#mat-input-2')
            page.wait_for_timeout(3000)
            comercios = page.query_selector_all(f'text={CUC_COMERCIO}')
            if comercios:
                comercios[0].click(force=True)
            page.wait_for_timeout(2000)
            
            aceptars = page.query_selector_all('button:has-text("ACEPTAR")')
            if aceptars:
                aceptars[0].click(force=True)
            page.wait_for_timeout(6000)
            
            print("[*] Abriendo transacciones...")
            page.click('text=Consulta Transacciones')
            page.wait_for_timeout(5000)
            
            print("[*] Buscando...")
            buscars = page.query_selector_all('button:has-text("Buscar")')
            if buscars:
                buscars[0].click(force=True)
            page.wait_for_timeout(8000)
            
            print("[*] Extrayendo datos...")
            page.wait_for_timeout(3000)
            
            contenedor = page.query_selector('div[role="main"]') or page.query_selector('body')
            if contenedor:
                texto = contenedor.inner_text()
                
                transacciones = []
                transacciones_rechazadas = []
                bloques = texto.split('Nro de transacción:')
                
                for bloque in bloques[1:]:
                    try:
                        nro_match = re.search(r'^([0-9]+)', bloque)
                        nro = nro_match.group(1)[:15] if nro_match else "N/A"
                        
                        fecha_match = re.search(r'(\d{4}-\d{2}-\d{2})', bloque)
                        fecha = fecha_match.group(1) if fecha_match else ""
                        
                        hora_match = re.search(r'(\d{2}):(\d{2})', bloque)
                        hora = f"{hora_match.group(1)}:{hora_match.group(2)}" if hora_match else ""
                        
                        valor_match = re.search(r'\$\s*([\d,]+\.\d+)', bloque)
                        valor = float(valor_match.group(1).replace(',', '')) if valor_match else 0
                        
                        estado = "RECHAZADA" if "RECHAZADA" in bloque else "ACEPTADA"
                        
                        if fecha and hora and valor > 0:
                            if estado == "ACEPTADA":
                                transacciones.append({'fecha': fecha, 'hora': hora, 'valor': valor, 'nro': nro})
                            else:
                                transacciones_rechazadas.append({'fecha': fecha, 'hora': hora, 'valor': valor, 'nro': nro})
                    except:
                        pass
                
                print(f"[OK] {len(transacciones)} transacciones")
                
                if transacciones:
                    mañana = [t for t in transacciones if int(t['hora'].split(':')[0]) < 12]
                    tarde = [t for t in transacciones if int(t['hora'].split(':')[0]) >= 12]
                    
                    total_mañana = sum(t['valor'] for t in mañana)
                    total_tarde = sum(t['valor'] for t in tarde)
                    total_general = total_mañana + total_tarde
                    total_rechazado = sum(t['valor'] for t in transacciones_rechazadas)
                    
                    msg = f"""
📊 <b>REDEBAN {datetime.now(ZONA).strftime('%d/%m/%Y %H:%M')}</b>
🏪 PANADERIA EL PORTON | CUC: {CUC_COMERCIO}

<b>🌅 MAÑANA (00:00-12:00)</b>
📝 {len(mañana)} transacciones | 💰 ${total_mañana:,.2f}

<b>🌆 TARDE (12:00-23:59)</b>
📝 {len(tarde)} transacciones | 💰 ${total_tarde:,.2f}

<b>TOTAL: ${total_general:,.2f}</b> ({len(transacciones)} txns)
"""
                    
                    if total_rechazado > 0:
                        msg += f"\n⚠️ RECHAZADAS: ${total_rechazado:,.2f}"
                    
                    enviar_telegram(msg)
        
        except Exception as e:
            print(f"[ERROR] {e}")
            enviar_telegram(f"❌ Error: {str(e)[:100]}")
        
        finally:
            browser.close()
    
    print(f"[FIN] {datetime.now(ZONA).strftime('%H:%M:%S')}\n")

if __name__ == '__main__':
    ejecutar_redeban()
    sys.exit(0)
