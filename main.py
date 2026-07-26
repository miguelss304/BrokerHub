"""
===============================================================================
BrokerHub API - Plataforma de Corretaje
===============================================================================
API RESTful construida con FastAPI para consultar y operar sobre la plataforma 
de corretaje BrokerHub.

Instrucciones de ejecución local:
    uvicorn main:app --reload

Documentación interactiva Swagger UI:
    http://127.0.0.1:8000/docs
===============================================================================
"""

from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import mysql.connector
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

# Módulos propios del proyecto (Asegúrate de que existan en el entorno)
from conexion_db import obtener_conexion
from auth import verificar_contrasena, crear_token, hash_contrasena, verificar_token
# Definir o importar funciones de seguridad JWT y Bcrypt
# from seguridad import crear_token, verificar_token, hash_contrasena, verificar_contrasena


# =============================================================================
# INICIALIZACIÓN Y CONFIGURACIÓN DE FASTAPI
# =============================================================================

app = FastAPI(
    title="BrokerHub API",
    description="API para consultar y operar sobre la plataforma de corretaje BrokerHub.",
    version="1.0.0",
)

security = HTTPBearer(auto_error=False)

# Habilita peticiones Cross-Origin (CORS) para clientes frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# MODELOS DE DATOS (PYDANTIC SCHEMAS)
# =============================================================================

class NuevaOrden(BaseModel):
    """Esquema para la creación de una nueva orden de compra/venta."""
    id_cuenta: int
    ticker: str
    tipo_orden: str      # 'COMPRA' o 'VENTA'
    cantidad: int
    precio_limite: float


class NuevoCliente(BaseModel):
    """Esquema para el registro de un nuevo cliente y su usuario."""
    nombre_completo: str
    tipo_cliente: str          # 'N' (Natural) o 'J' (Jurídico)
    documento_identidad: str
    correo: EmailStr
    perfil_riesgo: str         # 'CONSERVADOR', 'MODERADO' o 'AGRESIVO'
    usuario: str
    contrasena: str


class LoginRequest(BaseModel):
    """Esquema para la solicitud de autenticación."""
    usuario: str
    contrasena: str


class MovimientoCuenta(BaseModel):
    """Esquema para depósitos y retiros de fondos."""
    monto: float


class ClienteUpdate(BaseModel):
    """Esquema para actualizar datos de contacto y perfil de riesgo de un cliente."""
    nombre_completo: Optional[str] = None
    correo: Optional[EmailStr] = None
    perfil_riesgo: Optional[str] = None


class NuevaCuenta(BaseModel):
    """Esquema para abrir una nueva cuenta de inversión."""
    tipo_cuenta: str
    saldo_inicial: float = 0


# =============================================================================
# FUNCIONES AUXILIARES Y SERVICIOS INTERNOS
# =============================================================================

def consultar(query: str, params: Optional[tuple] = None) -> list:
    """Ejecuta una consulta SQL de lectura (SELECT) y devuelve los resultados 
    como una lista de diccionarios.
    
    Raises:
        HTTPException: Status 503 si la base de datos no está disponible.
    """
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


def mercado_esta_abierto() -> bool:
    """Verifica si el mercado financiero (NYSE/NASDAQ) se encuentra abierto.
    
    Regla: Lunes a Viernes, de 9:30 AM a 4:00 PM (Hora de Nueva York).
    """
    ahora_ny = datetime.now(ZoneInfo("America/New_York"))

    # Días de fin de semana (5 = Sábado, 6 = Domingo)
    if ahora_ny.weekday() >= 5:
        return False

    apertura = ahora_ny.replace(hour=9, minute=30, second=0, microsecond=0)
    cierre = ahora_ny.replace(hour=16, minute=0, second=0, microsecond=0)

    return apertura <= ahora_ny <= cierre


def obtener_ultimo_precio(id_instrumento: int) -> tuple[Optional[float], str]:
    """Obtiene la última cotización disponible de un instrumento financiero.
    
    Estrategia:
      1. Si el mercado está abierto, intenta obtener el precio en tiempo real.
      2. Si el mercado está cerrado o no hay precio en vivo, consulta el precio 
         de cierre histórico más reciente.

    Returns:
        tuple: (precio, fuente) donde fuente es 'vivo', 'historico' o 'sin_datos'.
    """
    if mercado_esta_abierto():
        vivo = consultar(
            """SELECT precio_actual FROM Precio_Tiempo_Real
               WHERE id_instrumento = %s ORDER BY fecha_hora DESC LIMIT 1""",
            (id_instrumento,),
        )
        if vivo:
            return float(vivo[0]["precio_actual"]), "vivo"

    historico = consultar(
        """SELECT precio_cierre FROM Cotizacion_Historica
           WHERE id_instrumento = %s ORDER BY fecha DESC LIMIT 1""",
        (id_instrumento,),
    )
    if historico:
        return float(historico[0]["precio_cierre"]), "historico"

    return None, "sin_datos"


