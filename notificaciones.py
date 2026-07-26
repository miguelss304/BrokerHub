"""Servicio de notificaciones para BrokerHub.

Este módulo expone utilidades para guardar notificaciones en la tabla
`Notificacion` de MySQL y puede ser usado desde la API y desde procesos
de backend como el ejecutor de órdenes.
"""

from typing import Optional
import mysql.connector

from conexion_db import obtener_conexion


def crear_notificacion(id_cliente: int, tipo: str, titulo: str, mensaje: str, conexion=None, cursor=None, commit: bool = True) -> None:
    """Registra una notificación para un cliente.

    Si se pasa un cursor o conexión existente, no la cierra localmente.
    """
    propio_cursor = False
    propio_conexion = False

    if cursor is None:
        if conexion is None:
            conexion = obtener_conexion()
            propio_conexion = True
        cursor = conexion.cursor()
        propio_cursor = True

    cursor.execute(
        """INSERT INTO Notificacion (id_cliente, tipo, titulo, mensaje)
           VALUES (%s, %s, %s, %s)""",
        (id_cliente, tipo, titulo, mensaje),
    )

    if commit and conexion is not None:
        conexion.commit()

    if propio_cursor:
        cursor.close()
    if propio_conexion:
        conexion.close()
