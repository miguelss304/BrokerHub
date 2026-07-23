"""
Conexión reutilizable a MySQL (Railway).
Se importa desde los demás scripts: from conexion_db import obtener_conexion
"""

import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def obtener_conexion():
    conexion = mysql.connector.connect(
        host=os.getenv("MYSQLHOST"),
        port=int(os.getenv("MYSQLPORT")),
        user=os.getenv("MYSQLUSER"),
        password=os.getenv("MYSQLPASSWORD"),
        database=os.getenv("MYSQLDATABASE"),
        ssl_disabled=True,
    )
    return conexion


def asegurar_conexion(conexion):
    """Verifica que la conexión siga viva; si se cayó, la reconecta
    automáticamente (hasta 3 intentos, esperando 5s entre cada uno).
    Se debe llamar antes de cada bloque de trabajo (ej. antes de cada ticker).
    """
    try:
        conexion.ping(reconnect=True, attempts=3, delay=5)
    except mysql.connector.Error as e:
        print(f"  [AVISO] No se pudo reconectar automáticamente: {e}")
        raise
    return conexion


def reconectar_forzado(conexion):
    """Cierra la conexión actual (si se puede) y abre una completamente nueva.
    Más agresivo que ping(reconnect=True): úsalo cuando una consulta ya falló
    con 'Lost connection' a pesar del ping previo.
    """
    try:
        conexion.close()
    except Exception:
        pass  # la conexión ya estaba rota, no importa que falle al cerrar
    return obtener_conexion()


if __name__ == "__main__":
    conexion = obtener_conexion()
    print("Conectado correctamente" if conexion.is_connected() else "Falló la conexión")
    conexion.close()