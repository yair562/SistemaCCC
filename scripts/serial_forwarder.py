#!/usr/bin/env python3
"""
Auto serial forwarder with server discovery and robust read loop.

Features added/adapted:
- Auto-detect scanner port by description/hwid keywords.
- Resolve server automatically via hostname, `server.txt`, `server_cache.txt` or quick LAN scan.
- Read scanner input char-by-char and assemble lines (handles HID-like keyboard scanners and serial scanners).
- Reconnection logic and retries.

To run:
  python serial_forwarder.py --server 192.168.1.10
  python serial_forwarder.py --auto --filter "USB"

Requires: pyserial, requests
"""
import argparse
import time
import sys
import socket
import os
import re
from typing import Optional

try:
    import serial
    import serial.tools.list_ports
except Exception:
    print('pyserial is required. Install with: pip install pyserial')
    sys.exit(1)

try:
    import requests
except Exception:
    print('requests is required. Install with: pip install requests')
    sys.exit(1)


# -------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------
DEFAULT_SERVER_HOSTNAME = "inventario.local"
SERVER_FILE = "server.txt"
SERVER_CACHE = "server_cache.txt"
PUSH_ENDPOINT = "/push_scan"
BAUD = 9600

# Prefijos típicos de scanners USB (pueden ampliarse)
COMMON_SCANNER_KEYWORDS = ["USB", "Scanner", "HID", "Barcode", "Prolific"]


def validate_ip(ip: str) -> bool:
    return re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip) is not None


def save_server_cache(ip: str):
    try:
        with open(SERVER_CACHE, "w") as f:
            f.write(ip)
    except Exception:
        pass


def detect_scanner_port(filter_text: Optional[str] = None, timeout: float = 0.0) -> Optional[str]:
    """Scan ports and return first matching device. If timeout>0, keep trying until timeout seconds."""
    start = time.time()
    while True:
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            dev = p.device
            if filter_text:
                if filter_text.lower() in desc or filter_text.lower() in hwid or filter_text.lower() in (dev or '').lower():
                    return dev
            # common keywords
            if any(k.lower() in desc or k.lower() in hwid for k in COMMON_SCANNER_KEYWORDS):
                return dev

        if timeout and (time.time() - start) > timeout:
            return None
        time.sleep(0.5)


def resolve_server(quick_subnet_scan: bool = True) -> Optional[str]:
    # 1. Try default hostname
    try:
        ip = socket.gethostbyname(DEFAULT_SERVER_HOSTNAME)
        if ip:
            save_server_cache(ip)
            return ip
    except Exception:
        pass

    # 2. Read server.txt
    try:
        if os.path.exists(SERVER_FILE):
            txt = open(SERVER_FILE).read().strip()
            if validate_ip(txt):
                save_server_cache(txt)
                return txt
    except Exception:
        pass

    # 3. Read cache
    try:
        if os.path.exists(SERVER_CACHE):
            txt = open(SERVER_CACHE).read().strip()
            if validate_ip(txt):
                return txt
    except Exception:
        pass

    # 4. Quick subnet scan (192.168.1.x) if requested
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


def send_to_server(server_ip: str, code: str) -> bool:
    url = f"http://{server_ip}:5000{PUSH_ENDPOINT}"
    try:
        # prefer JSON; server accepts JSON payload
        r = requests.post(url, json={"code": code}, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def read_from_scanner_loop(port: str, server_ip: str, baud: int = BAUD, delay: float = 0.01, dtr_mode: str = 'auto'):
    print(f"[INFO] Opening serial port {port} @ {baud}")
    try:
        ser = serial.Serial(port, baud, timeout=1)
    except Exception as e:
        print(f"[ERR] Cannot open serial {port}: {e}")
        return False
    # Apply DTR/RTS settings to avoid toggling power on some scanners
    try:
        # default: do nothing (auto) — but if user requested off/on, enforce
        if dtr_mode == 'off':
            try:
                ser.dtr = False
            except Exception:
                try:
                    ser.setDTR(False)
                except Exception:
                    pass
        elif dtr_mode == 'on':
            try:
                ser.dtr = True
            except Exception:
                try:
                    ser.setDTR(True)
                except Exception:
                    pass
    except Exception:
        pass

    buffer = ""
    try:
        while True:
            try:
                b = ser.read(1)
            except Exception as e:
                print('[ERR] Serial read failed:', e)
                break

            if not b:
                time.sleep(delay)
                continue

            try:
                c = b.decode('utf-8', errors='ignore')
            except Exception:
                c = b.decode('latin1', errors='ignore')

            if c in ('\n', '\r'):
                code = buffer.strip()
                buffer = ""
                if code:
                    print(f"[SCAN] → {code}")
                    ok = send_to_server(server_ip, code)
                    if ok:
                        print('[OK] Enviado ✔')
                    else:
                        print('[ERR] No se pudo enviar, reintentando…')
                        # On send fail we still continue; could buffer for retry later
                continue

            buffer += c

    finally:
        try:
            ser.close()
        except Exception:
            pass

    return False


def main():
    p = argparse.ArgumentParser(description='Auto serial forwarder with server discovery')
    p.add_argument('--server', help='Server IP (no http://). If omitted will try auto-resolve')
    p.add_argument('--port', help='Serial port name (COM3). If omitted use --auto')
    p.add_argument('--baud', type=int, default=9600)
    p.add_argument('--auto', action='store_true', help='Detect serial port automatically')
    p.add_argument('--filter', help='Prefer ports whose description/manufacturer contains this text')
    p.add_argument('--retries', type=int, default=5, help='Retries on open before exit (-1 for infinite)')
    p.add_argument('--dtr', choices=['auto', 'on', 'off'], default='auto', help='Control DTR line: `off` may prevent some scanners from powering down when opened')
    args = p.parse_args()

    server_ip = args.server
    if not server_ip:
        print('[INFO] Resolving server...')
        server_ip = resolve_server()

    if not server_ip:
        print('[FATAL] No server found on network.')
        print('Create a file named server.txt containing the server IP, or provide --server')
        return

    print(f"[OK] Server: http://{server_ip}:5000")

    port = args.port
    if args.auto and not port:
        print('[INFO] Detecting scanner port...')
        port = detect_scanner_port(filter_text=args.filter, timeout=10)

    if not port:
        print('[FATAL] No serial port provided or detected. Use --port or --auto')
        return

    retries = args.retries
    while True:
        ok = read_from_scanner_loop(port, server_ip, baud=args.baud, dtr_mode=args.dtr)
        # If read loop returned False, attempt reconnection/re-detect
        if retries == 0:
            print('[FATAL] Exhausted retries. Exiting.')
            return

        if retries > 0:
            retries -= 1

        print('[INFO] Serial connection lost, retrying in 2s...')
        time.sleep(2)
        if args.auto:
            new_port = detect_scanner_port(filter_text=args.filter, timeout=5)
            if new_port:
                print(f'[INFO] Auto-detected new port: {new_port}')
                port = new_port


if __name__ == '__main__':
    main()
