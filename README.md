# BrokerHub — Proyecto Final Bases de Datos

Plataforma de corretaje de inversiones desarrollada en Python con FastAPI,
MySQL, datos reales de Finnhub/yfinance y datos sintéticos generados con Faker.
El proyecto está centrado en acciones de EEUU (NYSE/NASDAQ), streaming de
precios en vivo y ejecución automática de órdenes.

## Estructura del proyecto

```
BrokerHub/
├── .env                          # credenciales reales (NO se sube a git)
├── .env.example                  # plantilla de variables necesarias
├── .gitignore
├── requirements.txt
│
├── broker_esquema_mysql.sql      # DDL: crea las 12 tablas del modelo
├── trigger_procs_func.sql        # Triggers, procedimientos y funciones almacenadas
│
├── auth.py                       # seguridad JWT/Bcrypt
├── conexion_db.py                # conexión reutilizable y reconexión a MySQL
├── utils_mercado.py              # lógica compartida de horario de mercado
├── cliente_finnhub.py            # consumo de Finnhub y yfinance
│
├── carga_inicial.py              # puebla mercados, emisores, instrumentos y cotizaciones
├── actualizar_historico.py       # actualiza Cotizacion_Historica periódicamente
├── generador_faker.py            # genera clientes, credenciales y cuentas sintéticas
├── simulador_ordenes.py          # genera historial de órdenes ejecutadas
├── streaming.py                  # WebSocket en vivo a Finnhub
├── ejecutor_ordenes.py           # motor de ejecución de órdenes PENDIENTES
├── colocar_orden.py              # utilidad para colocar una orden de prueba
├── main.py                       # API REST con FastAPI
├── streamlit_app.py              # UI de ejemplo basada en la API
├── reiniciar_todo.py             # resetea y repuebla la base de datos
│
└── Procfile                      # comando de arranque para Railway
```

## 1. Instalación

```bash
pip install -r requirements.txt
```

> En Windows el README original usa `py`; si tu instalación no tiene `py`,
> reemplaza `py` por `python` en los comandos.

## 2. Configurar credenciales

Crea un archivo `.env` con los valores reales:

```env
MYSQLHOST=tokaido.proxy.rlwy.net
MYSQLPORT=45849
MYSQLUSER=root
MYSQLPASSWORD=<password de Railway>
MYSQLDATABASE=railway
FINNHUB_API_KEY=<api key de Finnhub>
JWT_SECRET_KEY=<secret para tokens JWT>
```

Las credenciales de Railway se obtienen desde el servicio de MySQL:
- **Variables**: usuario/password
- **Networking → Public Networking**: host/puerto

