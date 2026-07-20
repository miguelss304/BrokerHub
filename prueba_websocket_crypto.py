"""
Prueba aislada del WebSocket de Finnhub usando BTCUSDT (cripto, opera 24/7).
Sirve solo para confirmar que la conexión y la suscripción funcionan,
sin depender del horario de mercado de acciones.
"""

import os
import json
import websocket
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("FINNHUB_API_KEY")
WS_URL = f"wss://ws.finnhub.io?token={API_KEY}"


def on_message(ws, mensaje):
    print("Mensaje recibido:", mensaje)


def on_error(ws, error):
    print("Error:", error)


def on_close(ws, code, msg):
    print("Cerrado:", code, msg)


def on_open(ws):
    print("Conectado. Suscribiendo a BINANCE:BTCUSDT...")
    ws.send(json.dumps({"type": "subscribe", "symbol": "BINANCE:BTCUSDT"}))


if __name__ == "__main__":
    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever()