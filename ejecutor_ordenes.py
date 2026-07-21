"""
Ejecutor de órdenes en tiempo real para BrokerHub.

Corre en paralelo a streaming.py (que llena Precio_Tiempo_Real).
Cada N segundos:
  1. Trae las órdenes en estado PENDIENTE.
  2. Trae el último precio conocido de cada instrumento involucrado
     (de Precio_Tiempo_Real si hay datos en vivo, si no cae a
     Cotizacion_Historica como respaldo).
  3. Compara cada orden contra el precio actual:
       COMPRA se ejecuta si precio_actual <= precio_limite
       VENTA  se ejecuta si precio_actual >= precio_limite
  4. Si se cumple: crea la Transaccion_Ejecutada, actualiza saldo de la
     cuenta, actualiza la Posicion del cliente, y marca la Orden como
     EJECUTADA.

Sigue el mismo patrón de "leer todo -> calcular en memoria -> escribir
en lote" para minimizar el tiempo de conexión abierta a MySQL.
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo
from conexion_db import obtener_conexion
import mysql.connector

INTERVALO_REVISION_SEGUNDOS = 5
COMISION_PORCENTAJE = 0.001  # 0.1%, igual que en simulador_ordenes.py


def mercado_esta_abierto() -> bool:
    """Horario de NYSE/NASDAQ: lunes a viernes, 9:30 AM - 4:00 PM hora de
    Nueva York. No contempla feriados (simplificación aceptada para el
    alcance del proyecto). Misma lógica que en main.py (API)."""
    ahora_ny = datetime.now(ZoneInfo("America/New_York"))

    if ahora_ny.weekday() >= 5:  # 5=sábado, 6=domingo
        return False

    apertura = ahora_ny.replace(hour=9, minute=30, second=0, microsecond=0)
    cierre = ahora_ny.replace(hour=16, minute=0, second=0, microsecond=0)

    return apertura <= ahora_ny <= cierre


# ------------------------------------------------------------------
# FASE 1: LECTURA
# ------------------------------------------------------------------

def leer_ordenes_pendientes(cursor):
    cursor.execute(
        """SELECT o.id_orden, o.id_cuenta, o.id_instrumento, o.tipo_orden,
                  o.cantidad, o.precio_limite, c.id_cliente, c.saldo_disponible
           FROM Orden o
           JOIN Cuenta_Inversion c ON c.id_cuenta = o.id_cuenta
           WHERE o.estado = 'PENDIENTE'"""
    )
    columnas = [d[0] for d in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def leer_precios_actuales(cursor, ids_instrumento):
    if not ids_instrumento:
        return {}

    formato = ",".join(["%s"] * len(ids_instrumento))
    precios = {}

    # Prioridad 1: último precio en vivo, SOLO si el mercado está abierto
    # (si está cerrado, el último trade puede ser de horas atrás y ya no
    # refleja el precio "actual" real -- se prefiere el cierre oficial)
    if mercado_esta_abierto():
        cursor.execute(
            f"""SELECT pt.id_instrumento, pt.precio_actual
                FROM Precio_Tiempo_Real pt
                INNER JOIN (
                    SELECT id_instrumento, MAX(fecha_hora) AS max_fecha
                    FROM Precio_Tiempo_Real
                    WHERE id_instrumento IN ({formato})
                    GROUP BY id_instrumento
                ) ultimo ON ultimo.id_instrumento = pt.id_instrumento
                         AND ultimo.max_fecha = pt.fecha_hora""",
            tuple(ids_instrumento),
        )
        precios = {fila[0]: float(fila[1]) for fila in cursor.fetchall()}

    # Prioridad 2 (respaldo): último cierre histórico -- para instrumentos
    # sin precio en vivo, o para todos si el mercado está cerrado
    faltantes = [i for i in ids_instrumento if i not in precios]
    if faltantes:
        formato2 = ",".join(["%s"] * len(faltantes))
        cursor.execute(
            f"""SELECT ch.id_instrumento, ch.precio_cierre
                FROM Cotizacion_Historica ch
                INNER JOIN (
                    SELECT id_instrumento, MAX(fecha) AS max_fecha
                    FROM Cotizacion_Historica
                    WHERE id_instrumento IN ({formato2})
                    GROUP BY id_instrumento
                ) ultimo ON ultimo.id_instrumento = ch.id_instrumento
                         AND ultimo.max_fecha = ch.fecha""",
            tuple(faltantes),
        )
        for id_instrumento, precio_cierre in cursor.fetchall():
            precios[id_instrumento] = float(precio_cierre)

    return precios


# ------------------------------------------------------------------
# FASE 2: CÁLCULO EN MEMORIA
# ------------------------------------------------------------------

def evaluar_ordenes(ordenes, precios_actuales):
    """Devuelve las órdenes que sí deben ejecutarse, junto con los datos
    necesarios para las escrituras (transacción, saldo, posición)."""

    ejecuciones = []       # (id_orden, id_cuenta, id_cliente, id_instrumento, cantidad, precio_ejecucion, comision, tipo)
    saldos_delta = {}      # id_cuenta -> cuánto sumar/restar al saldo_disponible
    posiciones_delta = {}  # (id_cuenta, id_instrumento) -> {"cantidad_delta", "costo_delta"}

    for orden in ordenes:
        precio_actual = precios_actuales.get(orden["id_instrumento"])
        if precio_actual is None:
            continue  # todavía no hay ningún precio conocido para este instrumento

        tipo = orden["tipo_orden"]
        precio_limite = float(orden["precio_limite"])
        cantidad = orden["cantidad"]

        se_ejecuta = (
            (tipo == "COMPRA" and precio_actual <= precio_limite) or
            (tipo == "VENTA" and precio_actual >= precio_limite)
        )
        if not se_ejecuta:
            continue

        valor_total = round(precio_actual * cantidad, 2)
        comision = round(valor_total * COMISION_PORCENTAJE, 2)

        if tipo == "COMPRA":
            saldo_requerido = valor_total + comision
            if float(orden["saldo_disponible"]) + saldos_delta.get(orden["id_cuenta"], 0) < saldo_requerido:
                continue  # ya no alcanza el saldo (pudo cambiar por otra orden ejecutada en esta misma pasada)
            saldos_delta[orden["id_cuenta"]] = saldos_delta.get(orden["id_cuenta"], 0) - saldo_requerido
        else:
            saldos_delta[orden["id_cuenta"]] = saldos_delta.get(orden["id_cuenta"], 0) + (valor_total - comision)

        clave_pos = (orden["id_cuenta"], orden["id_instrumento"])
        delta = posiciones_delta.setdefault(clave_pos, {"cantidad_delta": 0, "costo_delta": 0.0})
        if tipo == "COMPRA":
            delta["cantidad_delta"] += cantidad
            delta["costo_delta"] += valor_total
        else:
            delta["cantidad_delta"] -= cantidad
            delta["costo_delta"] -= valor_total

        ejecuciones.append({
            "id_orden": orden["id_orden"],
            "id_cuenta": orden["id_cuenta"],
            "id_cliente": orden["id_cliente"],
            "id_instrumento": orden["id_instrumento"],
            "cantidad": cantidad,
            "precio_ejecucion": precio_actual,
            "comision": comision,
        })

    return ejecuciones, saldos_delta, posiciones_delta


# ------------------------------------------------------------------
# FASE 3: ESCRITURA EN LOTE
# ------------------------------------------------------------------

def escribir_ejecuciones(cursor, ejecuciones, saldos_delta, posiciones_delta):
    if not ejecuciones:
        return

    ahora = datetime.now()

    # 1. Transacciones ejecutadas
    datos_transacciones = [
        (e["id_orden"], e["cantidad"], e["precio_ejecucion"], ahora, e["comision"])
        for e in ejecuciones
    ]
    cursor.executemany(
        """INSERT INTO Transaccion_Ejecutada
           (id_orden, cantidad_ejecutada, precio_ejecucion, fecha_hora, comision)
           VALUES (%s, %s, %s, %s, %s)""",
        datos_transacciones,
    )

    # 2. Marcar las órdenes como EJECUTADA
    ids_orden = [(e["id_orden"],) for e in ejecuciones]
    cursor.executemany(
        "UPDATE Orden SET estado = 'EJECUTADA' WHERE id_orden = %s",
        ids_orden,
    )

    # 3. Actualizar saldo de las cuentas afectadas (delta, no valor absoluto)
    datos_saldos = [(delta, id_cuenta) for id_cuenta, delta in saldos_delta.items()]
    cursor.executemany(
        "UPDATE Cuenta_Inversion SET saldo_disponible = saldo_disponible + %s WHERE id_cuenta = %s",
        datos_saldos,
    )

    # 4. Actualizar/crear posiciones (necesita fusionar con lo que ya existe)
    for (id_cuenta_pos, id_instrumento), delta in posiciones_delta.items():
        cursor.execute(
            """SELECT cantidad, precio_promedio_compra FROM Posicion
               WHERE id_cuenta = %s AND id_instrumento = %s""",
            (id_cuenta_pos, id_instrumento),
        )
        fila = cursor.fetchone()

        if fila:
            cantidad_previa, precio_prom_previo = fila
            costo_previo = float(cantidad_previa) * float(precio_prom_previo)
            nueva_cantidad = cantidad_previa + delta["cantidad_delta"]
            nuevo_costo = costo_previo + delta["costo_delta"]

            if nueva_cantidad <= 0:
                cursor.execute(
                    "DELETE FROM Posicion WHERE id_cuenta = %s AND id_instrumento = %s",
                    (id_cuenta_pos, id_instrumento),
                )
            else:
                nuevo_precio_prom = round(nuevo_costo / nueva_cantidad, 4)
                cursor.execute(
                    """UPDATE Posicion SET cantidad = %s, precio_promedio_compra = %s
                       WHERE id_cuenta = %s AND id_instrumento = %s""",
                    (nueva_cantidad, nuevo_precio_prom, id_cuenta_pos, id_instrumento),
                )
        else:
            # No existía posición previa (solo puede pasar si la orden era de COMPRA)
            if delta["cantidad_delta"] > 0:
                precio_prom = round(delta["costo_delta"] / delta["cantidad_delta"], 4)
                cursor.execute(
                    """INSERT INTO Posicion (id_cuenta, id_instrumento, cantidad,
                                              precio_promedio_compra, fecha_primera_compra)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (id_cuenta_pos, id_instrumento, delta["cantidad_delta"], precio_prom, datetime.now().date()),
                )