La API key de Finnhub se obtiene en [finnhub.io](https://finnhub.io).

## 3. Crear el esquema de la base de datos

Abre `broker_esquema_mysql.sql` en MySQL Workbench conectado a Railway y
 ejecútalo completo. El script contiene `USE railway;` y crea las 12 tablas
del modelo, eliminando tablas existentes en el orden correcto según las
llaves foráneas.

## 4. Orden de ejecución de los scripts

Cada script se puede volver a ejecutar sin duplicar datos gracias a
"buscar o crear", `INSERT IGNORE` y `ON DUPLICATE KEY`.

```bash
# 1. Carga inicial de mercado: emisores, instrumentos, listados y precios históricos
py carga_inicial.py

# 1.5. Actualizar periódicamente el histórico sin repetir todo el dataset
py actualizar_historico.py

# 2. Generar clientes, credenciales y cuentas sintéticas
py generador_faker.py

# 3. Simular órdenes ejecutadas y generar historial
py simulador_ordenes.py

# 4. Iniciar streaming en vivo de Finnhub
py streaming.py

# 5. Iniciar el motor de ejecución de órdenes en tiempo real
py ejecutor_ordenes.py

# 6. Probar el flujo colocando una orden PENDIENTE
py colocar_orden.py

# 7. Levantar la API localmente
uvicorn main:app --reload
```

### Streaming y ejecutor en paralelo

`streaming.py` y `ejecutor_ordenes.py` deben ejecutarse en terminales
separadas. En VS Code, usa `Terminal → New Terminal` o el botón `+`.

`streaming.py` recibe datos solo durante el horario de mercado de EE.UU.:
lunes a viernes, 9:30 AM - 4:00 PM hora de Nueva York. Fuera de ese
término el WebSocket permanece conectado sin enviar trades.

## 5. Verificación rápida en MySQL Workbench

```sql
SELECT COUNT(*) FROM Cliente;
SELECT COUNT(*) FROM Instrumento_Financiero;
SELECT COUNT(*) FROM Cotizacion_Historica;
SELECT COUNT(*) FROM Orden;
SELECT COUNT(*) FROM Posicion;
SELECT COUNT(*) FROM Precio_Tiempo_Real;  -- solo si streaming.py corrió en horario de mercado

SELECT estado, COUNT(*) FROM Orden GROUP BY estado;
```

## 6. Motor de ejecución de órdenes en tiempo real

`ejecutor_ordenes.py` procesa órdenes pendientes en ciclos de 5 segundos:

1. Un cliente coloca una `Orden` en estado `PENDIENTE` (`colocar_orden.py` o `POST /ordenes`).
2. `streaming.py` escribe ticks reales en `Precio_Tiempo_Real`.
3. El ejecutor obtiene el último precio conocido de cada instrumento.
4. Se ejecuta la orden si la condición se cumple:
   - `COMPRA` si `precio_actual <= precio_limite`
   - `VENTA` si `precio_actual >= precio_limite`
5. Si no hay precio en vivo, usa el último `precio_cierre` de
   `Cotizacion_Historica` como respaldo.

Al ejecutarse, el sistema:
- crea `Transaccion_Ejecutada`
- actualiza `saldo_disponible` de la cuenta
- actualiza o crea `Posicion`
- marca la `Orden` como `EJECUTADA`

`streaming.py` y `ejecutor_ordenes.py` están diseñados para correr indefinidamente
en paralelo.

## 7. Consistencia del precio actual

`main.py` y `ejecutor_ordenes.py` usan la misma regla de horario de mercado en
`utils_mercado.py`:

- Si el mercado está abierto y hay datos en `Precio_Tiempo_Real`, se usa el
  último trade.
- Si el mercado está cerrado o no hay precio en vivo, se usa el último
  `precio_cierre` de `Cotizacion_Historica`.

Por eso es importante correr `actualizar_historico.py` periódicamente: el
respaldo fuera de horario depende del cierre histórico.

## 8. Notas sobre `streaming.py`

`Precio_Tiempo_Real` usa clave primaria `(id_instrumento, fecha_hora)` con
precisión de segundos. Si llegan dos trades del mismo ticker en el mismo
segundo, `INSERT IGNORE` descarta el duplicado sin fallar el lote.

El hilo de escritura está protegido con manejo de errores para que no muera
silenciosamente.

## 9. API (FastAPI)

`main.py` expone la API REST del sistema. La mayoría de endpoints de cliente y
cuenta requieren autenticación JWT.

### Cómo correrla

```bash
uvicorn main:app --reload
```

Documentación interactiva:

```text
http://127.0.0.1:8000/docs
```

### Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Verifica que la API y la base de datos respondan |
| POST | `/auth/registro` | Registra un cliente, crea credenciales y cuenta inicial |
| POST | `/auth/login` | Autentica un usuario y devuelve token JWT |
| GET | `/clientes` | Lista todos los clientes |
| GET | `/clientes/{id_cliente}` | Datos de un cliente específico |
| PUT | `/clientes/{id_cliente}` | Actualiza nombre, correo o perfil de riesgo |
| GET | `/clientes/{id_cliente}/cuentas` | Cuentas de inversión de un cliente |
| GET | `/clientes/{id_cliente}/portafolio` | Posiciones actuales y P&L no realizado |
| GET | `/clientes/{id_cliente}/ordenes` | Historial de órdenes de un cliente |
| GET | `/clientes/{id_cliente}/perfil-real` | Perfil real estimado según las posiciones |
| POST | `/cuentas` | Abre una nueva cuenta de inversión |
| GET | `/cuentas/{id_cuenta}/saldo` | Consulta saldo disponible |
| POST | `/cuentas/{id_cuenta}/depositos` | Deposita fondos en la cuenta |
| POST | `/cuentas/{id_cuenta}/retiros` | Retira fondos de la cuenta |
| GET | `/cuentas/{id_cuenta}/ordenes` | Órdenes de una cuenta |
| GET | `/cuentas/{id_cuenta}/posiciones` | Posiciones abiertas de una cuenta |
| GET | `/cuentas/{id_cuenta}/valor-portafolio` | Valor de mercado del portafolio |
| GET | `/cuentas/{id_cuenta}/rentabilidad` | Rentabilidad estimada del portafolio |
| GET | `/cuentas/{id_cuenta}/movimientos` | Historial de movimientos |
| GET | `/instrumentos` | Lista de instrumentos disponibles |
| GET | `/instrumentos/{id_instrumento}` | Detalle de instrumento por ID |
| GET | `/instrumentos/{id_instrumento}/cotizaciones` | Histórico filtrable por fechas |
| GET | `/instrumentos/{id_instrumento}/precios-vivo` | Ticks de precio en vivo recientes |
| GET | `/instrumentos/{ticker}/precio-actual` | Último precio conocido (vivo/histórico) |
| GET | `/instrumentos/{ticker}/historico` | Histórico diario de un ticker |
| POST | `/ordenes` | Coloca una orden en estado `PENDIENTE` |
| GET | `/ordenes/{id_orden}` | Detalle de orden y sus transacciones |
| DELETE | `/ordenes/{id_orden}` | Cancela una orden `PENDIENTE` |

### Notas de diseño

- CORS habilitado (`allow_origins=["*"]`).
- Errores de conexión a MySQL devuelven `503` con mensaje claro.
- Las validaciones de `tipo_cliente` y `perfil_riesgo` no bloquean aún `POST /ordenes`.
- `POST /auth/login` actualiza `ultimo_acceso`, pero no falla si ese update fallara.

### Despliegue en Railway

- `Procfile`:
  ```text
  web: uvicorn main:app --host 0.0.0.0 --port $PORT
  ```
- Variables de entorno en Railway: `MYSQLHOST`, `MYSQLPORT`, `MYSQLUSER`,
  `MYSQLPASSWORD`, `MYSQLDATABASE`, `FINNHUB_API_KEY`, `JWT_SECRET_KEY`, etc.
- Para verificarlo, llama a `<url-de-railway>/health`.

> Nota: `streaming.py` y `ejecutor_ordenes.py` se ejecutan localmente. Solo
> `main.py` se despliega en Railway.

## 10. UI de ejemplo con Streamlit

`streamlit_app.py` es una interfaz de ejemplo que consume la API.
Por defecto usa `BROKERHUB_API_URL` para apuntar a la API desplegada o una URL
local según la configuración.

Para ejecutarla:

```bash
streamlit run streamlit_app.py
```

## 11. Funcionalidades futuras (fuera del alcance actual)

- Dashboard oficial con Streamlit.
- Sugerencias de riesgo comparando `Cliente.perfil_riesgo` y
  `Categoria_Instrumento.nivel_riesgo`.
- Ejecución parcial de órdenes (`PARCIALMENTE_EJECUTADA`).

## 12. Notas de diseño del modelo

- **Solo acciones**: `Instrumento_Financiero.tipo` es `'ACCION'`.
- **Solo mercados de EE.UU.**: NYSE y NASDAQ.
- **Jerarquía**: `Categoria_Instrumento.id_categoria_padre` forma un árbol de
  3 niveles.
- **M:N con atributos propios**: `Posicion` y `Listado_Mercado`.
- **Dimensión temporal**: `Cotizacion_Historica` + `Precio_Tiempo_Real`.
- **Zona horaria**: `America/New_York` con `zoneinfo` y `tzdata` en Windows.

## 13. Notas técnicas para Railway

- Railway puede cerrar conexiones inactivas; los scripts usan reconexión
  automática en `conexion_db.py`.
- Para cargas masivas se usa: leer primero → calcular en memoria → escribir
  en lote.
- `streaming.py` escribe en lote cada 5 segundos.
- `simulador_ordenes.py` maneja el caso en que
  `information_schema.TABLES.AUTO_INCREMENT` devuelve `NULL`.

## 14. Reinicio completo de la base

`reiniciar_todo.py` reinicia la base y ejecuta:
- `broker_esquema_mysql.sql`
- `trigger_procs_func.sql`
- `carga_inicial.py`
- `generador_faker.py`
- `simulador_ordenes.py`

> ADVERTENCIA: esto borra toda la base de datos `railway` y la recrea vacía.
> Confirma con el equipo antes de ejecutarlo.

## 15. Trabajo en equipo

- Antes de correr scripts que modifiquen el esquema, avisa al equipo.
- Los `SELECT` se pueden ejecutar en cualquier momento.
- `.env` nunca se sube a GitHub; compártelo por canal privado.
