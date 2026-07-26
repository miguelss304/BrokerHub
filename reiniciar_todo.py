"""
Reinicia la base de datos de BrokerHub por completo y la repuebla.

Corre, en orden:
  1. broker_esquema_mysql.sql  -> DROP + CREATE de las 12 tablas (esquema limpio)
  2. 03_plsql.sql              -> triggers, funciones y procedimientos almacenados
  3. carga_inicial.py          -> Emisor, Instrumento, Categoría, Cotización, Listado
  4. generador_faker.py        -> Cliente, Credencial (bcrypt, contraseña conocida), Cuenta_Inversion
  5. simulador_ordenes.py      -> Orden, Transaccion_Ejecutada, Posicion (histórico simulado)

Uso:
    py reiniciar_todo.py

ADVERTENCIA: esto borra TODA la base de datos "railway" en Railway y la
vuelve a crear vacía. No lo corras si el equipo tiene datos que alguien
más quiere conservar -- avisa antes en el chat del equipo (ver README,
sección "Trabajo en equipo").
"""

import re
import subprocess
import sys
import time

from conexion_db import obtener_conexion

RUTA_DDL = "broker_esquema_mysql.sql"
RUTA_PLSQL = "trigger_procs_func.sql"  # ajusta el nombre si en tu proyecto se llama distinto

SCRIPTS_POBLAMIENTO = [
    "carga_inicial.py",
    "generador_faker.py",
    "simulador_ordenes.py",
]

CONTRASENA_DEMO = "Demo1234"  # debe coincidir con la de generador_faker.py


def confirmar():
    print("=" * 60)
    print("ADVERTENCIA: esto va a BORRAR toda la base de datos 'railway'")
    print("en Railway y la va a recrear vacía desde cero.")
    print("=" * 60)
    respuesta = input("¿Confirmas que quieres continuar? (escribe 'si' para continuar): ")
    if respuesta.strip().lower() != "si":
        print("Cancelado. No se modificó nada.")
        sys.exit(0)


def ejecutar_ddl(total_pasos):
    print(f"\n[1/{total_pasos}] Ejecutando DDL (reset del esquema)...")
    with open(RUTA_DDL, "r", encoding="utf-8") as archivo:
        script_sql = archivo.read()

    # mysql.connector no soporta bien multi-statement con execute() normal,
    # así que se parte por sentencias usando ';' como separador. Es
    # suficiente aquí porque el DDL no usa ';' dentro de strings/comentarios.
    sentencias = [s.strip() for s in script_sql.split(";") if s.strip()]

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    for sentencia in sentencias:
        cursor.execute(sentencia)
    conexion.commit()
    cursor.close()
    conexion.close()
    print("    Esquema recreado correctamente (12 tablas vacías).")


def ejecutar_plsql(total_pasos):
    """Ejecuta trigger_procs_func.sql, que usa bloques DELIMITER $$ ... $$ para
    definir triggers/funciones/procedimientos (su cuerpo contiene ';'
    internamente, así que NO se puede partir por ';' como el DDL plano).

    Estrategia: se parte el archivo respetando los bloques DELIMITER,
    y cada CREATE TRIGGER/FUNCTION/PROCEDURE se ejecuta como una sola
    sentencia completa.
    """
    print(f"\n[2/{total_pasos}] Ejecutando triggers, funciones y procedimientos (trigger_procs_func.sql)...")
    with open(RUTA_PLSQL, "r", encoding="utf-8") as archivo:
        script_sql = archivo.read()

    sentencias = _dividir_script_con_delimiter(script_sql)

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    for sentencia in sentencias:
        if sentencia.strip():
            cursor.execute(sentencia)
    conexion.commit()
    cursor.close()
    conexion.close()
    print("    Triggers, funciones y procedimientos creados correctamente.")


def _dividir_script_con_delimiter(script_sql: str) -> list[str]:
    """Divide un script SQL en sentencias individuales, respetando los
    bloques 'DELIMITER $$ ... cuerpo con ; ... $$' y las sentencias
    normales separadas por ';' fuera de esos bloques."""
    sentencias = []
    delimitador_actual = ";"
    buffer_actual = ""

    for linea in script_sql.splitlines():
        linea_limpia = linea.strip()

        coincidencia = re.match(r"^DELIMITER\s+(\S+)$", linea_limpia, re.IGNORECASE)
        if coincidencia:
            # cambio de delimitador: cierra lo que hubiera pendiente y arranca de nuevo
            if buffer_actual.strip():
                sentencias.append(buffer_actual.strip())
            buffer_actual = ""
            delimitador_actual = coincidencia.group(1)
            continue

        buffer_actual += linea + "\n"

        if buffer_actual.rstrip().endswith(delimitador_actual):
            sentencia = buffer_actual.rstrip()[: -len(delimitador_actual)].strip()
            if sentencia:
                sentencias.append(sentencia)
            buffer_actual = ""

    if buffer_actual.strip():
        sentencias.append(buffer_actual.strip())

    return sentencias


def ejecutar_script(nombre_script, paso, total):
    print(f"\n[{paso}/{total}] Corriendo {nombre_script} ...")
    resultado = subprocess.run([sys.executable, nombre_script], capture_output=False)
    if resultado.returncode != 0:
        print(f"    ERROR: {nombre_script} terminó con código {resultado.returncode}. Deteniendo el proceso.")
        sys.exit(1)
    print(f"    {nombre_script} terminado correctamente.")


def mostrar_resumen():
    conexion = obtener_conexion()
    cursor = conexion.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) AS total FROM Cliente")
    total_clientes = cursor.fetchone()["total"]

    cursor.execute(
        """SELECT c.id_cliente, c.nombre_completo, cr.usuario
           FROM Cliente c
           JOIN Credencial cr ON cr.id_cliente = c.id_cliente
           LIMIT 5"""
    )
    muestra = cursor.fetchall()
    cursor.close()
    conexion.close()

    print("\n" + "=" * 60)
    print(f"LISTO. Se generaron {total_clientes} clientes.")
    print(f"Todos pueden loguearse en POST /auth/login con la contraseña: {CONTRASENA_DEMO}")
    print("\nAlgunos usuarios de ejemplo para probar el login:")
    for fila in muestra:
        print(f"  usuario: {fila['usuario']:20s}  (cliente #{fila['id_cliente']}: {fila['nombre_completo']})")
    print("=" * 60)


def main():
    tiempo_inicio = time.time()

    total_pasos = 2 + len(SCRIPTS_POBLAMIENTO)  # DDL + plsql + los 3 scripts de poblamiento

    confirmar()
    ejecutar_ddl(total_pasos)
    ejecutar_plsql(total_pasos)

    for indice, script in enumerate(SCRIPTS_POBLAMIENTO, start=3):  # arranca en 3 (DDL=1, plsql=2)
        ejecutar_script(script, indice, total_pasos)

    mostrar_resumen()

    duracion = round(time.time() - tiempo_inicio, 1)
    print(f"\nProceso completo en {duracion} segundos.")


if __name__ == "__main__":
    main()