import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

try:
    from carga_inicial import TICKERS
except ImportError:
    TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA"]

API_BASE_URL = os.getenv("BROKERHUB_API_URL", "http://127.0.0.1:8000").rstrip("/")


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
            timeout=10,
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
        raise Exception(
            f"No se pudo conectar con la API en {API_BASE_URL}. "
            "Configura BROKERHUB_API_URL con la URL de tu API desplegada o asegúrate de que tu API local esté disponible."
        ) from exc


def ensure_session_context() -> tuple[str | None, int | None, int | None]:
    token = st.session_state.get("token")
    cliente_id = st.session_state.get("cliente_id")
    account_id = st.session_state.get("account_id")
    if token and cliente_id is None:
        try:
            data = api_request("/auth/login", method="post", json_body={"usuario": st.session_state.get("usuario", ""), "contrasena": st.session_state.get("password", "")})
            st.session_state["cliente_id"] = data.get("id_cliente")
            st.session_state["token"] = data.get("token")
        except Exception:
            pass
    if token and account_id is None and cliente_id is not None:
        try:
            cuentas = api_request(f"/clientes/{cliente_id}/cuentas", token=token)
            if isinstance(cuentas, list) and cuentas:
                st.session_state["account_id"] = cuentas[0]["id_cuenta"]
        except Exception:
            pass
    return token, cliente_id, account_id


st.set_page_config(layout="wide")
st.title("BrokerHub UI")
st.caption("Frontend conectado a la API de corretaje")

menu = st.sidebar.radio(
    "Módulos",
    [
        "Onboarding",
        "Dashboard",
        "Mercado",
        "Trading",
        "Portafolio",
        "Movimientos",
        "Notificaciones",
        "Admin/Backoffice",
    ],
)

with st.sidebar.expander("Autenticación", expanded=True):
    token, cliente_id, account_id = ensure_session_context()
    if token:
        st.success("Sesión activa")
        st.write(f"Cliente ID: {cliente_id}")
        st.write(f"Cuenta ID: {account_id}")
        if st.button("Cerrar sesión"):
            st.session_state.clear()
            st.rerun()
    else:
        with st.form("login_form"):
            usuario = st.text_input("Usuario")
            contrasena = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Iniciar sesión")
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
                    st.session_state["password"] = contrasena
                    st.success("Inicio de sesión correcto")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        with st.form("registro_form"):
            nombre = st.text_input("Nombre completo")
            documento = st.text_input("Documento de identidad")
            correo = st.text_input("Correo")
            usuario_reg = st.text_input("Nuevo usuario")
            perfil = st.selectbox("Perfil de riesgo", ["CONSERVADOR", "MODERADO", "AGRESIVO"])
            password_reg = st.text_input("Contraseña", type="password")
            submitted_reg = st.form_submit_button("Registrar")
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

if menu == "Onboarding":
    st.header("Onboarding")
    st.subheader("Registro, identidad y perfil de riesgo")
    st.info("El registro y el login ya están conectados a la API. Usa el panel lateral para entrar.")
    if st.session_state.get("token"):
        st.success("Ya tienes una sesión activa y puedes pasar al dashboard.")

elif menu == "Dashboard":
    st.header("Dashboard")
    token, cliente_id, account_id = ensure_session_context()
    if not token or cliente_id is None:
        st.warning("Inicia sesión para ver el dashboard")
        st.stop()

    col1, col2, col3 = st.columns(3)
    try:
        saldo = api_request(f"/cuentas/{account_id}/saldo", token=token)
        col1.metric("Saldo disponible", f"${saldo.get('saldo_disponible', 0):.2f}")
    except Exception as exc:
        col1.metric("Saldo disponible", "Error")
        st.caption(str(exc))

    try:
        valor = api_request(f"/cuentas/{account_id}/valor-portafolio", token=token)
        col2.metric("Valor de portafolio", f"${valor.get('valor_portafolio', 0):.2f}")
    except Exception as exc:
        col2.metric("Valor de portafolio", "Error")
        st.caption(str(exc))

    try:
        rentabilidad = api_request(f"/cuentas/{account_id}/rentabilidad", token=token)
        col3.metric("Rentabilidad total", f"{rentabilidad.get('rentabilidad_total', 0):.2f}")
    except Exception as exc:
        col3.metric("Rentabilidad total", "Error")
        st.caption(str(exc))

    st.subheader("Resumen de posiciones")
    try:
        posiciones = api_request(f"/cuentas/{account_id}/posiciones", token=token)
        if posiciones:
            df_pos = pd.DataFrame(posiciones)
            st.dataframe(df_pos, use_container_width=True)
        else:
            st.info("No hay posiciones abiertas")
    except Exception as exc:
        st.error(str(exc))

