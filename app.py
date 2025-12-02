from sre_parse import CATEGORIES
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from datetime import datetime
import sqlite3
import os
import secrets
import threading
import time
import json
from io import BytesIO
try:
    import qrcode
    from PIL import Image
except Exception:
    qrcode = None
    Image = None
try:
    from xhtml2pdf import pisa
except Exception:
    pisa = None
try:
    import serial
    import serial.tools.list_ports
except Exception:
    serial = None
    import serial as _serial_disabled  # placeholder

# Se especifica la carpeta de archivos estáticos (statics)
app = Flask(__name__, static_folder='static')
# SECRET_KEY segura desde entorno o generada aleatoriamente (no determinista)
app.secret_key = os.environ.get('FLASK_SECRET') or secrets.token_hex(32)
DB_PATH = r"C:\Users\ROG\Desktop\SS\SistemaCCC\inventario_consolidado.db"

CATEGORIAS = {
    "ANT": "Antenas",
    "UPS": "APC / Energía",
    "DIA": "Audífonos / Diademas",
    "BAJ": "Baja",
    "MON": "Bodega / Monitores",
    "BX": "Boombox",
    "CPU": "Computadoras / CPU",
    "ELI": "Eliminadores",
    "MAC": "Mac",
    "MZ": "Mezcladoras",
    "PR": "Pilas de Radio",
    "MOU": "Ratones",
    "TEC": "Teclados",
    "TEL": "Teléfonos",
    "WM": "Micrófonos inalámbricos",
    "MC": "Multicontactos / Hubs",
    "POLY": "Polycom",
    "PRO": "Proyectores"
}


def log_movimiento(usuario, accion, rowid_producto=None, sku=None, detalles=None, max_retries=5, retry_delay=0.12):
    """Guarda un registro en movimientos con reintentos si la BD está bloqueada."""
    detalles_json = json.dumps(detalles, ensure_ascii=False) if detalles is not None else None
    attempt = 0
    while attempt <= max_retries:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            cur = conn.cursor()
            try:
                cur.execute("PRAGMA busy_timeout=4000")
                cur.execute("PRAGMA journal_mode=WAL")
            except Exception:
                pass
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS movimientos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT,
                    accion TEXT,
                    rowid_producto INTEGER,
                    sku TEXT,
                    detalles TEXT,
                    cuando TEXT
                )
                """
            )
            cur.execute(
                "INSERT INTO movimientos (usuario, accion, rowid_producto, sku, detalles, cuando) VALUES (?,?,?,?,?,?)",
                (usuario, accion, rowid_producto, sku, detalles_json, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.OperationalError as oe:
            if 'locked' in str(oe).lower():
                attempt += 1
                if attempt > max_retries:
                    try:
                        print(f"[WARN] log_movimiento abandonado por lock: accion={accion} sku={sku}")
                    except Exception:
                        pass
                    return False
                time.sleep(retry_delay)
                continue
            else:
                try:
                    print(f"[WARN] log_movimiento fallo operativo: {oe}")
                except Exception:
                    pass
                return False
        except Exception as e:
            try:
                print(f"[WARN] log_movimiento excepción: {e}")
            except Exception:
                pass
            return False


def get_db():
    """Devuelve una conexión SQLite con configuración segura.
    Uso recomendado: with get_db() as conn:
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=4000")
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    return conn

def ensure_ventas_table():
    """Garantiza que la tabla ventas exista con todas las columnas necesarias."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rowid_producto INTEGER,
        sku TEXT,
        tipo TEXT,
        marca TEXT,
        modelo TEXT,
        no_serie TEXT,
        precio_venta REAL,
        comprador TEXT,
        vendedor TEXT,
        observaciones TEXT,
        fecha_venta TEXT,
        evento_fecha TEXT,
        ticket_id INTEGER
    )""")
    # Verificar columnas faltantes (por migraciones anteriores parciales)
    cur.execute("PRAGMA table_info(ventas)")
    cols = {r[1] for r in cur.fetchall()}
    required = ["rowid_producto","sku","tipo","marca","modelo","no_serie","precio_venta","comprador","vendedor","observaciones","fecha_venta","evento_fecha","ticket_id"]
    for col in required:
        if col not in cols:
            # Intentar agregar si falta (tipo REAL/TEXT flexible según campo)
            tipo_sql = "TEXT"
            if col in ("precio_venta"): tipo_sql = "REAL"
            if col == "ticket_id": tipo_sql = "INTEGER"
            cur.execute(f"ALTER TABLE ventas ADD COLUMN {col} {tipo_sql}")
    conn.commit()
    conn.close()


def ensure_venta_tickets_table():
    """Tabla que agrupa varias partidas de venta bajo un solo ticket."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS venta_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comprador TEXT,
        vendedor TEXT,
        observaciones TEXT,
        fecha_venta TEXT,
        evento_fecha TEXT,
        total REAL,
        total_items INTEGER
    )""")
    conn.commit()
    conn.close()


def ensure_ticket_support():
    """Conveniencia para garantizar que ventas y tickets estén listos."""
    ensure_ventas_table()
    ensure_venta_tickets_table()


@app.route("/", methods=["GET", "POST"])
def login():
    mensaje = ""
    
    if request.method == "POST":
        usuario = request.form["usuario"]
        password = request.form["password"]
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE usuario=? AND password=?", (usuario, password))
        user = cur.fetchone()
        conn.close()
        
        if user:
            # Guardar el usuario en la sesión para mostrar su nombre en el panel
            try:
                session['usuario'] = usuario
            except Exception:
                pass
            # Registrar login en movimientos
            try:
                log_movimiento(usuario, 'LOGIN')
            except Exception:
                pass
            # Suponemos que la columna tipo está en user[3]
            tipo = user[3]   # Ajusta si está en otro índice

            if tipo == 1:
                return redirect(url_for("admin"))
            elif tipo == 2:
                return redirect(url_for("invitado"))
            else:
                mensaje = "Rol de usuario no válido."
        else:
            mensaje = "Usuario o contraseña incorrectos."

    return render_template("login.html", mensaje=mensaje)

# -------------------------
#    VISTAS (vacías)
# -------------------------


@app.route("/admin")
def admin():
    # Tomar el nombre de usuario de la sesión si existe
    usuario = session.get('usuario') or "Administrador"
    # Capitalizar la primera letra
    try:
        usuario = usuario.capitalize()
    except Exception:
        usuario = usuario
    # Intentar leer datos reales desde la BD
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # Total productos
        cur.execute("SELECT COUNT(*) FROM inventory")
        total_productos = cur.fetchone()[0] or 0

        # Total categorías (prefijo del SKU antes del guion)
        cur.execute(
            "SELECT COUNT(DISTINCT(CASE WHEN instr(sku,'-')>0 THEN substr(sku,1,instr(sku,'-')-1) ELSE sku END)) FROM inventory"
        )
        total_categorias = cur.fetchone()[0] or 0

        # Entradas recientes (últimos 7 días) — si fecha_registro está presente
        entradas_recientes = 0
        try:
            cur.execute("SELECT COUNT(*) FROM inventory WHERE (julianday('now') - julianday(fecha_registro)) <= 7")
            entradas_recientes = cur.fetchone()[0] or 0
        except Exception:
            entradas_recientes = 0

        # Salidas: no existe tabla de movimientos, por ahora 0
        salidas_recientes = 0

        # Actividad reciente: últimos 9 registros por orden de inserción (rowid)
        recent_activity = []
        try:
            cur.execute("SELECT rowid, sku, tipo, fecha_registro FROM inventory ORDER BY rowid DESC LIMIT 9")
            rows = cur.fetchall()
            for r in rows:
                rowid_val = r[0]
                sku = r[1] or ''
                tipo_val = r[2] or ''
                fecha = r[3] or ''
                if isinstance(fecha, str) and fecha:
                    meta = fecha.replace('T', ' ')
                else:
                    # si fecha_registro no es confiable, mostrar el rowid como fallback
                    meta = f"row {rowid_val}"
                recent_activity.append({"sku": sku, "tipo": tipo_val, "meta": meta})
        except Exception:
            recent_activity = []

        # Total usuarios
        try:
            cur.execute("SELECT COUNT(*) FROM usuarios")
            total_usuarios = cur.fetchone()[0] or 0
        except Exception:
            total_usuarios = 0

        conn.close()
    except Exception:
        total_productos = 0
        total_categorias = len(CATEGORIAS)
        entradas_recientes = 0
        salidas_recientes = 0
        recent_activity = []
        total_usuarios = 0

    contexto = {
        "usuario": usuario,
        "total_productos": total_productos,
        "total_categorias": total_categorias,
        "entradas_recientes": entradas_recientes,
        "salidas_recientes": salidas_recientes,
        "recent_activity": recent_activity,
        "total_usuarios": total_usuarios,
    }

    return render_template("admin.html", **contexto)


@app.route("/invitado")
def invitado():
    return render_template("invitado.html")

@app.route("/entradas", methods=["GET"])
def entradas():
    # Obtener el prefijo y los campos mantenidos (para casos de error)
    prefijo_mantener = request.args.get('prefijo', '')
    
    # También obtener valores de campos mantenidos si vienen en los parámetros
    # (esto pasa cuando hay error de validación)
    tipo_mantener = request.args.get('tipo', '')
    marca_mantener = request.args.get('marca', '')
    modelo_mantener = request.args.get('modelo', '')
    precio_mantener = request.args.get('precio', '')
    estado_mantener = request.args.get('estado', '')
    ubicacion_mantener = request.args.get('ubicacion', '')
    observacion_mantener = request.args.get('observacion', '')
    
    # Mostrar formulario para registrar nuevas entradas
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT(CASE WHEN instr(sku,'-')>0 THEN substr(sku,1,instr(sku,'-')-1) ELSE sku END) as pref FROM inventory ORDER BY pref")
        prefs = [r[0] for r in cur.fetchall()]
        conn.close()
    except Exception:
        prefs = []

    # Pasar todos los valores a la plantilla
    return render_template("entradas.html", 
                         prefixes=prefs, 
                         prefijo_mantener=prefijo_mantener,
                         tipo_mantener=tipo_mantener,
                         marca_mantener=marca_mantener,
                         modelo_mantener=modelo_mantener,
                         precio_mantener=precio_mantener,
                         estado_mantener=estado_mantener,
                         ubicacion_mantener=ubicacion_mantener,
                         observacion_mantener=observacion_mantener)

@app.route('/entradas/options')
def entradas_options():
    pref = request.args.get('prefijo', '').strip()
    if not pref:
        return jsonify({'ok': False, 'msg': 'prefijo requerido'}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        like_pat = f"{pref}-%"
        data = {}
        for col in ('tipo','marca','modelo','estado','ubicacion','volts'):
            cur.execute(f"SELECT DISTINCT {col} FROM inventory WHERE sku LIKE ? AND {col} IS NOT NULL AND {col}!='' LIMIT 200", (like_pat,))
            data[col] = [r[0] for r in cur.fetchall() if r[0] is not None]
        conn.close()
        return jsonify({'ok': True, 'data': data})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


@app.route('/entradas/skus')
def entradas_skus():
    pref = request.args.get('prefijo', '').strip()
    if not pref:
        return jsonify({'ok': False, 'msg': 'prefijo requerido'}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT rowid, sku, tipo, marca, modelo FROM inventory WHERE sku LIKE ? ORDER BY sku LIMIT 500", (f"{pref}-%",))
        rows = cur.fetchall()
        conn.close()
        data = [{'rowid': r[0], 'sku': r[1], 'tipo': r[2], 'marca': r[3], 'modelo': r[4]} for r in rows]
        return jsonify({'ok': True, 'data': data})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


@app.route('/product_by_sku')
def product_by_sku():
    sku = request.args.get('sku', '').strip()
    if not sku:
        return jsonify({'ok': False, 'msg': 'sku requerido'}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT rowid, sku, id_original, tipo, marca, modelo, no_serie, volts, precio, estado, ubicacion, fecha_registro, observacion FROM inventory WHERE sku = ? LIMIT 1", (sku,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({'ok': False, 'msg': 'not found'}), 404
        keys = ['rowid','sku','id_original','tipo','marca','modelo','no_serie','volts','precio','estado','ubicacion','fecha_registro','observacion']
        data = dict(zip(keys, row))
        return jsonify({'ok': True, 'data': data})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


@app.route('/entradas/next_sku')
def entradas_next_sku():
    pref = request.args.get('prefijo', '').strip()
    if not pref:
        return jsonify({'ok': False, 'msg': 'prefijo requerido'}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT MAX(CAST(substr(sku, instr(sku,'-')+1) AS INTEGER)) FROM inventory WHERE sku LIKE ?", (f"{pref}-%",))
        r = cur.fetchone()
        conn.close()
        maxnum = r[0] if r and r[0] is not None else 0
        nextnum = int(maxnum or 0) + 1
        next_sku = f"{pref}-{nextnum}"
        return jsonify({'ok': True, 'next_sku': next_sku, 'next_number': nextnum})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


@app.route('/entradas/register', methods=['POST'])
def entradas_register():
    # Insertar nuevo producto en inventory
    form = request.form
    sku = form.get('sku', '').strip()
    id_original = form.get('id_original', '').strip() or None
    tipo = form.get('tipo', '').strip() or None
    marca = form.get('marca', '').strip() or None
    modelo = form.get('modelo', '').strip() or None
    no_serie = form.get('no_serie', '').strip() or None
    volts = form.get('volts', '').strip() or None
    precio = form.get('precio', '').strip() or None
    estado = form.get('estado', '').strip() or None
    ubicacion = form.get('ubicacion', '').strip() or None
    fecha_registro = form.get('fecha_registro', '').strip() or datetime.now().isoformat()
    observacion = form.get('observacion', '').strip() or None
    campos_mantenidos = form.get('campos_mantenidos', '').split(',') if form.get('campos_mantenidos') else []

    if not sku:
        return "SKU requerido", 400

    # ---------------- VALIDACIÓN DE DUPLICADO ----------------
    if no_serie:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM inventory WHERE no_serie = ?", (no_serie,))
            exists_count = cur.fetchone()[0]
            conn.close()

            if exists_count and exists_count > 0:
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cur = conn.cursor()
                    cur.execute("SELECT DISTINCT(CASE WHEN instr(sku,'-')>0 THEN substr(sku,1,instr(sku,'-')-1) ELSE sku END) as pref FROM inventory ORDER BY pref")
                    prefs = [r[0] for r in cur.fetchall()]
                    conn.close()
                except Exception:
                    prefs = []

                # ✅ PRESERVAR LOS CAMPOS MANTENIDOS CUANDO HAY ERROR
                form_values = {
                    'prefijo': sku.split('-')[0] if '-' in sku else sku,
                    'tipo': tipo if 'tipo' in campos_mantenidos else '',
                    'marca': marca if 'marca' in campos_mantenidos else '',
                    'modelo': modelo if 'modelo' in campos_mantenidos else '',
                    'precio': precio if 'precio' in campos_mantenidos else '',
                    'estado': estado if 'estado' in campos_mantenidos else '',
                    'ubicacion': ubicacion if 'ubicacion' in campos_mantenidos else '',
                    'observacion': observacion if 'observacion' in campos_mantenidos else ''
                }
                
                return render_template('entradas.html', 
                                    prefixes=prefs, 
                                    error='No. serie ya registrado en la base de datos.', 
                                    **form_values), 400
        except Exception:
            pass

    # ---------------- INSERTAR PRODUCTO ----------------
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO inventory (sku, id_original, tipo, marca, modelo, no_serie, volts, precio, estado, ubicacion, fecha_registro, origen_hoja, observacion, extras) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sku, id_original, tipo, marca, modelo, no_serie, volts, precio, estado, ubicacion, fecha_registro, None, observacion, None)
        )
        lastid = cur.lastrowid
        conn.commit()
        conn.close()

        # Registrar movimiento
        try:
            detalles = {'no_serie': no_serie, 'precio': precio, 'ubicacion': ubicacion}
            log_movimiento(session.get('usuario'), 'ENTRADA', lastid, sku, detalles)
        except Exception:
            pass

        # ✅ CORRECTO: Solo mantener el prefijo
        prefijo = sku.split('-')[0] if '-' in sku else sku
        
        # Redirigir solo con el prefijo
        return redirect(url_for('entradas') + '?prefijo=' + prefijo)

    except Exception as e:
        return f"Error al insertar: {e}", 500

########

@app.route("/categorias")
def categorias_list():
    # Build categories from inventory prefixes and optional overrides stored in DB
    categorias_map = {}
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # ensure categorias table exists
        cur.execute("CREATE TABLE IF NOT EXISTS categorias_prefijos (prefijo TEXT PRIMARY KEY, nombre TEXT)")
        # get distinct prefixes from inventory
        cur.execute("SELECT DISTINCT(CASE WHEN instr(sku,'-')>0 THEN substr(sku,1,instr(sku,'-')-1) ELSE sku END) as pref FROM inventory ORDER BY pref")
        prefs = [r[0] for r in cur.fetchall()]
        # load overrides
        cur.execute("SELECT prefijo, nombre FROM categorias_prefijos")
        overrides = {r[0]: r[1] for r in cur.fetchall()}
        conn.close()
        for p in prefs:
            if p in overrides and overrides[p]:
                categorias_map[p] = overrides[p]
            elif p in CATEGORIAS:
                categorias_map[p] = CATEGORIAS[p]
            else:
                categorias_map[p] = p
    except Exception:
        categorias_map = CATEGORIAS

    return render_template("categorias_list.html", categorias=categorias_map)


@app.route('/categorias/update', methods=['POST'])
def categorias_update():
    prefijo = request.form.get('prefijo', '').strip()
    nombre = request.form.get('nombre', '').strip()
    if not prefijo:
        return jsonify({'ok': False, 'msg': 'prefijo requerido'}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS categorias_prefijos (prefijo TEXT PRIMARY KEY, nombre TEXT)")
        cur.execute("INSERT INTO categorias_prefijos(prefijo,nombre) VALUES(?,?) ON CONFLICT(prefijo) DO UPDATE SET nombre=excluded.nombre", (prefijo, nombre))
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'msg': 'Actualizado'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500
#####################
@app.route("/productos/<prefijo>")
def productos_por_categoria(prefijo):
    q = request.args.get('q', '').strip()
    parametros = []
    nombre_categoria = CATEGORIAS.get(prefijo, prefijo)

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # Usamos la tabla `inventory` y seleccionamos todas las columnas relevantes
        base_query = ("SELECT rowid, sku, id_original, tipo, marca, modelo, no_serie, volts, precio, "
                  "estado, ubicacion, fecha_registro, origen_hoja, observacion, extras "
                  "FROM inventory WHERE sku LIKE ?")
        parametros.append(f"{prefijo}-%")

        if q:
            base_query += " AND (sku LIKE ? OR marca LIKE ? OR modelo LIKE ? OR observacion LIKE ? OR id_original LIKE ? )"
            like_q = f"%{q}%"
            parametros.extend([like_q, like_q, like_q, like_q, like_q])

        cur.execute(base_query, parametros)
        productos = cur.fetchall()
        conn.close()
    except Exception:
        # En caso de fallo con la BD, devolver ejemplo estático
        productos = [
            (1, f"{prefijo}-001", "Producto ejemplo"),
        ]

    return render_template("productos_list.html", productos=productos, categoria=nombre_categoria, prefijo=prefijo, q=q)


@app.route("/productos")
def productos_all():
    # Soporta filtro por query 'q' (busca en sku y descripcion)
    q = request.args.get('q', '').strip()
    search_field = request.args.get('search_field', '').strip()
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        if q:
            if search_field == 'no_serie':
                # Búsqueda exacta por número de serie
                query = ("SELECT rowid, sku, id_original, tipo, marca, modelo, no_serie, volts, precio, "
                         "estado, ubicacion, fecha_registro, origen_hoja, observacion, extras "
                         "FROM inventory WHERE no_serie = ? LIMIT 1000")
                cur.execute(query, (q,))
            else:
                query = ("SELECT rowid, sku, id_original, tipo, marca, modelo, no_serie, volts, precio, "
                         "estado, ubicacion, fecha_registro, origen_hoja, observacion, extras "
                         "FROM inventory WHERE sku LIKE ? OR marca LIKE ? OR modelo LIKE ? OR observacion LIKE ? OR id_original LIKE ? LIMIT 1000")
                like_q = f"%{q}%"
                cur.execute(query, (like_q, like_q, like_q, like_q, like_q))
        else:
            query = ("SELECT rowid, sku, id_original, tipo, marca, modelo, no_serie, volts, precio, "
                     "estado, ubicacion, fecha_registro, origen_hoja, observacion, extras FROM inventory LIMIT 1000")
            cur.execute(query)
        productos = cur.fetchall()
        conn.close()
    except Exception:
        # Si hay algún problema con la BD, mostramos datos simulados
        if q:
            productos = [
                (1, "CPU-001", "Computadora ejemplo que coincide con: " + q),
            ]
        else:
            productos = [
                (1, "CPU-001", "Computadora de escritorio ejemplo"),
                (2, "MON-001", "Monitor 24 pulgadas ejemplo"),
                (3, "MOU-001", "Mouse inalámbrico ejemplo"),
            ]

    return render_template("productos_list.html", productos=productos, categoria="Todos los productos", q=q)


# --- Edición de producto con clave de acceso ---
@app.route('/productos/<int:rowid>/request_edit', methods=['GET', 'POST'])
def request_edit(rowid):
    error = None
    if request.method == 'POST':
        key = request.form.get('key', '').strip()
        if key == '9247':
            return redirect(url_for('editar_producto', rowid=rowid))
        else:
            error = 'Clave incorrecta.'
    return render_template('edit_key.html', rowid=rowid, error=error)


@app.route('/productos/<int:rowid>/edit', methods=['GET', 'POST'])
def editar_producto(rowid):
    if request.method == 'POST':
        # Recoger valores del formulario
        sku = request.form.get('sku')
        id_original = request.form.get('id_original')
        tipo = request.form.get('tipo')
        marca = request.form.get('marca')
        modelo = request.form.get('modelo')
        no_serie = request.form.get('no_serie')
        volts = request.form.get('volts')
        precio = request.form.get('precio')
        estado = request.form.get('estado')
        ubicacion = request.form.get('ubicacion')
        fecha_registro = request.form.get('fecha_registro')
        observacion = request.form.get('observacion')

        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE inventory SET sku=?, id_original=?, tipo=?, marca=?, modelo=?, no_serie=?, volts=?, precio=?, estado=?, ubicacion=?, fecha_registro=?, observacion=?
                WHERE rowid=?
                """,
                (sku, id_original, tipo, marca, modelo, no_serie, volts, precio, estado, ubicacion, fecha_registro, observacion, rowid)
            )
            conn.commit()
            conn.close()
            # Registrar edición en movimientos
            try:
                detalles = {'observacion': observacion}
                log_movimiento(session.get('usuario'), 'EDIT', rowid, sku, detalles)
            except Exception:
                pass
        except Exception:
            # En caso de error, simplemente redirigimos de vuelta
            return redirect(url_for('productos_all'))

        return redirect(url_for('productos_all'))

    # GET: obtener datos actuales del producto
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT rowid, sku, id_original, tipo, marca, modelo, no_serie, volts, precio, estado, ubicacion, fecha_registro, origen_hoja, observacion, extras FROM inventory WHERE rowid=?",
            (rowid,)
        )
        row = cur.fetchone()
        conn.close()
    except Exception:
        row = None

    if not row:
        return redirect(url_for('productos_all'))

    # Construir diccionario con campos (omitimos origen_hoja y extras del formulario editable)
    producto = {
        'rowid': row[0],
        'sku': row[1],
        'id_original': row[2],
        'tipo': row[3],
        'marca': row[4],
        'modelo': row[5],
        'no_serie': row[6],
        'volts': row[7],
        'precio': row[8],
        'estado': row[9],
        'ubicacion': row[10],
        'fecha_registro': row[11],
        'observacion': row[13]
    }

    return render_template('edit_product.html', producto=producto)





@app.route("/salidas")
def salidas():
    q = request.args.get('q', '').strip()
    search_field = request.args.get('search_field', '').strip()
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # Productos que están en VENTA y tienen precio (VERSIÓN ORIGINAL QUE SÍ FUNCIONA)
        cur.execute(("SELECT rowid, sku, id_original, tipo, marca, modelo, no_serie, volts, precio, "
                     "estado, ubicacion, fecha_registro, origen_hoja, observacion, extras "
                     "FROM inventory WHERE estado = 'VENTA' AND precio IS NOT NULL ORDER BY sku LIMIT 1000"))
        productos_venta = cur.fetchall()

        # Búsqueda para marcar salidas (DONADO/OBSOLETO)
        search_results = []
        if q:
            if search_field == 'no_serie':
                query = ("SELECT rowid, sku, id_original, tipo, marca, modelo, no_serie, volts, precio, "
                         "estado, ubicacion, fecha_registro, origen_hoja, observacion, extras "
                         "FROM inventory WHERE no_serie = ? LIMIT 1000")
                cur.execute(query, (q,))
            else:
                query = ("SELECT rowid, sku, id_original, tipo, marca, modelo, no_serie, volts, precio, "
                         "estado, ubicacion, fecha_registro, origen_hoja, observacion, extras "
                         "FROM inventory WHERE sku LIKE ? OR marca LIKE ? OR modelo LIKE ? OR observacion LIKE ? OR id_original LIKE ? LIMIT 1000")
                like_q = f"%{q}%"
                cur.execute(query, (like_q, like_q, like_q, like_q, like_q))
            search_results = cur.fetchall()

        conn.close()
    except Exception:
        productos_venta = []
        search_results = []

    return render_template("salidas.html", productos_venta=productos_venta, search_results=search_results, q=q)

@app.route('/salidas/registrar_venta', methods=['POST'])
def registrar_venta():
    rowid = request.form.get('rowid') or request.json.get('rowid') if request.is_json else None
    comprador = request.form.get('comprador', '').strip()
    precio_venta = request.form.get('precio_venta', '').strip()
    observaciones = request.form.get('observaciones', '').strip()
    fecha_evento = (request.form.get('fecha_evento') if request.form.get('fecha_evento') is not None else (request.json.get('fecha_evento') if request.is_json else None))
    
    if not rowid or not comprador or not precio_venta:
        return jsonify({'ok': False, 'msg': 'Producto, comprador y precio son requeridos'}), 400
    try:
        precio_venta_num = float(precio_venta)
    except Exception:
        return jsonify({'ok': False, 'msg': 'Precio inválido'}), 400
    
    try:
        ensure_ticket_support()
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Obtener información del producto
        cur.execute("""
            SELECT sku, tipo, marca, modelo, no_serie, precio 
            FROM inventory WHERE rowid=?
        """, (rowid,))
        producto = cur.fetchone()
        
        if not producto:
            conn.close()
            return jsonify({'ok': False, 'msg': 'Producto no encontrado'}), 404
        
        sku, tipo, marca, modelo, no_serie, precio_inventory = producto
        
        # Validar evento (si se proporcionó)
        if fecha_evento:
            cur.execute("SELECT estado FROM venta_eventos WHERE fecha=?", (fecha_evento,))
            ev = cur.fetchone()
            if not ev:
                conn.close()
                return jsonify({'ok': False, 'msg': 'No existe evento para la fecha indicada'}), 400
            if ev[0] != 'OPEN':
                conn.close()
                return jsonify({'ok': False, 'msg': 'El evento no está abierto'}), 400

        # Insertar en tabla de ventas
        fecha_venta = datetime.now().isoformat()
        vendedor = session.get('usuario', 'Sistema')

        cur.execute("""
            INSERT INTO venta_tickets (comprador, vendedor, observaciones, fecha_venta, evento_fecha, total, total_items)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (comprador, vendedor, observaciones, fecha_venta, fecha_evento, precio_venta_num, 1))
        ticket_id = cur.lastrowid

        cur.execute("""
            INSERT INTO ventas (rowid_producto, sku, tipo, marca, modelo, no_serie, precio_venta, comprador, vendedor, fecha_venta, observaciones, evento_fecha, ticket_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (rowid, sku, tipo, marca, modelo, no_serie, precio_venta_num, comprador, vendedor, fecha_venta, observaciones, fecha_evento, ticket_id))
        venta_id = cur.lastrowid
        try:
            print(f"[DEBUG] registrar_venta: venta_id={venta_id} sku={sku} precio={precio_venta} evento_fecha={fecha_evento}")
        except Exception:
            pass
        
        # Actualizar estado del producto a VENDIDO
        cur.execute("UPDATE inventory SET estado='VENDIDO' WHERE rowid=?", (rowid,))
        
        conn.commit()
        conn.close()
        
        # Registrar movimiento
        try:
            log_movimiento(session.get('usuario'), 'VENTA_REGISTRADA', rowid, sku, {
                'precio_venta': precio_venta_num,
                'comprador': comprador,
                'observaciones': observaciones,
                'ticket_id': ticket_id
            })
        except Exception:
            pass
        
        return jsonify({'ok': True, 'msg': 'Venta registrada correctamente', 'venta_id': venta_id, 'ticket_id': ticket_id})
        
    except Exception as e:
        return jsonify({'ok': False, 'msg': f'Error: {str(e)}'}), 500

@app.route('/salidas/registrar_ventas_bulk', methods=['POST'])
def registrar_ventas_bulk():
    """Registra múltiples ventas en una sola transacción para un comprador."""
    try:
        payload = request.get_json(silent=True) or {}
        items = payload.get('items') or []
        comprador = (payload.get('comprador') or '').strip()
        observaciones = (payload.get('observaciones') or '').strip()
        fecha_evento = payload.get('fecha_evento')
        if not items or not isinstance(items, list):
            return jsonify({'ok': False, 'msg': 'Lista de artículos requerida'}), 400
        if not comprador:
            return jsonify({'ok': False, 'msg': 'Comprador requerido'}), 400
        if not fecha_evento:
            return jsonify({'ok': False, 'msg': 'Fecha de evento requerida'}), 400

        ensure_ticket_support()
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT estado FROM venta_eventos WHERE fecha=?", (fecha_evento,))
        ev = cur.fetchone()
        if not ev:
            conn.close()
            return jsonify({'ok': False, 'msg': 'No existe evento para la fecha indicada'}), 400
        if ev[0] != 'OPEN':
            conn.close()
            return jsonify({'ok': False, 'msg': 'El evento no está abierto'}), 400

        fecha_venta = datetime.now().isoformat()
        vendedor = session.get('usuario', 'Sistema')
        inserted_ids = []
        movement_queue = []
        prepared_items = []
        total_ticket = 0.0
        try:
            for it in items:
                rowid = str(it.get('rowid') or '').strip()
                precio_venta = it.get('precio_venta')
                if not rowid:
                    raise Exception('Elemento sin rowid')
                try:
                    precio_venta = float(precio_venta)
                except Exception:
                    raise Exception('Precio inválido para algún artículo')
                cur.execute("SELECT sku, tipo, marca, modelo, no_serie, estado FROM inventory WHERE rowid=?", (rowid,))
                pr = cur.fetchone()
                if not pr:
                    raise Exception(f'Producto {rowid} no encontrado')
                sku, tipo, marca, modelo, no_serie, estado = pr
                if estado in ('VENDIDO', 'DONADO', 'OBSOLETO'):
                    raise Exception(f'Producto {sku} ya no está disponible ({estado})')
                prepared_items.append({
                    'rowid': rowid,
                    'sku': sku,
                    'tipo': tipo,
                    'marca': marca,
                    'modelo': modelo,
                    'no_serie': no_serie,
                    'precio_venta': precio_venta
                })
                total_ticket += precio_venta

            if not prepared_items:
                raise Exception('No se recibieron artículos válidos')

            cur.execute("""
                INSERT INTO venta_tickets (comprador, vendedor, observaciones, fecha_venta, evento_fecha, total, total_items)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (comprador, vendedor, observaciones, fecha_venta, fecha_evento, total_ticket, len(prepared_items)))
            ticket_id = cur.lastrowid

            for item in prepared_items:
                cur.execute(
                    """
                    INSERT INTO ventas (rowid_producto, sku, tipo, marca, modelo, no_serie, precio_venta, comprador, vendedor, fecha_venta, observaciones, evento_fecha, ticket_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (item['rowid'], item['sku'], item['tipo'], item['marca'], item['modelo'], item['no_serie'], item['precio_venta'],
                     comprador, vendedor, fecha_venta, observaciones, fecha_evento, ticket_id)
                )
                venta_pk = cur.lastrowid
                inserted_ids.append(venta_pk)
                cur.execute("UPDATE inventory SET estado='VENDIDO' WHERE rowid=?", (item['rowid'],))
                movement_queue.append({
                    'rowid': item['rowid'],
                    'sku': item['sku'],
                    'precio_venta': item['precio_venta'],
                    'comprador': comprador,
                    'ticket_id': ticket_id
                })

            conn.commit()
            try:
                print(f"[DEBUG] registrar_ventas_bulk: inserted_ids={inserted_ids} ticket_id={ticket_id} comprador={comprador} evento_fecha={fecha_evento}")
            except Exception:
                pass
        except Exception as inner:
            conn.rollback()
            conn.close()
            return jsonify({'ok': False, 'msg': str(inner)}), 400

        conn.close()
        for mv in movement_queue:
            try:
                log_movimiento(session.get('usuario'), 'VENTA_REGISTRADA', mv['rowid'], mv['sku'], {
                    'precio_venta': mv['precio_venta'],
                    'comprador': mv['comprador'],
                    'ticket_id': mv['ticket_id']
                })
            except Exception:
                pass
        return jsonify({'ok': True, 'msg': f"{len(items)} ventas registradas para {comprador}", 'venta_ids': inserted_ids, 'ticket_id': ticket_id})
    except Exception as e:
        return jsonify({'ok': False, 'msg': f'Error: {str(e)}'}), 500

# Mantener las rutas existentes para mark_sold y mark_out...
@app.route('/salidas/mark_sold', methods=['POST'])
def salidas_mark_sold():
    rowid = request.form.get('rowid') or request.json.get('rowid') if request.is_json else None
    if not rowid:
        return jsonify({'ok': False, 'msg': 'rowid requerido'}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # obtener info para log
        cur.execute("SELECT sku, precio FROM inventory WHERE rowid=?", (rowid,))
        r = cur.fetchone()
        sku = r[0] if r else None
        precio = r[1] if r else None
        # actualizar estado
        cur.execute("UPDATE inventory SET estado='VENDIDO' WHERE rowid=?", (rowid,))
        conn.commit()
        conn.close()
        # Registrar movimiento
        try:
            log_movimiento(session.get('usuario'), 'VENDIDO', rowid, sku, {'precio': precio})
        except Exception:
            pass
        return jsonify({'ok': True, 'msg': 'Producto marcado como VENDIDO'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500

@app.route('/salidas/mark_out', methods=['POST'])
def salidas_mark_out():
    # Cambiar estado a DONADO o OBSOLETO/BASURA
    rowid = request.form.get('rowid') or (request.json.get('rowid') if request.is_json else None)
    accion = (request.form.get('accion') or (request.json.get('accion') if request.is_json else None) or '').upper()
    if not rowid or accion not in ('DONADO', 'OBSOLETO', 'BASURA'):
        return jsonify({'ok': False, 'msg': 'parámetros inválidos'}), 400
    # normalizar OBSOLETO/BASURA a 'OBSOLETO'
    if accion == 'BASURA':
        accion = 'OBSOLETO'
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT sku FROM inventory WHERE rowid=?", (rowid,))
        r = cur.fetchone()
        sku = r[0] if r else None
        cur.execute("UPDATE inventory SET estado=? WHERE rowid=?", (accion, rowid))
        conn.commit()
        conn.close()
        try:
            log_movimiento(session.get('usuario'), accion, rowid, sku, None)
        except Exception:
            pass
        return jsonify({'ok': True, 'msg': f'Producto marcado como {accion}'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


@app.route('/venta')
def venta():
    # Muestra dos secciones: (A) productos en estado VENTA, (B) buscador para poner equipos a VENTA
    q = request.args.get('q', '').strip()
    search_field = request.args.get('search_field', '').strip()
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # A) productos que ya están en estado VENTA
        cur.execute(("SELECT rowid, sku, id_original, tipo, marca, modelo, no_serie, volts, precio, "
                     "estado, ubicacion, fecha_registro, origen_hoja, observacion, extras "
                     "FROM inventory WHERE estado = 'VENTA' ORDER BY sku LIMIT 1000"))
        productos_venta = cur.fetchall()

        # B) resultados de búsqueda para cambiar estado a VENTA
        search_results = []
        if q:
            if search_field == 'no_serie':
                # Búsqueda exacta por número de serie
                query = ("SELECT rowid, sku, id_original, tipo, marca, modelo, no_serie, volts, precio, "
                         "estado, ubicacion, fecha_registro, origen_hoja, observacion, extras "
                         "FROM inventory WHERE no_serie = ? AND estado != 'VENTA' LIMIT 1000")
                cur.execute(query, (q,))
            else:
                # Búsqueda general excluyendo productos ya en VENTA
                query = ("SELECT rowid, sku, id_original, tipo, marca, modelo, no_serie, volts, precio, "
                         "estado, ubicacion, fecha_registro, origen_hoja, observacion, extras "
                         "FROM inventory WHERE (sku LIKE ? OR marca LIKE ? OR modelo LIKE ? OR observacion LIKE ? OR id_original LIKE ?) "
                         "AND estado != 'VENTA' LIMIT 1000")
                like_q = f"%{q}%"
                cur.execute(query, (like_q, like_q, like_q, like_q, like_q))
            search_results = cur.fetchall()

        conn.close()
    except Exception as e:
        print(f"Error en venta: {e}")
        productos_venta = []
        search_results = []

    return render_template('venta.html', productos_venta=productos_venta, search_results=search_results, q=q)

@app.route('/venta/update_status', methods=['POST'])
def venta_update_status():
    # Cambia el estado de un producto a 'VENTA' (y opcionalmente actualiza precio)
    # Ahora soporta scope: 'single' o 'category'
    rowid = request.form.get('rowid')
    precio = request.form.get('precio', '').strip() or None
    scope = request.form.get('scope', 'single')  # 'single', 'category' o 'selected'
    rowids_bulk = request.form.get('rowids', '').strip()
    
    if scope == 'selected':
        # Procesar múltiples rowids recibidos como CSV
        ids = [s for s in (rowids_bulk.split(',') if rowids_bulk else []) if s.strip()]
        if not ids:
            return redirect(url_for('venta'))
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            for rid in ids:
                # obtener sku para el log
                cur.execute("SELECT sku FROM inventory WHERE rowid=?", (rid,))
                r = cur.fetchone()
                sku = r[0] if r else None
                if precio:
                    cur.execute("UPDATE inventory SET estado='VENTA', precio=? WHERE rowid=?", (precio, rid))
                else:
                    cur.execute("UPDATE inventory SET estado='VENTA' WHERE rowid=?", (rid,))
                try:
                    log_movimiento(session.get('usuario'), 'PONER_VENTA', rid, sku, {'precio': precio, 'bulk': True})
                except Exception:
                    pass
            conn.commit()
            conn.close()
        except Exception:
            pass
        return redirect(url_for('venta'))

    if not rowid:
        return redirect(url_for('venta'))
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        if scope == 'category':
            # obtener sku del producto para extraer prefijo
            cur.execute("SELECT sku FROM inventory WHERE rowid=?", (rowid,))
            r = cur.fetchone()
            if r and r[0]:
                sku = r[0]
                if '-' in sku: 
                    pref = sku.split('-')[0]
                else:
                    pref = sku
                
                # Actualizar todos los productos de la categoría
                if precio:
                    cur.execute("UPDATE inventory SET estado='VENTA', precio=? WHERE sku LIKE ?", (precio, f"{pref}-%"))
                else:
                    cur.execute("UPDATE inventory SET estado='VENTA' WHERE sku LIKE ?", (f"{pref}-%",))
                
                conn.commit()
                conn.close()
                try:
                    log_movimiento(session.get('usuario'), 'PONER_VENTA_CATEGORIA', None, pref, {'precio': precio})
                except Exception:
                    pass
                return redirect(url_for('venta'))
        
        # Si es scope 'single' o no se pudo obtener el SKU para category
        cur.execute("SELECT sku FROM inventory WHERE rowid=?", (rowid,))
        r = cur.fetchone()
        sku = r[0] if r else None
        
        if precio:
            cur.execute("UPDATE inventory SET estado='VENTA', precio=? WHERE rowid=?", (precio, rowid))
        else:
            cur.execute("UPDATE inventory SET estado='VENTA' WHERE rowid=?", (rowid,))
        
        conn.commit()
        conn.close()
        try:
            log_movimiento(session.get('usuario'), 'PONER_VENTA', rowid, sku, {'precio': precio})
        except Exception:
            pass
    except Exception:
        pass
    
    return redirect(url_for('venta'))


@app.route('/venta/update_price', methods=['POST'])
def venta_update_price():
    # Actualiza precio de un producto o de toda la categoría
    rowid = request.form.get('rowid')
    precio = request.form.get('precio', '').strip() or None
    scope = request.form.get('scope', 'single')  # 'single' o 'category'
    if not rowid or not precio:
        return redirect(url_for('venta'))
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        if scope == 'category':
            # obtener sku del producto para extraer prefijo
            cur.execute("SELECT sku FROM inventory WHERE rowid=?", (rowid,))
            r = cur.fetchone()
            if r and r[0]:
                sku = r[0]
                if '-' in sku: 
                    pref = sku.split('-')[0]
                else:
                    pref = sku
                cur.execute("UPDATE inventory SET precio=? WHERE sku LIKE ?", (precio, f"{pref}-%"))
                conn.commit()
                conn.close()
                try:
                    log_movimiento(session.get('usuario'), 'CAMBIAR_PRECIO_CATEGORIA', None, pref, {'precio': precio})
                except Exception:
                    pass
                return redirect(url_for('venta'))
        else:
            cur.execute("UPDATE inventory SET precio=? WHERE rowid=?", (precio, rowid))
            conn.commit()
            conn.close()
            try:
                log_movimiento(session.get('usuario'), 'CAMBIAR_PRECIO', rowid, None, {'precio': precio})
            except Exception:
                pass
    except Exception:
        pass
    return redirect(url_for('venta'))

###############################################################

@app.route("/historial")
def historial():
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT usuario, accion, sku, detalles, cuando FROM movimientos ORDER BY id DESC LIMIT 200")
        rows = cur.fetchall()
        conn.close()
        historial = []
        for r in rows:
            usuario, accion, sku, detalles_json, cuando = r
            try:
                detalles = json.loads(detalles_json) if detalles_json else None
            except Exception:
                detalles = detalles_json
            parts = []
            if usuario:
                parts.append(usuario)
            if accion:
                parts.append(accion)
            if sku:
                parts.append(str(sku))
            if detalles:
                parts.append(str(detalles))
            evento = ' — '.join(parts) if parts else accion or 'Movimiento'
            historial.append({"evento": evento, "cuando": cuando})
    except Exception:
        historial = [
            {"evento": "Entrada 15 unidades - Laptop Dell XPS 13", "cuando": "Hace 2 horas"},
            {"evento": "Salida 5 unidades - Monitor Samsung 24\"", "cuando": "Hace 4 horas"},
        ]
    return render_template("historial.html", historial=historial)

##############################################################
###USUARIOS
#############################################################
@app.route("/usuarios")
def usuarios():
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id, usuario, nivel FROM usuarios ORDER BY usuario")
        usuarios_db = cur.fetchall()
        conn.close()
        
        # Convertir a diccionarios para la plantilla
        usuarios_list = []
        for user in usuarios_db:
            usuarios_list.append({
                "id": user[0],
                "usuario": user[1],
                "rol": "Administrador"  # Siempre será Administrador
            })
            
    except Exception as e:
        print(f"Error al cargar usuarios: {e}")
        usuarios_list = [
            {"id": 1, "usuario": "admin", "rol": "Administrador"},
        ]
    
    return render_template("usuarios.html", usuarios=usuarios_list)

@app.route("/usuarios/agregar", methods=["POST"])
def agregar_usuario():
    try:
        usuario = request.form.get('usuario', '').strip()
        password = request.form.get('password', '').strip()
        nivel = 1  # Siempre será Administrador
        
        if not usuario or not password:
            return jsonify({'success': False, 'message': 'Usuario y contraseña son requeridos'})
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Verificar si el usuario ya existe
        cur.execute("SELECT COUNT(*) FROM usuarios WHERE usuario = ?", (usuario,))
        if cur.fetchone()[0] > 0:
            conn.close()
            return jsonify({'success': False, 'message': 'El usuario ya existe'})
        
        # Insertar nuevo usuario
        cur.execute(
            "INSERT INTO usuarios (usuario, password, nivel) VALUES (?, ?, ?)",
            (usuario, password, nivel)
        )
        conn.commit()
        conn.close()
        
        # Registrar en movimientos
        log_movimiento(session.get('usuario'), 'AGREGAR_USUARIO', None, None, {'usuario': usuario, 'nivel': nivel})
        
        return jsonify({'success': True, 'message': 'Usuario agregado correctamente'})
        
    except Exception as e:
        print(f"Error al agregar usuario: {e}")
        return jsonify({'success': False, 'message': f'Error del servidor: {str(e)}'})

@app.route("/usuarios/editar", methods=["POST"])
def editar_usuario():
    try:
        user_id = int(request.form.get('id'))
        usuario = request.form.get('usuario', '').strip()
        password = request.form.get('password', '').strip()
        nivel = 1  # Siempre será Administrador
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Verificar si el usuario existe
        cur.execute("SELECT usuario FROM usuarios WHERE id = ?", (user_id,))
        if not cur.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Usuario no encontrado'})
        
        # Actualizar usuario
        if password:
            cur.execute(
                "UPDATE usuarios SET usuario = ?, password = ?, nivel = ? WHERE id = ?",
                (usuario, password, nivel, user_id)
            )
        else:
            cur.execute(
                "UPDATE usuarios SET usuario = ?, nivel = ? WHERE id = ?",
                (usuario, nivel, user_id)
            )
            
        conn.commit()
        conn.close()
        
        # Registrar en movimientos
        log_movimiento(session.get('usuario'), 'EDITAR_USUARIO', None, None, {'usuario': usuario, 'nivel': nivel})
        
        return jsonify({'success': True, 'message': 'Usuario actualizado correctamente'})
        
    except Exception as e:
        print(f"Error al editar usuario: {e}")
        return jsonify({'success': False, 'message': f'Error del servidor: {str(e)}'})
@app.route("/usuarios/eliminar", methods=["POST"])
def eliminar_usuario():
    try:
        user_id = int(request.form.get('id'))
        
        # Prevenir eliminación del usuario actual
        usuario_actual = session.get('usuario')
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        cur.execute("SELECT usuario FROM usuarios WHERE id = ?", (user_id,))
        usuario_eliminar = cur.fetchone()
        
        if not usuario_eliminar:
            conn.close()
            return jsonify({'success': False, 'message': 'Usuario no encontrado'})
        
        if usuario_eliminar[0] == usuario_actual:
            conn.close()
            return jsonify({'success': False, 'message': 'No puedes eliminar tu propio usuario'})
        
        # Eliminar usuario
        cur.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        # Registrar en movimientos
        log_movimiento(session.get('usuario'), 'ELIMINAR_USUARIO', None, None, {'usuario_eliminado': usuario_eliminar[0]})
        
        return jsonify({'success': True, 'message': 'Usuario eliminado correctamente'})
        
    except Exception as e:
        print(f"Error al eliminar usuario: {e}")
        return jsonify({'success': False, 'message': f'Error del servidor: {str(e)}'})


import pandas as pd
import io
from flask import send_file
import sqlite3
from datetime import datetime

@app.route("/config")
def config():
    settings = {
        "sitio": "Inventario CCC", 
        "modo_debug": True,
        "version": "1.0.0",
        "total_productos": 0,
        "total_usuarios": 0,
        "total_movimientos": 0,
        "total_ventas": 0  # Agregar total_ventas
    }
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Obtener estadísticas
        cur.execute("SELECT COUNT(*) FROM inventory")
        settings["total_productos"] = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM usuarios")
        settings["total_usuarios"] = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM movimientos")
        settings["total_movimientos"] = cur.fetchone()[0]
        
        # Obtener total de ventas
        cur.execute("SELECT COUNT(*) FROM ventas")
        settings["total_ventas"] = cur.fetchone()[0]
        
        conn.close()
    except Exception as e:
        print(f"Error al cargar estadísticas: {e}")
    
    return render_template("config.html", settings=settings)

@app.route("/exportar_excel")
def exportar_excel():
    try:
        # Conectar a la base de datos
        conn = sqlite3.connect(DB_PATH)
        
        # Leer datos de todas las tablas
        df_inventory = pd.read_sql_query("SELECT * FROM inventory", conn)
        df_usuarios = pd.read_sql_query("SELECT * FROM usuarios", conn)
        df_movimientos = pd.read_sql_query("SELECT * FROM movimientos", conn)
        df_ventas = pd.read_sql_query("SELECT * FROM ventas", conn)  # Nueva tabla
        
        conn.close()
        
        # Crear un archivo Excel en memoria
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_inventory.to_excel(writer, sheet_name='Inventario', index=False)
            df_usuarios.to_excel(writer, sheet_name='Usuarios', index=False)
            df_movimientos.to_excel(writer, sheet_name='Movimientos', index=False)
            df_ventas.to_excel(writer, sheet_name='Ventas', index=False)  # Nueva hoja
        
        output.seek(0)
        
        # Registrar en movimientos
        log_movimiento(session.get('usuario'), 'EXPORTAR_EXCEL', None, None, {
            'archivo': 'backup_completo.xlsx',
            'tablas': ['inventory', 'usuarios', 'movimientos', 'ventas']  # Actualizar
        })
        
        # Enviar el archivo
        return send_file(
            output,
            as_attachment=True,
            download_name=f"backup_inventario_ccc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        print(f"Error al exportar Excel completo: {e}")
        return f"Error al exportar: {str(e)}", 500

@app.route("/exportar_inventario_excel")
def exportar_inventario_excel():
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM inventory", conn)
        conn.close()
        
        output = io.BytesIO()
        df.to_excel(output, engine='openpyxl', index=False, sheet_name='Inventario')
        output.seek(0)
        
        # Registrar en movimientos
        log_movimiento(session.get('usuario'), 'EXPORTAR_INVENTARIO', None, None, {
            'archivo': 'inventario.xlsx',
            'registros': len(df)
        })
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f"inventario_ccc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        print(f"Error al exportar inventario: {e}")
        return f"Error al exportar inventario: {str(e)}", 500

@app.route("/exportar_usuarios_excel")
def exportar_usuarios_excel():
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM usuarios", conn)
        conn.close()
        
        output = io.BytesIO()
        df.to_excel(output, engine='openpyxl', index=False, sheet_name='Usuarios')
        output.seek(0)
        
        log_movimiento(session.get('usuario'), 'EXPORTAR_USUARIOS', None, None, {
            'archivo': 'usuarios.xlsx',
            'registros': len(df)
        })
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f"usuarios_ccc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        print(f"Error al exportar usuarios: {e}")
        return f"Error al exportar usuarios: {str(e)}", 500

@app.route("/exportar_movimientos_excel")
def exportar_movimientos_excel():
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM movimientos", conn)
        conn.close()
        
        output = io.BytesIO()
        df.to_excel(output, engine='openpyxl', index=False, sheet_name='Movimientos')
        output.seek(0)
        
        log_movimiento(session.get('usuario'), 'EXPORTAR_MOVIMIENTOS', None, None, {
            'archivo': 'movimientos.xlsx',
            'registros': len(df)
        })
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f"movimientos_ccc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        print(f"Error al exportar movimientos: {e}")
        return f"Error al exportar movimientos: {str(e)}", 500
@app.route("/exportar_ventas_excel")
def exportar_ventas_excel():
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM ventas", conn)
        conn.close()
        
        output = io.BytesIO()
        df.to_excel(output, engine='openpyxl', index=False, sheet_name='Ventas')
        output.seek(0)
        
        log_movimiento(session.get('usuario'), 'EXPORTAR_VENTAS', None, None, {
            'archivo': 'ventas.xlsx',
            'registros': len(df)
        })
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f"ventas_ccc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        print(f"Error al exportar ventas: {e}")
        return f"Error al exportar ventas: {str(e)}", 500



@app.route("/logout")
def logout():
    # Redirige al login (no hay sesión implementada aún)
    return redirect(url_for('login'))


@app.route('/scan', methods=['GET', 'POST'])
def scan_code():
    # Endpoint que acepta un parámetro 'code' y redirige a la lista de productos filtrada
    code = request.values.get('code')
    if not code:
        return "Missing code", 400
    # redirigir a /productos indicando que la búsqueda es por no_serie
    return redirect(url_for('productos_all', q=code, search_field='no_serie'))


# ------------------ Scanner/Serial support ------------------
scanner_thread = None
scanner_running = False
scanner_lock = threading.Lock()
last_scanned = None

def find_serial_port():
    if serial is None:
        return None
    
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None

    # Keywords universales de dispositivos USB a Serial y escáneres
    keywords = [
        "usb", "serial", "scanner", "barcode", "dispositivo serie",
        "usb-to-serial", "ftdi", "prolific", "ch340", "uart", "hid"
    ]

    candidate_ports = []

    # 1) Escanear todos los puertos
    for p in ports:
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()

        # Cualquier puerto que parezca USB-Serial
        if any(k in desc for k in keywords) or any(k in hwid for k in keywords):
            candidate_ports.append(p.device)

    # 2) Si encontramos puertos candidatos, devolver el primero
    if candidate_ports:
        return candidate_ports[0]

    # 3) Si no encontramos nada, devolver el primer COM disponible
    return ports[0].device



def serial_worker(port, baud=9600):
    global scanner_running, last_scanned
    while scanner_running:
        try:
            with serial.Serial(port, baud, timeout=1) as ser:
                buffer = ""
                while scanner_running:
                    chunk = ser.read().decode("utf-8", errors="ignore")
                    if not chunk:
                        time.sleep(0.01)
                        continue
                    if chunk in ("\r", "\n"):
                        code = buffer.strip()
                        buffer = ""
                        if code:
                            with scanner_lock:
                                last_scanned = code
                    else:
                        buffer += chunk

        except Exception as e:
            print("Serial error:", e)
            time.sleep(1)  # espera y vuelve a intentar abrir puerto
            port = find_serial_port()


@app.route('/start_scanner')
def start_scanner():
         
    global scanner_thread, scanner_running
    if serial is None:
        return jsonify({'ok': False, 'msg': 'pyserial no está disponible.'}), 500

    if scanner_running:
        return jsonify({'ok': True, 'msg': 'Scanner ya estaba corriendo.'})

    port = find_serial_port()
    if not port:
        return jsonify({'ok': False, 'msg': 'No se detectó ningún escáner USB-COM-STD.'}), 404

    scanner_running = True
    
    scanner_thread = threading.Thread(target=serial_worker, args=(port,), daemon=True)
    
    scanner_thread.start()

    return jsonify({'ok': True, 'msg': f'Scanner iniciado en {port}'})


@app.route('/stop_scanner')
def stop_scanner():
    global scanner_running
    scanner_running = False
    return jsonify({'ok': True, 'msg': 'Scanner detenido.'})


@app.route('/last_scanned')
def get_last_scanned():
    global last_scanned
    with scanner_lock:
        code = last_scanned
        last_scanned = None
    return jsonify({'code': code})


@app.route('/push_scan', methods=['POST'])
def push_scan():
    """Permite que otra PC envíe un código (modo red)."""
    global last_scanned
    try:
        data = request.get_json(silent=True) or request.form.to_dict()
        code = data.get("code") if isinstance(data, dict) else request.values.get("code")

        if not code:
            return jsonify({'ok': False, 'msg': 'code required'}), 400

        with scanner_lock:
            last_scanned = str(code).strip()

        return jsonify({'ok': True, 'msg': 'scan received', 'code': last_scanned})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


@app.route('/simulate_scan', methods=['POST'])
def simulate_scan():
    global last_scanned
    try:
        data = request.get_json(silent=True) or request.form.to_dict()
        code = data.get("code") if isinstance(data, dict) else request.values.get("code")

        if not code:
            return jsonify({'ok': False, 'msg': 'code required'}), 400

        with scanner_lock:
            last_scanned = str(code).strip()

        return jsonify({'ok': True, 'msg': 'simulated', 'code': last_scanned})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500
 

# Eliminamos el bloque app.run()

# ============================
# LÓGICA DE EVENTOS DE VENTA
# ============================

def ensure_today_event():
    """Crea el evento de venta del día si no existe y cierra los anteriores abiertos."""
    hoy = datetime.now().date().isoformat()  # YYYY-MM-DD
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Crear tablas por si aún no existen
    cur.execute("""CREATE TABLE IF NOT EXISTS venta_eventos (
        fecha TEXT PRIMARY KEY,
        estado TEXT NOT NULL DEFAULT 'OPEN',
        creado_cuando TEXT,
        cerrado_cuando TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS venta_evento_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento_fecha TEXT NOT NULL,
        rowid_producto INTEGER NOT NULL,
        precio_asignado REAL,
        agregado_por TEXT,
        agregado_cuando TEXT,
        UNIQUE(evento_fecha,rowid_producto)
    )""")
    # Cerrar eventos anteriores abiertos
    cur.execute("SELECT fecha FROM venta_eventos WHERE estado='OPEN' AND fecha < ?", (hoy,))
    antiguos = [r[0] for r in cur.fetchall()]
    for f_ant in antiguos:
        cur.execute("UPDATE venta_eventos SET estado='CERRADA', cerrado_cuando=? WHERE fecha=?", (datetime.now().isoformat(), f_ant))
        try:
            log_movimiento(session.get('usuario'), 'CERRAR_EVENTO_AUTO', None, None, {'fecha_evento': f_ant})
        except Exception:
            pass
    # Crear evento de hoy si no existe
    cur.execute("SELECT fecha FROM venta_eventos WHERE fecha=?", (hoy,))
    if not cur.fetchone():
        cur.execute("INSERT INTO venta_eventos (fecha, estado, creado_cuando) VALUES (?,?,?)", (hoy, 'OPEN', datetime.now().isoformat()))
        try:
            log_movimiento(session.get('usuario'), 'CREAR_EVENTO', None, None, {'fecha_evento': hoy})
        except Exception:
            pass
    conn.commit()
    conn.close()
    return hoy

@app.route('/venta/evento/hoy')
def venta_evento_hoy():
    """Devuelve estado del evento de hoy sin crearlo automáticamente y total vendido."""
    hoy = datetime.now().date().isoformat()
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # Asegurar la tabla de eventos para consultar sin errores
        cur.execute("""
            CREATE TABLE IF NOT EXISTS venta_eventos (
                fecha TEXT PRIMARY KEY,
                estado TEXT NOT NULL DEFAULT 'OPEN',
                creado_cuando TEXT,
                cerrado_cuando TEXT
            )
        """)
        # Cerrar eventos abiertos de días anteriores (auto-cierre a medianoche)
        cur.execute("UPDATE venta_eventos SET estado='CERRADA', cerrado_cuando=? WHERE estado='OPEN' AND fecha < ?", (datetime.now().isoformat(), hoy))
        conn.commit()
        # Ver si existe evento hoy
        cur.execute("SELECT estado, creado_cuando, cerrado_cuando FROM venta_eventos WHERE fecha=?", (hoy,))
        evt = cur.fetchone()
        total_vendido = 0.0
        if evt:
            try:
                cur.execute("SELECT COALESCE(SUM(precio_venta),0) FROM ventas WHERE evento_fecha=?", (hoy,))
                rsum = cur.fetchone()
                total_vendido = float(rsum[0] or 0)
            except Exception:
                # Si no existe la tabla ventas aún, considerar total 0
                total_vendido = 0.0
        conn.close()
        if not evt:
            return jsonify({'ok': True, 'evento': None, 'total_vendido': total_vendido})
        return jsonify({'ok': True, 'evento': {'fecha': hoy, 'estado': evt[0], 'creado_cuando': evt[1], 'cerrado_cuando': evt[2]}, 'total_vendido': total_vendido})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500

@app.route('/venta/evento/agregar', methods=['POST'])
def venta_evento_agregar():
    fecha = ensure_today_event()
    rowid = request.form.get('rowid') or (request.json.get('rowid') if request.is_json else None)
    precio_asignado = request.form.get('precio') or (request.json.get('precio') if request.is_json else None)
    if not rowid:
        return jsonify({'ok': False, 'msg': 'rowid requerido'}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # Verificar estado evento
        cur.execute("SELECT estado FROM venta_eventos WHERE fecha=?", (fecha,))
        estado_evt = cur.fetchone()[0]
        if estado_evt != 'OPEN':
            conn.close()
            return jsonify({'ok': False, 'msg': 'Evento cerrado, no se puede agregar'}), 403
        # Verificar producto existente y no vendido/donado/obsoleto
        cur.execute("SELECT sku, estado, precio FROM inventory WHERE rowid=?", (rowid,))
        r = cur.fetchone()
        if not r:
            conn.close()
            return jsonify({'ok': False, 'msg': 'Producto no encontrado'}), 404
        sku, estado_prod, precio_inv = r
        if estado_prod in ('VENDIDO','DONADO','OBSOLETO'):
            conn.close()
            return jsonify({'ok': False, 'msg': f'Estado actual {estado_prod} no permite agregar'}), 400
        # Insertar item (si ya está ignorar)
        cur.execute("INSERT OR IGNORE INTO venta_evento_items (evento_fecha,rowid_producto,precio_asignado,agregado_por,agregado_cuando) VALUES (?,?,?,?,?)",
                    (fecha, rowid, precio_asignado, session.get('usuario'), datetime.now().isoformat()))
        conn.commit()
        conn.close()
        try:
            log_movimiento(session.get('usuario'), 'EVENTO_AGREGAR', rowid, sku, {'fecha_evento': fecha, 'precio_evento': precio_asignado})
        except Exception:
            pass
        return jsonify({'ok': True, 'msg': 'Producto agregado al evento', 'fecha_evento': fecha})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500

@app.route('/venta/evento/cerrar', methods=['POST'])
def venta_evento_cerrar():
    fecha = request.form.get('fecha') or (request.json.get('fecha') if request.is_json else None) or datetime.now().date().isoformat()
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT estado FROM venta_eventos WHERE fecha=?", (fecha,))
        r = cur.fetchone()
        if not r:
            conn.close()
            return jsonify({'ok': False, 'msg': 'Evento no existe'}), 404
        if r[0] == 'CERRADA':
            conn.close()
            return jsonify({'ok': True, 'msg': 'Ya estaba cerrado'})
        cur.execute("UPDATE venta_eventos SET estado='CERRADA', cerrado_cuando=? WHERE fecha=?", (datetime.now().isoformat(), fecha))
        conn.commit()
        conn.close()
        try:
            log_movimiento(session.get('usuario'), 'CERRAR_EVENTO_MANUAL', None, None, {'fecha_evento': fecha})
        except Exception:
            pass
        return jsonify({'ok': True, 'msg': 'Evento cerrado'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500

@app.route('/venta/evento/reporte')
def venta_evento_reporte():
    fecha = request.args.get('fecha', '').strip() or datetime.now().date().isoformat()
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT estado, creado_cuando, cerrado_cuando FROM venta_eventos WHERE fecha=?", (fecha,))
        evt = cur.fetchone()
        if not evt:
            conn.close()
            return jsonify({'ok': False, 'msg': 'Evento no existe'}), 404
        cur.execute("""SELECT i.rowid, i.sku, i.marca, i.modelo, i.precio
                       FROM venta_evento_items vei JOIN inventory i ON i.rowid=vei.rowid_producto
                       WHERE vei.evento_fecha=? ORDER BY i.sku""", (fecha,))
        items = cur.fetchall()
        conn.close()
        total = sum([r[4] for r in items if isinstance(r[4], (int,float))])
        data_items = [{'rowid': r[0], 'sku': r[1], 'marca': r[2], 'modelo': r[3], 'precio': r[4]} for r in items]
        return jsonify({'ok': True, 'fecha': fecha, 'evento': {'estado': evt[0], 'creado_cuando': evt[1], 'cerrado_cuando': evt[2]}, 'items': data_items, 'total_precio': total})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500

@app.route('/venta/evento')
def venta_evento_page():
    """Página de gestión de la venta del día: solo muestra si el evento existe."""
    hoy = datetime.now().date().isoformat()
    try:
        ensure_ventas_table()
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # Asegurar la tabla de eventos exista para evitar errores si aún no se creó
        cur.execute("""
            CREATE TABLE IF NOT EXISTS venta_eventos (
                fecha TEXT PRIMARY KEY,
                estado TEXT NOT NULL DEFAULT 'OPEN',
                creado_cuando TEXT,
                cerrado_cuando TEXT
            )
        """)
        # Cerrar eventos anteriores abiertos
        cur.execute("UPDATE venta_eventos SET estado='CERRADA', cerrado_cuando=? WHERE estado='OPEN' AND fecha < ?", (datetime.now().isoformat(), hoy))
        conn.commit()
        cur.execute("SELECT fecha, estado FROM venta_eventos WHERE fecha=?", (hoy,))
        ev = cur.fetchone()
        if not ev:
            conn.close()
            return render_template('venta_evento.html', evento_fecha=hoy, evento_estado='SIN EVENTO', evento_propietario=session.get('usuario'), productos_venta=[], ventas_hoy=[], total_vendido=0)
        estado = ev['estado']
        cur.execute("SELECT rowid, sku, tipo, marca, modelo, no_serie, precio FROM inventory WHERE estado='VENTA' ORDER BY marca, modelo")
        _prod_rows = cur.fetchall()
        productos_venta = []
        for r in _prod_rows:
            try:
                price = float(r[6]) if r[6] is not None else 0.0
            except Exception:
                price = 0.0
            productos_venta.append((r[0], r[1], r[2], r[3], r[4], r[5], price))
        cur.execute("""
            SELECT id, ticket_id, sku, marca, modelo, precio_venta, comprador, vendedor, fecha_venta
            FROM ventas
            WHERE evento_fecha = ?
            ORDER BY fecha_venta DESC
        """, (hoy,))
        _ventas_rows = cur.fetchall()
        ventas_hoy = []
        for r in _ventas_rows:
            try:
                pv = float(r[5]) if r[5] is not None else 0.0
            except Exception:
                pv = 0.0
            ventas_hoy.append({
                'id': r[0],
                'ticket_id': r[1],
                'sku': r[2],
                'marca': r[3],
                'modelo': r[4],
                'precio': pv,
                'comprador': r[6],
                'vendedor': r[7],
                'fecha': r[8]
            })
        cur.execute("SELECT COALESCE(SUM(precio_venta),0) FROM ventas WHERE evento_fecha=?", (hoy,))
        try:
            total_vendido = float(cur.fetchone()[0] or 0)
        except Exception:
            total_vendido = 0.0
        conn.close()
        return render_template('venta_evento.html', evento_fecha=hoy, evento_estado=estado, evento_propietario=session.get('usuario'), productos_venta=productos_venta, ventas_hoy=ventas_hoy, total_vendido=total_vendido)
    except Exception as e:
        try:
            print('[ERROR] venta_evento_page:', str(e))
        except Exception:
            pass
        return render_template('venta_evento.html', evento_fecha=hoy, evento_estado='ERROR', evento_propietario=session.get('usuario'), productos_venta=[], ventas_hoy=[], total_vendido=0)


def build_ticket_bundle(venta_id):
    """Obtiene metadata del ticket y todas las partidas asociadas."""
    ensure_ticket_support()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT v.*, 
               t.id AS t_id,
               t.total AS t_total,
               t.total_items AS t_items,
               t.comprador AS t_comprador,
               t.vendedor AS t_vendedor,
               t.observaciones AS t_observaciones,
               t.fecha_venta AS t_fecha_venta,
               t.evento_fecha AS t_evento_fecha
        FROM ventas v
        LEFT JOIN venta_tickets t ON v.ticket_id = t.id
        WHERE v.id=?
        """,
        (venta_id,)
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return None

    ticket_ref_id = row['ticket_id'] or row['t_id']
    if ticket_ref_id:
        cur.execute(
            """
            SELECT id, sku, tipo, marca, modelo, no_serie, precio_venta
            FROM ventas
            WHERE ticket_id=?
            ORDER BY id
            """,
            (ticket_ref_id,)
        )
        items_rows = cur.fetchall()
    else:
        items_rows = [row]

    items = []
    total_calc = 0.0
    for ir in items_rows:
        price = float(ir['precio_venta'] or 0)
        total_calc += price
        items.append({
            'venta_id': ir['id'],
            'sku': ir['sku'],
            'tipo': ir['tipo'],
            'marca': ir['marca'],
            'modelo': ir['modelo'],
            'no_serie': ir['no_serie'],
            'precio': price
        })

    ticket = {
        'id': ticket_ref_id or row['id'],
        'anchor_venta_id': row['id'],
        'comprador': row['t_comprador'] or row['comprador'],
        'vendedor': row['t_vendedor'] or row['vendedor'],
        'observaciones': row['t_observaciones'] if row['t_observaciones'] is not None else row['observaciones'],
        'fecha_venta': row['t_fecha_venta'] or row['fecha_venta'],
        'evento_fecha': row['t_evento_fecha'] or row['evento_fecha'],
        'total': row['t_total'] if row['t_total'] is not None else total_calc,
        'total_items': row['t_items'] or len(items)
    }
    ticket['codigo'] = f"T-{ticket['id']}"

    conn.close()
    return ticket, items


def build_event_report(fecha):
    """Devuelve resumen de ventas y tickets para una fecha determinada."""
    ensure_ticket_support()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT fecha, estado FROM venta_eventos WHERE fecha=?", (fecha,))
    evento = cur.fetchone()
    event_state = evento['estado'] if evento else None
    cur.execute(
        """
        SELECT v.id, v.ticket_id, v.sku, v.tipo, v.marca, v.modelo, v.no_serie,
               v.precio_venta, v.comprador, v.vendedor, v.observaciones, v.fecha_venta,
               vt.total AS vt_total, vt.total_items AS vt_total_items,
               vt.comprador AS vt_comprador, vt.vendedor AS vt_vendedor, vt.observaciones AS vt_obs
        FROM ventas v
        LEFT JOIN venta_tickets vt ON vt.id = v.ticket_id
        WHERE v.evento_fecha=?
        ORDER BY COALESCE(v.ticket_id, v.id), v.id
        """,
        (fecha,)
    )
    rows = cur.fetchall()
    conn.close()

    tickets = []
    ticket_map = {}
    total_vendido = 0.0
    total_items = 0

    for row in rows:
        tid = row['ticket_id'] or row['id']
        ticket = ticket_map.get(tid)
        if ticket is None:
            ticket = {
                'id': tid,
                'codigo': f"T-{tid}",
                'comprador': row['vt_comprador'] or row['comprador'],
                'vendedor': row['vt_vendedor'] or row['vendedor'],
                'observaciones': row['vt_obs'] if row['vt_obs'] is not None else row['observaciones'],
                'fecha_venta': row['fecha_venta'],
                'total': row['vt_total'],
                'total_items': row['vt_total_items'],
                'items': [],
                'estado': event_state
            }
            ticket_map[tid] = ticket
            tickets.append(ticket)

        price = float(row['precio_venta'] or 0)
        ticket['items'].append({
            'venta_id': row['id'],
            'sku': row['sku'],
            'tipo': row['tipo'],
            'marca': row['marca'],
            'modelo': row['modelo'],
            'no_serie': row['no_serie'],
            'precio': price,
            'comprador': row['comprador'],
            'vendedor': row['vendedor']
        })
        total_vendido += price
        total_items += 1

    for ticket in tickets:
        if ticket['total'] is None:
            ticket['total'] = sum(item['precio'] for item in ticket['items'])
        if not ticket['total_items']:
            ticket['total_items'] = len(ticket['items'])

    return {
        'evento': {'fecha': evento['fecha'], 'estado': evento['estado']} if evento else {'fecha': fecha, 'estado': 'SIN EVENTO'},
        'tickets': tickets,
        'total_vendido': total_vendido,
        'total_items': total_items,
        'total_tickets': len(tickets)
    }


@app.route('/venta/ticket/<int:venta_id>')
def venta_ticket(venta_id):
    """Muestra el ticket de una venta con detalles y opción de descarga/imprimir."""
    try:
        bundle = build_ticket_bundle(venta_id)
        if not bundle:
            return jsonify({'ok': False, 'msg': 'Venta no encontrada'}), 404
        ticket, items = bundle
        return render_template('venta_ticket.html', ticket=ticket, items=items)
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500

@app.route('/venta/ticket/<int:venta_id>/download')
def venta_ticket_download(venta_id):
    """Devuelve el ticket como archivo descargable (HTML adjunto)."""
    try:
        bundle = build_ticket_bundle(venta_id)
        if not bundle:
            return jsonify({'ok': False, 'msg': 'Venta no encontrada'}), 404
        ticket, items = bundle
        html = render_template('venta_ticket.html', ticket=ticket, items=items)
        from flask import Response
        filename = f"ticket-venta-{ticket['id']}.html"
        resp = Response(html)
        resp.headers['Content-Type'] = 'text/html; charset=utf-8'
        resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500

@app.route('/venta/ticket/<int:venta_id>/pdf')
def venta_ticket_pdf(venta_id):
    """Genera un PDF del ticket y lo devuelve como descarga."""
    if pisa is None:
        return jsonify({'ok': False, 'msg': 'Generación de PDF no disponible (falta xhtml2pdf)'}), 500
    try:
        bundle = build_ticket_bundle(venta_id)
        if not bundle:
            return jsonify({'ok': False, 'msg': 'Venta no encontrada'}), 404
        logo_path = os.path.join(app.static_folder, 'images', 'CCClogo.jpg')
        ticket, items = bundle
        html = render_template('venta_ticket_pdf.html', ticket=ticket, items=items, logo_path=logo_path if os.path.exists(logo_path) else None)
        pdf_buffer = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
        if pisa_status.err:
            return jsonify({'ok': False, 'msg': 'No se pudo generar el PDF del ticket'}), 500
        pdf_buffer.seek(0)
        filename = f"ticket-venta-{ticket['id']}.pdf"
        return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500

@app.route('/venta/ticket/<int:venta_id>/qr.png')
def venta_ticket_qr(venta_id):
    """Genera un PNG QR dinámico con la URL del ticket y logo CCC."""
    # Construir URL absoluta del ticket usando el host actual
    try:
        # Usar base pública si está configurada, si no request.host_url
        base = (app.config.get('PUBLIC_BASE_URL') or request.host_url).rstrip('/')
        # Que el QR apunte al endpoint de descarga directa en PDF
        url_ticket = base + url_for('venta_ticket_pdf', venta_id=venta_id)
        try:
            print(f"[QR] Generando QR para venta_id={venta_id} url={url_ticket}")
        except Exception:
            pass
    except Exception:
        # Fallback simple si request fallara
        url_ticket = f"/venta/ticket/{venta_id}"

    if qrcode is None or Image is None:
        # Fallback: redirigir a servicio externo de QR si faltan dependencias
        from flask import redirect
        fallback = f"https://chart.googleapis.com/chart?chs=200x200&cht=qr&chl={url_ticket}&chco=000000"
        return redirect(fallback)

    # Generar QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(url_ticket)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="black", back_color="white").convert('RGB')

    # Intentar overlay de logo
    try:
        logo_path = os.path.join(app.static_folder, 'images', 'CCClogo.jpg')
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert('RGBA')
            # Redimensionar logo al ~25% del QR
            w, h = img_qr.size
            target_w = max(70, int(w * 0.25))
            aspect = logo.width / logo.height if logo.height else 1
            logo = logo.resize((target_w, int(target_w / aspect)), Image.LANCZOS)
            # Centrar
            lx = (w - logo.width) // 2
            ly = (h - logo.height) // 2
            img_qr.paste(logo, (lx, ly), mask=logo)
    except Exception:
        # Si falla el logo, devolver solo QR
        pass

    buf = BytesIO()
    img_qr.save(buf, format='PNG')
    buf.seek(0)
    from flask import send_file
    return send_file(buf, mimetype='image/png')


@app.route('/venta/evento/reporte/pdf')
def venta_evento_reporte_pdf():
    if pisa is None:
        return jsonify({'ok': False, 'msg': 'Generación de PDF no disponible'}), 500
    fecha = request.args.get('fecha') or datetime.now().date().isoformat()
    try:
        report = build_event_report(fecha)
        logo_path = os.path.join(app.static_folder, 'images', 'CCClogo.jpg')
        html = render_template(
            'venta_evento_pdf.html',
            evento_fecha=fecha,
            evento_estado=report['evento']['estado'],
            tickets=report['tickets'],
            total_vendido=report['total_vendido'],
            total_items=report['total_items'],
            total_tickets=report['total_tickets'],
            generado=datetime.now(),
            logo_path=logo_path if os.path.exists(logo_path) else None
        )
        pdf_buffer = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
        if pisa_status.err:
            return jsonify({'ok': False, 'msg': 'No se pudo generar el PDF del reporte'}), 500
        pdf_buffer.seek(0)
        filename = f"reporte-ventas-{fecha}.pdf"
        return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


@app.route('/venta/evento/reporte/qr.png')
def venta_evento_reporte_qr():
    fecha = request.args.get('fecha') or datetime.now().date().isoformat()
    try:
        base = (app.config.get('PUBLIC_BASE_URL') or request.host_url).rstrip('/')
        url_pdf = base + url_for('venta_evento_reporte_pdf', fecha=fecha)
    except Exception:
        url_pdf = f"/venta/evento/reporte/pdf?fecha={fecha}"

    if qrcode is None or Image is None:
        from flask import redirect
        fallback = f"https://chart.googleapis.com/chart?chs=200x200&cht=qr&chl={url_pdf}&chco=000000"
        return redirect(fallback)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(url_pdf)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="black", back_color="white").convert('RGB')

    try:
        logo_path = os.path.join(app.static_folder, 'images', 'CCClogo.jpg')
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert('RGBA')
            w, h = img_qr.size
            target_w = max(40, int(w * 0.25))
            aspect = logo.width / logo.height if logo.height else 1
            logo = logo.resize((target_w, int(target_w / aspect)), Image.LANCZOS)
            lx = (w - logo.width) // 2
            ly = (h - logo.height) // 2
            img_qr.paste(logo, (lx, ly), mask=logo)
    except Exception:
        pass

    buf = BytesIO()
    img_qr.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


def revertir_ventas_por_ids(venta_ids, actor=None):
    """Restaura ventas y devuelve resumen."""
    if not venta_ids:
        raise ValueError('venta_ids requerido')

    ensure_ticket_support()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    placeholders = ','.join(['?'] * len(venta_ids))
    cur.execute(f"SELECT * FROM ventas WHERE id IN ({placeholders})", venta_ids)
    rows = cur.fetchall()
    if not rows:
        conn.close()
        raise LookupError('No se encontraron ventas para esos IDs')

    restored = []
    ticket_ids = set()
    try:
        for row in rows:
            rid_prod = row['rowid_producto']
            if rid_prod:
                cur.execute("UPDATE inventory SET estado='VENTA' WHERE rowid=?", (rid_prod,))
            cur.execute("DELETE FROM ventas WHERE id=?", (row['id'],))
            restored.append({'venta_id': row['id'], 'sku': row['sku'], 'rowid_producto': rid_prod, 'ticket_id': row['ticket_id']})
            if row['ticket_id']:
                ticket_ids.add(row['ticket_id'])
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise RuntimeError(f'No se pudieron revertir ventas: {e}')

    try:
        for tid in ticket_ids:
            cur.execute("SELECT COUNT(1) FROM ventas WHERE ticket_id=?", (tid,))
            count = cur.fetchone()[0]
            if not count:
                cur.execute("DELETE FROM venta_tickets WHERE id=?", (tid,))
        conn.commit()
    except Exception:
        conn.rollback()
    conn.close()

    for info in restored:
        try:
            log_movimiento(actor or session.get('usuario'), 'VENTA_REVERTIDA', info['rowid_producto'], info['sku'], {'ticket_id': info['ticket_id'], 'venta_id': info['venta_id']})
        except Exception:
            pass

    return restored


@app.route('/ventas/revertir', methods=['POST'])
def ventas_revertir():
    """Devuelve productos vendidos a estado VENTA y elimina sus tickets."""
    if not session.get('usuario'):
        return jsonify({'ok': False, 'msg': 'Sesión requerida'}), 401

    payload = request.get_json(silent=True) or {}
    ids_param = payload.get('venta_ids') or request.form.getlist('venta_ids') or []
    if isinstance(ids_param, str):
        ids_param = [ids_param]

    venta_ids = []
    for raw in ids_param:
        try:
            idx = int(raw)
            if idx not in venta_ids:
                venta_ids.append(idx)
        except Exception:
            continue

    if not venta_ids:
        return jsonify({'ok': False, 'msg': 'venta_ids requerido'}), 400

    try:
        restored = revertir_ventas_por_ids(venta_ids, actor=session.get('usuario'))
    except LookupError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 404
    except ValueError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 400
    except RuntimeError as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500

    return jsonify({'ok': True, 'msg': f"{len(restored)} ventas revertidas", 'restaurados': restored})

@app.route('/venta/evento/abrir', methods=['POST'])
def venta_evento_abrir():
    """Abre (o reabre) el evento de venta del día actual."""
    try:
        hoy = ensure_today_event()
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("UPDATE venta_eventos SET estado='OPEN', cerrado_cuando=NULL WHERE fecha=?", (hoy,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'msg': f'Evento de {hoy} abierto', 'fecha': hoy})
    except Exception as e:
        return jsonify({'ok': False, 'msg': f'Error: {str(e)}'}), 500

# ============================
# CRUD CATÁLOGO UBICACIONES
# ============================
@app.route('/ubicaciones/agregar', methods=['POST'])
def ubicaciones_agregar():
    nombre = (request.form.get('nombre') or (request.json.get('nombre') if request.is_json else '')).strip()
    nivel = (request.form.get('nivel') or (request.json.get('nivel') if request.is_json else '')).strip().upper()
    nota = (request.form.get('nota') or (request.json.get('nota') if request.is_json else '')).strip() or None
    if not nombre or not nivel:
        return jsonify({'ok': False, 'msg': 'nombre y nivel requeridos'}), 400
    if len(nombre) > 120:
        return jsonify({'ok': False, 'msg': 'Nombre demasiado largo'}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS ubicaciones_catalogo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            nivel TEXT NOT NULL,
            nota TEXT,
            UNIQUE(nivel,nombre)
        )""")
        cur.execute("INSERT OR IGNORE INTO ubicaciones_catalogo (nombre,nivel,nota) VALUES (?,?,?)", (nombre, nivel, nota))
        conn.commit()
        cur.execute("SELECT id FROM ubicaciones_catalogo WHERE nombre=? AND nivel=?", (nombre, nivel))
        rid = cur.fetchone()[0]
        conn.close()
        try:
            log_movimiento(session.get('usuario'), 'UBICACION_AGREGAR', rid, None, {'nombre': nombre, 'nivel': nivel})
        except Exception:
            pass
        return jsonify({'ok': True, 'msg': 'Ubicación agregada', 'id': rid})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500

@app.route('/ubicaciones/editar', methods=['POST'])
def ubicaciones_editar():
    rid = (request.form.get('id') or (request.json.get('id') if request.is_json else '')).strip()
    nombre = (request.form.get('nombre') or (request.json.get('nombre') if request.is_json else '')).strip()
    nivel = (request.form.get('nivel') or (request.json.get('nivel') if request.is_json else '')).strip().upper()
    nota = (request.form.get('nota') or (request.json.get('nota') if request.is_json else '')).strip() or None
    if not rid or not nombre or not nivel:
        return jsonify({'ok': False, 'msg': 'id, nombre y nivel requeridos'}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT nombre,nivel FROM ubicaciones_catalogo WHERE id=?", (rid,))
        prev = cur.fetchone()
        if not prev:
            conn.close()
            return jsonify({'ok': False, 'msg': 'Ubicación no encontrada'}), 404
        cur.execute("UPDATE ubicaciones_catalogo SET nombre=?, nivel=?, nota=? WHERE id=?", (nombre, nivel, nota, rid))
        conn.commit()
        conn.close()
        try:
            log_movimiento(session.get('usuario'), 'UBICACION_EDITAR', int(rid), None, {'antes': {'nombre': prev[0], 'nivel': prev[1]}, 'despues': {'nombre': nombre, 'nivel': nivel}})
        except Exception:
            pass
        return jsonify({'ok': True, 'msg': 'Ubicación actualizada'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500

@app.route('/ubicaciones/eliminar', methods=['POST'])
def ubicaciones_eliminar():
    rid = (request.form.get('id') or (request.json.get('id') if request.is_json else '')).strip()
    if not rid:
        return jsonify({'ok': False, 'msg': 'id requerido'}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT nombre,nivel FROM ubicaciones_catalogo WHERE id=?", (rid,))
        prev = cur.fetchone()
        if not prev:
            conn.close()
            return jsonify({'ok': False, 'msg': 'Ubicación no encontrada'}), 404
        cur.execute("DELETE FROM ubicaciones_catalogo WHERE id=?", (rid,))
        conn.commit()
        conn.close()
        try:
            log_movimiento(session.get('usuario'), 'UBICACION_ELIMINAR', int(rid), None, {'nombre': prev[0], 'nivel': prev[1]})
        except Exception:
            pass
        return jsonify({'ok': True, 'msg': 'Ubicación eliminada'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500
