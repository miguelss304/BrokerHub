# BrokerHub — Proyecto Final Bases de Datos

Plataforma de corretaje de inversiones (broker bursátil), enfocada en acciones
de mercados de Estados Unidos (NYSE/NASDAQ), con datos reales de Finnhub y
yfinance, y datos sintéticos generados con Faker.

## Estructura del proyecto

```
BrokerHub/
├── .env                          # credenciales reales (NO se sube a git)
├── .env.example                  # plantilla de variables necesarias
├── .gitignore
├── requirements.txt
│
├── broker_esquema_mysql.sql      # DDL: crea las 12 tablas del modelo
│
├── conexion_db.py                # conexión reutilizable a MySQL + reconexión automática
├── cliente_finnhub.py            # funciones REST a Finnhub + histórico vía yfinance
│
├── carga_inicial.py              # puebla Emisor, Instrumento, Categoría, Cotización, Listado
├── actualizar_historico.py       # trae solo los días nuevos que falten en Cotizacion_Historica
├── generador_faker.py            # genera Cliente y Cuenta_Inversion sintéticos
├── simulador_ordenes.py          # genera Orden, Transaccion_Ejecutada, Posicion (histórico simulado)
├── streaming.py                  # WebSocket en vivo -> Precio_Tiempo_Real
├── ejecutor_ordenes.py           # motor: ejecuta Órdenes PENDIENTE contra el precio en vivo
├── colocar_orden.py              # utilidad para colocar una Orden PENDIENTE de prueba
├── main.py                       # API (FastAPI): expone el sistema por HTTP
├── Procfile                      # comando de arranque para desplegar la API en Railway
│
└── exploracion_finnhub.ipynb     # notebook para explorar/visualizar datos con pandas
```

## 1. Instalación (una sola vez)

```bash
pip install -r requirements.txt
```

## 2. Configurar credenciales

Copia `.env.example` como `.env` y completa con tus valores reales:

```
MYSQLHOST=tokaido.proxy.rlwy.net
MYSQLPORT=45849
MYSQLUSER=root
MYSQLPASSWORD=<tu password de Railway>
MYSQLDATABASE=railway

FINNHUB_API_KEY=<tu api key de Finnhub>
```

