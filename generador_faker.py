"""
Generador de datos sintéticos para BrokerHub.

Puebla, con datos ficticios pero realistas:
- Cliente
- Cuenta_Inversion (1-2 cuentas por cliente)

Usa Faker en español (localización 'es_CO') para nombres y correos
coherentes con el contexto del proyecto.
"""

import hashlib
import random
from faker import Faker
from conexion_db import obtener_conexion, asegurar_conexion, reconectar_forzado
import mysql.connector

fake = Faker("es_CO")

# ------------------------------------------------------------------
# Configuración
# ------------------------------------------------------------------
NUM_CLIENTES = 30
PERFILES_RIESGO = ["CONSERVADOR", "MODERADO", "AGRESIVO"]
TIPOS_CUENTA = ["ORDINARIA", "RETIRO", "FIDUCIARIA"]


def generar_cliente():
    tipo_cliente = random.choices(["N", "J"], weights=[85, 15])[0]  # 85% naturales, 15% jurídicos
    nombre = fake.company() if tipo_cliente == "J" else fake.name()
    return {
        "nombre_completo": nombre,
        "tipo_cliente": tipo_cliente,
        "documento_identidad": fake.unique.numerify("1########"),
        "perfil_riesgo": random.choice(PERFILES_RIESGO),
        "correo": fake.unique.email(),
        "fecha_registro": fake.date_between(start_date="-2y", end_date="today"),
    }
    
def generar_credencial(cliente, id_cliente):
    usuario = fake.unique.user_name()
    contrasena_plana = fake.password(length=12)
    contrasena_hash = hashlib.sha256(contrasena_plana.encode()).hexdigest()
    fecha_creacion = fake.date_between(start_date=cliente["fecha_registro"], end_date="today")
    ultimo_acceso = fake.date_time_between(start_date=fecha_creacion, end_date="now")

    return {
        "id_cliente": id_cliente,
        "usuario": usuario,
        "contrasena_hash": contrasena_hash,
        "fecha_creacion": fecha_creacion,
        "ultimo_acceso": ultimo_acceso,
    }

#id_cliente, usuario, contrasena_hash, fecha_creacion, ultimo_acceso
def generar_cuenta(id_cliente):
    return {
        "id_cliente": id_cliente,
        "tipo_cuenta": random.choice(TIPOS_CUENTA),
        "saldo_disponible": round(random.uniform(1000, 50000), 2),
        "fecha_apertura": fake.date_between(start_date="-2y", end_date="today"),
        "estado": "A",
    }


def insertar_credenciales(cursor, credencial):
    cursor.execute(
        """INSERT INTO Credencial
           (id_cliente, usuario, contrasena_hash, fecha_creacion, ultimo_acceso)
           VALUES (%(id_cliente)s, %(usuario)s, %(contrasena_hash)s,
                   %(fecha_creacion)s, %(ultimo_acceso)s)""",
        credencial,
    )
    return cursor.lastrowid

def insertar_cliente(cursor, cliente):
    cursor.execute(
        """INSERT INTO Cliente
           (nombre_completo, tipo_cliente, documento_identidad, perfil_riesgo, correo, fecha_registro)
           VALUES (%(nombre_completo)s, %(tipo_cliente)s, %(documento_identidad)s,
                   %(perfil_riesgo)s, %(correo)s, %(fecha_registro)s)""",
        cliente,
    )
    return cursor.lastrowid


def insertar_cuenta(cursor, cuenta):
    cursor.execute(
        """INSERT INTO Cuenta_Inversion
           (id_cliente, tipo_cuenta, saldo_disponible, fecha_apertura, estado)
           VALUES (%(id_cliente)s, %(tipo_cuenta)s, %(saldo_disponible)s,
                   %(fecha_apertura)s, %(estado)s)""",
        cuenta,
    )
    return cursor.lastrowid


def main():
    conexion = obtener_conexion()

    total_insertados = 0

    for i in range(NUM_CLIENTES):
        conexion = asegurar_conexion(conexion)
        cursor = conexion.cursor()

        try:
            cliente = generar_cliente()
            id_cliente = insertar_cliente(cursor, cliente)
            credencial = generar_credencial(cliente, id_cliente)
            insertar_credenciales(cursor, credencial)

            # cada cliente tiene entre 1 y 2 cuentas
            num_cuentas = random.choice([1, 1, 1, 2])  # la mayoría con 1 sola cuenta
            for _ in range(num_cuentas):
                cuenta = generar_cuenta(id_cliente)
                insertar_cuenta(cursor, cuenta)

            conexion.commit()
            total_insertados += 1
            print(f"Cliente #{id_cliente} creado: {cliente['nombre_completo']} "
                  f"({cliente['perfil_riesgo']}, {num_cuentas} cuenta(s))")

        except mysql.connector.errors.InterfaceError as e:
            print(f"[RECONEXIÓN] Se perdió la conexión en el cliente #{i+1}: {e}")
            conexion = reconectar_forzado(conexion)
        except mysql.connector.Error as e:
            print(f"[ERROR DB] Falló insertando cliente #{i+1}: {e}")

    conexion.close()
    print(f"\nGeneración completa: {total_insertados}/{NUM_CLIENTES} clientes creados.")


if __name__ == "__main__":
    main()