def _validar_cuenta_del_cliente(id_cuenta: int, id_cliente: int) -> dict:
    """Valida la existencia, estado activo y titularidad de una cuenta.
    
    Raises:
        HTTPException: 404 si no existe/inactiva, 403 si pertenece a otro cliente.
    """
    resultado = consultar(
        "SELECT * FROM Cuenta_Inversion WHERE id_cuenta = %s AND estado = 'A'", (id_cuenta,)
    )
    if not resultado:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada o inactiva")

    cuenta = resultado[0]
    if cuenta["id_cliente"] != id_cliente:
        raise HTTPException(status_code=403, detail="Esta cuenta no pertenece al cliente autenticado")

    return cuenta


def _validar_cliente_autorizado(id_cliente: int, id_cliente_autenticado: int) -> None:
    """Garantiza que un cliente solo pueda operar sobre su propio perfil."""
    if id_cliente != id_cliente_autenticado:
        raise HTTPException(status_code=403, detail="No tienes permisos sobre este cliente")


# =============================================================================
# MIDDLEWARE Y DEPENDENCIAS DE SEGURIDAD
# =============================================================================

def obtener_cliente_actual(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Dependencia HTTP para validar el Bearer Token JWT en cabeceras.
    
    Returns:
        dict: Payload del token JWT con datos del cliente (id_cliente, usuario).
    
    Raises:
        HTTPException: Status 401 si el header falta, es inválido o expiró.
    """
    authorization = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        authorization = credentials.credentials.strip()
    else:
        authorization = request.headers.get("authorization") or request.headers.get("Authorization")

    if not authorization:
        raise HTTPException(status_code=401, detail="Falta el header Authorization: Bearer <token>")

    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    else:
        token = authorization.strip()

    try:
        payload = verificar_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido o expirado, inicia sesión de nuevo")

    return payload


# =============================================================================
# RUTAS / ENDPOINTS DE LA API
# =============================================================================

# -----------------------------------------------------------------------------
# 1. Monitoreo y Estado del Sistema
# -----------------------------------------------------------------------------

@app.get("/", tags=["Monitoreo"])
def raiz():
    """Endpoint de bienvenida."""
    return {"mensaje": "BrokerHub API activa. Ve a /docs para probar los endpoints."}


@app.get("/health", tags=["Monitoreo"])
def health():
    """Confirma que la API responde y verifica la conectividad con la base de datos."""
    try:
        conexion = obtener_conexion()
        vivo = conexion.is_connected()
        conexion.close()
        return {"status": "ok", "database": "conectada" if vivo else "desconectada"}
    except mysql.connector.Error as e:
        return {"status": "error", "database": f"no disponible: {e}"}


# -----------------------------------------------------------------------------
# 2. Autenticación y Registro (Auth)
# -----------------------------------------------------------------------------

@app.post("/auth/registro", status_code=201, tags=["Autenticación"])
def registrar_cliente(datos: NuevoCliente):
    """Registra un nuevo cliente, genera sus credenciales y crea su cuenta de 
    inversión inicial."""
    if datos.tipo_cliente not in ("N", "J"):
        raise HTTPException(status_code=400, detail="tipo_cliente debe ser 'N' o 'J'")
    if datos.perfil_riesgo not in ("CONSERVADOR", "MODERADO", "AGRESIVO"):
        raise HTTPException(status_code=400, detail="perfil_riesgo inválido")

    existente = consultar(
        "SELECT id_cliente FROM Credencial WHERE usuario = %s", (datos.usuario,)
    )
    if existente:
        raise HTTPException(status_code=409, detail="Ese nombre de usuario ya está en uso")

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()

        # Insertar registro principal del Cliente
        cursor.execute(
            """INSERT INTO Cliente (nombre_completo, tipo_cliente, documento_identidad,
                                     correo, perfil_riesgo, fecha_registro)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (datos.nombre_completo, datos.tipo_cliente, datos.documento_identidad,
             datos.correo, datos.perfil_riesgo, datetime.now().date()),
        )
        id_cliente = cursor.lastrowid

        # Guardar Credenciales asociadas (Hash de contraseña con Bcrypt)
        cursor.execute(
            """INSERT INTO Credencial (id_cliente, usuario, contrasena_hash, fecha_creacion)
               VALUES (%s, %s, %s, %s)""",
            (id_cliente, datos.usuario, hash_contrasena(datos.contrasena), datetime.now()),
        )

        # Apertura de cuenta de inversión por defecto
        cursor.execute(
            """INSERT INTO Cuenta_Inversion (id_cliente, tipo_cuenta, saldo_disponible,
                                              fecha_apertura, estado)
               VALUES (%s, 'ORDINARIA', 0, %s, 'A')""",
            (id_cliente, datetime.now().date()),
        )
        id_cuenta = cursor.lastrowid

        conexion.commit()
        cursor.close()
        conexion.close()
    except mysql.connector.IntegrityError as e:
        raise HTTPException(status_code=409, detail=f"Datos duplicados: {e}")
    except mysql.connector.Error as e:
        raise HTTPException(status_code=503, detail=f"Base de datos no disponible: {e}")

    token = crear_token(id_cliente, datos.usuario)
    return {
        "mensaje": "Cliente registrado correctamente",
        "id_cliente": id_cliente,
        "id_cuenta": id_cuenta,
        "token": token,
    }


