"""
Simulador de órdenes para BrokerHub.

Estrategia (para evitar cortes de conexión con Railway):
1. LECTURA: trae clientes, cuentas, instrumentos e histórico de precios
   a memoria en una sola conexión rápida.
2. CÁLCULO: genera órdenes, transacciones y recalcula saldo/posición
   completamente en memoria (sin tocar la base de datos).
3. ESCRITURA: abre una conexión nueva y hace todos los INSERT/UPDATE
   en lote (executemany), lo más rápido posible.
"""

import random
from datetime import datetime, timedelta
from conexion_db import obtener_conexion, reconectar_forzado
import mysql.connector

# ------------------------------------------------------------------
# Configuración
# ------------------------------------------------------------------
ORDENES_POR_CLIENTE_MIN = 2
ORDENES_POR_CLIENTE_MAX = 6
COMISION_PORCENTAJE = 0.001  # 0.1% por transacción


# ------------------------------------------------------------------
# FASE 1: LECTURA (conexión corta, solo SELECTs)
# ------------------------------------------------------------------

def leer_datos_base():
    conexion = obtener_conexion()
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("SELECT id_cuenta, id_cliente, saldo_disponible FROM Cuenta_Inversion WHERE estado = 'A'")
    cuentas = cursor.fetchall()

    cursor.execute("SELECT id_instrumento, ticker FROM Instrumento_Financiero")
    instrumentos = cursor.fetchall()

    cursor.execute(
        "SELECT id_instrumento, fecha, precio_cierre FROM Cotizacion_Historica ORDER BY id_instrumento, fecha"
    )
    filas_precios = cursor.fetchall()

    cursor.close()
    conexion.close()

    # Organiza precios por instrumento para acceso rápido en memoria
    precios_por_instrumento = {}
    for fila in filas_precios:
        precios_por_instrumento.setdefault(fila["id_instrumento"], []).append(fila)

    return cuentas, instrumentos, precios_por_instrumento


# ------------------------------------------------------------------
# FASE 2: CÁLCULO EN MEMORIA (nada de base de datos aquí)
# ------------------------------------------------------------------

def simular_ordenes(cuentas, instrumentos, precios_por_instrumento):
    """Devuelve listas listas para insertar: ordenes, transacciones,
    y los saldos/posiciones finales ya recalculados."""

    ordenes_a_insertar = []       # (id_cuenta, id_instrumento, tipo, cantidad, precio_limite, fecha_hora, estado)
    transacciones_a_insertar = [] # (indice_orden, cantidad_ejecutada, precio_ejecucion, fecha_hora, comision)
    saldos_finales = {c["id_cuenta"]: float(c["saldo_disponible"]) for c in cuentas}
    posiciones = {}  # (id_cliente, id_instrumento) -> {cantidad, costo_total, fecha_primera_compra}

    id_cliente_por_cuenta = {c["id_cuenta"]: c["id_cliente"] for c in cuentas}

    instrumentos_con_precio = [i for i in instrumentos if precios_por_instrumento.get(i["id_instrumento"])]

    for cuenta in cuentas:
        id_cuenta = cuenta["id_cuenta"]
        id_cliente = cuenta["id_cliente"]
        num_ordenes = random.randint(ORDENES_POR_CLIENTE_MIN, ORDENES_POR_CLIENTE_MAX)

        for _ in range(num_ordenes):
            if not instrumentos_con_precio:
                break
            instrumento = random.choice(instrumentos_con_precio)
            id_instrumento = instrumento["id_instrumento"]
            historico = precios_por_instrumento[id_instrumento]

            fila_precio = random.choice(historico)
            precio_referencia = float(fila_precio["precio_cierre"])
            fecha_orden = fila_precio["fecha"]

            tipo_orden = random.choice(["COMPRA", "VENTA"])
            cantidad = random.randint(1, 20)
            # precio límite cercano al precio real (+/- 1%)
            variacion = random.uniform(-0.01, 0.01)
            precio_limite = round(precio_referencia * (1 + variacion), 4)

            valor_total = round(precio_limite * cantidad, 2)
            comision = round(valor_total * COMISION_PORCENTAJE, 2)

            # Validar saldo si es COMPRA
            if tipo_orden == "COMPRA":
                if saldos_finales[id_cuenta] < (valor_total + comision):
                    continue  # no alcanza el saldo, se descarta esta orden
                saldos_finales[id_cuenta] -= (valor_total + comision)
            else:  # VENTA - solo vende si ya tiene posición suficiente
                clave_pos = (id_cliente, id_instrumento)
                pos_actual = posiciones.get(clave_pos)
                if not pos_actual or pos_actual["cantidad"] < cantidad:
                    continue  # no tiene suficientes unidades, se descarta
                saldos_finales[id_cuenta] += (valor_total - comision)

            fecha_hora = datetime.combine(fecha_orden, datetime.min.time()) + timedelta(
                hours=random.randint(9, 15), minutes=random.randint(0, 59)
            )

            indice_orden = len(ordenes_a_insertar)
            ordenes_a_insertar.append(
                (id_cuenta, id_instrumento, tipo_orden, cantidad, precio_limite, fecha_hora, "EJECUTADA")
            )
            transacciones_a_insertar.append(
                (indice_orden, cantidad, precio_limite, fecha_hora, comision)
            )

            # Actualiza posición en memoria
            clave_pos = (id_cliente, id_instrumento)
            if tipo_orden == "COMPRA":
                if clave_pos not in posiciones:
                    posiciones[clave_pos] = {
                        "cantidad": 0, "costo_total": 0.0, "fecha_primera_compra": fecha_orden
                    }
                pos = posiciones[clave_pos]
                pos["costo_total"] += precio_limite * cantidad
                pos["cantidad"] += cantidad
                if fecha_orden < pos["fecha_primera_compra"]:
                    pos["fecha_primera_compra"] = fecha_orden
            else:
                pos = posiciones[clave_pos]
                pos["cantidad"] -= cantidad
                if pos["cantidad"] <= 0:
                    del posiciones[clave_pos]

    return ordenes_a_insertar, transacciones_a_insertar, saldos_finales, posiciones, id_cliente_por_cuenta


