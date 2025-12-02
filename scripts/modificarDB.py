import sqlite3

ruta_bd = r"C:\Users\ROG\Desktop\SS\SistemaCCC\inventario_consolidado.db"
conn = sqlite3.connect(ruta_bd)
cursor = conn.cursor()

try:
    # Crear tabla de inventory (TABLA PRINCIPAL QUE FALTABA)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT,
            id_original TEXT,
            tipo TEXT,
            marca TEXT,
            modelo TEXT,
            no_serie TEXT,
            volts TEXT,
            precio REAL,
            estado TEXT,
            ubicacion TEXT,
            fecha_registro TEXT,
            origen_hoja TEXT,
            observacion TEXT,
            extras TEXT
        );
    """)

    # Crear tabla de usuarios
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
    ]

    # Insertar usuarios si no existen
    cursor.executemany("""
        INSERT OR IGNORE INTO usuarios (usuario, password, nivel)
        VALUES (?, ?, ?)
    """, usuarios)

    # Crear tabla de ventas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rowid_producto INTEGER NOT NULL,
            sku TEXT NOT NULL,
            tipo TEXT,
            marca TEXT,
            modelo TEXT,
            no_serie TEXT,
            precio_venta REAL NOT NULL,
            comprador TEXT,
            vendedor TEXT,
            fecha_venta TEXT NOT NULL,
            observaciones TEXT,
            FOREIGN KEY (rowid_producto) REFERENCES inventory (rowid)
        );
    """)

    # -----------------------------------------------------
    # Tablas para eventos de venta del día
    # -----------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS venta_eventos (
            fecha TEXT PRIMARY KEY,
            estado TEXT NOT NULL DEFAULT 'OPEN', -- OPEN / CERRADA
            creado_cuando TEXT,
            cerrado_cuando TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS venta_evento_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evento_fecha TEXT NOT NULL,
            rowid_producto INTEGER NOT NULL,
            precio_asignado REAL,
            agregado_por TEXT,
            agregado_cuando TEXT,
            UNIQUE(evento_fecha, rowid_producto),
            FOREIGN KEY (rowid_producto) REFERENCES inventory(rowid),
            FOREIGN KEY (evento_fecha) REFERENCES venta_eventos(fecha)
        );
    """)

    # Añadir columna evento_fecha a ventas si aún no existe
    try:
        cursor.execute("ALTER TABLE ventas ADD COLUMN evento_fecha TEXT")
    except Exception:
        # Ignorar error si la columna ya existe
        pass

    conn.commit()
    print("Tablas verificadas: inventory, usuarios, ventas, venta_eventos, venta_evento_items")

    # ---------------------------------------------
    # Crear tabla de catálogo de ubicaciones (salones)
    # ---------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ubicaciones_catalogo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            nivel TEXT NOT NULL,
            nota TEXT,
            UNIQUE(nivel, nombre)
        );
    """)

    # Lista normalizada de ubicaciones por nivel (sin duplicados por nivel)
    # Notas extraídas de las descripciones originales.
    ubicaciones_preescolar = [
        ("SALA JUNTAS DIRECCIÓN", "PREESCOLAR", None),
        ("MÚSICA", "PREESCOLAR", None),
        ("3C", "PREESCOLAR", None),
        ("1A", "PREESCOLAR", None),
        ("2B", "PREESCOLAR", None),
        ("1B", "PREESCOLAR", "Repetido en otras secciones"),
        ("2C", "PREESCOLAR", None),
        ("2A", "PREESCOLAR", None),
        ("MULTIPLES", "PREESCOLAR", None),
        ("AJEDREZ", "PREESCOLAR", None),
        ("3A", "PREESCOLAR", None),
        ("PF-B", "PREESCOLAR", None),
        ("COMPUTACIÓN I", "PREESCOLAR", None),
        ("3B", "PREESCOLAR", None),
        ("PF-A", "PREESCOLAR", None),
        ("MATERNIDAD", "PREESCOLAR", None),
        ("1D", "PREESCOLAR", None),
    ]

    ubicaciones_primaria = [
        ("AUDIOVISUAL", "PRIMARIA", None),
        ("2A", "PRIMARIA", None),
        ("6C", "PRIMARIA", None),
        ("1E", "PRIMARIA", None),
        ("BODEGA", "PRIMARIA", "Solo donde indicaba PRIMARIA"),
        ("2C", "PRIMARIA", None),
        ("6A", "PRIMARIA", None),
        ("3E", "PRIMARIA", None),
        ("5E", "PRIMARIA", None),
        ("4D", "PRIMARIA", None),
        ("6F", "PRIMARIA", None),
        ("4C", "PRIMARIA", None),
        ("5C", "PRIMARIA", None),
        ("5D", "PRIMARIA", None),
        ("2B", "PRIMARIA", None),
        ("4A", "PRIMARIA", None),
        ("5B", "PRIMARIA", "Bajar ángulo de protector"),
        ("6B", "PRIMARIA", None),
        ("5A", "PRIMARIA", None),
        ("1C", "PRIMARIA", None),
        ("ARAÑA", "PRIMARIA", None),
        ("AJEDREZ", "PRIMARIA", None),
        ("3F", "PRIMARIA", None),
        ("1B", "PRIMARIA", None),
        ("3A", "PRIMARIA", None),
        ("4F INGLÉS", "PRIMARIA", None),
        ("4B", "PRIMARIA", None),
        ("5F", "PRIMARIA", None),
        ("6D", "PRIMARIA", None),
        ("6E", "PRIMARIA", None),
        ("2E", "PRIMARIA", None),
        ("2D", "PRIMARIA", "No detecta el control"),
        ("1A", "PRIMARIA", None),
        ("1F", "PRIMARIA", None),
        ("3B", "PRIMARIA", None),
        ("3C", "PRIMARIA", None),
        ("4", "PRIMARIA", None),
        ("MÚSICA I", "PRIMARIA", None),
        ("MÚSICA II", "PRIMARIA", None),
        ("COMPUTO II", "PRIMARIA", None),
        ("COMPUTO I", "PRIMARIA", None),
        ("STEAM", "PRIMARIA", None),
    ]

    ubicaciones_secundaria = [
        ("2C", "SECUNDARIA", None),
        ("5B", "SECUNDARIA", "Bajar ángulo de protector"),
        ("3B", "SECUNDARIA", None),
        ("3F", "SECUNDARIA", None),
        ("CREACIÓN ARTESANAL Y PINTURA SALÓN 10", "SECUNDARIA", None),
        ("1B", "SECUNDARIA", None),
        ("1C", "SECUNDARIA", None),
        ("1F", "SECUNDARIA", None),
        ("1G", "SECUNDARIA", None),
        ("2A", "SECUNDARIA", None),
        ("3D", "SECUNDARIA", None),
        ("2G", "SECUNDARIA", None),
        ("2F", "SECUNDARIA", None),
        ("3A", "SECUNDARIA", None),
        ("3C", "SECUNDARIA", None),
        ("INGLÉS IV", "SECUNDARIA", None),
        ("3G", "SECUNDARIA", None),
        ("INGLÉS I", "SECUNDARIA", None),
        ("INGLÉS II", "SECUNDARIA", None),
        ("INGLÉS III", "SECUNDARIA", None),
        ("BIOLOGÍA", "SECUNDARIA", None),
        ("COMPUTO I", "SECUNDARIA", None),
        ("COMPUTO II", "SECUNDARIA", None),
        ("COMPUTO III", "SECUNDARIA", None),
        ("1D", "SECUNDARIA", None),
        ("1A", "SECUNDARIA", None),
        ("COMPUTO IV", "SECUNDARIA", None),
        ("DIRECCIÓN", "SECUNDARIA", None),
        ("QUÍMICA", "SECUNDARIA", None),
        ("FÍSICA", "SECUNDARIA", None),
        ("FOTOGRAFÍA Y PIANO SALÓN 8", "SECUNDARIA", None),
        ("DISEÑO ARQUITECTÓNICO SALÓN 11", "SECUNDARIA", None),
        ("CANTO E INSTRUMENTO SALÓN 6", "SECUNDARIA", None),
    ]

    ubicaciones_preparatoria = [
        ("PREPARATORIA", "PREPARATORIA", "Incluye variantes de SALA JUNTAS DIRECCIÓN"),
        ("23", "PREPARATORIA", None),
        ("SALA DE DIRECTORES", "PREPARATORIA", None),
        ("FÍSICA", "PREPARATORIA", None),
        ("QUÍMICA", "PREPARATORIA", None),
        ("NO LOCALIZABLE", "PREPARATORIA", "Marcaba PREPARATORIA"),
        ("3 – CENTRO DE IDIOMAS", "PREPARATORIA", None),
        ("VIDEO CONFERENCIA – CENTRO DE IDIOMAS", "PREPARATORIA", None),
        ("1 – CENTRO DE IDIOMAS", "PREPARATORIA", None),
        ("2 – CENTRO DE IDIOMAS", "PREPARATORIA", None),
        ("COMPUTO I", "PREPARATORIA", None),
        ("20", "PREPARATORIA", None),
        ("1", "PREPARATORIA", None),
        ("2", "PREPARATORIA", None),
        ("18", "PREPARATORIA", None),
        ("16", "PREPARATORIA", None),
        ("5", "PREPARATORIA", None),
        ("COMPUTO II", "PREPARATORIA", None),
        ("INNOVACIÓN Y TECNOLOGÍA II", "PREPARATORIA", None),
        ("22", "PREPARATORIA", None),
        ("21", "PREPARATORIA", None),
        ("6", "PREPARATORIA", None),
        ("MULTI2", "PREPARATORIA", None),
        ("19", "PREPARATORIA", None),
        ("8", "PREPARATORIA", None),
        ("9", "PREPARATORIA", None),
        ("17", "PREPARATORIA", None),
        ("15", "PREPARATORIA", None),
        ("10", "PREPARATORIA", None),
        ("14", "PREPARATORIA", None),
        ("11", "PREPARATORIA", None),
        ("12", "PREPARATORIA", None),
        ("4", "PREPARATORIA", None),
        ("3", "PREPARATORIA", None),
        ("7", "PREPARATORIA", None),
        ("AULA MAGNA I", "PREPARATORIA", None),
        ("13", "PREPARATORIA", None),
        ("BIOLOGÍA", "PREPARATORIA", "PREPARATORIA"),
    ]

    todas_ubicaciones = (
        ubicaciones_preescolar + ubicaciones_primaria + ubicaciones_secundaria + ubicaciones_preparatoria
    )

    cursor.executemany(
        "INSERT OR IGNORE INTO ubicaciones_catalogo (nombre, nivel, nota) VALUES (?,?,?)",
        todas_ubicaciones
    )
    conn.commit()
    print(f"Catálogo de ubicaciones actualizado. Total cargadas (intentos): {len(todas_ubicaciones)}")

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