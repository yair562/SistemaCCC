# SistemaCCC (Inventario)

Simple Flask inventory app. This repository contains the Flask app, templates, and static assets.

Quick start

- Create a Python virtual environment and activate it (Windows PowerShell):

  ```powershell
  python -m venv .venv; .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```

- Run the development server:

  ```powershell
  python run.py
  ```

Configuration

- Environment variables (optional but recommended):
  - `FLASK_SECRET`: secret key for sessions. If not set, a random key is generated at startup.
  - `DB_PATH`: path to the SQLite database file. Defaults to `inventario_consolidado.db` in project root.
  
  Example on Windows PowerShell:
  ```powershell
  $env:FLASK_SECRET = "paste-a-strong-random-key-here"
  $env:DB_PATH = (Get-Location).Path + "\inventario_consolidado.db"
  python run.py
  ```

Notes
- The SQLite database file is `inventario_consolidado.db` in the project root. `app.py` uses that path.
- Utility scripts were moved into the `scripts/` folder. The legacy `modificarDB.py` at project root now imports `scripts/modificarDB.py` for compatibility.
- The server-side serial/scanner worker requires the `pyserial` package. If not installed, the endpoints will show a helpful message and the client-side scanner will still work when a USB keyboard-scanner is used.

Layout
- `app.py` - Flask application and routes
- `app/__init__.py` - App factory `create_app()` used by `run.py`
- `templates/` - Jinja2 templates
- `static/` - CSS, JS, images
- `scripts/` - utility scripts (DB setup, migration helpers)

Database schema

The app expects the following tables to exist in the SQLite DB:
- `inventory` (sku, id_original, tipo, marca, modelo, no_serie, volts, precio, estado, ubicacion, fecha_registro, origen_hoja, observacion, extras)
- `usuarios` (id, usuario, password, nivel)
- `movimientos` (id, usuario, accion, rowid_producto, sku, detalles, cuando)
- `ventas` (rowid_producto, sku, tipo, marca, modelo, no_serie, precio_venta, comprador, vendedor, fecha_venta, observaciones)
- `categorias_prefijos` (prefijo, nombre)

Security notes
- Do not store plaintext passwords in production. Consider using `bcrypt` for hashing and verifying passwords.
- Protect admin routes (`/admin`, `/usuarios`, `/venta`, `/salidas`, `/exportar_*`) with authentication decorators when deploying.

Troubleshooting
- If you see serial scanner errors, ensure `pyserial` is installed or leave scanner features disabled.
- For large databases, Excel export can be memory intensive; run on a machine with sufficient RAM.

If you'd like, I can:
- Run a quick smoke test of the main pages (start server & curl the endpoints), or
- Remove the root wrapper `modificarDB.py` now that the script is in `scripts/`.
