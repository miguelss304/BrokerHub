"""
Actualizador de Cotizacion_Historica.

A diferencia de carga_inicial.py (que trae 6 meses una sola vez y se salta
tickers ya cargados), este script revisa cuál es la fecha MAS RECIENTE que
ya existe por instrumento, y solo trae los días que faltan desde ahí hasta
hoy. Pensado para correrse periódicamente (ej. una vez al día).

Uso recomendado: correrlo manualmente cada cierto tiempo, o programarlo
con el Programador de tareas de Windows / cron para que corra solo.
"""

from datetime import date, timedelta
import yfinance as yf
from conexion_db import obtener_conexion, reconectar_forzado
import mysql.connector


def obtener_instrumentos_y_ultima_fecha(cursor):
    cursor.execute(
        """SELECT i.id_instrumento, i.ticker, MAX(c.fecha) AS ultima_fecha
           FROM Instrumento_Financiero i
           LEFT JOIN Cotizacion_Historica c ON c.id_instrumento = i.id_instrumento
           GROUP BY i.id_instrumento, i.ticker"""
    )
    columnas = [d[0] for d in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def traer_dias_faltantes(ticker, ultima_fecha):
    """Trae solo los días entre ultima_fecha (exclusiva) y hoy.
    Si ultima_fecha es None (nunca se cargó nada), trae los últimos 6 meses."""
    accion = yf.Ticker(ticker)

    if ultima_fecha is None:
        df = accion.history(period="6mo")
    else:
        desde = ultima_fecha + timedelta(days=1)
        hoy = date.today()
        if desde > hoy:
            return []  # ya está actualizado, no hay nada nuevo que traer
        df = accion.history(start=desde.isoformat(), end=(hoy + timedelta(days=1)).isoformat())

    filas = []
    for fecha, row in df.iterrows():
        filas.append({
            "fecha": fecha.strftime("%Y-%m-%d"),
            "precio_apertura": round(row["Open"], 4),
            "precio_cierre": round(row["Close"], 4),
            "precio_maximo": round(row["High"], 4),
            "precio_minimo": round(row["Low"], 4),
            "volumen": int(row["Volume"]),
        })
    return filas


def insertar_dias_nuevos(cursor, id_instrumento, filas):
    if not filas:
        return
    datos = [
        (
            id_instrumento, fila["fecha"], fila["precio_apertura"], fila["precio_cierre"],
            fila["precio_maximo"], fila["precio_minimo"], fila["volumen"],
        )
        for fila in filas
    ]
    cursor.executemany(
        """INSERT IGNORE INTO Cotizacion_Historica
           (id_instrumento, fecha, precio_apertura, precio_cierre, precio_maximo, precio_minimo, volumen)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        datos,
    )


def main():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    instrumentos = obtener_instrumentos_y_ultima_fecha(cursor)
    print(f"Revisando {len(instrumentos)} instrumentos...")

    total_nuevos = 0
    for item in instrumentos:
        ticker = item["ticker"]
        try:
            filas_nuevas = traer_dias_faltantes(ticker, item["ultima_fecha"])
        except Exception as e:
            print(f"  [ERROR] {ticker}: no se pudo traer histórico nuevo ({e})")
            continue

        if not filas_nuevas:
            print(f"  {ticker}: ya está al día, sin días nuevos.")
            continue

        for intento in range(1, 4):
            try:
                cursor2 = conexion.cursor()
                insertar_dias_nuevos(cursor2, item["id_instrumento"], filas_nuevas)
                conexion.commit()
                cursor2.close()
                print(f"  {ticker}: {len(filas_nuevas)} día(s) nuevo(s) insertado(s).")
                total_nuevos += len(filas_nuevas)
                break
            except (mysql.connector.errors.InterfaceError, mysql.connector.errors.OperationalError) as e:
                print(f"  [RECONEXIÓN] {ticker} (intento {intento}/3): {e}")
                conexion = reconectar_forzado(conexion)
            except mysql.connector.Error as e:
                print(f"  [ERROR DB] {ticker}: {e}")
                break

    cursor.close()
    conexion.close()
    print(f"\nActualización completa: {total_nuevos} registros nuevos en total.")


if __name__ == "__main__":
    main()