@app.post("/auth/login", tags=["Autenticación"])
def login(datos: LoginRequest):
    """Autentica las credenciales de un usuario y retorna un Token JWT de acceso."""
    resultado = consultar(
        """SELECT cr.id_cliente, cr.usuario, cr.contrasena_hash
           FROM Credencial cr
           WHERE cr.usuario = %s""",
        (datos.usuario,),
    )
    
    credenciales_invalidas = HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    if not resultado:
        raise credenciales_invalidas

    credencial = resultado[0]
    if not verificar_contrasena(datos.contrasena, credencial["contrasena_hash"]):
        raise credenciales_invalidas

    # Actualizar la fecha y hora del último acceso
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE Credencial SET ultimo_acceso = %s WHERE usuario = %s",
            (datetime.now(), datos.usuario),
        )
        conexion.commit()
        cursor.close()
        conexion.close()
    except mysql.connector.Error:
        pass  # Tolerancia a fallos: no bloquea el login si este UPDATE falla

    token = crear_token(credencial["id_cliente"], credencial["usuario"])
    return {
        "id_cliente": credencial["id_cliente"],
        "usuario": credencial["usuario"],
        "token": token,
    }


# -----------------------------------------------------------------------------
# 3. Gestión de Clientes
# -----------------------------------------------------------------------------

@app.get("/clientes", tags=["Clientes"])
def listar_clientes():
    """Obtiene la lista general de todos los clientes registrados."""
    return consultar(
        "SELECT id_cliente, nombre_completo, tipo_cliente, perfil_riesgo, correo FROM Cliente"
    )


@app.get("/clientes/{id_cliente}", tags=["Clientes"])
def obtener_cliente(id_cliente: int, cliente=Depends(obtener_cliente_actual)):
    """Retorna los datos del perfil de un cliente específico."""
    _validar_cliente_autorizado(id_cliente, cliente["id_cliente"])
    resultado = consultar("SELECT * FROM Cliente WHERE id_cliente = %s", (id_cliente,))
    if not resultado:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return resultado[0]


@app.put("/clientes/{id_cliente}", tags=["Clientes"])
def actualizar_cliente(id_cliente: int, datos: ClienteUpdate, cliente=Depends(obtener_cliente_actual)):
    """Actualiza datos de contacto y perfil de riesgo de un cliente."""
    _validar_cliente_autorizado(id_cliente, cliente["id_cliente"])

    if datos.perfil_riesgo is not None and datos.perfil_riesgo not in ("CONSERVADOR", "MODERADO", "AGRESIVO"):
        raise HTTPException(status_code=400, detail="perfil_riesgo inválido")

    cambios = {}
    if datos.nombre_completo is not None:
        cambios["nombre_completo"] = datos.nombre_completo
    if datos.correo is not None:
        cambios["correo"] = str(datos.correo)
    if datos.perfil_riesgo is not None:
        cambios["perfil_riesgo"] = datos.perfil_riesgo

    if not cambios:
        return {"mensaje": "No hay cambios para aplicar"}

    campos = ", ".join(f"{campo} = %s" for campo in cambios.keys())
    valores = list(cambios.values()) + [id_cliente]

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute(f"UPDATE Cliente SET {campos} WHERE id_cliente = %s", tuple(valores))
        conexion.commit()
        cursor.close()
        conexion.close()
    except mysql.connector.Error as e:
        raise HTTPException(status_code=503, detail=f"Base de datos no disponible: {e}")

    return {"mensaje": "Cliente actualizado correctamente"}


