import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from cliente_finnhub import obtener_historico

# Intentar importar la lista de tickers desde carga_inicial
try:
    from carga_inicial import TICKERS
except ImportError:
    # Lista de respaldo por si el archivo no existe
    TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA"]

# Configuración de la página
st.set_page_config(layout="wide")
st.title("📊 Visor de Gráficas de Velas")

# Selector de ticker en la barra lateral
ticker_seleccionado = st.sidebar.selectbox("Selecciona un Ticker:", TICKERS)

# Cargar datos históricos (1 año)
with st.spinner(f"Cargando datos de {ticker_seleccionado}..."):
    try:
        datos = obtener_historico(ticker_seleccionado, periodo="1y")
    except Exception as e:
        st.error(f"Error al obtener datos: {e}")
        st.stop()

if not datos:
    st.warning(f"No se encontraron datos para {ticker_seleccionado}.")
    st.stop()

# Convertir a DataFrame (ya tiene las columnas correctas)
df = pd.DataFrame(datos)

# Verificar que las columnas esperadas existan
columnas_requeridas = ["fecha", "precio_apertura", "precio_cierre", "precio_maximo", "precio_minimo"]
if not all(col in df.columns for col in columnas_requeridas):
    st.error("Los datos recibidos no tienen el formato esperado.")
    st.stop()

# Construir gráfico de velas
fig = go.Figure(
    data=[
        go.Candlestick(
            x=df["fecha"],
            open=df["precio_apertura"],
            high=df["precio_maximo"],
            low=df["precio_minimo"],
            close=df["precio_cierre"],
            name=ticker_seleccionado,
        )
    ]
)

# Ajustes estéticos (modo oscuro, sin slider de rango)
fig.update_layout(
    xaxis_rangeslider_visible=False,
    template="plotly_dark",
    xaxis_title="Fecha",
    yaxis_title="Precio (USD)",
    margin=dict(l=20, r=20, t=40, b=20),
)

# Mostrar gráfica ocupando todo el ancho
st.plotly_chart(fig, use_container_width=True)

# Mostrar estadísticas rápidas
with st.expander("📈 Estadísticas del período"):
    col1, col2, col3 = st.columns(3)
    col1.metric("Máximo", f"${df['precio_maximo'].max():.2f}")
    col2.metric("Mínimo", f"${df['precio_minimo'].min():.2f}")
    col3.metric("Cierre más reciente", f"${df['precio_cierre'].iloc[-1]:.2f}")