import os
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(layout="wide", page_title="BrokerHub", page_icon="📈", initial_sidebar_state="expanded")

try:
    from carga_inicial import TICKERS
except ImportError:
    TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA"]

API_BASE_URL = os.getenv("BROKERHUB_API_URL") or "https://brokerhub-api-production.up.railway.app"
if not API_BASE_URL.startswith(("http://", "https://")):
    API_BASE_URL = f"https://{API_BASE_URL}"
API_BASE_URL = API_BASE_URL.rstrip("/")

# ============================================================================
# ESTILO GLOBAL — TEMA "TERMINAL FINANCIERA" (verde institucional)
# ============================================================================

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Serif:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&family=Source+Sans+Pro:wght@400;500;600;700&display=swap');

    :root {
        --bh-bg-0: #0a120d;
        --bh-bg-1: #0e1a13;
        --bh-bg-2: #12241a;
        --bh-panel: #101d15;
        --bh-border: #23402c;
        --bh-border-soft: rgba(52, 105, 66, 0.35);
        --bh-green-500: #1e7d43;
        --bh-green-600: #17632f;
        --bh-green-accent: #2fae5d;
        --bh-green-bright: #4fd47e;
        --bh-text-main: #e7f3ea;
        --bh-text-muted: #93ab9a;
        --bh-red: #c0453f;
        --bh-gold: #c9a24b;
    }

    html, body, [class*='css'] {
        font-family: 'Source Sans Pro', 'Segoe UI', sans-serif;
        color: var(--bh-text-main);
    }

    /* Titulares serios, tipo prensa financiera */
    h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        font-family: 'IBM Plex Serif', Georgia, serif !important;
        color: var(--bh-text-main) !important;
        letter-spacing: 0.2px;
    }

    /* Cifras y datos en monoespaciada, como una terminal Bloomberg/Reuters */
    .stMetric, .stMetric label, .stMetric [data-testid="stMetricValue"],
    .stDataFrame, code, .bh-mono {
        font-family: 'IBM Plex Mono', 'Consolas', monospace !important;
    }

    .stApp {
        background: linear-gradient(180deg, var(--bh-bg-0) 0%, var(--bh-bg-1) 55%, var(--bh-bg-0) 100%);
    }

    .block-container {
        padding: 1.4rem 2.4rem 3rem;
        max-width: 1400px;
    }

    /* -------------------- SIDEBAR: navegación vertical -------------------- */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0b1710 0%, #0a140e 100%);
        border-right: 1px solid var(--bh-border);
    }
    section[data-testid="stSidebar"] .block-container {
        padding: 0.6rem 1.1rem 1rem;
    }
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {
        gap: 0.35rem !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stElementContainer"] {
        margin-bottom: 0 !important;
    }
    section[data-testid="stSidebar"] .stButton>button {
        width: 100%;
        text-align: left;
        justify-content: flex-start;
        background: transparent !important;
        color: var(--bh-text-muted) !important;
        border: 1px solid transparent !important;
        border-radius: 6px !important;
        padding: 0.4rem 0.8rem !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        letter-spacing: 0.2px;
        margin-bottom: 0 !important;
        line-height: 1.3;
        transition: all 0.12s ease-in-out;
    }
    section[data-testid="stSidebar"] .stButton>button:hover {
        background: rgba(47, 174, 93, 0.10) !important;
        color: var(--bh-text-main) !important;
        border: 1px solid var(--bh-border-soft) !important;
    }
    section[data-testid="stSidebar"] .stButton>button:focus:not(:active) {
        color: var(--bh-text-main) !important;
    }

    /* Botón de la página activa */
    .bh-nav-active button {
        background: rgba(30, 125, 67, 0.22) !important;
        color: var(--bh-green-bright) !important;
        border: 1px solid var(--bh-green-500) !important;
        border-left: 3px solid var(--bh-green-bright) !important;
    }

    /* -------------------- Botones generales (main area) -------------------- */
    .stButton>button, .stFormSubmitButton>button {
        background-color: var(--bh-green-600) !important;
        color: #f2fbf4 !important;
        border-radius: 4px !important;
        border: 1px solid var(--bh-green-500) !important;
        font-weight: 600 !important;
        letter-spacing: 0.3px;
        font-family: 'Source Sans Pro', sans-serif !important;
    }
    .stButton>button:hover, .stFormSubmitButton>button:hover {
        background-color: var(--bh-green-accent) !important;
        border-color: var(--bh-green-accent) !important;
        color: #06120a !important;
    }

    /* -------------------- Métricas: estilo panel de cotización -------------------- */
    div[data-testid="stMetric"] {
        border: 1px solid var(--bh-border-soft);
        border-radius: 6px;
        background: var(--bh-panel);
        padding: 1rem 1.1rem !important;
        border-left: 3px solid var(--bh-green-500);
    }
    div[data-testid="stMetricLabel"] {
        color: var(--bh-text-muted) !important;
        text-transform: uppercase;
        font-size: 0.72rem !important;
        letter-spacing: 0.8px;
    }
    div[data-testid="stMetricValue"] {
        color: var(--bh-text-main) !important;
        font-size: 1.55rem !important;
    }

    /* -------------------- Tablas -------------------- */
    .stDataFrame {
        border: 1px solid var(--bh-border-soft) !important;
        border-radius: 6px;
    }
    .stDataFrame table {
        background: var(--bh-panel) !important;
    }

    /* -------------------- Inputs / forms -------------------- */
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div,
    .stTextArea textarea {
        background-color: #0c1a12 !important;
        border: 1px solid var(--bh-border-soft) !important;
        color: var(--bh-text-main) !important;
        border-radius: 4px !important;
    }
    label, .stSelectbox label, .stTextInput label, .stNumberInput label, .stTextArea label {
        color: var(--bh-text-muted) !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
    }

    div[data-testid="stForm"] {
        border: 1px solid var(--bh-border-soft);
        border-radius: 8px;
        background: rgba(16, 29, 21, 0.55);
        padding: 1.2rem 1.3rem 0.6rem;
    }

    /* -------------------- Expander -------------------- */
    .stExpander {
        border: 1px solid var(--bh-border-soft) !important;
        border-radius: 6px !important;
        background: var(--bh-panel) !important;
    }
    .stExpander summary {
        color: var(--bh-text-main) !important;
        font-weight: 600 !important;
    }

    /* -------------------- Tabs -------------------- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        border-bottom: 1px solid var(--bh-border);
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        color: var(--bh-text-muted);
        font-weight: 600;
        border-radius: 4px 4px 0 0;
    }
    .stTabs [aria-selected="true"] {
        color: var(--bh-green-bright) !important;
        border-bottom: 2px solid var(--bh-green-bright) !important;
    }

    /* -------------------- Alerts -------------------- */
    div[data-testid="stAlert"] {
        border-radius: 4px !important;
        border-left: 3px solid var(--bh-green-500) !important;
    }

    /* -------------------- Encabezado / marca -------------------- */
    .bh-brand-title {
        font-family: 'IBM Plex Serif', Georgia, serif;
        font-weight: 700;
        font-size: 1.55rem;
        color: var(--bh-text-main);
        letter-spacing: 0.3px;
        margin-bottom: 0;
    }
    .bh-brand-sub {
        color: var(--bh-text-muted);
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 1.4px;
        margin-top: -2px;
    }
    .bh-divider-gold {
        height: 1px;
        background: linear-gradient(90deg, var(--bh-green-500), var(--bh-gold), var(--bh-green-500));
        opacity: 0.55;
        margin: 0.25rem 0 0.5rem 0;
    }
    .bh-session-pill {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 3px;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.78rem;
        font-weight: 600;
        border: 1px solid var(--bh-border-soft);
        color: var(--bh-text-muted);
    }
    .bh-session-pill.on {
        border-color: var(--bh-green-500);
        color: var(--bh-green-bright);
        background: rgba(47, 174, 93, 0.08);
    }
    .bh-sidebar-label {
        color: var(--bh-text-muted);
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin: 0.6rem 0 0.3rem 0;
    }

    /* Ocultar el header nativo de Streamlit para un look más "app" */
    header[data-testid="stHeader"] {
        background: transparent;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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
            proxies={"http": "", "https": ""},  # ignora proxy del sistema para localhost
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
    if "role" not in st.session_state:
        st.session_state.role = "CLIENTE"
    if "page" not in st.session_state:
        st.session_state.page = "Dashboard"
    if "show_onboarding" not in st.session_state:
        st.session_state.show_onboarding = False

init_session_state()

token = st.session_state.token
cliente_id = st.session_state.cliente_id

# ============================================================================
# SIDEBAR — MARCA + NAVEGACIÓN VERTICAL + ESTADO DE SESIÓN
# ============================================================================

MODULOS = [
    ("Dashboard", "📊"),
    ("Mercado", "📈"),
    ("Trading", "⚡"),
    ("Portafolio", "💼"),
    ("Movimientos", "🏦"),
    ("Notificaciones", "🔔"),
    ("Admin", "🛠️"),
]

with st.sidebar:
    st.markdown('<div class="bh-brand-title">BROKERHUB</div>', unsafe_allow_html=True)
    st.markdown('<div class="bh-brand-sub">Mesa de Trading Simulada</div>', unsafe_allow_html=True)
    st.markdown('<div class="bh-divider-gold"></div>', unsafe_allow_html=True)

    if token:
        st.markdown(f'<span class="bh-session-pill on">● SESIÓN ACTIVA</span>', unsafe_allow_html=True)
        st.caption(f"Usuario: **{st.session_state.usuario}**  ·  Rol: {st.session_state.role}")
    else:
        st.markdown(f'<span class="bh-session-pill">○ SIN AUTENTICAR</span>', unsafe_allow_html=True)

    st.markdown('<div class="bh-sidebar-label">MÓDULOS</div>', unsafe_allow_html=True)

    for nombre, icono in MODULOS:
        es_activo = st.session_state.page == nombre
        wrapper_class = "bh-nav-active" if es_activo else ""
        st.markdown(f'<div class="{wrapper_class}">', unsafe_allow_html=True)
        if st.button(f"{icono}  {nombre}", key=f"nav_{nombre}", use_container_width=True):
            st.session_state.page = nombre
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="bh-divider-gold"></div>', unsafe_allow_html=True)

    col_perfil, col_logout = st.columns(2)
    with col_perfil:
        if st.button("👤 Perfil", use_container_width=True):
            st.session_state.show_onboarding = not st.session_state.show_onboarding
            st.rerun()
    with col_logout:
        if token and st.button("Salir", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    st.caption(f"API: `{API_BASE_URL.replace('https://', '')}`")

# ============================================================================
# CABECERA PRINCIPAL
# ============================================================================

header_left, header_right = st.columns([5, 2])
with header_left:
    st.markdown(f'<div class="bh-brand-title">{st.session_state.page}</div>', unsafe_allow_html=True)
with header_right:
    st.caption(datetime.now().strftime("Sesión del %d/%m/%Y — %H:%M"))
st.markdown('<div class="bh-divider-gold"></div>', unsafe_allow_html=True)

if st.session_state.show_onboarding:
    with st.expander("👤 Onboarding", expanded=True):
        if token:
            st.success(f"Sesión activa: {st.session_state.usuario}")
            st.write("Accede a los módulos con mayor control operativo y reportes financieros.")
            st.write("Este panel te ayuda a revisar tu estado y a abrir la ruta rápida de soporte interno.")
        else:
            st.warning("No has iniciado sesión.")
            st.write("Usa el botón de perfil para iniciar sesión o registrarte y obtener acceso completo.")
        st.write("Presiona de nuevo el botón de perfil para ocultar este panel.")

# ============================================================================
# MODAL DE AUTENTICACIÓN
# ============================================================================

if not token:
    st.markdown("### Acceso a la plataforma")

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
                    st.session_state["role"] = data.get("rol", "CLIENTE")
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
                    st.session_state["role"] = data.get("rol", "CLIENTE")
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
    st.session_state.page = "Dashboard"
    page = "Dashboard"

if page == "Dashboard":
    if not account_id:
        st.warning("No se pudo cargar la cuenta. Intenta recargar la página.")
        st.stop()

    col1, col2, col3 = st.columns(3)

    try:
        saldo = api_request(f"/cuentas/{account_id}/saldo", token=token)
        col1.metric("Saldo disponible", f"${saldo.get('saldo_disponible', 0):.2f}")
    except Exception as exc:
        col1.error("Error al cargar saldo")

    try:
        valor = api_request(f"/cuentas/{account_id}/valor-portafolio", token=token)
        col2.metric("Valor de portafolio", f"${valor.get('valor_portafolio', 0):.2f}")
    except Exception as exc:
        col2.error("Error al cargar portafolio")

    try:
        rentabilidad = api_request(f"/cuentas/{account_id}/rentabilidad", token=token)
        col3.metric("Rentabilidad total", f"{rentabilidad.get('rentabilidad_total', 0):.2f}%")
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
        st.write("")
        st.write("")
        if st.button("Actualizar gráficas", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    ticker = seleccion.split(" - ")[0]
    instrumento = df_inst[df_inst["ticker"] == ticker].iloc[0]
    instrument_id = instrumento["id_instrumento"]

    # ------------------------------------------------------------------
    # Gráfica histórica: serie de línea, rango extenso (precio de cierre)
    # ------------------------------------------------------------------
    st.subheader("Histórico")
    try:
        cotizaciones = api_request(f"/instrumentos/{instrument_id}/cotizaciones")

        if cotizaciones:
            df_hist = pd.DataFrame(cotizaciones)
            df_hist["fecha"] = pd.to_datetime(df_hist["fecha"])
            df_hist["precio_cierre"] = pd.to_numeric(df_hist["precio_cierre"], errors="coerce")
            df_hist = df_hist.sort_values("fecha")

            import plotly.express as px
            fig_hist = px.line(
                df_hist,
                x="fecha",
                y="precio_cierre",
                title=None,
            )
            fig_hist.update_traces(line=dict(color="#2fae5d", width=2))
            fig_hist.update_layout(
                template="plotly_dark",
                paper_bgcolor="#101d15",
                plot_bgcolor="#101d15",
                font=dict(family="IBM Plex Mono, monospace", color="#e7f3ea"),
                xaxis_title="Fecha",
                yaxis_title="Precio de cierre",
                height=400,
                margin=dict(l=20, r=20, t=30, b=20),
            )
            fig_hist.update_xaxes(gridcolor="#23402c")
            fig_hist.update_yaxes(gridcolor="#23402c")
            st.plotly_chart(fig_hist, use_container_width=True, key="chart_historico_v2_express")
        else:
            st.info("No hay cotizaciones históricas cargadas para este instrumento todavía.")
    except Exception as exc:
        st.error(f"Error al cargar histórico: {exc}")

    # ------------------------------------------------------------------
    # Gráfica en vivo: velas, ventana corta (ticks de Precio_Tiempo_Real)
    # ------------------------------------------------------------------
    st.subheader("En vivo (velas)")

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
                            increasing_line_color="#2fae5d",
                            decreasing_line_color="#c0453f",
                        )
                    ]
                )
                fig_vivo.update_layout(
                    xaxis_rangeslider_visible=False,
                    template="plotly_dark",
                    paper_bgcolor="#101d15",
                    plot_bgcolor="#101d15",
                    font=dict(family="IBM Plex Mono, monospace", color="#e7f3ea"),
                    xaxis_title="Hora",
                    yaxis_title="Precio",
                    height=450,
                    margin=dict(l=20, r=20, t=30, b=20),
                )
                fig_vivo.update_xaxes(gridcolor="#23402c")
                fig_vivo.update_yaxes(gridcolor="#23402c")
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
    if not account_id:
        st.warning("No se pudo cargar la cuenta")
        st.stop()

    col1, col2 = st.columns(2)

    with col1:
        with st.form("nueva_orden"):
            st.markdown("**Nueva orden**")
            ticker = st.text_input("Ticker (ej: AAPL)")
            tipo_orden = st.selectbox("Tipo de orden", ["COMPRA", "VENTA"])
            cantidad = st.number_input("Cantidad", min_value=1, step=1)
            precio_limite = st.number_input("Precio límite", min_value=0.0, step=0.01)
            submitted = st.form_submit_button("Crear orden", use_container_width=True)

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
    if not account_id:
        st.warning("No se pudo cargar la cuenta")
        st.stop()

    col1, col2 = st.columns(2)

    with col1:
        with st.form("deposito"):
            st.markdown("**Depósito**")
            monto_dep = st.number_input("Monto a depositar", min_value=0.01, step=0.01, key="monto_dep")
            submit_dep = st.form_submit_button("Depositar", use_container_width=True)

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
            st.markdown("**Retiro**")
            monto_ret = st.number_input("Monto a retirar", min_value=0.01, step=0.01, key="monto_ret")
            submit_ret = st.form_submit_button("Retirar", use_container_width=True)

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
    if not account_id:
        st.warning("No se pudo cargar la cuenta")
        st.stop()

    with st.expander("Enviar notificación de prueba"):
        with st.form("crear_notificacion_form"):
            tipo = st.selectbox("Tipo de notificación", ["INFO", "ORDEN", "ALERTA", "SISTEMA"])
            titulo = st.text_input("Título")
            mensaje = st.text_area("Mensaje")
            enviada = st.form_submit_button("Enviar notificación", use_container_width=True)
            if enviada:
                try:
                    api_request(
                        f"/clientes/{cliente_id}/notificaciones",
                        method="post",
                        token=token,
                        json_body={"tipo": tipo, "titulo": titulo, "mensaje": mensaje},
                    )
                    st.success("Notificación enviada correctamente")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error al enviar notificación: {exc}")

    try:
        notificaciones = api_request(f"/clientes/{cliente_id}/notificaciones", token=token)
    except Exception as exc:
        st.error(f"No se pudieron cargar las notificaciones: {exc}")
        st.stop()

    if notificaciones:
        no_leidas = sum(1 for n in notificaciones if not n.get("leida"))
        st.metric("Notificaciones sin leer", no_leidas)

        for notificacion in notificaciones:
            estado = "Leída" if notificacion.get("leida") else "Sin leer"
            with st.container():
                cols = st.columns([9, 1])
                with cols[0]:
                    st.markdown(f"**{notificacion['titulo']}**  ")
                    st.caption(f"{notificacion['tipo']} · {notificacion['fecha_hora']} · {estado}")
                    st.write(notificacion['mensaje'])
                with cols[1]:
                    if not notificacion.get("leida"):
                        if st.button("Marcar leída", key=f"leer_{notificacion['id_notificacion']}"):
                            try:
                                api_request(
                                    f"/clientes/{cliente_id}/notificaciones/{notificacion['id_notificacion']}/leer",
                                    method="patch",
                                    token=token,
                                )
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Error al marcar como leída: {exc}")
                st.markdown("---")
    else:
        st.info("No hay notificaciones para mostrar.")

