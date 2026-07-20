# BrokerHub — Proyecto Final Bases de Datos

Plataforma de corretaje de inversiones (broker bursátil), enfocada en acciones
de mercados de Estados Unidos (NYSE/NASDAQ), con datos reales de Finnhub y
yfinance, y datos sintéticos generados con Faker.

## Estructura del proyecto

```
BrokerHub/
├── .env                          # credenciales reales (NO se sube a git)
├── .gitignore
├── requirements.txt
│
├── broker_esquema_mysql.sql      # DDL: crea las 12 tablas del modelo
│
├── conexion_db.py                # conexión reutilizable a MySQL + reconexión automática
├── cliente_finnhub.py            # funciones REST a Finnhub + histórico vía yfinance
│
├── carga_inicial.py              # puebla Emisor, Instrumento, Categoría, Cotización, Listado
├── generador_faker.py            # genera Cliente y Cuenta_Inversion sintéticos
├── simulador_ordenes.py          # genera Orden, Transaccion_Ejecutada, Posicion
├── streaming.py                  # WebSocket en vivo -> Precio_Tiempo_Real
│
└── exploracion_finnhub.ipynb     # notebook para explorar/visualizar datos con pandas
```

## 1. Instalación (una sola vez)

```bash
pip install -r requirements.txt
```

## 2. Configurar credenciales

Completa con tus valores reales:

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

# 2. Clientes y cuentas sintéticas
python generador_faker.py

# 3. Órdenes, transacciones y posiciones (usa los precios reales ya cargados)
python simulador_ordenes.py

# 4. Streaming en vivo (dejar corriendo durante la demo)
python streaming.py
```

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
```

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