@app.get("/clientes/{id_cliente}/cuentas", tags=["Clientes"])
def obtener_cuentas_cliente(id_cliente: int, cliente=Depends(obtener_cliente_actual)):
    """Lista las cuentas de inversión asociadas a un cliente."""
    _validar_cliente_autorizado(id_cliente, cliente["id_cliente"])
    return consultar(
        "SELECT * FROM Cuenta_Inversion WHERE id_cliente = %s",
        (id_cliente,),
    )


@app.get("/clientes/{id_cliente}/portafolio", tags=["Clientes"])
def obtener_portafolio(id_cliente: int, cliente=Depends(obtener_cliente_actual)):
    """Muestra el portafolio consolidado del cliente con sus posiciones, 
    valor actual de mercado y P&L (ganancias/pérdidas no realizadas)."""
    _validar_cliente_autorizado(id_cliente, cliente["id_cliente"])
    posiciones = consultar(
        """SELECT p.id_cuenta, p.id_instrumento, i.ticker, i.nombre, p.cantidad,
                  p.precio_promedio_compra, p.fecha_primera_compra
           FROM Posicion p
           JOIN Cuenta_Inversion c ON c.id_cuenta = p.id_cuenta
           JOIN Instrumento_Financiero i ON i.id_instrumento = p.id_instrumento
           WHERE c.id_cliente = %s""",
        (id_cliente,),
    )

    for pos in posiciones:
        precio_actual, _fuente = obtener_ultimo_precio(pos["id_instrumento"])
        pos["precio_actual"] = precio_actual
        if precio_actual is not None:
            pos["ganancia_perdida"] = round(
                (precio_actual - float(pos["precio_promedio_compra"])) * pos["cantidad"], 2
            )
        else:
            pos["ganancia_perdida"] = None

    return posiciones


@app.get("/clientes/{id_cliente}/ordenes", tags=["Clientes"])
def obtener_ordenes_cliente(id_cliente: int, cliente=Depends(obtener_cliente_actual)):
    """Obtiene el historial de órdenes de un cliente ordenadas recientemente."""
    _validar_cliente_autorizado(id_cliente, cliente["id_cliente"])
    return consultar(
        """SELECT o.* FROM Orden o
           JOIN Cuenta_Inversion c ON c.id_cuenta = o.id_cuenta
           WHERE c.id_cliente = %s
           ORDER BY o.fecha_hora DESC""",
        (id_cliente,),
    )


@app.get("/clientes/{id_cliente}/perfil-real", tags=["Clientes"])
def perfil_real_cliente(id_cliente: int, cliente=Depends(obtener_cliente_actual)):
    """Devuelve una clasificación básica del perfil real del cliente a partir de su portafolio."""
    _validar_cliente_autorizado(id_cliente, cliente["id_cliente"])

    posiciones = consultar(
        """SELECT p.cantidad, p.precio_promedio_compra
           FROM Posicion p
           JOIN Cuenta_Inversion c ON c.id_cuenta = p.id_cuenta
           WHERE c.id_cliente = %s""",
        (id_cliente,),
    )

    cliente_db = consultar("SELECT perfil_riesgo FROM Cliente WHERE id_cliente = %s", (id_cliente,))
    perfil_declarado = cliente_db[0]["perfil_riesgo"] if cliente_db else None

    if not posiciones:
        perfil_real = "CONSERVADOR"
        detalle = "Sin posiciones abiertas"
    else:
        cantidad_posiciones = len(posiciones)
        perfil_real = "AGRESIVO" if cantidad_posiciones >= 3 else "MODERADO" if cantidad_posiciones >= 2 else "CONSERVADOR"
        detalle = f"{cantidad_posiciones} posiciones abiertas"

    return {
        "id_cliente": id_cliente,
        "perfil_declarado": perfil_declarado,
        "perfil_real": perfil_real,
        "detalle": detalle,
    }


