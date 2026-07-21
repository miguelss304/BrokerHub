import pandas as pd
from cliente_finnhub import obtener_historico
import plotly.graph_objects as go
import streamlit as st

# Configuración de la página (estilo ancho por defecto)
st.set_page_config(layout="wide")
st.title("📊 Visor de Gráficas de Velas")

# 1. Buscador con tu lista específica de tickers en la barra lateral
lista_tickers = [
    "AAPL", "MSFT", "NVDA", "GOOGL",
    "XOM", "CVX",
    "JPM", "BAC",
    "JNJ", "PFE",
    "KO", "WMT"
]

ticker_seleccionado = st.sidebar.selectbox("Selecciona un Ticker:", lista_tickers)

# 2. Llamada a tu función original usando el ticker dinámico
datos_en_lista = obtener_historico(ticker_seleccionado, periodo="1y")

# 3. Función puente integrada para transformar y graficar si hay datos
if datos_en_lista:
    df_listo = pd.DataFrame(datos_en_lista)
    
    # Construcción del gráfico de velas
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df_listo["fecha"],
                open=df_listo["precio_apertura"],
                high=df_listo["precio_maximo"],
                low=df_listo["precio_minimo"],
                close=df_listo["precio_cierre"],
                name=ticker_seleccionado
            )
        ]
    )

    # Ajustes estéticos de trading en modo oscuro
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        xaxis_title="Fecha",
        yaxis_title="Precio (USD)",
        margin=dict(l=20, r=20, t=40, b=20)
    )

    # Dibujar la gráfica usando la nueva sintaxis 'stretch'
    st.plotly_chart(fig, width="stretch")
else:
    st.warning(f"No se encontraron datos disponibles para el ticker {ticker_seleccionado}.")
