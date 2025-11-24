from sre_parse import CATEGORIES
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from datetime import datetime
import sqlite3
import threading
import time
import json
try:
    import serial
    import serial.tools.list_ports
except Exception:
    serial = None
    import serial as _serial_disabled  # placeholder

# Se especifica la carpeta de archivos estáticos (statics)
app = Flask(__name__, static_folder='static')
app.secret_key = 'dev-secret-key-change-me'
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


def log_movimiento(usuario, accion, rowid_producto=None, sku=None, detalles=None):
    """Guarda un registro en la tabla movimientos con quién hizo qué y cuándo.
    detalles puede ser cualquier estructura serializable (se guarda como JSON).
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
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
        detalles_json = json.dumps(detalles, ensure_ascii=False) if detalles is not None else None
        cur.execute(
            "INSERT INTO movimientos (usuario, accion, rowid_producto, sku, detalles, cuando) VALUES (?,?,?,?,?,?)",
            (usuario, accion, rowid_producto, sku, detalles_json, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


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
    # Mostrar formulario para registrar nuevas entradas
    # Obtenemos prefijos de SKU existentes para ayudar al usuario
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT(CASE WHEN instr(sku,'-')>0 THEN substr(sku,1,instr(sku,'-')-1) ELSE sku END) as pref FROM inventory ORDER BY pref")
        prefs = [r[0] for r in cur.fetchall()]
        conn.close()
    except Exception:
        prefs = []

    return render_template("entradas.html", prefixes=prefs)


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
        return jsonify({'ok': False, 'msg': 'sku parameter required'}), 400
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

    if not sku:
        return "SKU requerido", 400

    # Si se proporcionó número de serie, verificar duplicados
    if no_serie:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM inventory WHERE no_serie = ?", (no_serie,))
            exists_count = cur.fetchone()[0]
            conn.close()
            if exists_count and exists_count > 0:
                # Re-render formulario con mensaje de error y valores rellenados
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cur = conn.cursor()
                    cur.execute("SELECT DISTINCT(CASE WHEN instr(sku,'-')>0 THEN substr(sku,1,instr(sku,'-')-1) ELSE sku END) as pref FROM inventory ORDER BY pref")
                    prefs = [r[0] for r in cur.fetchall()]
                    conn.close()
                except Exception:
                    prefs = []

                form_values = request.form.to_dict()
                return render_template('entradas.html', prefixes=prefs, error='No. serie ya registrado en la base de datos.', form=form_values), 400
        except Exception:
            # si la comprobación falla, seguimos y permitimos que la inserción intente seguir
            pass

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

        # Registrar movimiento de entrada
        try:
            detalles = {'no_serie': no_serie, 'precio': precio, 'ubicacion': ubicacion}
            log_movimiento(session.get('usuario'), 'ENTRADA', lastid, sku, detalles)
        except Exception:
            pass

        return redirect(url_for('productos_all', q=no_serie or sku, search_field='no_serie' if no_serie else ''))
    except Exception as e:
        return f"Error al insertar: {e}", 500
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
        # Productos que están en VENTA y tienen precio
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

    return render_template('venta.html', productos_venta=productos_venta, search_results=search_results, q=q)


@app.route('/venta/update_status', methods=['POST'])
def venta_update_status():
    # Cambia el estado de un producto a 'VENTA' (y opcionalmente actualiza precio)
    rowid = request.form.get('rowid')
    precio = request.form.get('precio', '').strip() or None
    if not rowid:
        return redirect(url_for('venta'))
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
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


@app.route("/usuarios")
def usuarios():
    usuarios_sim = [
        {"usuario": "admin", "rol": "Administrador"},
        {"usuario": "invitado", "rol": "Invitado"},
    ]
    return render_template("usuarios.html", usuarios=usuarios_sim)


@app.route("/config")
def config():
    settings = {"sitio": "Inventario CCC", "modo_debug": True}
    return render_template("config.html", settings=settings)


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
    for p in ports:
        desc = (p.description or "").lower()
        if any(k in desc for k in ("usb", "serial", "ftdi", "prolific", "ch340")):
            return p.device
    return ports[0].device if ports else None


def serial_worker(port, baud=9600):
    global scanner_running, last_scanned
    try:
        with serial.Serial(port, baud, timeout=1) as ser:
            while scanner_running:
                try:
                    linea = ser.readline()
                except Exception:
                    break
                if not linea:
                    time.sleep(0.05)
                    continue
                try:
                    data = linea.decode('utf-8', errors='ignore').strip()
                except Exception:
                    data = linea.decode('latin1', errors='ignore').strip()
                if data:
                    with scanner_lock:
                        last_scanned = data
    except Exception:
        pass


@app.route('/start_scanner')
def start_scanner():
    global scanner_thread, scanner_running
    if serial is None:
        return jsonify({'ok': False, 'msg': 'pyserial no está disponible en el servidor.'}), 500
    if scanner_running:
        return jsonify({'ok': True, 'msg': 'Scanner ya en ejecución.'})
    port = find_serial_port()
    if not port:
        return jsonify({'ok': False, 'msg': 'No se detectó puerto serial.'}), 404
    scanner_running = True
    scanner_thread = threading.Thread(target=serial_worker, args=(port,), daemon=True)
    scanner_thread.start()
    return jsonify({'ok': True, 'msg': f'Escaner iniciado en {port}'})


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
    if code:
        return jsonify({'code': code})
    return jsonify({'code': None})


@app.route('/product_by_serial')
def product_by_serial():
    no = request.args.get('no', '').strip()
    if not no:
        return jsonify({'ok': False, 'msg': 'no parameter required'}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT rowid, sku, id_original, tipo, marca, modelo, no_serie, volts, precio, estado, ubicacion, fecha_registro, observacion FROM inventory WHERE no_serie = ? LIMIT 1", (no,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({'ok': False, 'msg': 'not found'}), 404
        keys = ['rowid','sku','id_original','tipo','marca','modelo','no_serie','volts','precio','estado','ubicacion','fecha_registro','observacion']
        data = dict(zip(keys, row))
        return jsonify({'ok': True, 'data': data})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


@app.route('/push_scan', methods=['POST'])
def push_scan():
    """Endpoint para que un cliente remoto reenvíe un código escaneado.
    Acepta JSON `{'code': '...'}'` o form-data `code=...`.
    Almacena el último escaneado en `last_scanned` para que los clientes que
    polleen `/last_scanned` lo reciban.
    """
    global last_scanned
    try:
        data = None
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        code = (data.get('code') if data else None) or request.values.get('code')
        if not code:
            return jsonify({'ok': False, 'msg': 'code required'}), 400
        with scanner_lock:
            last_scanned = str(code).strip()
        return jsonify({'ok': True, 'msg': 'scan received', 'code': last_scanned})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


@app.route('/simulate_scan', methods=['POST'])
def simulate_scan():
    """Administrativo: permite inyectar un código escaneado manualmente (testing).
    Esta ruta acepta form-data `code=` o JSON {"code":"..."}.
    Guarda el valor en `last_scanned` (protegido por lock) para que clientes poll
    obtengan el código como si hubiera sido escaneado.
    """
    global last_scanned
    try:
        data = request.get_json(silent=True) or request.form.to_dict()
        code = (data.get('code') if isinstance(data, dict) else None) or request.values.get('code')
        if not code:
            return jsonify({'ok': False, 'msg': 'code required'}), 400
        with scanner_lock:
            last_scanned = str(code).strip()
        return jsonify({'ok': True, 'msg': 'simulated', 'code': last_scanned})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)

