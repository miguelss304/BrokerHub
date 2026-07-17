"""
Cliente para traer datos del proyecto BrokerHub.

- Finnhub (REST): perfil de empresa (Emisor) y precio actual.
- Finnhub (WebSocket, en otro script aparte): streaming en vivo -> Precio_Tiempo_Real.
- yfinance: histórico diario OHLCV -> Cotizacion_Historica
  (el endpoint /stock/candle de Finnhub dejó de ser gratuito, por eso
  el histórico se resuelve con yfinance en vez de Finnhub).
"""

import os
import requests
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("FINNHUB_API_KEY")
BASE_URL = "https://finnhub.io/api/v1"


# ------------------------------------------------------------------
# FINNHUB - datos de empresa y precio actual (gratis)
# ------------------------------------------------------------------

def obtener_perfil_empresa(ticker):
    """Trae nombre, sector, país y capitalización de mercado de una empresa.
    Sirve para poblar Emisor e Instrumento_Financiero.
    """
    url = f"{BASE_URL}/stock/profile2"
    params = {"symbol": ticker, "token": API_KEY}
    respuesta = requests.get(url, params=params)
    respuesta.raise_for_status()
    return respuesta.json()


def obtener_precio_actual(ticker):
    """Trae la cotización actual (precio, máximo, mínimo, apertura)."""
    url = f"{BASE_URL}/quote"
    params = {"symbol": ticker, "token": API_KEY}
    respuesta = requests.get(url, params=params)
    respuesta.raise_for_status()
    return respuesta.json()


# ------------------------------------------------------------------
# YFINANCE - histórico diario (reemplaza al candle endpoint de Finnhub)
# ------------------------------------------------------------------

def obtener_historico(ticker, periodo="1y"):
    """Trae histórico diario OHLCV usando yfinance.
    periodo: '1mo', '3mo', '6mo', '1y', '2y', 'max', etc.
    Devuelve una lista de diccionarios, uno por día, lista para insertar
    en Cotizacion_Historica.
    """
    accion = yf.Ticker(ticker)
    df = accion.history(period=periodo)

    filas = []
    for fecha, row in df.iterrows():
        filas.append({
            "fecha": fecha.strftime("%Y-%m-%d"),
            "precio_apertura": round(row["Open"], 4),
            "precio_cierre": round(row["Close"], 4),
            "precio_maximo": round(row["High"], 4),
            "precio_minimo": round(row["Low"], 4),
            "volumen": int(row["Volume"]),
        })
    return filas


# ------------------------------------------------------------------
# Regla de clasificación por capitalización (nivel 3 de Categoria_Instrumento)
# ------------------------------------------------------------------

def clasificar_por_capitalizacion(market_cap_millones):
    """market_cap_millones viene del campo 'marketCapitalization' de Finnhub
    (ya reportado en millones de USD). Devuelve Blue Chip / Growth / Small Cap.
    """
    if market_cap_millones is None:
        return "Growth"  # valor por defecto razonable si falta el dato
    if market_cap_millones > 200_000:      # > $200B
        return "Blue Chip"
    elif market_cap_millones >= 10_000:    # entre $10B y $200B
        return "Growth"
    else:                                   # < $10B
        return "Small Cap"


# ------------------------------------------------------------------
# Prueba rápida al correr este archivo directamente
# ------------------------------------------------------------------

if __name__ == "__main__":
    ticker = "AAPL"

    perfil = obtener_perfil_empresa(ticker)
    print("Perfil de empresa:", perfil)

    precio = obtener_precio_actual(ticker)
    print("Precio actual:", precio)

    categoria = clasificar_por_capitalizacion(perfil.get("marketCapitalization"))
    print("Categoría por capitalización:", categoria)

    historico = obtener_historico(ticker, periodo="1mo")
    print(f"Histórico ({len(historico)} días), primeros 3 registros:")
    for fila in historico[:3]:
        print(fila)