# -----------------------------------------------------------------------------
# 4. Movimientos Financieros (Cuentas)
# -----------------------------------------------------------------------------

@app.post("/cuentas", status_code=201, tags=["Cuentas"])
def abrir_cuenta(nueva_cuenta: NuevaCuenta, cliente=Depends(obtener_cliente_actual)):
    """Abre una nueva cuenta de inversión para el cliente autenticado."""
    if nueva_cuenta.tipo_cuenta not in ("ORDINARIA", "RETIRO", "FIDUCIARIA"):
        raise HTTPException(status_code=400, detail="tipo_cuenta inválido")
    if nueva_cuenta.saldo_inicial < 0:
        raise HTTPException(status_code=400, detail="saldo_inicial no puede ser negativo")

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute(
            """INSERT INTO Cuenta_Inversion (id_cliente, tipo_cuenta, saldo_disponible, fecha_apertura, estado)
               VALUES (%s, %s, %s, %s, 'A')""",
            (cliente["id_cliente"], nueva_cuenta.tipo_cuenta, nueva_cuenta.saldo_inicial, datetime.now().date()),
        )
        id_cuenta = cursor.lastrowid
        conexion.commit()
        cursor.close()
        conexion.close()
    except mysql.connector.Error as e:
        raise HTTPException(status_code=503, detail=f"Base de datos no disponible: {e}")

    return {"mensaje": "Cuenta abierta correctamente", "id_cuenta": id_cuenta}


@app.get("/cuentas/{id_cuenta}/saldo", tags=["Cuentas"])
def consultar_saldo(id_cuenta: int, cliente=Depends(obtener_cliente_actual)):
    """Consulta el saldo disponible de una cuenta."""
    cuenta = _validar_cuenta_del_cliente(id_cuenta, cliente["id_cliente"])
    return {"id_cuenta": id_cuenta, "saldo_disponible": float(cuenta["saldo_disponible"])}

@app.post("/cuentas/{id_cuenta}/depositos", tags=["Cuentas"])
def depositar(id_cuenta: int, movimiento: MovimientoCuenta, cliente=Depends(obtener_cliente_actual)):
    """Deposita fondos en la cuenta de inversión especificada."""
    if movimiento.monto <= 0:
        raise HTTPException(status_code=400, detail="El monto a depositar debe ser mayor a 0")

    _validar_cuenta_del_cliente(id_cuenta, cliente["id_cliente"])

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE Cuenta_Inversion SET saldo_disponible = saldo_disponible + %s WHERE id_cuenta = %s",
            (movimiento.monto, id_cuenta),
        )
        conexion.commit()
        cursor.close()
        conexion.close()
    except mysql.connector.Error as e:
        raise HTTPException(status_code=503, detail=f"Base de datos no disponible: {e}")

    return {"mensaje": f"Depósito de {movimiento.monto} realizado en la cuenta #{id_cuenta}"}


@app.post("/cuentas/{id_cuenta}/retiros", tags=["Cuentas"])
def retirar(id_cuenta: int, movimiento: MovimientoCuenta, cliente=Depends(obtener_cliente_actual)):
    """Retira fondos de la cuenta de inversión previo chequeo de saldo disponible."""
    if movimiento.monto <= 0:
        raise HTTPException(status_code=400, detail="El monto a retirar debe ser mayor a 0")

    cuenta = _validar_cuenta_del_cliente(id_cuenta, cliente["id_cliente"])

    if float(cuenta["saldo_disponible"]) < movimiento.monto:
        raise HTTPException(status_code=400, detail="Saldo insuficiente para retirar ese monto")

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute(
            "UPDATE Cuenta_Inversion SET saldo_disponible = saldo_disponible - %s WHERE id_cuenta = %s",
            (movimiento.monto, id_cuenta),
        )
        conexion.commit()
        cursor.close()
        conexion.close()
    except mysql.connector.Error as e:
        raise HTTPException(status_code=503, detail=f"Base de datos no disponible: {e}")

    return {"mensaje": f"Retiro de {movimiento.monto} realizado de la cuenta #{id_cuenta}"}