elif page == "Admin":
    # Control de acceso en el frontend: solo mostrar el panel cuando el token
    # indica que el usuario tiene rol ADMIN.
    if st.session_state.role != "ADMIN":
        st.warning("Solo usuarios con rol ADMIN pueden usar este módulo.")
        st.info("Inicia sesión con una cuenta administrativa para acceder aquí.")
        st.stop()

    st.success(f"Modo ADMIN activo — {st.session_state.usuario}")
    st.markdown("### Acciones administrativas disponibles")

    with st.expander("Cancelar orden"):
        with st.form("admin_cancelar_orden"):
            id_orden_cancelar = st.number_input("ID de orden", min_value=1, step=1)
            cancelar = st.form_submit_button("Cancelar orden")
            if cancelar:
                try:
                    resultado = api_request(
                        f"/admin/ordenes/{id_orden_cancelar}/cancelar",
                        method="post",
                        token=token,
                    )
                    st.success(resultado.get("mensaje"))
                except Exception as exc:
                    st.error(f"Error: {exc}")

    with st.expander("Cambiar estado de cuenta"):
        with st.form("admin_cambiar_estado_cuenta"):
            id_cuenta_estado = st.number_input("ID de cuenta", min_value=1, step=1, key="admin_estado_cuenta")
            nuevo_estado = st.selectbox("Nuevo estado", ["A", "I"], key="admin_estado_select")
            guardar_estado = st.form_submit_button("Actualizar estado")
            if guardar_estado:
                try:
                    resultado = api_request(
                        f"/admin/cuentas/{id_cuenta_estado}/estado",
                        method="patch",
                        token=token,
                        json_body={"estado": nuevo_estado},
                    )
                    st.success(resultado.get("mensaje"))
                except Exception as exc:
                    st.error(f"Error: {exc}")

    with st.expander("Ajustar saldo de cuenta"):
        with st.form("admin_ajustar_saldo"):
            id_cuenta_saldo = st.number_input("ID de cuenta", min_value=1, step=1, key="admin_saldo_cuenta")
            nuevo_saldo = st.number_input("Nuevo saldo disponible", min_value=0.0, format="%.2f", key="admin_nuevo_saldo")
            ajustar_saldo = st.form_submit_button("Ajustar saldo")
            if ajustar_saldo:
                try:
                    resultado = api_request(
                        f"/admin/cuentas/{id_cuenta_saldo}/saldo",
                        method="patch",
                        token=token,
                        json_body={"nuevo_saldo": float(nuevo_saldo)},
                    )
                    st.success(resultado.get("mensaje"))
                except Exception as exc:
                    st.error(f"Error: {exc}")

    with st.expander("Enviar notificación administrativa"):
        with st.form("admin_notificacion"):
            cliente_destino = st.number_input("ID de cliente", min_value=1, step=1)
            tipo_notif = st.selectbox("Tipo", ["ADMIN", "ALERTA", "SISTEMA"], key="admin_tipo_notif")
            titulo_notif = st.text_input("Título", key="admin_titulo_notif")
            mensaje_notif = st.text_area("Mensaje", key="admin_mensaje_notif")
            enviar_notif = st.form_submit_button("Enviar notificación")
            if enviar_notif:
                try:
                    resultado = api_request(
                        f"/admin/clientes/{cliente_destino}/notificaciones",
                        method="post",
                        token=token,
                        json_body={"tipo": tipo_notif, "titulo": titulo_notif, "mensaje": mensaje_notif},
                    )
                    st.success(resultado.get("mensaje"))
                except Exception as exc:
                    st.error(f"Error: {exc}")

    with st.expander("Listar cuentas y credenciales"):
        with st.form("admin_listar_credenciales"):
            st.write("Consulta los hashes de credenciales de las cuentas registradas.")
            cargar_credenciales = st.form_submit_button("Cargar cuentas")
            if cargar_credenciales:
                try:
                    cuentas_credenciales = api_request(
                        "/admin/cuentas/credenciales",
                        method="get",
                        token=token,
                    )
                    if cuentas_credenciales:
                        st.dataframe(cuentas_credenciales, use_container_width=True)
                    else:
                        st.info("No se encontraron cuentas ni credenciales.")
                except Exception as exc:
                    st.error(f"Error: {exc}")

    with st.expander("Crear administrador"):
        with st.form("admin_crear_admin"):
            nombre_admin = st.text_input("Nombre completo", key="admin_nombre")
            usuario_admin = st.text_input("Usuario", key="admin_usuario")
            correo_admin = st.text_input("Correo", key="admin_correo")
            documento_admin = st.text_input("Documento de identidad", key="admin_documento")
            contrasena_admin = st.text_input("Contraseña", type="password", key="admin_contrasena")
            perfil_admin = st.selectbox("Perfil de riesgo", ["CONSERVADOR", "MODERADO", "AGRESIVO"], key="admin_perfil")
            crear_admin = st.form_submit_button("Crear administrador")
            if crear_admin:
                try:
                    resultado = api_request(
                        "/admin/registro",
                        method="post",
                        token=token,
                        json_body={
                            "nombre_completo": nombre_admin,
                            "tipo_cliente": "N",
                            "documento_identidad": documento_admin,
                            "correo": correo_admin,
                            "perfil_riesgo": perfil_admin,
                            "usuario": usuario_admin,
                            "contrasena": contrasena_admin,
                        },
                    )
                    st.success(resultado.get("mensaje"))
                except Exception as exc:
                    st.error(f"Error: {exc}")