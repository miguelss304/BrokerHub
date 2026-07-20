"""
API de BrokerHub construida con FastAPI.

Corre localmente con:
    uvicorn main:app --reload

Documentación interactiva automática (para probar todo desde el navegador):
    http://127.0.0.1:8000/docs
"""

from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import mysql.connector

from conexion_db import obtener_conexion

app = FastAPI(
    title="BrokerHub API",
    description="API para consultar y operar sobre la plataforma de corretaje BrokerHub.",
    version="1.0.0",
)

# Habilita que cualquier frontend (dashboard, app, etc.) pueda llamar esta API
# desde el navegador. En producción se puede restringir allow_origins a
# dominios específicos en vez de "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Modelos de datos que entran en el "body" de las peticiones (POST)
# ------------------------------------------------------------------

class NuevaOrden(BaseModel):
    id_cuenta: int
    ticker: str
    tipo_orden: str      # "COMPRA" o "VENTA"
    cantidad: int
    precio_limite: float


# ------------------------------------------------------------------
# Utilidad interna: ejecutar un SELECT y devolver lista de diccionarios
# ------------------------------------------------------------------

def consultar(query, params=None):
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(query, params or ())
        resultado = cursor.fetchall()
        cursor.close()
        conexion.close()
        return resultado
    except mysql.connector.Error as e:
        raise HTTPException(
            status_code=503,
            detail=f"Base de datos no disponible en este momento: {e}",
        )


# ------------------------------------------------------------------
# Endpoint raíz (para confirmar que la API está viva)
# ------------------------------------------------------------------

@app.get("/")
def raiz():
    return {"mensaje": "BrokerHub API activa. Ve a /docs para probar los endpoints."}


@app.get("/health")
def health():
    """Endpoint de monitoreo: confirma que la API responde y que la base
    de datos está accesible en este momento."""
    try:
        conexion = obtener_conexion()
        vivo = conexion.is_connected()
        conexion.close()
        return {"status": "ok", "database": "conectada" if vivo else "desconectada"}
    except mysql.connector.Error as e:
        return {"status": "error", "database": f"no disponible: {e}"}


# ------------------------------------------------------------------
# Clientes
# ------------------------------------------------------------------

@app.get("/clientes")
def listar_clientes():
    return consultar(
        "SELECT id_cliente, nombre_completo, tipo_cliente, perfil_riesgo, correo FROM Cliente"
    )


@app.get("/clientes/{id_cliente}")
def obtener_cliente(id_cliente: int):
    resultado = consultar("SELECT * FROM Cliente WHERE id_cliente = %s", (id_cliente,))
    if not resultado:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return resultado[0]


@app.get("/clientes/{id_cliente}/cuentas")
def obtener_cuentas_cliente(id_cliente: int):
    return consultar(
        "SELECT * FROM Cuenta_Inversion WHERE id_cliente = %s",
        (id_cliente,),
    )


@app.get("/clientes/{id_cliente}/portafolio")
def obtener_portafolio(id_cliente: int):
    """Muestra las posiciones actuales del cliente, con el precio actual
    de cada instrumento y la ganancia/pérdida no realizada."""
    posiciones = consultar(
        """SELECT p.id_instrumento, i.ticker, i.nombre, p.cantidad,
                  p.precio_promedio_compra, p.fecha_primera_compra
           FROM Posicion p
           JOIN Instrumento_Financiero i ON i.id_instrumento = p.id_instrumento
           WHERE p.id_cliente = %s""",
        (id_cliente,),
    )

    for pos in posiciones:
        precio_actual = obtener_ultimo_precio(pos["id_instrumento"])
        pos["precio_actual"] = precio_actual
        if precio_actual is not None:
            pos["ganancia_perdida"] = round(
                (precio_actual - float(pos["precio_promedio_compra"])) * pos["cantidad"], 2
            )
        else:
            pos["ganancia_perdida"] = None

    return posiciones


@app.get("/clientes/{id_cliente}/ordenes")
def obtener_ordenes_cliente(id_cliente: int):
    return consultar(
        """SELECT o.* FROM Orden o
           JOIN Cuenta_Inversion c ON c.id_cuenta = o.id_cuenta
           WHERE c.id_cliente = %s
           ORDER BY o.fecha_hora DESC""",
        (id_cliente,),
    )


# ------------------------------------------------------------------
# Instrumentos
# ------------------------------------------------------------------

@app.get("/instrumentos")
def listar_instrumentos():
    return consultar(
        """SELECT i.id_instrumento, i.ticker, i.nombre, e.razon_social,
                  c.nombre AS categoria
           FROM Instrumento_Financiero i
           JOIN Emisor e ON e.id_emisor = i.id_emisor
           JOIN Categoria_Instrumento c ON c.id_categoria = i.id_categoria"""
    )