@app.get("/cuentas/{id_cuenta}/ordenes", tags=["Cuentas"])
def obtener_ordenes_cuenta(id_cuenta: int, estado: Optional[str] = None, cliente=Depends(obtener_cliente_actual)):
    """Lista las órdenes asociadas a una cuenta, con filtro opcional por estado."""
    _validar_cuenta_del_cliente(id_cuenta, cliente["id_cliente"])

    if estado is not None:
        return consultar(
            "SELECT * FROM Orden WHERE id_cuenta = %s AND estado = %s ORDER BY fecha_hora DESC",
            (id_cuenta, estado),
        )

    return consultar(
        "SELECT * FROM Orden WHERE id_cuenta = %s ORDER BY fecha_hora DESC",
        (id_cuenta,),
    )


@app.get("/cuentas/{id_cuenta}/posiciones", tags=["Cuentas"])
def obtener_posiciones_cuenta(id_cuenta: int, cliente=Depends(obtener_cliente_actual)):
    """Lista las posiciones abiertas de una cuenta."""
    _validar_cuenta_del_cliente(id_cuenta, cliente["id_cliente"])
    return consultar(
        """SELECT p.*, i.ticker, i.nombre
           FROM Posicion p
           JOIN Instrumento_Financiero i ON i.id_instrumento = p.id_instrumento
           WHERE p.id_cuenta = %s""",
        (id_cuenta,),
    )


@app.get("/cuentas/{id_cuenta}/valor-portafolio", tags=["Cuentas"])
def valor_portafolio_cuenta(id_cuenta: int, cliente=Depends(obtener_cliente_actual)):
    """Calcula el valor de mercado del portafolio de una cuenta."""
    _validar_cuenta_del_cliente(id_cuenta, cliente["id_cliente"])

    posiciones = consultar(
        "SELECT id_instrumento, cantidad, precio_promedio_compra FROM Posicion WHERE id_cuenta = %s",
        (id_cuenta,),
    )

    total = 0.0
    for posicion in posiciones:
        precio_actual, _ = obtener_ultimo_precio(posicion["id_instrumento"])
        if precio_actual is not None:
            total += precio_actual * posicion["cantidad"]

    return {"id_cuenta": id_cuenta, "valor_portafolio": round(total, 2)}


@app.get("/cuentas/{id_cuenta}/rentabilidad", tags=["Cuentas"])
def rentabilidad_cuenta(id_cuenta: int, cliente=Depends(obtener_cliente_actual)):
    """Compara el precio promedio de compra con el precio actual para estimar la rentabilidad."""
    _validar_cuenta_del_cliente(id_cuenta, cliente["id_cliente"])

    posiciones = consultar(
        "SELECT id_instrumento, cantidad, precio_promedio_compra FROM Posicion WHERE id_cuenta = %s",
        (id_cuenta,),
    )

    pnl_total = 0.0
    for posicion in posiciones:
        precio_actual, _ = obtener_ultimo_precio(posicion["id_instrumento"])
        if precio_actual is not None:
            pnl_total += (precio_actual - float(posicion["precio_promedio_compra"])) * posicion["cantidad"]

    return {"id_cuenta": id_cuenta, "rentabilidad_total": round(pnl_total, 2)}


@app.get("/cuentas/{id_cuenta}/movimientos", tags=["Cuentas"])
def movimientos_cuenta(id_cuenta: int, cliente=Depends(obtener_cliente_actual)):
    """Devuelve el historial de movimientos de una cuenta."""
    _validar_cuenta_del_cliente(id_cuenta, cliente["id_cliente"])
    return consultar(
        "SELECT * FROM Bitacora_Movimiento_Cuenta WHERE id_cuenta = %s ORDER BY fecha_hora DESC",
        (id_cuenta,),
    )


# -----------------------------------------------------------------------------
# 5. Mercado e Instrumentos Financieros
# -----------------------------------------------------------------------------

@app.get("/instrumentos", tags=["Instrumentos"])
def listar_instrumentos():
    """Consulta el catálogo de instrumentos financieros habilitados para operar."""
    return consultar(
        """SELECT i.id_instrumento, i.ticker, i.nombre, e.razon_social,
                  c.nombre AS categoria
           FROM Instrumento_Financiero i
           JOIN Emisor e ON e.id_emisor = i.id_emisor
           JOIN Categoria_Instrumento c ON c.id_categoria = i.id_categoria"""
    )


