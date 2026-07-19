"""
Streaming en vivo para BrokerHub.

Se conecta al WebSocket de Finnhub, se suscribe a los tickers que ya
existen en Instrumento_Financiero, y cada trade que llega se inserta
en Precio_Tiempo_Real.

Pensado para dejarlo corriendo durante la demo. Maneja:
- Reconexión del WebSocket si Finnhub lo cierra.
- Reconexión de MySQL si Railway corta la conexión por inactividad.
- Inserts en lotes pequeños (cada N segundos) en vez de uno por trade,
  para no abrir/cerrar la conexión a MySQL constantemente.
"""

import os
import json
import time
import threading
import websocket
from dotenv import load_dotenv
from conexion_db import obtener_conexion, reconectar_forzado
import mysql.connector

load_dotenv()
API_KEY = os.getenv("FINNHUB_API_KEY")
WS_URL = f"wss://ws.finnhub.io?token={API_KEY}"

INTERVALO_ESCRITURA_SEGUNDOS = 5  # cada cuánto se vacía el buffer a MySQL

# Buffer en memoria: aquí se acumulan los trades antes de escribirlos en lote
buffer_trades = []
buffer_lock = threading.Lock()

# Cache ticker -> id_instrumento (se carga una sola vez al inicio)
id_instrumento_por_ticker = {}


# ------------------------------------------------------------------
# Cargar el mapeo ticker -> id_instrumento (una sola vez)
# ------------------------------------------------------------------

def cargar_tickers():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id_instrumento, ticker FROM Instrumento_Financiero")
    for id_instrumento, ticker in cursor.fetchall():
        id_instrumento_por_ticker[ticker] = id_instrumento
    cursor.close()
    conexion.close()
    print(f"Tickers cargados para streaming: {list(id_instrumento_por_ticker.keys())}")


# ------------------------------------------------------------------
# Hilo que cada N segundos vacía el buffer hacia MySQL
# ------------------------------------------------------------------

def escritor_periodico():
    while True:
        time.sleep(INTERVALO_ESCRITURA_SEGUNDOS)

        with buffer_lock:
            if not buffer_trades:
                continue
            trades_a_escribir = buffer_trades.copy()
            buffer_trades.clear()

        for intento in range(1, 4):
            try:
                conexion = obtener_conexion()
                cursor = conexion.cursor()
                cursor.executemany(
                    """INSERT INTO Precio_Tiempo_Real (id_instrumento, precio_actual, volumen_tick, fecha_hora)
                       VALUES (%s, %s, %s, %s)""",
                    trades_a_escribir,
                )
                conexion.commit()
                cursor.close()
                conexion.close()
                print(f"[DB] {len(trades_a_escribir)} trades guardados en Precio_Tiempo_Real")
                break
            except (mysql.connector.errors.InterfaceError, mysql.connector.errors.OperationalError) as e:
                print(f"[RECONEXIÓN] Falló guardar lote (intento {intento}/3): {e}")
                time.sleep(2)
        else:
            print(f"[ABANDONADO] Se perdieron {len(trades_a_escribir)} trades tras 3 intentos.")


# ------------------------------------------------------------------
# Callbacks del WebSocket
# ------------------------------------------------------------------

def on_message(ws, mensaje):
    datos = json.loads(mensaje)
    if datos.get("type") != "trade":
        return  # ignora mensajes que no son trades (ej. "ping")

    for trade in datos.get("data", []):
        ticker = trade.get("s")
        precio = trade.get("p")
        volumen = trade.get("v")
        timestamp_ms = trade.get("t")

        id_instrumento = id_instrumento_por_ticker.get(ticker)
        if id_instrumento is None:
            continue  # llegó un ticker que no está en nuestra base

        fecha_hora = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_ms / 1000))

        with buffer_lock:
            buffer_trades.append((id_instrumento, precio, volumen, fecha_hora))

        print(f"[TRADE] {ticker}: ${precio} (vol {volumen})")


def on_error(ws, error):
    print(f"[WS ERROR] {error}")


def on_close(ws, close_status_code, close_msg):
    print(f"[WS CERRADO] código={close_status_code}, motivo={close_msg}")


def on_open(ws):
    print("[WS ABIERTO] Suscribiendo tickers...")
    for ticker in id_instrumento_por_ticker.keys():
        ws.send(json.dumps({"type": "subscribe", "symbol": ticker}))
        time.sleep(0.2)  # pequeña pausa para no saturar la suscripción


# ------------------------------------------------------------------
# Loop principal con reconexión del WebSocket
# ------------------------------------------------------------------

def iniciar_streaming():
    while True:
        try:
            ws = websocket.WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            print(f"[WS] Excepción inesperada: {e}")

        print("[WS] Conexión perdida, reintentando en 5 segundos...")
        time.sleep(5)


def main():
    cargar_tickers()
    if not id_instrumento_por_ticker:
        print("No hay tickers en Instrumento_Financiero. Corre primero carga_inicial.py")
        return

    hilo_escritor = threading.Thread(target=escritor_periodico, daemon=True)
    hilo_escritor.start()

    print("Iniciando streaming en vivo... (Ctrl+C para detener)")
    iniciar_streaming()


if __name__ == "__main__":
    main()