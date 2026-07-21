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
├── broker_esquema_mysql.sql  # DDL: crea las 12 tablas del modelo
│
├── conexion_db.py                # conexión reutilizable a MySQL + reconexión automática
├── cliente_finnhub.py            # funciones REST a Finnhub + histórico vía yfinance
│
├── carga_inicial.py              # puebla Emisor, Instrumento, Categoría, Cotización, Listado
├── actualizar_historico.py       # trae los días nuevos que falten en Cotizacion_Historica
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

## 1. Instalación

```bash
pip install -r requirements.txt
```

Los comandos de este README usan `py` (launcher de Windows). Si tu instalación
usa `python`, reemplázalo en cada comando.

## 2. Configurar credenciales

Crea`.env` y completa con los valores reales:

```
MYSQLHOST=tokaido.proxy.rlwy.net
MYSQLPORT=45849
MYSQLUSER=root
MYSQLPASSWORD=<password de Railway>
MYSQLDATABASE=railway

FINNHUB_API_KEY=<api key de Finnhub>
```

Las credenciales de Railway están en el servicio de MySQL → pestaña **Variables**
(usuario/password) y pestaña **Networking → Public Networking** (host/puerto).
La API key de Finnhub se obtiene gratis en [finnhub.io](https://finnhub.io).

## 3. Crear el esquema de la base de datos

Abre `broker_esquema_mysql.sql` en MySQL Workbench (conectado a Railway)
y ejecútalo completo. El script usa `USE railway;` (esa es la base de datos
real en Railway; "BrokerHub" es solo el nombre del proyecto). Crea las 12
tablas del modelo, empezando por borrar cualquier tabla existente con esos
nombres (en el orden correcto por las llaves foráneas).

## 4. Orden de ejecución de los scripts

Cada script se puede volver a correr sin duplicar datos (usan "buscar o
crear", `INSERT IGNORE` o `ON DUPLICATE KEY`):

```bash
# 1. Datos reales de mercado: Emisor, Instrumento, Categoría, Cotización, Listado
py carga_inicial.py

# 1.5. (Correr periódicamente, ej. una vez al día) Trae los días nuevos
#      que falten en Cotizacion_Historica, sin repetir todo el histórico.
py actualizar_historico.py

# 2. Clientes y cuentas sintéticas
py generador_faker.py

# 3. Órdenes, transacciones y posiciones (usa los precios reales ya cargados)
#    Quedan en estado EJECUTADA -- es la simulación del historial del proyecto.
py simulador_ordenes.py

# 4. Streaming en vivo (dejar corriendo durante la demo, en su propia terminal)
py streaming.py

# 5. Ejecutor de órdenes en tiempo real (dejar corriendo, en OTRA terminal)
#    Revisa cada 5s las Órdenes PENDIENTE y las ejecuta si el precio en vivo
#    (o el último cierre histórico como respaldo) cumple el precio_limite.
py ejecutor_ordenes.py

# 6. (Pruebas/demo) Coloca una Orden nueva en estado PENDIENTE, para ver
#    cómo el ejecutor la resuelve en el siguiente ciclo.
py colocar_orden.py

# 7. API (en su propia terminal): expone todo por HTTP
uvicorn main:app --reload
```

### Correr varios scripts a la vez (streaming + ejecutor)

`streaming.py` y `ejecutor_ordenes.py` corren **al mismo tiempo, en terminales
separadas**. En VS Code: `Terminal → New Terminal` (o el botón `+` del panel
de terminal) para abrir una pestaña nueva por cada script, sin cerrar las
anteriores.

`streaming.py` solo recibe trades cuando el mercado de EE.UU. está abierto
(lunes a viernes, 9:30 AM - 4:00 PM hora de Nueva York). Fuera de ese
horario, el WebSocket queda conectado pero sin mensajes.

## 5. Verificación rápida en MySQL Workbench

```sql
SELECT COUNT(*) FROM Cliente;
SELECT COUNT(*) FROM Instrumento_Financiero;
SELECT COUNT(*) FROM Cotizacion_Historica;
SELECT COUNT(*) FROM Orden;
SELECT COUNT(*) FROM Posicion;
SELECT COUNT(*) FROM Precio_Tiempo_Real;  -- solo tiene datos si streaming.py corrió en horario de mercado

-- Órdenes por estado
SELECT estado, COUNT(*) FROM Orden GROUP BY estado;
```

## Motor de ejecución de órdenes en tiempo real

`ejecutor_ordenes.py` hace que el sistema reaccione en vivo:

1. Un cliente coloca una `Orden` (queda en estado `PENDIENTE`) — ver `colocar_orden.py`.
2. `streaming.py` llena `Precio_Tiempo_Real` con datos reales de Finnhub.
3. `ejecutor_ordenes.py` revisa cada 5 segundos las órdenes `PENDIENTE` y las
   compara contra el último precio conocido de su instrumento:
   - **COMPRA** se ejecuta si `precio_actual <= precio_limite`
   - **VENTA** se ejecuta si `precio_actual >= precio_limite`
   - Si no hay ningún precio en vivo (mercado cerrado), usa como respaldo el
     último `precio_cierre` de `Cotizacion_Historica`.
4. Al ejecutarse: crea la `Transaccion_Ejecutada`, actualiza
   `saldo_disponible` de la cuenta, actualiza (o crea) la `Posicion` de esa
   cuenta, y marca la `Orden` como `EJECUTADA`.

`streaming.py` y `ejecutor_ordenes.py` están pensados para correr en paralelo
de forma indefinida.

## Consistencia del "precio actual" (horario de mercado)

`main.py` (API) y `ejecutor_ordenes.py` usan la misma lógica para decidir
qué es el "precio actual" de un instrumento:

- Si el mercado está abierto (lunes-viernes, 9:30 AM - 4:00 PM hora de
  Nueva York) **y** hay datos en `Precio_Tiempo_Real`, se usa el último trade.
- Si el mercado está cerrado, o aún no ha llegado ningún dato en vivo, se usa
  el último `precio_cierre` de `Cotizacion_Historica`.

Por esto, `Cotizacion_Historica` debe mantenerse al día corriendo
`actualizar_historico.py` periódicamente — si no, el respaldo fuera de
horario queda desactualizado.

## Notas sobre streaming.py (trades duplicados)

`Precio_Tiempo_Real` tiene como clave primaria `(id_instrumento, fecha_hora)`,
con precisión de segundos. Si llegan dos trades del mismo instrumento en el
mismo segundo, se usa `INSERT IGNORE` para descartar el duplicado sin tumbar
el lote completo. El hilo escritor está envuelto en un manejo de errores
general para que nunca muera en silencio.

## API (FastAPI)

`main.py` expone el sistema por HTTP, para que cualquier interfaz (o
herramienta como Postman) pueda consultar y operar sobre la base sin
escribir SQL ni correr scripts a mano.

### Cómo correrla

```bash
uvicorn main:app --reload
```

Documentación interactiva:
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

- CORS habilitado (`allow_origins=["*"]`), para que cualquier interfaz pueda
  consultarla desde el navegador sin bloqueos.
- Los errores de conexión a MySQL se traducen a un `503` con mensaje claro,
  en vez de un traceback de Python.
- Validaciones relacionadas con `tipo_cliente` y `perfil_riesgo` quedan fuera
  del `POST /ordenes` hasta que se defina la interfaz final.

### Despliegue en Railway

La API está desplegada en Railway (mismo proyecto que el servicio de MySQL),
accesible públicamente.

- El `Procfile` indica cómo arrancar la API:
  ```
  web: uvicorn main:app --host 0.0.0.0 --port $PORT
  ```
- Las variables de entorno (`MYSQLHOST`, `FINNHUB_API_KEY`, etc.) se
  configuran en la pestaña **Variables** del servicio de la API en Railway.
- El dominio público se genera en **Settings → Networking → Generate Domain**.
- Para verificar que sigue viva: `<url-de-railway>/health` debe responder
  `{"status": "ok", "database": "conectada"}`.

`streaming.py` y `ejecutor_ordenes.py` corren localmente (no están
desplegados en Railway); solo `main.py` (la API) vive en la nube.

## Funcionalidades futuras (fuera del alcance actual)

- **Interfaz de usuario**: opción considerada, un dashboard con Streamlit
  consumiendo los endpoints de `main.py`. Pendiente de decisión.
- **Sugerencia por perfil de riesgo**: comparar `Cliente.perfil_riesgo`
  contra `Categoria_Instrumento.nivel_riesgo` para mostrar una advertencia
  al colocar una orden (no bloquear, solo sugerir).
- Ejecución parcial de órdenes (`PARCIALMENTE_EJECUTADA`) — el ejecutor
  actual solo resuelve órdenes completas (todo o nada).

## Notas de diseño del modelo

- **Solo acciones**: el campo `tipo` de `Instrumento_Financiero` está
  restringido a `'ACCION'` (no se manejan bonos ni ETFs).
- **Solo mercados de EE.UU.** (NYSE, NASDAQ) — limitación por la cobertura
  del plan gratuito de Finnhub para datos en tiempo real fuera de EE.UU.
- **Jerarquía**: `Categoria_Instrumento.id_categoria_padre` forma un árbol
  de 3 niveles (Acciones → Sector → Perfil de riesgo por capitalización).
- **M:N con atributos propios**: `Posicion` (Cuenta_Inversion ↔
  Instrumento_Financiero) y `Listado_Mercado` (Instrumento_Financiero ↔
  Mercado_Bolsa). El portafolio de un cliente se consulta uniendo `Posicion`
  con `Cuenta_Inversion`, ya que un cliente puede tener varias cuentas y
  cada una lleva sus propias posiciones.
- **Dimensión temporal**: `Cotizacion_Historica` (histórico diario) y
  `Precio_Tiempo_Real` (streaming en vivo).
- **Zona horaria**: la detección de horario de mercado usa `zoneinfo` con
  `America/New_York`. En Windows requiere el paquete `tzdata` (incluido en
  `requirements.txt`).

## Notas técnicas sobre la conexión a Railway (plan gratuito)

- Railway puede cerrar conexiones inactivas; todos los scripts implementan
  reconexión automática (`conexion_db.asegurar_conexion` /
  `conexion_db.reconectar_forzado`).
- Para operaciones masivas (carga inicial, simulación de órdenes), se sigue
  el patrón: leer todo primero → calcular en memoria → escribir en un solo
  lote al final, para minimizar el tiempo que la conexión permanece abierta.
- `streaming.py` usa un buffer en memoria + hilo separado que escribe a
  MySQL cada 5 segundos en lote, en vez de insertar cada trade
  individualmente.
- `information_schema.TABLES.AUTO_INCREMENT` puede devolver `NULL` en una
  tabla recién creada y vacía (antes de que MySQL actualice sus estadísticas
  internas). `simulador_ordenes.py` asume `1` en ese caso.

## Trabajo en equipo (base de datos compartida en Railway)

- Antes de correr un script que modifique el esquema (`CREATE TABLE`,
  `ALTER TABLE`, `DROP TABLE`), avisar al equipo.
- Los `SELECT` se pueden correr en cualquier momento sin coordinación.
- Las credenciales del `.env` se comparten por un canal privado del equipo,
  nunca se suben a GitHub (`.env` está en `.gitignore`).