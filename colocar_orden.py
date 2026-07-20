"""
Utilidad para colocar una orden nueva en estado PENDIENTE.
Sirve para probar ejecutor_ordenes.py en vivo: coloca una orden con un
precio_limite cercano al precio actual y observa si el ejecutor la toma.

Uso:
    python colocar_orden.py
(edita los valores de ejemplo abajo, o conviértelo en función reutilizable)
"""

from datetime import datetime
from conexion_db import obtener_conexion


def colocar_orden(id_cuenta, ticker, tipo_orden, cantidad, precio_limite):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("SELECT id_instrumento FROM Instrumento_Financiero WHERE ticker = %s", (ticker,))
    fila = cursor.fetchone()
    if not fila:
        print(f"Ticker {ticker} no encontrado.")
        cursor.close()
        conexion.close()
        return None

    id_instrumento = fila[0]

    cursor.execute(
        """INSERT INTO Orden (id_cuenta, id_instrumento, tipo_orden, cantidad,
                               precio_limite, fecha_hora, estado)
           VALUES (%s, %s, %s, %s, %s, %s, 'PENDIENTE')""",
        (id_cuenta, id_instrumento, tipo_orden, cantidad, precio_limite, datetime.now()),
    )
    conexion.commit()
    id_orden = cursor.lastrowid

    cursor.close()
    conexion.close()

    print(f"Orden #{id_orden} colocada: {tipo_orden} {cantidad}x {ticker} @ {precio_limite}")
    return id_orden


if __name__ == "__main__":
    # Ejemplo: ajusta id_cuenta, ticker, tipo, cantidad y precio a tu gusto
    colocar_orden(
        id_cuenta=1,
        ticker="AAPL",
        tipo_orden="COMPRA",
        cantidad=5,
        precio_limite=999999,  # precio absurdamente alto para que SIEMPRE se ejecute (prueba rápida)
    )