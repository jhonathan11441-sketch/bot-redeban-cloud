from flask import Flask, jsonify
import requests
import os
from dotenv import load_dotenv
from datetime import datetime
import pytz
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
PUERTO = int(os.getenv('PORT', 8080))

# Variables de entorno
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
ZONA = pytz.timezone('America/Bogota')

def enviar_telegram(msg):
    """Envía mensaje a Telegram"""
    try:
        logger.info(f"Intentando enviar mensaje a Telegram...")
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
        logger.info(f"Telegram response status: {response.status_code}")
        logger.info(f"Telegram response: {response.text}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error enviando Telegram: {e}")
        import traceback
        traceback.print_exc()
        return False

@app.route('/', methods=['GET', 'POST'])
def ejecutar_bot():
    """Endpoint para ejecutar el bot"""
    logger.info("[*] Iniciando ejecución del bot...")
    
    try:
        fecha_hoy = datetime.now(ZONA).strftime('%d/%m/%Y')
        hora_hoy = datetime.now(ZONA).strftime('%H:%M:%S')
        
        # Mensaje de prueba
        msg = f"""\ud83d\udc4b <b>PRUEBA DE BOT REDEBAN</b><br>
        Fecha: {fecha_hoy}<br>
        Hora: {hora_hoy}<br>
        <br>
        <b>Estado:</b> \u2705 Bot funcionando correctamente<br>
        <b>Destino:</b> Cloud Run<br>
        <b>Activador:</b> Cloud Scheduler
        """
        
        logger.info("[*] Enviando mensaje de prueba a Telegram...")
        if enviar_telegram(msg):
            logger.info("[\u2713] Mensaje enviado exitosamente a Telegram")
            return jsonify({"success": True, "message": "Mensaje de prueba enviado a Telegram"}), 200
        else:
            logger.error("[\u2717] Error: No se pudo enviar el mensaje a Telegram")
            return jsonify({"success": False, "message": "Error al enviar a Telegram"}), 500
            
    except Exception as e:
        logger.error(f"[\u2717] Error general: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    logger.info(f"[*] Iniciando servidor en puerto {PUERTO}")
    app.run(host='0.0.0.0', port=PUERTO, debug=False)
