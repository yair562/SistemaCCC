#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serial Scanner Forwarder – versión limpia y documentada

Propósito:
    Detectar automáticamente un escáner conectado por USB/Serial,
    leer sus datos, y enviarlos a un servidor Flask centralizado.

Características:
    ✓ Auto-detección del puerto del escáner.
    ✓ Resolución automática del servidor (hostname, server.txt, cache, escaneo rápido LAN).
    ✓ Lectura carácter por carácter para compatibilidad con HID/Serial.
    ✓ Ensamblado seguro de líneas completas (cada lect ura = un código).
    ✓ Control opcional de la línea DTR (evita que algunos escáneres se apaguen).
    ✓ Reintentos automáticos si el puerto se desconecta.
    ✓ Funciona en cualquier PC conectada a la misma red.

Requiere:
    pip install pyserial requests
"""

import argparse
import time
import sys
import socket
import os
import re
from typing import Optional

# ---------------------------------------
# MÓDULOS EXTERNOS
# ---------------------------------------
try:
    import serial
    import serial.tools.list_ports
except Exception:
    print("ERROR: pyserial es obligatorio. Instala con: pip install pyserial")
    sys.exit(1)

try:
    import requests
except Exception:
    print("ERROR: requests es obligatorio. Instala con: pip install requests")
    sys.exit(1)


# ---------------------------------------
# CONFIGURACIÓN
# ---------------------------------------
DEFAULT_SERVER_HOSTNAME = "inventario.local"
SERVER_FILE = "server.txt"
SERVER_CACHE = "server_cache.txt"
PUSH_ENDPOINT = "/push_scan"
BAUD = 9600

# Palabras clave típicas en descripciones de escáneres USB/Serial
COMMON_SCANNER_KEYWORDS = ["usb", "scanner", "hid", "barcode", "prolific"]


# ---------------------------------------
# VALIDACIONES BÁSICAS
# ---------------------------------------
def validate_ip(ip: str) -> bool:
    """Verifica si la cadena tiene formato IPv4 simple."""
    return re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip) is not None


def save_server_cache(ip: str):
    """Guarda la IP resuelta en un archivo de caché."""
    try:
        with open(SERVER_CACHE, "w") as f:
            f.write(ip)
    except Exception:
        pass  # No es crítico


# ---------------------------------------
# DETECCIÓN DE PUERTO SERIAL
# ---------------------------------------
def detect_scanner_port(filter_text: Optional[str] = None, timeout: float = 0.0) -> Optional[str]:
    """
    Busca un dispositivo serial cuyo descriptor coincida con:
    - Palabras clave típicas de escáner
    - Texto filtrado por el usuario (--filter)
    Si timeout > 0, reintenta hasta que el tiempo expire.
    """
    start = time.time()

    filter_lower = filter_text.lower() if filter_text else None

    while True:
        ports = list(serial.tools.list_ports.comports())

        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            dev = (p.device or "").lower()

            # Si se especificó un filtro explícito
            if filter_lower and (filter_lower in desc or filter_lower in hwid or filter_lower in dev):
                return p.device

            # Coincidencia por palabras clave típicas
            if any(k in desc or k in hwid for k in COMMON_SCANNER_KEYWORDS):
                return p.device

        if timeout and (time.time() - start) >= timeout:
            return None

        time.sleep(0.5)


# ---------------------------------------
# RESOLUCIÓN AUTOMÁTICA DEL SERVIDOR
# ---------------------------------------
def resolve_server(quick_subnet_scan: bool = True) -> Optional[str]:
    """
    Intenta obtener la IP del servidor en este orden:
      1) Hostname inventario.local
      2) Archivo server.txt
      3) Caché local server_cache.txt
      4) Escaneo rápido 192.168.1.x buscando /health
    """

    # 1. Hostname
    try:
        ip = socket.gethostbyname(DEFAULT_SERVER_HOSTNAME)
        if ip:
            save_server_cache(ip)
            return ip
    except Exception:
        pass

    # 2. Archivo server.txt
    try:
        if os.path.exists(SERVER_FILE):
            txt = open(SERVER_FILE).read().strip()
            if validate_ip(txt):
                save_server_cache(txt)
                return txt
    except Exception:
        pass

    # 3. Caché
    try:
        if os.path.exists(SERVER_CACHE):
            txt = open(SERVER_CACHE).read().strip()
            if validate_ip(txt):
                return txt
    except Exception:
        pass

    # 4. Escaneo LAN rápido
    if quick_subnet_scan:
        for i in range(1, 255):
            target = f"192.168.1.{i}"
            try:
                r = requests.get(f"http://{target}:5000/health", timeout=0.25)
                if r.status_code == 200:
                    save_server_cache(target)
                    return target
            except Exception:
                pass

    return None


# ---------------------------------------
# ENVÍO DEL CÓDIGO AL SERVIDOR
# ---------------------------------------
def send_to_server(server_ip: str, code: str) -> bool:
    """Envía el código recién leído al servidor Flask."""
    url = f"http://{server_ip}:5000{PUSH_ENDPOINT}"
    try:
        r = requests.post(url, json={"code": code}, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# ---------------------------------------
# LECTURA DEL ESCÁNER
# ---------------------------------------
def read_from_scanner_loop(port: str, server_ip: str, baud: int = BAUD, delay: float = 0.01, dtr_mode: str = 'auto'):
    """
    Lee del puerto serial carácter por carácter, arma líneas completas,
    y envía cada código al servidor.
    Mantiene el puerto abierto hasta que falle.
    """
    print(f"[INFO] Abriendo puerto serial {port} @ {baud}")

    try:
        ser = serial.Serial(port, baud, timeout=1)
    except Exception as e:
        print(f"[ERR] No se pudo abrir {port}: {e}")
        return False

    # Control de DTR (evita que algunos escáneres se apaguen)
    try:
        if dtr_mode == 'off':
            try:
                ser.dtr = False
            except Exception:
                ser.setDTR(False)
        elif dtr_mode == 'on':
            try:
                ser.dtr = True
            except Exception:
                ser.setDTR(True)
    except Exception:
        pass

    buffer = ""

    try:
        while True:
            try:
                raw = ser.read(1)
            except Exception as e:
                print("[ERR] Fallo de lectura serial:", e)
                break

            # Sin datos → esperar
            if not raw:
                time.sleep(delay)
                continue

            # Decode seguro
            try:
                char = raw.decode("utf-8", errors="ignore")
            except Exception:
                char = raw.decode("latin1", errors="ignore")

            # ¿Fin de línea?
            if char in ("\n", "\r"):
                code = buffer.strip()
                buffer = ""
                if code:
                    print(f"[SCAN] → {code}")
                    ok = send_to_server(server_ip, code)
                    if ok:
                        print("[OK] Enviado ✔")
                    else:
                        print("[ERR] Error enviando al servidor (se reintentará).")
                continue

            buffer += char

    finally:
        try:
            ser.close()
        except Exception:
            pass

    return False


# ---------------------------------------
# PROGRAMA PRINCIPAL
# ---------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Serial Scanner Forwarder – Limpio y Documentado")
    parser.add_argument("--server", help="IP del servidor (sin http://). Si no, intenta autodetección.")
    parser.add_argument("--port", help="Ej: COM3 o /dev/ttyUSB0. Si no, usar --auto.")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--auto", action="store_true", help="Detectar el puerto del escáner automáticamente.")
    parser.add_argument("--filter", help="Texto preferido para filtrar puertos (ej: USB)")
    parser.add_argument("--retries", type=int, default=5, help="Reintentos antes de salir (-1 = infinito).")
    parser.add_argument("--dtr", choices=["auto", "on", "off"], default="auto", help="Control DTR.")
    args = parser.parse_args()

    # Resolver servidor
    server_ip = args.server
    if not server_ip:
        print("[INFO] Resolviendo servidor...")
        server_ip = resolve_server()

    if not server_ip:
        print("[FATAL] No se encontró servidor.")
        print("Crea server.txt con la IP o proporciona --server.")
        return

    print(f"[OK] Servidor detectado: http://{server_ip}:5000")

    # Resolver puerto serial
    port = args.port
    if args.auto and not port:
        print("[INFO] Detectando puerto del escáner...")
        port = detect_scanner_port(filter_text=args.filter, timeout=10)

    if not port:
        print("[FATAL] No se encontró puerto serial. Usa --port o --auto.")
        return

    # Loop de reintentos si el puerto se pierde
    retries = args.retries

    while True:
        ok = read_from_scanner_loop(port, server_ip, baud=args.baud, dtr_mode=args.dtr)

        if retries == 0:
            print("[FATAL] Demasiados reintentos. Saliendo.")
            return

        if retries > 0:
            retries -= 1

        print("[INFO] Conexión serial perdida. Reintentando en 2s...")
        time.sleep(2)

        # Re-detección del puerto si hay auto
        if args.auto:
            new_port = detect_scanner_port(filter_text=args.filter, timeout=5)
            if new_port:
                print(f"[INFO] Nuevo puerto detectado: {new_port}")
                port = new_port


if __name__ == "__main__":
    main()
