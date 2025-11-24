import sqlite3

ruta_bd = r"C:\Users\ROG\Desktop\SS\SistemaCCC\inventario_consolidado.db"
conn = sqlite3.connect(ruta_bd)
cursor = conn.cursor()

try:
    # Crear tabla de usuarios si no existe
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            nivel INTEGER NOT NULL
        );
    """)

    # Lista de usuarios a insertar
    usuarios = [
        ("yair", "123", 1),
        ("justino", "cccJ", 1),
        ("jorge", "cccJ", 1),
        ("sebastian", "cccS", 1),
        ("alex", "cccA", 1),
        ("mario", "cccM", 1)
    ]

    # Insertar usuarios si no existen
    cursor.executemany("""
        INSERT OR IGNORE INTO usuarios (usuario, password, nivel)
        VALUES (?, ?, ?)
    """, usuarios)

    conn.commit()
    print("Tabla 'usuarios' creada y usuarios insertados correctamente.")

except Exception as e:
    print("Error:", e)

finally:
    conn.close()

# Crear tabla de movimientos / historial de actividad si no existe
try:
    conn = sqlite3.connect(ruta_bd)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            accion TEXT,
            rowid_producto INTEGER,
            sku TEXT,
            detalles TEXT,
            cuando TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("Tabla 'movimientos' verificada/creada correctamente.")
except Exception as e:
    print('No se pudo crear tabla movimientos:', e)