def obtener_ultimo_precio(id_instrumento: int) -> Optional[float]:
    """Precio en vivo si existe, si no cae al último cierre histórico."""
    vivo = consultar(
        """SELECT precio_actual FROM Precio_Tiempo_Real
           WHERE id_instrumento = %s ORDER BY fecha_hora DESC LIMIT 1""",
        (id_instrumento,),
    )
    if vivo:
        return float(vivo[0]["precio_actual"])

    historico = consultar(
        """SELECT precio_cierre FROM Cotizacion_Historica
           WHERE id_instrumento = %s ORDER BY fecha DESC LIMIT 1""",
        (id_instrumento,),
    )
    if historico:
        return float(historico[0]["precio_cierre"])

    return None


@app.get("/instrumentos/{ticker}/precio-actual")
def precio_actual(ticker: str):
    instrumento = consultar(
        "SELECT id_instrumento FROM Instrumento_Financiero WHERE ticker = %s", (ticker,)
    )
    if not instrumento:
        raise HTTPException(status_code=404, detail="Ticker no encontrado")

    precio = obtener_ultimo_precio(instrumento[0]["id_instrumento"])
    if precio is None:
        raise HTTPException(status_code=404, detail="Sin datos de precio para este instrumento")

    return {"ticker": ticker, "precio": precio}


@app.get("/instrumentos/{ticker}/historico")
def historico_instrumento(ticker: str, dias: int = 30):
    instrumento = consultar(
        "SELECT id_instrumento FROM Instrumento_Financiero WHERE ticker = %s", (ticker,)
    )
    if not instrumento:
        raise HTTPException(status_code=404, detail="Ticker no encontrado")

    return consultar(
        """SELECT fecha, precio_apertura, precio_cierre, precio_maximo, precio_minimo, volumen
           FROM Cotizacion_Historica
           WHERE id_instrumento = %s
           ORDER BY fecha DESC
           LIMIT %s""",
        (instrumento[0]["id_instrumento"], dias),
    )


# ------------------------------------------------------------------
# Órdenes
# ------------------------------------------------------------------

@app.post("/ordenes")
def colocar_orden(orden: NuevaOrden):
    if orden.tipo_orden not in ("COMPRA", "VENTA"):
        raise HTTPException(status_code=400, detail="tipo_orden debe ser 'COMPRA' o 'VENTA'")
    if orden.cantidad <= 0:
        raise HTTPException(status_code=400, detail="cantidad debe ser mayor a 0")

    instrumento = consultar(
        "SELECT id_instrumento FROM Instrumento_Financiero WHERE ticker = %s", (orden.ticker,)
    )
    if not instrumento:
        raise HTTPException(status_code=404, detail="Ticker no encontrado")

    cuenta = consultar(
        "SELECT id_cuenta FROM Cuenta_Inversion WHERE id_cuenta = %s AND estado = 'A'",
        (orden.id_cuenta,),
    )
    if not cuenta:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada o inactiva")

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute(
            """INSERT INTO Orden (id_cuenta, id_instrumento, tipo_orden, cantidad,
                                   precio_limite, fecha_hora, estado)
               VALUES (%s, %s, %s, %s, %s, %s, 'PENDIENTE')""",
            (
                orden.id_cuenta,
                instrumento[0]["id_instrumento"],
                orden.tipo_orden,
                orden.cantidad,
                orden.precio_limite,
                datetime.now(),
            ),
        )
        conexion.commit()
        id_orden = cursor.lastrowid
        cursor.close()
        conexion.close()
    except mysql.connector.Error as e:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo guardar la orden, base de datos no disponible: {e}",
        )

    return {
        "mensaje": "Orden colocada, queda PENDIENTE hasta que el ejecutor la resuelva",
        "id_orden": id_orden,
    }


@app.delete("/ordenes/{id_orden}")
def cancelar_orden(id_orden: int):
    """Cancela una orden, solo si todavía está en estado PENDIENTE
    (una orden ya EJECUTADA no se puede cancelar)."""
    resultado = consultar("SELECT estado FROM Orden WHERE id_orden = %s", (id_orden,))
    if not resultado:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    if resultado[0]["estado"] != "PENDIENTE":
        raise HTTPException(
            status_code=400,
            detail=f"Solo se pueden cancelar órdenes PENDIENTE (estado actual: {resultado[0]['estado']})",
        )

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE Orden SET estado = 'CANCELADA' WHERE id_orden = %s", (id_orden,)
        )
        conexion.commit()
        cursor.close()
        conexion.close()
    except mysql.connector.Error as e:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo cancelar la orden, base de datos no disponible: {e}",
        )

    return {"mensaje": f"Orden #{id_orden} cancelada correctamente"}


@app.get("/ordenes/{id_orden}")
def obtener_orden(id_orden: int):
    resultado = consultar("SELECT * FROM Orden WHERE id_orden = %s", (id_orden,))
    if not resultado:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    orden = resultado[0]
    orden["transacciones"] = consultar(
        "SELECT * FROM Transaccion_Ejecutada WHERE id_orden = %s", (id_orden,)
    )
    return orden