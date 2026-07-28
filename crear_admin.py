"""Script de utilidad para crear administradores en BrokerHub sin usar la API.

Este script usa la configuración de conexión de `conexion_db.py` y el hash bcrypt
definido en `auth.py` para insertar un cliente y su credencial con rol ADMIN.

Uso:
    py crear_admin.py --nombre "Admin Prueba" --usuario admin_prueba --contrasena Admin123! --correo admin@prueba.local --documento 00000000A

También acepta varios parámetros opcionales para controlar el tipo de cliente y
perfil de riesgo.
"""

import argparse
import sys

from auth import hash_contrasena
from conexion_db import obtener_conexion


def crear_admin_directo(
    nombre_completo: str,
    usuario: str,
    contrasena: str,
    correo: str,
    documento_identidad: str,
    tipo_cliente: str = "N",
    perfil_riesgo: str = "CONSERVADOR",
) -> int:
    """Inserta un admin directamente en la base de datos.

    Retorna el id_cliente del nuevo administrador.
    """
    tipo_cliente = tipo_cliente.upper()
    perfil_riesgo = perfil_riesgo.upper()

    if tipo_cliente not in ("N", "J"):
        raise ValueError("tipo_cliente debe ser 'N' o 'J'")
    if perfil_riesgo not in ("CONSERVADOR", "MODERADO", "AGRESIVO"):
        raise ValueError("perfil_riesgo inválido")

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:
        cursor.execute(
            """INSERT INTO Cliente (nombre_completo, tipo_cliente, documento_identidad,
                                     correo, perfil_riesgo, fecha_registro)
               VALUES (%s, %s, %s, %s, %s, CURDATE())""",
            (nombre_completo, tipo_cliente, documento_identidad, correo, perfil_riesgo),
        )
        id_cliente = cursor.lastrowid

        cursor.execute(
            """INSERT INTO Credencial (id_cliente, usuario, contrasena_hash, rol, fecha_creacion)
               VALUES (%s, %s, %s, 'ADMIN', NOW())""",
            (id_cliente, usuario, hash_contrasena(contrasena)),
        )

        conexion.commit()
        return id_cliente
    except Exception:
        conexion.rollback()
        raise
    finally:
        cursor.close()
        conexion.close()


def main():
    parser = argparse.ArgumentParser(description="Crear un administrador de BrokerHub directamente en la base de datos.")
    parser.add_argument("--nombre", required=True, help="Nombre completo del administrador")
    parser.add_argument("--usuario", required=True, help="Usuario de login del administrador")
    parser.add_argument("--contrasena", required=True, help="Contraseña del administrador")
    parser.add_argument("--correo", required=True, help="Correo electrónico del administrador")
    parser.add_argument("--documento", required=True, help="Documento de identidad del administrador")
    parser.add_argument("--tipo-cliente", default="N", choices=["N", "J"], help="Tipo de cliente: N o J")
    parser.add_argument(
        "--perfil-riesgo",
        default="CONSERVADOR",
        choices=["CONSERVADOR", "MODERADO", "AGRESIVO"],
        help="Perfil de riesgo del administrador",
    )

    args = parser.parse_args()

    try:
        id_cliente = crear_admin_directo(
            nombre_completo=args.nombre,
            usuario=args.usuario,
            contrasena=args.contrasena,
            correo=args.correo,
            documento_identidad=args.documento,
            tipo_cliente=args.tipo_cliente,
            perfil_riesgo=args.perfil_riesgo,
        )
        print(f"Administrador creado correctamente. id_cliente = {id_cliente}")
        print(f"Usuario: {args.usuario}")
        print(f"Contraseña: {args.contrasena}")
        print("Rol: ADMIN")
    except Exception as exc:
        print("Error al crear el administrador:", exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
