"""
Wrapper script. The actual script was moved to `scripts/modificarDB.py`.
Run the script in the scripts/ folder instead, or import it here.
"""

try:
    # Importing will execute the setup in scripts/modificarDB.py
    from scripts import modificarDB  # noqa: F401
except Exception as e:
    print('No se pudo ejecutar scripts/modificarDB.py:', e)
