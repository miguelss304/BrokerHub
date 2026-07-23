"""
Carga inicial de BrokerHub.

Puebla, con datos reales:
- Mercado_Bolsa (NYSE, NASDAQ)
- Emisor
- Categoria_Instrumento (árbol de 3 niveles: Acciones -> Sector -> Perfil de riesgo)
- Instrumento_Financiero
- Listado_Mercado
- Cotizacion_Historica

Se puede correr más de una vez sin duplicar datos (usa "buscar o crear").
"""

from conexion_db import obtener_conexion, asegurar_conexion, reconectar_forzado
import mysql.connector
from cliente_finnhub import (
    obtener_perfil_empresa,
    obtener_historico,
    clasificar_por_capitalizacion,
)

# ------------------------------------------------------------------
# Lista de tickers del proyecto
# ------------------------------------------------------------------
TICKERS = [
    "MSI", "ETN", "CAH", "AZO", "AAPL",
    "DUOL", "AXON", "NET", "IOT", "GTLB",
    "EXTR", "ASTH", "BOOT", "CRCT", "INOD"
]

MERCADOS = [
    {"nombre": "NYSE", "pais": "Estados Unidos", "zona_horaria": "America/New_York"},
    {"nombre": "NASDAQ", "pais": "Estados Unidos", "zona_horaria": "America/New_York"},
]


# ------------------------------------------------------------------
# Funciones "buscar o crear" (evitan duplicados si se corre 2 veces)
# ------------------------------------------------------------------

def obtener_o_crear_mercado(cursor, nombre, pais, zona_horaria):
    cursor.execute("SELECT id_mercado FROM Mercado_Bolsa WHERE nombre = %s", (nombre,))
    fila = cursor.fetchone()
    if fila:
        return fila[0]
    cursor.execute(
        "INSERT INTO Mercado_Bolsa (nombre, pais, zona_horaria) VALUES (%s, %s, %s)",
        (nombre, pais, zona_horaria),
    )
    return cursor.lastrowid


def obtener_o_crear_emisor(cursor, razon_social, sector, pais):
    cursor.execute("SELECT id_emisor FROM Emisor WHERE razon_social = %s", (razon_social,))
    fila = cursor.fetchone()
    if fila:
        return fila[0]
    cursor.execute(
        "INSERT INTO Emisor (razon_social, sector_economico, pais_origen) VALUES (%s, %s, %s)",
        (razon_social, sector, pais),
    )
    return cursor.lastrowid


def obtener_o_crear_categoria(cursor, nombre, nivel_riesgo, id_categoria_padre=None):
    cursor.execute("SELECT id_categoria FROM Categoria_Instrumento WHERE nombre = %s", (nombre,))
    fila = cursor.fetchone()
    if fila:
        return fila[0]
    cursor.execute(
        "INSERT INTO Categoria_Instrumento (nombre, nivel_riesgo, id_categoria_padre) VALUES (%s, %s, %s)",
        (nombre, nivel_riesgo, id_categoria_padre),
    )
    return cursor.lastrowid


def obtener_o_crear_instrumento(cursor, ticker, nombre, id_emisor, id_categoria, fecha_listado):
    cursor.execute("SELECT id_instrumento FROM Instrumento_Financiero WHERE ticker = %s", (ticker,))
    fila = cursor.fetchone()
    if fila:
        return fila[0]
    cursor.execute(
        """INSERT INTO Instrumento_Financiero
           (ticker, nombre, tipo, id_emisor, id_categoria, fecha_listado)
           VALUES (%s, %s, 'ACCION', %s, %s, %s)""",
        (ticker, nombre, id_emisor, id_categoria, fecha_listado),
    )
    return cursor.lastrowid


def insertar_listado_mercado(cursor, id_instrumento, id_mercado, ticker_local, moneda, fecha_listado):
    cursor.execute(
        "SELECT 1 FROM Listado_Mercado WHERE id_instrumento = %s AND id_mercado = %s",
        (id_instrumento, id_mercado),
    )
    if cursor.fetchone():
        return
    cursor.execute(
        """INSERT INTO Listado_Mercado (id_instrumento, id_mercado, ticker_local, moneda, fecha_listado)
           VALUES (%s, %s, %s, %s, %s)""",
        (id_instrumento, id_mercado, ticker_local, moneda, fecha_listado),
    )


def ya_tiene_historico(cursor, id_instrumento):
    cursor.execute(
        "SELECT COUNT(*) FROM Cotizacion_Historica WHERE id_instrumento = %s",
        (id_instrumento,),
    )
    return cursor.fetchone()[0] > 0


