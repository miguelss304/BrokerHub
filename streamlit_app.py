import os
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(layout="wide", page_title="BrokerHub", initial_sidebar_state="collapsed")

try:
    from carga_inicial import TICKERS
except ImportError:
    TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA"]

API_BASE_URL = os.getenv("BROKERHUB_API_URL") or "https://brokerhub-api-production.up.railway.app"
API_BASE_URL = API_BASE_URL.rstrip("/")

st.caption(f"🔧 DEBUG: conectando a `{API_BASE_URL}`")

# ============================================================================
# FUNCIONES GLOBALES
# ============================================================================

def api_request(path: str, method: str = "get", token: str | None = None, json_body: dict | None = None, params: dict | None = None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.request(
            method.upper(),
            f"{API_BASE_URL}{path}",
            headers=headers,
            json=json_body,
            params=params,
            timeout=30,  # la BD está en Railway (remota), la API local necesita más margen
            proxies={"http": None, "https": None},  # ignora proxy del sistema para localhost
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise Exception(f"{response.status_code}: {detail}")
        try:
            return response.json()
        except Exception:
            return {}
    except requests.exceptions.RequestException as exc:
        raise Exception(f"No se pudo conectar con la API en {API_BASE_URL}. Detalle: {type(exc).__name__}: {exc}")

def init_session_state():
    """Inicializa session state si no existe."""
    if "token" not in st.session_state:
        st.session_state.token = None
    if "cliente_id" not in st.session_state:
        st.session_state.cliente_id = None
    if "account_id" not in st.session_state:
        st.session_state.account_id = None
    if "usuario" not in st.session_state:
        st.session_state.usuario = None
    if "page" not in st.session_state:
        st.session_state.page = "Onboarding"

init_session_state()


# ============================================================================
# NAVEGACIÓN - BOTONES ESTÉTICOS
# ============================================================================

st.markdown("# 🏦 BrokerHub")
st.caption("🔧 VERSION_DEBUG: v3-numeric-fix")

token = st.session_state.token
cliente_id = st.session_state.cliente_id

# Barra de navegación
col_nav = st.columns(8)
botones = ["Onboarding", "Dashboard", "Mercado", "Trading", "Portafolio", "Movimientos", "Notificaciones", "Admin"]

for i, boton in enumerate(botones):
    with col_nav[i]:
        if st.button(boton, use_container_width=True, type="secondary"):
            st.session_state.page = boton
            st.rerun()

st.divider()

# ============================================================================
# AUTENTICACIÓN (SIDEBAR MÍNIMO)
# ============================================================================

auth_col1, auth_col2 = st.columns([3, 1])

with auth_col1:
    if token:
        st.success(f"✅ Sesión activa ({st.session_state.usuario})")
    else:
        st.info("❌ No autenticado")

with auth_col2:
    if token and st.button("Cerrar sesión", type="primary"):
        st.session_state.clear()
        st.rerun()

# ============================================================================
# MODAL DE AUTENTICACIÓN
# ============================================================================

if not token:
    st.markdown("### Autenticación")
    
    tab_login, tab_registro = st.tabs(["Iniciar sesión", "Registrarse"])
    
    with tab_login:
        with st.form("login_form"):
            usuario = st.text_input("Usuario")
            contrasena = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Iniciar sesión", use_container_width=True)
            if submitted:
                try:
                    data = api_request(
                        "/auth/login",
                        method="post",
                        json_body={"usuario": usuario, "contrasena": contrasena},
                    )
                    st.session_state["token"] = data.get("token")
                    st.session_state["cliente_id"] = data.get("id_cliente")
                    st.session_state["usuario"] = data.get("usuario")
                    st.success("Inicio de sesión correcto")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
    
    with tab_registro:
        with st.form("registro_form"):
            nombre = st.text_input("Nombre completo")
            documento = st.text_input("Documento de identidad")
            correo = st.text_input("Correo")
            usuario_reg = st.text_input("Nuevo usuario")
            perfil = st.selectbox("Perfil de riesgo", ["CONSERVADOR", "MODERADO", "AGRESIVO"])
            password_reg = st.text_input("Contraseña", type="password")
            submitted_reg = st.form_submit_button("Registrar", use_container_width=True)
            if submitted_reg:
                try:
                    data = api_request(
                        "/auth/registro",
                        method="post",
                        json_body={
                            "nombre_completo": nombre,
                            "tipo_cliente": "N",
                            "documento_identidad": documento,
                            "correo": correo,
                            "perfil_riesgo": perfil,
                            "usuario": usuario_reg,
                            "contrasena": password_reg,
                        },
                    )
                    st.session_state["token"] = data.get("token")
                    st.session_state["cliente_id"] = data.get("id_cliente")
                    st.session_state["usuario"] = usuario_reg
                    st.success("Registro correcto")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
    
    st.stop()

# ============================================================================
# CARGA DE DATOS DE CUENTA (CACHEO)
# ============================================================================

@st.cache_data(ttl=60)
def get_account_data(cliente_id, token):
    """Obtiene datos de la cuenta del cliente (cacheado por 60 segundos)."""
    try:
        cuentas = api_request(f"/clientes/{cliente_id}/cuentas", token=token)
        if isinstance(cuentas, list) and cuentas:
            return cuentas[0]["id_cuenta"]
    except Exception:
        pass
    return None

if not st.session_state.account_id:
    account_id = get_account_data(cliente_id, token)
    if account_id:
        st.session_state.account_id = account_id

account_id = st.session_state.get("account_id")

# ============================================================================
# PÁGINAS
# ============================================================================

page = st.session_state.page

if page == "Onboarding":
    st.header("Onboarding")
    st.info("✅ Ya tienes una sesión activa. Elige un módulo arriba para empezar.")

elif page == "Dashboard":
    st.header("Dashboard")
    
    if not account_id:
        st.warning("No se pudo cargar la cuenta. Intenta recargar la página.")
        st.stop()
    
    col1, col2, col3 = st.columns(3)
    
    try:
        saldo = api_request(f"/cuentas/{account_id}/saldo", token=token)
        col1.metric("💰 Saldo disponible", f"${saldo.get('saldo_disponible', 0):.2f}")
    except Exception as exc:
        col1.error("Error al cargar saldo")
    
    try:
        valor = api_request(f"/cuentas/{account_id}/valor-portafolio", token=token)
        col2.metric("📊 Valor de portafolio", f"${valor.get('valor_portafolio', 0):.2f}")
    except Exception as exc:
        col2.error("Error al cargar portafolio")
    
    try:
        rentabilidad = api_request(f"/cuentas/{account_id}/rentabilidad", token=token)
        col3.metric("📈 Rentabilidad total", f"{rentabilidad.get('rentabilidad_total', 0):.2f}%")
    except Exception as exc:
        col3.error("Error al cargar rentabilidad")
    
    st.subheader("Posiciones abiertas")
    try:
        posiciones = api_request(f"/cuentas/{account_id}/posiciones", token=token)
        if posiciones:
            df_pos = pd.DataFrame(posiciones)
            st.dataframe(df_pos, use_container_width=True)
        else:
            st.info("No hay posiciones abiertas")
    except Exception as exc:
        st.error(str(exc))

elif page == "Mercado":
    st.header("Mercado - Gráficas")

    try:
        instrumentos = api_request("/instrumentos")
    except Exception as exc:
        st.error(f"No se pudo cargar instrumentos: {exc}")
        st.stop()

    if not instrumentos:
        st.warning("No hay instrumentos disponibles")
        st.stop()

    df_inst = pd.DataFrame(instrumentos)
    opciones = [f"{row['ticker']} - {row['nombre']}" for _, row in df_inst[["ticker", "nombre"]].iterrows()]

    col1, col2 = st.columns([3, 1])

    with col1:
        seleccion = st.selectbox("Selecciona un instrumento", opciones)

    with col2:
        if st.button("Actualizar gráficas"):
            st.cache_data.clear()
            st.rerun()

    ticker = seleccion.split(" - ")[0]
    instrumento = df_inst[df_inst["ticker"] == ticker].iloc[0]
    instrument_id = instrumento["id_instrumento"]

    # ------------------------------------------------------------------
    # Gráfica histórica: serie de línea, rango extenso (precio de cierre)
    # ------------------------------------------------------------------
    st.subheader("📈 Histórico (línea)")
    try:
        cotizaciones = api_request(f"/instrumentos/{instrument_id}/cotizaciones")

        st.caption(f"🔧 DEBUG: ticker={ticker} | id_instrumento={instrument_id} | filas recibidas={len(cotizaciones) if cotizaciones else 0}")

        if cotizaciones:
            df_hist = pd.DataFrame(cotizaciones)
            with st.expander("🔧 DEBUG: ver datos crudos"):
                st.dataframe(df_hist)
            df_hist["fecha"] = pd.to_datetime(df_hist["fecha"])
            df_hist["precio_cierre"] = pd.to_numeric(df_hist["precio_cierre"], errors="coerce")
            df_hist = df_hist.sort_values("fecha")

            st.caption(f"🔧 DEBUG: dtype precio_cierre={df_hist['precio_cierre'].dtype} | min={df_hist['precio_cierre'].min()} | max={df_hist['precio_cierre'].max()}")
            st.write("🔧 DEBUG primeros 5 valores:", df_hist["precio_cierre"].head().tolist())
            st.write("🔧 DEBUG últimos 5 valores:", df_hist["precio_cierre"].tail().tolist())

            import plotly.express as px
            fig_hist = px.line(
                df_hist,
                x="fecha",
                y="precio_cierre",
                title=None,
            )
            fig_hist.update_traces(line=dict(color="#4da6ff", width=2))
            fig_hist.update_layout(
                template="plotly_dark",
                xaxis_title="Fecha",
                yaxis_title="Precio de cierre",
                height=400,
                margin=dict(l=20, r=20, t=30, b=20),
            )
            st.plotly_chart(fig_hist, use_container_width=True, key="chart_historico_v2_express")
        else:
            st.info("No hay cotizaciones históricas cargadas para este instrumento todavía.")
    except Exception as exc:
        st.error(f"Error al cargar histórico: {exc}")

    # ------------------------------------------------------------------
    # Gráfica en vivo: velas, ventana corta (ticks de Precio_Tiempo_Real)
    # ------------------------------------------------------------------
    st.subheader("🕯️ En vivo (velas)")

    ventana_min = st.select_slider(
        "Ventana de tiempo",
        options=[15, 30, 60, 120, 240],
        value=60,
        format_func=lambda m: f"Últimos {m} min",
    )
    intervalo_vela = st.select_slider(
        "Tamaño de cada vela",
        options=["30s", "1min", "5min"],
        value="1min",
    )

    try:
        ticks = api_request(f"/instrumentos/{instrument_id}/precios-vivo", params={"minutos": ventana_min})

        if ticks and len(ticks) > 1:
            df_vivo = pd.DataFrame(ticks)
            df_vivo["fecha_hora"] = pd.to_datetime(df_vivo["fecha_hora"])
            df_vivo["precio_actual"] = pd.to_numeric(df_vivo["precio_actual"], errors="coerce")
            df_vivo = df_vivo.sort_values("fecha_hora").set_index("fecha_hora")

            ohlc = df_vivo["precio_actual"].resample(intervalo_vela).ohlc().dropna()

            if not ohlc.empty:
                fig_vivo = go.Figure(
                    data=[
                        go.Candlestick(
                            x=ohlc.index,
                            open=ohlc["open"],
                            high=ohlc["high"],
                            low=ohlc["low"],
                            close=ohlc["close"],
                            name=f"{ticker} en vivo",
                        )
                    ]
                )
                fig_vivo.update_layout(
                    xaxis_rangeslider_visible=False,
                    template="plotly_dark",
                    xaxis_title="Hora",
                    yaxis_title="Precio",
                    height=450,
                    margin=dict(l=20, r=20, t=30, b=20),
                )
                st.plotly_chart(fig_vivo, use_container_width=True, key="chart_vivo")
            else:
                st.info("No hay suficientes ticks en la ventana elegida para formar velas. Prueba una ventana mayor.")
        elif ticks:
            st.info("Solo hay un tick registrado en esta ventana; espera a que lleguen más datos en vivo.")
        else:
            st.warning(
                "No hay datos de precio en tiempo real para este instrumento en la ventana seleccionada. "
                "Verifica que el servicio de streaming (streaming.py) esté corriendo y conectado a Finnhub, "
                "y que el mercado esté abierto (Lun-Vie, 9:30am-4:00pm hora NY)."
            )
    except Exception as exc:
        st.error(f"Error al cargar precios en vivo: {exc}")

elif page == "Trading":
    st.header("Trading - Crear orden")
    
    if not account_id:
        st.warning("No se pudo cargar la cuenta")
        st.stop()
    
    col1, col2 = st.columns(2)
    
    with col1:
        with st.form("nueva_orden"):
            ticker = st.text_input("Ticker (ej: AAPL)")
            tipo_orden = st.selectbox("Tipo de orden", ["COMPRA", "VENTA"])
            cantidad = st.number_input("Cantidad", min_value=1, step=1)
            precio_limite = st.number_input("Precio límite", min_value=0.0, step=0.01)
            submitted = st.form_submit_button("Crear orden")
            
            if submitted:
                try:
                    result = api_request(
                        "/ordenes",
                        method="post",
                        token=token,
                        json_body={
                            "id_cuenta": account_id,
                            "ticker": ticker,
                            "tipo_orden": tipo_orden,
                            "cantidad": cantidad,
                            "precio_limite": precio_limite,
                        },
                    )
                    st.success(f"Orden creada: {result}")
                except Exception as exc:
                    st.error(f"Error: {str(exc)}")

elif page == "Portafolio":
    st.header("Portafolio - Mis posiciones")
    
    if not account_id:
        st.warning("No se pudo cargar la cuenta")
        st.stop()
    
    try:
        portafolio = api_request(f"/clientes/{cliente_id}/portafolio", token=token)
        if portafolio:
            df = pd.DataFrame(portafolio)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No hay posiciones en el portafolio")
    except Exception as exc:
        st.error(str(exc))

elif page == "Movimientos":
    st.header("Movimientos - Depósitos y retiros")
    
    if not account_id:
        st.warning("No se pudo cargar la cuenta")
        st.stop()
    
    col1, col2 = st.columns(2)
    
    with col1:
        with st.form("deposito"):
            st.subheader("💳 Depósito")
            monto_dep = st.number_input("Monto a depositar", min_value=0.01, step=0.01, key="monto_dep")
            submit_dep = st.form_submit_button("Depositar")
            
            if submit_dep:
                try:
                    result = api_request(
                        f"/cuentas/{account_id}/depositos",
                        method="post",
                        token=token,
                        json_body={"monto": float(monto_dep)},
                    )
                    st.success(f"Depósito exitoso: ${monto_dep:.2f}")
                except Exception as exc:
                    st.error(f"Error: {str(exc)}")
    
    with col2:
        with st.form("retiro"):
            st.subheader("🏦 Retiro")
            monto_ret = st.number_input("Monto a retirar", min_value=0.01, step=0.01, key="monto_ret")
            submit_ret = st.form_submit_button("Retirar")
            
            if submit_ret:
                try:
                    result = api_request(
                        f"/cuentas/{account_id}/retiros",
                        method="post",
                        token=token,
                        json_body={"monto": float(monto_ret)},
                    )
                    st.success(f"Retiro exitoso: ${monto_ret:.2f}")
                except Exception as exc:
                    st.error(f"Error: {str(exc)}")

elif page == "Notificaciones":
    st.header("Notificaciones")
    st.info("📢 Módulo de notificaciones en construcción")

elif page == "Admin":
    st.header("Admin/Backoffice")
    st.info("⚙️ Módulo administrativo en construcción")