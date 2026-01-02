from flask import Flask, request, jsonify
from playwright.async_api import async_playwright
import requests
import os
from dotenv import load_dotenv
from datetime import datetime
import pytz
import re
import asyncio
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
PUERTO = int(os.getenv('PORT', 8080))

# Variables de entorno
USUARIO = os.getenv('USUARIO_REDEBAN')
CONTRASEÑA = os.getenv('CONTRASEÑA_REDEBAN')
CUC_COMERCIO = os.getenv('CUC_COMERCIO')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

ZONA = pytz.timezone('America/Bogota')

def enviar_telegram(msg):
    """Envía mensaje a Telegram"""
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
        logger.info(f"Telegram response: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error enviando Telegram: {e}")
        return False

async def procesar_redeban():
    """Procesa Redeban y retorna el informe"""
    
    logger.info("[*] Iniciando proceso Redeban...")
    
    async with async_playwright() as p:
        # Usar chromium en modo headless (más ligero)
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        page = await browser.new_page()
        
        try:
            logger.info("[*] Abriendo Redeban...")
            await page.goto('https://www.entrecuentasredeban.com.co/webcopi/#/login', timeout=60000)
            await page.wait_for_timeout(5000)
            
            # LOGIN
            inputs = await page.query_selector_all('input')
            await inputs[0].fill(USUARIO)
            await inputs[1].fill(CONTRASEÑA)
            await page.click('button:has-text("Ingresar")')
            await page.wait_for_timeout(10000)
            
            # COMERCIO
            await page.click('#mat-input-2')
            await page.wait_for_timeout(3000)
            comercios = await page.query_selector_all(f'text={CUC_COMERCIO}')
            if comercios:
                await comercios[0].click(force=True)
            await page.wait_for_timeout(2000)
            
            aceptars = await page.query_selector_all('button:has-text("ACEPTAR")')
            if aceptars:
                await aceptars[0].click(force=True)
            await page.wait_for_timeout(6000)
            
            # CONSULTA TRANSACCIONES
            await page.click('text=Consulta Transacciones')
            await page.wait_for_timeout(5000)
            
            # BUSCAR
            buscars = await page.query_selector_all('button:has-text("Buscar")')
            if buscars:
                await buscars[0].click(force=True)
            logger.info("[*] Esperando resultados...")
            await page.wait_for_timeout(8000)
            
            # CAMBIAR A 100 ITEMS
            logger.info("[*] Configurando 100 items por página...")
            try:
                dropdown_container = await page.query_selector('mat-paginator')
                if dropdown_container:
                    select_elem = await dropdown_container.query_selector('mat-select')
                    if select_elem:
                        await select_elem.click()
                        await page.wait_for_timeout(2000)
                        
                        option_100 = await page.query_selector('mat-option[value="100"]')
                        if option_100:
                            await option_100.click()
                            logger.info("[✓] Cambiado a 100 items")
                        else:
                            options = await page.query_selector_all('mat-option')
                            for opt in options:
                                text = await opt.text_content()
                                if "100" in text:
                                    await opt.click()
                                    break
                        
                        await page.wait_for_timeout(5000)
            except Exception as e:
                logger.warning(f"[!] No se pudo cambiar items: {e}")
            
            # EXTRAER DATOS
            logger.info("[*] Extrayendo datos...")
            await page.wait_for_timeout(3000)
            
            contenedor = await page.query_selector('div[role="main"]') or await page.query_selector('body')
            if contenedor:
                texto = await contenedor.inner_text()
                
                transacciones = []
                transacciones_rechazadas = []
                bloques = texto.split('Nro de transacción:')
                
                logger.info("="*70)
                logger.info("TRANSACCIONES EXTRAÍDAS")
                logger.info("="*70)
                
                for idx, bloque in enumerate(bloques[1:], 1):
                    try:
                        nro_match = re.search(r'^([0-9]+)', bloque)
                        nro = nro_match.group(1)[:15] if nro_match else "N/A"
                        
                        fecha_match = re.search(r'(\d{4}-\d{2}-\d{2})', bloque)
                        fecha = fecha_match.group(1) if fecha_match else ""
                        
                        hora_match = re.search(r'(\d{2}):(\d{2})', bloque)
                        hora = f"{hora_match.group(1)}:{hora_match.group(2)}" if hora_match else ""
                        
                        valor_match = re.search(r'\$\s*([\d,]+\.\d+)', bloque)
                        valor = float(valor_match.group(1).replace(',', '')) if valor_match else 0
                        
                        estado = "ACEPTADA"
                        if "RECHAZADA" in bloque:
                            estado = "RECHAZADA"
                        
                        if fecha and hora and valor > 0:
                            if estado == "ACEPTADA":
                                transacciones.append({
                                    'fecha': fecha,
                                    'hora': hora,
                                    'valor': valor,
                                    'nro': nro,
                                    'estado': estado
                                })
                                logger.info(f"{idx:2d}. {hora} | ${valor:>10,.2f} | {estado:>10} | Nro: {nro}")
                            else:
                                transacciones_rechazadas.append({
                                    'fecha': fecha,
                                    'hora': hora,
                                    'valor': valor,
                                    'nro': nro,
                                    'estado': estado
                                })
                                logger.info(f"{idx:2d}. {hora} | ${valor:>10,.2f} | {estado:>10} | Nro: {nro} [EXCLUIDA]")
                    except:
                        pass
                
                logger.info("="*70)
                logger.info(f"✓ TRANSACCIONES ACEPTADAS: {len(transacciones)}")
                logger.info(f"✗ TRANSACCIONES RECHAZADAS: {len(transacciones_rechazadas)}")
                
                if transacciones:
                    # Separar por período
                    mañana = [t for t in transacciones if int(t['hora'].split(':')[0]) < 12 or (int(t['hora'].split(':')[0]) == 12 and int(t['hora'].split(':')[1]) < 30)]
                    tarde = [t for t in transacciones if int(t['hora'].split(':')[0]) >= 12 and not (int(t['hora'].split(':')[0]) == 12 and int(t['hora'].split(':')[1]) < 30)]
                    
                    total_mañana = sum(t['valor'] for t in mañana)
                    total_tarde = sum(t['valor'] for t in tarde)
                    total_general = total_mañana + total_tarde
                    total_rechazado = sum(t['valor'] for t in transacciones_rechazadas)
                    
                    logger.info(f"\n🌅 MAÑANA (00:00-12:30): {len(mañana)} transacciones - ${total_mañana:,.2f}")
                    logger.info(f"🌆 TARDE (12:30-21:00): {len(tarde)} transacciones - ${total_tarde:,.2f}")
                    logger.info(f"TOTAL: {len(transacciones)} transacciones - ${total_general:,.2f}")
                    
                    # Construir mensaje
                    rechazadas_info = ""
                    if transacciones_rechazadas:
                        rechazadas_info = f"""\n\n⚠️ <b>TRANSACCIONES RECHAZADAS ({len(transacciones_rechazadas)})</b>
💰 Monto: ${total_rechazado:,.2f}
<i>(Excluidas del total)</i>"""
                    
                    msg = f"""📊 <b>INFORME QR COMPLETO - {datetime.now(ZONA).strftime('%d/%m/%Y')}</b>
🏪 PANADERIA EL PORTON
📍 CUC: {CUC_COMERCIO}

<b>🌅 MAÑANA (00:00-12:30)</b>
📝 Transacciones: {len(mañana)}
💰 Total: <b>${total_mañana:,.2f}</b>

<b>🌆 TARDE (12:30-21:00)</b>
📝 Transacciones: {len(tarde)}
💰 Total: <b>${total_tarde:,.2f}</b>
{rechazadas_info}

━━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>📊 RESUMEN DEL DÍA</b>
📝 Total Transacciones (Válidas): {len(transacciones)}
💰 Monto Total: <b>${total_general:,.2f}</b>
"""
                    
                    logger.info("[*] Enviando a Telegram...")
                    if enviar_telegram(msg):
                        logger.info("[✓] Informe enviado correctamente")
                        return {"success": True, "message": "Informe enviado", "transacciones": len(transacciones)}
                    else:
                        return {"success": False, "message": "Error al enviar Telegram"}
                else:
                    logger.warning("[!] No se encontraron transacciones")
                    return {"success": False, "message": "No se encontraron transacciones"}
            
        except Exception as e:
            logger.error(f"[✗] Error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
        finally:
            await browser.close()

@app.route('/', methods=['GET', 'POST'])
def ejecutar_bot():
    """Endpoint para ejecutar el bot"""
    logger.info("[*] Ejecutando bot...")
    try:
        # Ejecutar la función asíncrona
        resultado = asyncio.run(procesar_redeban())
        return jsonify(resultado), 200
    except Exception as e:
        logger.error(f"Error en endpoint: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    logger.info(f"[*] Iniciando servidor en puerto {PUERTO}")
    app.run(host='0.0.0.0', port=PUERTO, debug=False)
