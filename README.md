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

Notes
- The SQLite database file is `inventario_consolidado.db` in the project root. `app.py` uses that path.
- Utility scripts were moved into the `scripts/` folder. The legacy `modificarDB.py` at project root now imports `scripts/modificarDB.py` for compatibility.
- The server-side serial/scanner worker requires the `pyserial` package. If not installed, the endpoints will show a helpful message and the client-side scanner will still work when a USB keyboard-scanner is used.

Layout
- `app.py` - Flask application and routes
- `templates/` - Jinja2 templates
- `static/` - CSS, JS, images
- `scripts/` - utility scripts (DB setup, migration helpers)

If you'd like, I can:
- Run a quick smoke test of the main pages (start server & curl the endpoints), or
- Remove the root wrapper `modificarDB.py` now that the script is in `scripts/`.