# ------------------------------------------------------------------
# Loop principal
# ------------------------------------------------------------------

def ciclo_revision():
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()

        ordenes = leer_ordenes_pendientes(cursor)
        print(f"[EJECUTOR] Ciclo de revisión: {len(ordenes)} orden(es) pendiente(s) encontradas.")
        if not ordenes:
            cursor.close()
            conexion.close()
            return

        ids_instrumento = list({o["id_instrumento"] for o in ordenes})
        precios_actuales = leer_precios_actuales(cursor, ids_instrumento)
        print(f"[EJECUTOR] Precios encontrados para instrumentos {ids_instrumento}: {precios_actuales}")

        ejecuciones, saldos_delta, posiciones_delta = evaluar_ordenes(ordenes, precios_actuales)
        print(f"[EJECUTOR] {len(ejecuciones)} de {len(ordenes)} órdenes cumplen condición de ejecución.")

        if ejecuciones:
            escribir_ejecuciones(cursor, ejecuciones, saldos_delta, posiciones_delta)
            conexion.commit()
            print(f"[EJECUTOR] {len(ejecuciones)} orden(es) ejecutada(s) en este ciclo.")

        cursor.close()
        conexion.close()

    except mysql.connector.Error as e:
        print(f"[EJECUTOR] Error de base de datos en este ciclo (se reintenta en el próximo): {e}")


def main():
    print(f"Ejecutor de órdenes iniciado (revisa cada {INTERVALO_REVISION_SEGUNDOS}s). Ctrl+C para detener.")
    while True:
        ciclo_revision()
        time.sleep(INTERVALO_REVISION_SEGUNDOS)


if __name__ == "__main__":
    main()simul