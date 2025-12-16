import sqlite3

ruta_bd = r"C:\Users\ROG\PruebaGit\SistemaCCC\inventario_consolidado.db"

conn = sqlite3.connect(ruta_bd)
cursor = conn.cursor()

try:
    print("⚠️ Reiniciando tickets y ventas...")

    # Desactivar llaves foráneas temporalmente
    cursor.execute("PRAGMA foreign_keys = OFF;")

    # Borrar datos de tickets / ventas
    cursor.execute("DELETE FROM venta_evento_items;")
    cursor.execute("DELETE FROM venta_eventos;")
    cursor.execute("DELETE FROM ventas;")
    cursor.execute("DELETE FROM movimientos;")

    # Resetear autoincrement (SQLite)
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='ventas';")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='venta_evento_items';")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='movimientos';")

    conn.commit()

    print("✅ Tickets eliminados.")
    print("🔄 Contadores reiniciados.")
    print("🎫 El próximo ticket comenzará desde el 1.")

except Exception as e:
    conn.rollback()
    print("❌ Error al reiniciar tickets:", e)

finally:
    cursor.execute("PRAGMA foreign_keys = ON;")
    conn.close()