@app.get("/instrumentos/{id_instrumento}", tags=["Instrumentos"])
def obtener_instrumento(id_instrumento: int):
    """Devuelve el detalle de un instrumento financiero por su identificador."""
    resultado = consultar(
        """SELECT i.*, e.razon_social, c.nombre AS categoria
           FROM Instrumento_Financiero i
           JOIN Emisor e ON e.id_emisor = i.id_emisor
           JOIN Categoria_Instrumento c ON c.id_categoria = i.id_categoria
           WHERE i.id_instrumento = %s""",
        (id_instrumento,),
    )
    if not resultado:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado")
    return resultado[0]


@app.get("/instrumentos/{id_instrumento}/cotizaciones", tags=["Instrumentos"])
def cotizaciones_instrumento(id_instrumento: int, desde: Optional[date] = None, hasta: Optional[date] = None):
    """Retorna el histórico de cotizaciones de un instrumento con filtros opcionales por fecha."""
    resultado = consultar("SELECT id_instrumento FROM Instrumento_Financiero WHERE id_instrumento = %s", (id_instrumento,))
    if not resultado:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado")

    query = "SELECT * FROM Cotizacion_Historica WHERE id_instrumento = %s"
    params: list = [id_instrumento]
    if desde is not None:
        query += " AND fecha >= %s"
        params.append(desde)
    if hasta is not None:
        query += " AND fecha <= %s"
        params.append(hasta)
    query += " ORDER BY fecha DESC"

    return consultar(query, tuple(params))


@app.get("/instrumentos/{id_instrumento}/precios-vivo", tags=["Instrumentos"])
def precios_vivo_instrumento(id_instrumento: int, minutos: int = 60):
    """Retorna los ticks de precio en tiempo real de los últimos N minutos
    (por defecto 60), para armar gráficas de corto plazo (velas intradía)."""
    resultado = consultar(
        "SELECT id_instrumento FROM Instrumento_Financiero WHERE id_instrumento = %s",
        (id_instrumento,),
    )
    if not resultado:
        raise HTTPException(status_code=404, detail="Instrumento no encontrado")

    return consultar(
        """SELECT fecha_hora, precio_actual, volumen_tick
           FROM Precio_Tiempo_Real
           WHERE id_instrumento = %s
             AND fecha_hora >= NOW() - INTERVAL %s MINUTE
           ORDER BY fecha_hora ASC""",
        (id_instrumento, minutos),
    )


@app.get("/instrumentos/{ticker}/precio-actual", tags=["Instrumentos"])
def precio_actual(ticker: str):
    """Consulta el precio actual de cotización para un ticker en específico."""
    instrumento = consultar(
        "SELECT id_instrumento FROM Instrumento_Financiero WHERE ticker = %s", (ticker,)
    )
    if not instrumento:
        raise HTTPException(status_code=404, detail="Ticker no encontrado")

    precio, fuente = obtener_ultimo_precio(instrumento[0]["id_instrumento"])
    if precio is None:
        raise HTTPException(status_code=404, detail="Sin datos de precio para este instrumento")

    return {
        "ticker": ticker,
        "precio": precio,
        "mercado_abierto": mercado_esta_abierto(),
        "fuente": "precio en vivo" if fuente == "vivo" else "cierre histórico",
    }


@app.get("/instrumentos/{ticker}/historico", tags=["Instrumentos"])
def historico_instrumento(ticker: str, dias: int = 30):
    """Retorna la serie de tiempo histórica de cotizaciones para un ticker."""
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


# -----------------------------------------------------------------------------
# 6. Operaciones y Órdenes
# -----------------------------------------------------------------------------

@app.post("/ordenes", status_code=201, tags=["Órdenes"])
def colocar_orden(orden: NuevaOrden):
    """Envía una nueva orden de mercado (COMPRA o VENTA) quedando en estado PENDIENTE."""
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


@app.get("/ordenes/{id_orden}", tags=["Órdenes"])
def obtener_orden(id_orden: int):
    """Consulta la información detallada de una orden y sus ejecuciones."""
    resultado = consultar("SELECT * FROM Orden WHERE id_orden = %s", (id_orden,))
    if not resultado:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    orden = resultado[0]
    orden["transacciones"] = consultar(
        "SELECT * FROM Transaccion_Ejecutada WHERE id_orden = %s", (id_orden,)
    )
    return orden


@app.delete("/ordenes/{id_orden}", tags=["Órdenes"])
def cancelar_orden(id_orden: int):
    """Cancela una orden activa únicamente si su estado actual es PENDIENTE."""
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