Las credenciales de Railway están en el servicio de MySQL → pestaña **Variables**
(usuario/password) y pestaña **Networking → Public Networking** (host/puerto).
La API key de Finnhub se obtiene gratis en [finnhub.io](https://finnhub.io).

## 3. Crear el esquema de la base de datos

Abre `broker_esquema_mysql.sql` en MySQL Workbench (conectado a Railway) y
ejecútalo completo. Esto crea las 12 tablas del modelo. **Solo se corre una vez**
(o si se necesita recrear el esquema desde cero).

## 4. Orden de ejecución de los scripts

Corre los scripts **en este orden**, cada uno se puede volver a correr sin
duplicar datos (usan "buscar o crear" o `INSERT IGNORE` / `ON DUPLICATE KEY`):

```bash
# 1. Datos reales de mercado: Emisor, Instrumento, Categoría, Cotización, Listado
python carga_inicial.py

# 1.5. (Correr periódicamente, ej. una vez al día) Trae solo los días nuevos
#      que falten en Cotizacion_Historica, sin repetir todo el histórico.
python actualizar_historico.py

# 2. Clientes y cuentas sintéticas
python generador_faker.py

# 3. Órdenes, transacciones y posiciones (usa los precios reales ya cargados)
#    Estas quedan ya EJECUTADAS -- es la simulación de "historial" del proyecto.
python simulador_ordenes.py

# 4. Streaming en vivo (dejar corriendo durante la demo, en su propia terminal)
python streaming.py

# 5. Ejecutor de órdenes en tiempo real (dejar corriendo, en OTRA terminal aparte)
#    Revisa cada 5s las Órdenes en estado PENDIENTE y las ejecuta si el precio
#    en vivo (o el último cierre histórico como respaldo) cumple el precio_limite.
python ejecutor_ordenes.py

# 6. (Solo para pruebas/demo) Colocar una Orden nueva en estado PENDIENTE,
#    para ver cómo el ejecutor la toma y la resuelve en el siguiente ciclo.
python colocar_orden.py

# 7. API (opcional, en su propia terminal): expone todo por HTTP
uvicorn main:app --reload
```

### Cómo correr varios scripts a la vez (streaming + ejecutor)

`streaming.py` y `ejecutor_ordenes.py` deben quedar corriendo **al mismo tiempo, en
terminales separadas** (no una detrás de otra). En VS Code: `Terminal → New Terminal`
(o el botón `+` del panel de terminal) para abrir una pestaña nueva por cada script,
sin cerrar las anteriores.

**Importante sobre `streaming.py`:** solo vas a ver trades llegando cuando el
mercado de EE.UU. esté abierto — lunes a viernes, 9:30 AM a 4:00 PM hora de
Nueva York. Fuera de ese horario, el WebSocket queda conectado pero sin
mensajes (esto es esperado, no es un error).

## 5. Verificación rápida en MySQL Workbench

```sql
SELECT COUNT(*) FROM Cliente;
SELECT COUNT(*) FROM Instrumento_Financiero;
SELECT COUNT(*) FROM Cotizacion_Historica;
SELECT COUNT(*) FROM Orden;
SELECT COUNT(*) FROM Posicion;
SELECT COUNT(*) FROM Precio_Tiempo_Real;  -- solo tendrá datos si se corrió streaming.py en horario de mercado

-- Ver órdenes pendientes vs ejecutadas
SELECT estado, COUNT(*) FROM Orden GROUP BY estado;
```

## Motor de ejecución de órdenes en tiempo real

`ejecutor_ordenes.py` es lo que convierte el proyecto de "scripts que corren una
vez" a una aplicación que reacciona en vivo:

1. Un cliente coloca una `Orden` (queda en estado `PENDIENTE`) — ver `colocar_orden.py`.
2. `streaming.py` sigue llenando `Precio_Tiempo_Real` con datos reales de Finnhub.
3. `ejecutor_ordenes.py` revisa cada 5 segundos las órdenes `PENDIENTE` y las
   compara contra el último precio conocido de su instrumento:
   - **COMPRA** se ejecuta si `precio_actual <= precio_limite`
   - **VENTA** se ejecuta si `precio_actual >= precio_limite`
   - Si no hay ningún precio en vivo todavía (mercado cerrado), usa como
     respaldo el último `precio_cierre` de `Cotizacion_Historica`.
4. Al ejecutarse: crea la `Transaccion_Ejecutada`, actualiza `saldo_disponible`
   de la cuenta, actualiza (o crea) la `Posicion` del cliente, y marca la
   `Orden` como `EJECUTADA`.

`streaming.py` y `ejecutor_ordenes.py` están pensados para correr **en paralelo**
de forma indefinida (streaming captura precios, el ejecutor reacciona a ellos).

## Consistencia del "precio actual" (horario de mercado)

Tanto `main.py` (API) como `ejecutor_ordenes.py` usan la misma lógica para
decidir qué es el "precio actual" de un instrumento:

- Si el mercado está abierto (lunes-viernes, 9:30 AM - 4:00 PM hora de
  Nueva York) **y** hay datos en `Precio_Tiempo_Real`, se usa el último trade.
- Si el mercado está cerrado, o aún no ha llegado ningún dato en vivo, se usa
  el último `precio_cierre` de `Cotizacion_Historica`.

Esto evita que se use un precio "viejo" del streaming (por ejemplo, el último
trade antes de que cerrara el mercado) como si fuera el precio actual. Por la
misma razón, `Cotizacion_Historica` debe mantenerse actualizada corriendo
`actualizar_historico.py` periódicamente -- si no, el respaldo fuera de
horario también queda desactualizado.

## Notas sobre streaming.py (trades duplicados)

`Precio_Tiempo_Real` tiene como clave primaria `(id_instrumento, fecha_hora)`,
y `fecha_hora` solo guarda precisión de segundos. Si llegan dos trades del
mismo instrumento en el mismo segundo, se usa `INSERT IGNORE` para descartar
el duplicado sin tumbar el lote completo. El hilo escritor además está
envuelto en un manejo de errores general para que nunca muera en silencio
(si muriera, se dejarían de guardar trades sin ningún aviso visible).

## API (FastAPI)

`main.py` expone el sistema por HTTP, para que cualquier interfaz (o herramienta
como Postman) pueda consultar y operar sobre la base sin escribir SQL ni correr
scripts a mano.

### Cómo correrla

```bash
uvicorn main:app --reload
```

Documentación interactiva (para probar cada endpoint con botones, sin código):
```
http://127.0.0.1:8000/docs
```

### Endpoints disponibles

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/health` | Confirma que la API y la base de datos están activas |
| GET | `/clientes` | Lista todos los clientes |
| GET | `/clientes/{id_cliente}` | Datos de un cliente específico |
| GET | `/clientes/{id_cliente}/cuentas` | Cuentas de inversión de un cliente |
| GET | `/clientes/{id_cliente}/portafolio` | Posiciones actuales, con precio actual y ganancia/pérdida no realizada |
| GET | `/clientes/{id_cliente}/ordenes` | Historial de órdenes de un cliente |
| GET | `/instrumentos` | Lista todos los instrumentos (acciones) disponibles |
| GET | `/instrumentos/{ticker}/precio-actual` | Último precio conocido (en vivo, o histórico como respaldo) |
| GET | `/instrumentos/{ticker}/historico?dias=30` | Histórico diario de precios |
| POST | `/ordenes` | Coloca una orden nueva (queda `PENDIENTE`) |
| GET | `/ordenes/{id_orden}` | Detalle de una orden y sus transacciones |
| DELETE | `/ordenes/{id_orden}` | Cancela una orden (solo si sigue `PENDIENTE`) |

### Notas de diseño

- Tiene **CORS habilitado** (`allow_origins=["*"]`), para que cualquier
  interfaz futura pueda consultarla desde el navegador sin bloqueos.
- Los errores de conexión a MySQL (ej. Railway inactivo) se traducen a un
  `503` con mensaje claro, en vez de un traceback de Python.
- **Pendiente de definir**: validaciones relacionadas con `tipo_cliente` y
  `perfil_riesgo` se dejaron fuera intencionalmente hasta decidir cómo será
  la interfaz final (afecta qué datos se piden/validan en el `POST /ordenes`
  y en futuros endpoints de creación de clientes).

### Despliegue en Railway

La API ya está desplegada en Railway (mismo proyecto que el servicio de MySQL),
accesible públicamente sin depender de que un computador esté prendido.

- El `Procfile` le indica a Railway cómo arrancar la API:
  ```
  web: uvicorn main:app --host 0.0.0.0 --port $PORT
  ```
- Las variables de entorno (`MYSQLHOST`, `FINNHUB_API_KEY`, etc.) se configuran
  por separado en la pestaña **Variables** del servicio de la API en Railway
  (no reutiliza el `.env` local — cada entorno tiene las suyas).
- El dominio público se genera en **Settings → Networking → Generate Domain**.
- Verificar que sigue viva: `<url-de-railway>/health` debe responder
  `{"status": "ok", "database": "conectada"}`.

**Nota:** `streaming.py` y `ejecutor_ordenes.py` siguen corriendo localmente
(no están desplegados en Railway todavía) — solo `main.py` (la API) vive en
la nube por ahora.

## Funcionalidades futuras (fuera del alcance actual)

- **Interfaz de usuario**: aún no se ha decidido cómo será. La opción
  considerada por ahora es un dashboard simple con **Streamlit**
  (rápido de construir en Python, sin necesidad de saber frontend "de verdad"),
  consumiendo los endpoints de `main.py`. Pendiente de decisión final.
- **Sugerencia por perfil de riesgo**: comparar el perfil de riesgo del cliente
  (`Cliente.perfil_riesgo`) contra el nivel de riesgo del instrumento
  (`Categoria_Instrumento.nivel_riesgo`) para mostrar una advertencia al colocar
  una orden (no bloquear la operación, solo sugerir). Se dejó como funcionalidad
  secundaria porque los 12 tickers elegidos son en su mayoría empresas grandes
  (Blue Chip), por lo que hay poca variedad de riesgo real para demostrar la regla.
  También se omitió intencionalmente de la API (`main.py`) por ahora, hasta
  definir la interfaz.
- Despliegue de `main.py` en Railway (junto al servicio de MySQL), para que la
  API sea accesible fuera de tu computador.
- Ejecución parcial de órdenes (`PARCIALMENTE_EJECUTADA`) — actualmente el
  ejecutor solo resuelve órdenes completas (todo o nada).

## Notas de diseño del modelo

- **Solo acciones**: el campo `tipo` de `Instrumento_Financiero` está restringido
  a `'ACCION'` (no se manejan bonos ni ETFs).
- **Solo mercados de EE.UU.** (NYSE, NASDAQ) — limitación por la cobertura del
  plan gratuito de Finnhub para datos en tiempo real fuera de EE.UU.
- **Jerarquía**: `Categoria_Instrumento.id_categoria_padre` forma un árbol de
  3 niveles (Acciones → Sector → Perfil de riesgo por capitalización).
- **M:N con atributos propios**: `Posicion` (Cliente ↔ Instrumento_Financiero)
  y `Listado_Mercado` (Instrumento_Financiero ↔ Mercado_Bolsa).
- **Dimensión temporal**: `Cotizacion_Historica` (histórico diario) y
  `Precio_Tiempo_Real` (streaming en vivo).
- **Zona horaria**: la detección de horario de mercado usa `zoneinfo` con
  `America/New_York`. En Windows requiere el paquete `tzdata` (ya incluido
  en `requirements.txt`) para tener la base de datos de zonas horarias.

## Notas técnicas sobre la conexión a Railway (plan gratuito)

- Railway puede cerrar conexiones inactivas; todos los scripts implementan
  reconexión automática (`conexion_db.asegurar_conexion` /
  `conexion_db.reconectar_forzado`).
- Para operaciones masivas (carga inicial, simulación de órdenes), se sigue
  el patrón: **leer todo primero → calcular en memoria → escribir en un solo
  lote al final**, para minimizar el tiempo que la conexión permanece abierta.
- `streaming.py` usa un buffer en memoria + hilo separado que escribe a MySQL
  cada 5 segundos en lote, en vez de insertar cada trade individualmente.

## Trabajo en equipo (base de datos compartida en Railway)

- Antes de correr un script que modifique el esquema (`CREATE TABLE`,
  `ALTER TABLE`, `DROP TABLE`), avisar al equipo.
- Los `SELECT` se pueden correr en cualquier momento sin coordinación.
- Las credenciales del `.env` se comparten por un canal privado del equipo,
  nunca se suben a GitHub (`.env` está en `.gitignore`).