def insertar_cotizaciones(cursor, id_instrumento, filas_historico):
    datos = [
        (
            id_instrumento,
            fila["fecha"],
            fila["precio_apertura"],
            fila["precio_cierre"],
            fila["precio_maximo"],
            fila["precio_minimo"],
            fila["volumen"],
        )
        for fila in filas_historico
    ]
    cursor.executemany(
        """INSERT IGNORE INTO Cotizacion_Historica
           (id_instrumento, fecha, precio_apertura, precio_cierre, precio_maximo, precio_minimo, volumen)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        datos,
    )


# ------------------------------------------------------------------
# Proceso principal
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# Procesamiento de un solo ticker (se puede reintentar completo si falla)
# ------------------------------------------------------------------

def procesar_ticker(conexion, ticker, ids_mercado, id_raiz):
    """Procesa un ticker de principio a fin. Devuelve la conexión usada
    (puede ser una nueva, si hubo que reconectar) y no relanza errores
    de red -- esos los maneja quien la llama, reintentando."""
    cursor = conexion.cursor()

    try:
        perfil = obtener_perfil_empresa(ticker)
    except Exception as e:
        print(f"  [ERROR] No se pudo traer perfil de {ticker}: {e}")
        return conexion, True  # no es error de conexión, no reintentar

    razon_social = perfil.get("name") or ticker
    sector = perfil.get("finnhubIndustry") or "Sin clasificar"
    pais = perfil.get("country") or "US"
    market_cap = perfil.get("marketCapitalization")
    fecha_ipo = perfil.get("ipo") or "2000-01-01"

    # 3-7. Emisor, categorías, instrumento, listado_mercado
    id_emisor = obtener_o_crear_emisor(cursor, razon_social, sector, pais)
    id_sector = obtener_o_crear_categoria(cursor, sector, "MEDIO", id_raiz)

    nombre_nivel3 = f"{sector} - {clasificar_por_capitalizacion(market_cap)}"
    nivel_riesgo_map = {"Blue Chip": "BAJO", "Growth": "MEDIO", "Small Cap": "ALTO"}
    etiqueta = clasificar_por_capitalizacion(market_cap)
    id_categoria_final = obtener_o_crear_categoria(
        cursor, nombre_nivel3, nivel_riesgo_map[etiqueta], id_sector
    )

    id_instrumento = obtener_o_crear_instrumento(
        cursor, ticker, razon_social, id_emisor, id_categoria_final, fecha_ipo
    )

    mercado_asignado = "NASDAQ" if sector == "Technology" else "NYSE"
    insertar_listado_mercado(
        cursor, id_instrumento, ids_mercado[mercado_asignado], ticker, "USD", fecha_ipo,
    )

    conexion.commit()
    print(f"  Emisor, categoría e instrumento listos (id_instrumento={id_instrumento})")

    # 8. Histórico de precios (yfinance) - se salta si ya está cargado
    if ya_tiene_historico(cursor, id_instrumento):
        print(f"  Histórico ya existente para {ticker}, se omite.")
        return conexion, True

    try:
        historico = obtener_historico(ticker, periodo="6mo")
    except Exception as e:
        print(f"  [ERROR] No se pudo traer histórico de {ticker} (yfinance): {e}")
        return conexion, True  # no es error de conexión a MySQL, no reintentar

    cursor = conexion.cursor()  # refresca el cursor por si yfinance tardó mucho
    insertar_cotizaciones(cursor, id_instrumento, historico)
    conexion.commit()
    print(f"  {len(historico)} registros de Cotizacion_Historica insertados")

    return conexion, True


def procesar_ticker_con_reintento(conexion, ticker, ids_mercado, id_raiz, max_intentos=3):
    """Envuelve procesar_ticker con reintento: si falla por conexión perdida,
    reconecta desde cero y vuelve a intentar el ticker completo."""
    for intento in range(1, max_intentos + 1):
        try:
            conexion, _ = procesar_ticker(conexion, ticker, ids_mercado, id_raiz)
            return conexion  # éxito
        except mysql.connector.errors.InterfaceError as e:
            print(f"  [RECONEXIÓN] Se perdió la conexión procesando {ticker} "
                  f"(intento {intento}/{max_intentos}): {e}")
            conexion = reconectar_forzado(conexion)
        except mysql.connector.Error as e:
            print(f"  [ERROR DB] Falló guardando datos de {ticker}: {e}")
            return conexion  # error real de datos, no tiene sentido reintentar
    print(f"  [ABANDONADO] {ticker} falló {max_intentos} veces por conexión, se omite.")
    return conexion


# ------------------------------------------------------------------
# Proceso principal
# ------------------------------------------------------------------

def main():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    # 1. Mercados (NYSE, NASDAQ) - una sola vez
    ids_mercado = {}
    for m in MERCADOS:
        ids_mercado[m["nombre"]] = obtener_o_crear_mercado(
            cursor, m["nombre"], m["pais"], m["zona_horaria"]
        )
    conexion.commit()

    # 2. Categoría raíz (nivel 1)
    id_raiz = obtener_o_crear_categoria(cursor, "Acciones", "MEDIO", None)
    conexion.commit()

    for ticker in TICKERS:
        print(f"\nProcesando {ticker}...")
        conexion = asegurar_conexion(conexion)
        conexion = procesar_ticker_con_reintento(conexion, ticker, ids_mercado, id_raiz)

    conexion.close()
    print("\nCarga inicial completa.")


if __name__ == "__main__":
    main()