elif menu == "Mercado":
    st.header("Mercado")
    token, cliente_id, account_id = ensure_session_context()
    try:
        instrumentos = api_request("/instrumentos")
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    if not instrumentos:
        st.warning("No se pudieron cargar instrumentos")
        st.stop()

    instrumentos_df = pd.DataFrame(instrumentos)
    opciones = [
        {"label": f"{row['ticker']} - {row['nombre']}", "id": row["id_instrumento"]}
        for _, row in instrumentos_df[["id_instrumento", "ticker", "nombre"]].iterrows()
    ]

    busqueda = st.text_input("Buscar instrumento por ticker o nombre")
    opciones_filtradas = [
        opcion for opcion in opciones
        if busqueda.lower() in opcion["label"].lower()
    ]

    if not opciones_filtradas:
        st.info("No hay resultados para esa búsqueda")
        st.stop()

    labels = [opcion["label"] for opcion in opciones_filtradas]
    seleccion = st.selectbox("Selecciona un instrumento", labels)
    selected_option = next(opcion for opcion in opciones_filtradas if opcion["label"] == seleccion)
    instrument_id = selected_option["id"]

    try:
        cotizaciones = api_request(f"/instrumentos/{instrument_id}/cotizaciones")
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    if cotizaciones:
        df = pd.DataFrame(cotizaciones)
        df["fecha"] = pd.to_datetime(df["fecha"])
        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=df["fecha"],
                    open=df["precio_apertura"],
                    high=df["precio_maximo"],
                    low=df["precio_minimo"],
                    close=df["precio_cierre"],
                    name=seleccion,
                )
            ]
        )
        fig.update_layout(
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            xaxis_title="Fecha",
            yaxis_title="Precio",
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay cotizaciones disponibles para este instrumento")

    st.subheader("Watchlist")
    for ticker in ["AAPL", "MSFT", "NVDA"]:
        st.checkbox(ticker)

elif menu == "Trading":
    st.header("Trading")
    token, cliente_id, account_id = ensure_session_context()
    if not token or cliente_id is None:
        st.warning("Inicia sesión para operar")
        st.stop()

    with st.form("orden"):
        ticker = st.text_input("Ticker")
        tipo = st.selectbox("Tipo de orden", ["COMPRA", "VENTA"])
        cantidad = st.number_input("Cantidad", min_value=1, step=1)
        precio = st.number_input("Precio límite", min_value=0.0, step=1.0)
        submitted = st.form_submit_button("Confirmar orden")
        if submitted:
            try:
                api_request(
                    "/ordenes",
                    method="post",
                    token=token,
                    json_body={
                        "id_cuenta": account_id,
                        "ticker": ticker,
                        "tipo_orden": tipo,
                        "cantidad": int(cantidad),
                        "precio_limite": float(precio),
                    },
                )
                st.success("Orden enviada")
            except Exception as exc:
                st.error(str(exc))

    st.subheader("Historial de órdenes")
    try:
        ordenes = api_request(f"/cuentas/{account_id}/ordenes", token=token)
        if ordenes:
            st.dataframe(pd.DataFrame(ordenes), use_container_width=True)
        else:
            st.info("No hay órdenes")
    except Exception as exc:
        st.error(str(exc))

elif menu == "Portafolio":
    st.header("Portafolio")
    token, cliente_id, account_id = ensure_session_context()
    if not token or cliente_id is None:
        st.warning("Inicia sesión para ver el portafolio")
        st.stop()

    try:
        portafolio = api_request(f"/clientes/{cliente_id}/portafolio", token=token)
        if portafolio:
            st.dataframe(pd.DataFrame(portafolio), use_container_width=True)
        else:
            st.info("No hay posiciones")
    except Exception as exc:
        st.error(str(exc))

elif menu == "Movimientos":
    st.header("Movimientos")
    token, cliente_id, account_id = ensure_session_context()
    if not token or cliente_id is None:
        st.warning("Inicia sesión para ver movimientos")
        st.stop()

    tab1, tab2 = st.tabs(["Depósitos/Retiros", "Historial de transacciones"])
    with tab1:
        with st.form("movimiento"):
            tipo = st.selectbox("Tipo", ["Depósito", "Retiro"])
            monto = st.number_input("Monto", min_value=0.0, step=10.0)
            if st.form_submit_button("Procesar"):
                try:
                    endpoint = "/cuentas/{id}/depositos" if tipo == "Depósito" else "/cuentas/{id}/retiros"
                    api_request(
                        endpoint.format(id=account_id),
                        method="post",
                        token=token,
                        json_body={"monto": float(monto)},
                    )
                    st.success(f"{tipo} procesado correctamente")
                except Exception as exc:
                    st.error(str(exc))
    with tab2:
        try:
            movimientos = api_request(f"/cuentas/{account_id}/movimientos", token=token)
            if movimientos:
                st.dataframe(pd.DataFrame(movimientos), use_container_width=True)
            else:
                st.info("No hay movimientos")
        except Exception as exc:
            st.error(str(exc))

elif menu == "Notificaciones":
    st.header("Notificaciones")
    if st.session_state.get("token"):
        st.success("Orden ejecutada correctamente")
        st.info("Orden parcial ejecutada: 5/10 acciones")
        st.warning("Alerta: saldo bajo en la cuenta")
    else:
        st.info("Inicia sesión para recibir notificaciones")

elif menu == "Admin/Backoffice":
    st.header("Admin/Backoffice")
    try:
        riesgo = api_request("/admin/reporte-riesgo")
        if riesgo:
            st.dataframe(pd.DataFrame(riesgo), use_container_width=True)
        else:
            st.info("No hay datos de riesgo")
    except Exception as exc:
        st.error(str(exc))