# ------------------------------------------------------------------
# FASE 3: ESCRITURA EN LOTE (conexión nueva, todo de un tirón)
# ------------------------------------------------------------------

def escribir_resultados(ordenes, transacciones, saldos_finales, posiciones, max_intentos=3):
    for intento in range(1, max_intentos + 1):
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        try:
            # --- 1. Averiguar el próximo AUTO_INCREMENT de Orden ANTES de insertar ---
            cursor.execute(
                """SELECT AUTO_INCREMENT FROM information_schema.TABLES
                   WHERE table_schema = DATABASE() AND table_name = 'Orden'"""
            )
            siguiente_id_orden = cursor.fetchone()[0]

            # --- 2. Insertar TODAS las órdenes en un solo statement (batch real) ---
            cursor.executemany(
                """INSERT INTO Orden (id_cuenta, id_instrumento, tipo_orden, cantidad,
                                       precio_limite, fecha_hora, estado)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                ordenes,
            )

            # Como InnoDB asigna AUTO_INCREMENT de forma contigua para un solo
            # INSERT multi-fila (modo por defecto), los IDs reales son consecutivos
            # a partir de siguiente_id_orden, en el mismo orden en que se insertaron.
            ids_orden_reales = list(range(siguiente_id_orden, siguiente_id_orden + len(ordenes)))

            # --- 3. Insertar transacciones, referenciando el id_orden real ---
            datos_transacciones = [
                (ids_orden_reales[indice], cantidad, precio, fecha, comision)
                for (indice, cantidad, precio, fecha, comision) in transacciones
            ]
            cursor.executemany(
                """INSERT INTO Transaccion_Ejecutada
                   (id_orden, cantidad_ejecutada, precio_ejecucion, fecha_hora, comision)
                   VALUES (%s, %s, %s, %s, %s)""",
                datos_transacciones,
            )

            # --- 4. Actualizar saldo_disponible de cada cuenta afectada ---
            datos_saldos = [(saldo, id_cuenta) for id_cuenta, saldo in saldos_finales.items()]
            cursor.executemany(
                "UPDATE Cuenta_Inversion SET saldo_disponible = %s WHERE id_cuenta = %s",
                datos_saldos,
            )

            # --- 5. Insertar/actualizar posiciones finales ---
            datos_posiciones = []
            for (id_cliente, id_instrumento), pos in posiciones.items():
                precio_promedio = round(pos["costo_total"] / pos["cantidad"], 4)
                datos_posiciones.append(
                    (id_cliente, id_instrumento, pos["cantidad"], precio_promedio, pos["fecha_primera_compra"])
                )
            cursor.executemany(
                """INSERT INTO Posicion (id_cliente, id_instrumento, cantidad, precio_promedio_compra, fecha_primera_compra)
                   VALUES (%s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                       cantidad = VALUES(cantidad),
                       precio_promedio_compra = VALUES(precio_promedio_compra)""",
                datos_posiciones,
            )

            conexion.commit()
            print(f"Escritura completa: {len(ordenes)} órdenes, {len(datos_transacciones)} transacciones, "
                  f"{len(datos_saldos)} saldos actualizados, {len(datos_posiciones)} posiciones.")
            cursor.close()
            conexion.close()
            return  # éxito, salimos de la función

        except (mysql.connector.errors.InterfaceError, mysql.connector.errors.OperationalError) as e:
            print(f"[RECONEXIÓN] Se perdió la conexión durante la escritura "
                  f"(intento {intento}/{max_intentos}): {e}")
            try:
                conexion.close()
            except Exception:
                pass
            # Como no hubo commit, no se insertó nada -> es seguro reintentar todo desde cero
        except mysql.connector.Error as e:
            conexion.rollback()
            print(f"[ERROR DB] Falló la escritura en lote, se revirtió todo: {e}")
            cursor.close()
            conexion.close()
            return

    print(f"[ABANDONADO] No se pudo escribir tras {max_intentos} intentos por problemas de conexión.")


# ------------------------------------------------------------------
# Proceso principal
# ------------------------------------------------------------------

def main():
    print("Fase 1: leyendo datos base...")
    cuentas, instrumentos, precios_por_instrumento = leer_datos_base()
    print(f"  {len(cuentas)} cuentas, {len(instrumentos)} instrumentos con histórico disponible")

    print("Fase 2: simulando órdenes en memoria...")
    ordenes, transacciones, saldos_finales, posiciones, _ = simular_ordenes(
        cuentas, instrumentos, precios_por_instrumento
    )
    print(f"  {len(ordenes)} órdenes generadas, {len(posiciones)} posiciones resultantes")

    print("Fase 3: escribiendo resultados en la base de datos...")
    escribir_resultados(ordenes, transacciones, saldos_finales, posiciones)


if __name__ == "__main__":
    main()