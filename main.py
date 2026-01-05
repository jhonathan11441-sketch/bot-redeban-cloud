from flask import Flask, jsonify
from playwright.sync_api import sync_playwright
import requests
import os
from dotenv import load_dotenv
from datetime import datetime
import pytz
import re
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
EMAIL_DESTINO = os.getenv('EMAIL_DESTINO')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
ZONA = pytz.timezone('America/Bogota')

def enviar_telegram(msg):
    """Envía mensaje a Telegram"""
    try:
        logger.info(f"Enviando mensaje a Telegram...")
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
        logger.info(f"Telegram status: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error enviando Telegram: {e}")
        return False

def procesar_redeban():
    """Procesa Redeban y retorna el informe"""
    
    logger.info("="*70)
    logger.info("AUTOMATIZACIÓN REDEBAN")
    logger.info("="*70)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        page = browser.new_page()
        
        try:
            logger.info("[*] Abriendo Redeban...")
            page.goto('https://www.entrecuentasredeban.com.co/webcopi/#/login', timeout=60000)
            page.wait_for_timeout(5000)
            
            # LOGIN
            logger.info("[*] Rellenando credenciales...")
            inputs = page.query_selector_all('input')
            inputs[0].fill(USUARIO)
            inputs[1].fill(CONTRASEÑA)
            logger.info("[*] Haciendo clic en Ingresar...")
            page.click('button:has-text("Ingresar")')
            page.wait_for_timeout(10000)
            
            # COMERCIO
            logger.info("[*] Seleccionando comercio...")
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
            
            # CONSULTA TRANSACCIONES
            logger.info("[*] Accediendo a Consulta Transacciones...")
            page.click('text=Consulta Transacciones')
            page.wait_for_timeout(5000)
            
            # BUSCAR
            logger.info("[*] Buscando transacciones...")
            buscars = page.query_selector_all('button:has-text("Buscar")')
            if buscars:
                buscars[0].click(force=True)
            page.wait_for_timeout(8000)
            
            # CAMBIAR A 100 ITEMS
            logger.info("[*] Configurando 100 items por página...")
            try:
                dropdown_container = page.query_selector('mat-paginator')
                if dropdown_container:
                    select_elem = dropdown_container.query_selector('mat-select')
                    if select_elem:
                        select_elem.click()
                        page.wait_for_timeout(2000)
                        
                        option_100 = page.query_selector('mat-option[value="100"]')
                        if option_100:
                            option_100.click()
                            logger.info("[OK] Cambiado a 100 items")
                        else:
                            options = page.query_selector_all('mat-option')
                            for opt in options:
                                if "100" in opt.text_content():
                                    opt.click()
                                    break
                        
                        page.wait_for_timeout(5000)
            except Exception as e:
                logger.warning(f"No se pudo cambiar items: {e}")
            
            # EXTRAER DATOS
            logger.info("[*] Extrayendo datos...")
            page.wait_for_timeout(3000)
            
            contenedor = page.query_selector('div[role="main"]') or page.query_selector('body')
            if contenedor:
                texto = contenedor.inner_text()
                
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
                logger.info(f"TRANSACCIONES ACEPTADAS: {len(transacciones)}")
                logger.info(f"TRANSACCIONES RECHAZADAS: {len(transacciones_rechazadas)}")
                
                if transacciones:
                    # Separar por período
                    mañana = [t for t in transacciones if int(t['hora'].split(':')[0]) < 12 or (int(t['hora'].split(':')[0]) == 12 and int(t['hora'].split(':')[1]) < 30)]
                    tarde = [t for t in transacciones if int(t['hora'].split(':')[0]) >= 12 and not (int(t['hora'].split(':')[0]) == 12 and int(t['hora'].split(':')[1]) < 30)]
                    
                    total_mañana = sum(t['valor'] for t in mañana)
                    total_tarde = sum(t['valor'] for t in tarde)
                    total_general = total_mañana + total_tarde
                    total_rechazado = sum(t['valor'] for t in transacciones_rechazadas)
                    
                    logger.info(f"MAÑANA (00:00-12:30): {len(mañana)} transacciones - ${total_mañana:,.2f}")
                    logger.info(f"TARDE (12:30-21:00): {len(tarde)} transacciones - ${total_tarde:,.2f}")
                    logger.info(f"TOTAL: {len(transacciones)} transacciones - ${total_general:,.2f}")
                    
                    # Construir mensaje
                    rechazadas_info = ""
                    if transacciones_rechazadas:
                        rechazadas_info = f"""\n\n⚠️ <b>TRANSACCIONES RECHAZADAS ({len(transacciones_rechazadas)})</b><br>💰 Monto: ${total_rechazado:,.2f}<br><i>(Excluidas del total)</i>""" 
                    
                    msg = f"""\ud83d\udcca <b>INFORME QR COMPLETO - {datetime.now(ZONA).strftime('%d/%m/%Y')}</b><br>\ud83c\udfd0 PANADERIA EL PORTON<br>\ud83d\udcd0 CUC: {CUC_COMERCIO}<br><br><b>\ud83c\udf05 MAÑANA (00:00-12:30)</b><br>\ud83d\udccb Transacciones: {len(mañana)}<br>\ud83d\udcb0 Total: <b>${total_mañana:,.2f}</b><br><br><b>\ud83c\udf06 TARDE (12:30-21:00)</b><br>\ud83d\udccb Transacciones: {len(tarde)}<br>\ud83d\udcb0 Total: <b>${total_tarde:,.2f}</b><br>{rechazadas_info}<br><br>━━━━━━━━━━━━━━━━━━━━━━━━━━━<b>\ud83d\udcca RESUMEN DEL DÍA</b><br>\ud83d\udccb Total Transacciones (Válidas): {len(transacciones)}<br>\ud83d\udcb0 Monto Total: <b>${total_general:,.2f}</b>
                    """
                    
                    logger.info("[*] Enviando a Telegram...")
                    if enviar_telegram(msg):
                        logger.info("[OK] Informe enviado correctamente")
                        return {"success": True, "message": "Informe enviado", "transacciones": len(transacciones)}
                    else:
                        return {"success": False, "message": "Error al enviar Telegram"}
                else:
                    logger.warning("No se encontraron transacciones")
                    return {"success": False, "message": "No se encontraron transacciones"}
            
        except Exception as e:
            logger.error(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
        finally:
            browser.close()

@app.route('/', methods=['GET', 'POST'])
def ejecutar_bot():
    """Endpoint para ejecutar el bot"""
    logger.info("[*] Ejecutando bot...")
    try:
        resultado = procesar_redeban()
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
