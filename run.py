from app import create_app
from waitress import serve
import socket
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ServidorCCC")

def get_ip_address():
    """Obtiene la mejor IP disponible de la red local."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Solo para saber qué interfaz usa la red
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        try:
            # Plan B: obtener IP por hostname
            return socket.gethostbyname(socket.gethostname())
        except:
            return "0.0.0.0"

if __name__ == "__main__":
    app = create_app()
    local_ip = get_ip_address()
    # Configurar URL pública base para generación de QR y enlaces absolutos
    try:
        app.config['PUBLIC_BASE_URL'] = f"http://{local_ip}:5000"
    except Exception:
        pass

    logger.info("🚀 INICIANDO SERVIDOR DEL SISTEMA CCC")
    logger.info(f"📍 Acceso local:     http://localhost:5000")
    logger.info(f"📍 Acceso en red:    http://{local_ip}:5000")
    logger.info("🌐 Servidor escuchando en 0.0.0.0 ...")

    try:
        serve(app, host="0.0.0.0", port=5000, threads=8)
    except Exception as e:
        logger.error(f"🔥 Error al iniciar Waitress: {e}")
