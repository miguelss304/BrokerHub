-- ================================================================
-- BrokerHub Proyecto Final Bases de Datos Sesión 3
-- 04_consultas_corregido.sql
-- Batería de consultas SQL organizada por nivel de complejidad
-- ================================================================

USE railway;


-- ================================================================
-- NIVEL 1 SELECCIÓN Y FILTRADO
-- ================================================================

-- ==============================================
-- N1-01: Qué órdenes de compra o venta se colocaron en el último
-- mes, con precio límite entre 20 y 500, que ya fueron ejecutadas
-- total o parcialmente?
-- ==============================================
SELECT o.id_orden, o.tipo_orden, o.cantidad, o.precio_limite,
       o.estado, o.fecha_hora
FROM Orden o
WHERE o.estado IN ('EJECUTADA', 'PARCIALMENTE_EJECUTADA')
  AND o.precio_limite BETWEEN 20 AND 500
  AND o.fecha_hora >= CURRENT_DATE - INTERVAL 1 MONTH
ORDER BY o.fecha_hora DESC;

-- ==============================================
-- N1-02: Qué clientes con perfil de riesgo AGRESIVO o MODERADO,
-- registrados entre 2023 y 2025, tienen un correo corporativo o de
-- Gmail? (Corregido: se eliminaron espacios en los LIKE)
-- ==============================================
SELECT id_cliente, nombre_completo, tipo_cliente, perfil_riesgo,
       correo, fecha_registro
FROM Cliente
WHERE perfil_riesgo IN ('AGRESIVO', 'MODERADO')
  AND fecha_registro BETWEEN '2023-01-01' AND '2025-12-31'
  AND (correo LIKE '%@gmail.com' OR correo LIKE '%.com.co')
ORDER BY fecha_registro;


-- ================================================================
-- NIVEL 2 JOINS MÚLTIPLES
-- ================================================================

-- ==============================================
-- N2-01: Qué instrumentos financieros existen, con su emisor y su
-- categoría de riesgo? (catálogo completo del mercado)
-- ==============================================
SELECT i.ticker, i.nombre AS instrumento, e.razon_social AS emisor,
       e.sector_economico, c.nombre AS categoria, c.nivel_riesgo
FROM Instrumento_Financiero i
INNER JOIN Emisor e ON e.id_emisor = i.id_emisor
INNER JOIN Categoria_Instrumento c ON c.id_categoria = i.id_categoria
ORDER BY c.nivel_riesgo, i.ticker;

-- ==============================================
-- N2-02: Qué instrumentos nunca han sido comprados por ningún
-- cliente?
-- ==============================================
-- Con INNER JOIN: solo aparecen los instrumentos que SÍ tienen posición
SELECT i.ticker, i.nombre, COUNT(p.id_cuenta) AS cuentas_que_lo_poseen
FROM Instrumento_Financiero i
INNER JOIN Posicion p ON p.id_instrumento = i.id_instrumento
GROUP BY i.id_instrumento, i.ticker, i.nombre;

-- Con LEFT JOIN: aparecen TODOS los instrumentos sin compras (cuentas = 0)
SELECT i.ticker, i.nombre, COUNT(p.id_cuenta) AS cuentas_que_lo_poseen
FROM Instrumento_Financiero i
LEFT JOIN Posicion p ON p.id_instrumento = i.id_instrumento
GROUP BY i.id_instrumento, i.ticker, i.nombre
HAVING cuentas_que_lo_poseen = 0;

-- ==============================================
-- N2-03: Cuál es el detalle completo de cada orden: cliente,
-- cuenta, instrumento y mercado donde cotiza?
-- ==============================================
SELECT o.id_orden, cl.nombre_completo, cu.tipo_cuenta,
       i.ticker, m.nombre AS mercado, o.tipo_orden, o.cantidad,
       o.precio_limite, o.estado
FROM Orden o
INNER JOIN Cuenta_Inversion cu ON cu.id_cuenta = o.id_cuenta
INNER JOIN Cliente cl ON cl.id_cliente = cu.id_cliente
INNER JOIN Instrumento_Financiero i ON i.id_instrumento = o.id_instrumento
INNER JOIN Listado_Mercado lm ON lm.id_instrumento = i.id_instrumento
INNER JOIN Mercado_Bolsa m ON m.id_mercado = lm.id_mercado
ORDER BY o.fecha_hora DESC;


-- ================================================================
-- NIVEL 3 AGREGACIÓN
-- ================================================================

-- ==============================================
-- N3-01: Cuánto dinero tienen invertido los clientes en cada
-- categoría de instrumento? (solo categorías con más de 1 posición abierta)
-- ==============================================
SELECT c.nombre AS categoria, c.nivel_riesgo,
       COUNT(p.id_cuenta) AS posiciones_abiertas,
       SUM(p.cantidad * p.precio_promedio_compra) AS monto_invertido
FROM Posicion p
JOIN Instrumento_Financiero i ON i.id_instrumento = p.id_instrumento
JOIN Categoria_Instrumento c ON c.id_categoria = i.id_categoria
GROUP BY c.id_categoria, c.nombre, c.nivel_riesgo
HAVING COUNT(p.id_cuenta) > 1
ORDER BY monto_invertido DESC;

-- ==============================================
-- N3-02: Cuánto ha pagado cada cliente en comisiones, mes a mes?
-- (Corregido: se eliminaron espacios en DATE_FORMAT)
-- ==============================================
SELECT cl.id_cliente, cl.nombre_completo,
       DATE_FORMAT(t.fecha_hora, '%Y-%m') AS mes,
       COUNT(t.id_transaccion) AS transacciones,
       SUM(t.comision) AS comision_total
FROM Transaccion_Ejecutada t
JOIN Orden o ON o.id_orden = t.id_orden
JOIN Cuenta_Inversion cu ON cu.id_cuenta = o.id_cuenta
JOIN Cliente cl ON cl.id_cliente = cu.id_cliente
GROUP BY cl.id_cliente, cl.nombre_completo, DATE_FORMAT(t.fecha_hora, '%Y-%m')
HAVING SUM(t.comision) > 0
ORDER BY mes, comision_total DESC;

-- ==============================================
-- N3-03: Cuál es el volumen histórico promedio y máximo negociado
-- por instrumento en cada mercado donde cotiza?
-- ==============================================
SELECT i.ticker, m.nombre AS mercado,
       ROUND(AVG(ch.volumen), 0) AS volumen_promedio,
       MAX(ch.volumen) AS volumen_maximo,
       MIN(ch.precio_cierre) AS precio_min_historico,
       MAX(ch.precio_cierre) AS precio_max_historico
FROM Cotizacion_Historica ch
JOIN Instrumento_Financiero i ON i.id_instrumento = ch.id_instrumento
JOIN Listado_Mercado lm ON lm.id_instrumento = i.id_instrumento
JOIN Mercado_Bolsa m ON m.id_mercado = lm.id_mercado
GROUP BY i.id_instrumento, i.ticker, m.id_mercado, m.nombre
ORDER BY volumen_promedio DESC;


-- ================================================================
-- NIVEL 4 SUBCONSULTAS Y COMPLETITUD
-- ================================================================

-- ==============================================
-- N4-01: Qué cuentas tienen un saldo disponible superior al
-- promedio de las cuentas de su mismo tipo?
-- ==============================================
SELECT cu.id_cuenta, cu.tipo_cuenta, cu.saldo_disponible, cl.nombre_completo
FROM Cuenta_Inversion cu
JOIN Cliente cl ON cl.id_cliente = cu.id_cliente
WHERE cu.saldo_disponible > (
    SELECT AVG(cu2.saldo_disponible)
    FROM Cuenta_Inversion cu2
    WHERE cu2.tipo_cuenta = cu.tipo_cuenta
)
ORDER BY cu.tipo_cuenta, cu.saldo_disponible DESC;

-- ==============================================
-- N4-02: Qué instrumentos nunca han recibido ni una sola orden de
-- ningún cliente? (NOT EXISTS)
-- ==============================================
SELECT i.ticker, i.nombre
FROM Instrumento_Financiero i
WHERE NOT EXISTS (
    SELECT 1
    FROM Orden o
    WHERE o.id_instrumento = i.id_instrumento
);

-- ==============================================
-- N4-03: Cuáles son los 5 clientes con mayor patrimonio total invertido?
-- (Completado: Lógica de agregación y límite de filas)
-- ==============================================
SELECT cl.id_cliente, cl.nombre_completo, 
       SUM(p.cantidad * p.precio_promedio_compra) AS patrimonio_invertido
FROM Cliente cl
JOIN Cuenta_Inversion cu ON cu.id_cliente = cl.id_cliente
JOIN Posicion p ON p.id_cuenta = cu.id_cuenta
GROUP BY cl.id_cliente, cl.nombre_completo
ORDER BY patrimonio_invertido DESC
LIMIT 5;


-- ==============================================
-- N4-04: Qué instrumentos estuvieron entre los de mayor volumen
-- negociado en el último trimestre? (subconsulta en la cláusula FROM)
-- ==============================================
ANALYZE TABLE Cotizacion_Historica UPDATE HISTOGRAM ON fecha WITH 100 BUCKETS;
EXPLAIN ANALYZE
SELECT resumen.ticker, resumen.volumen_trimestre
FROM (
    SELECT i.ticker, SUM(ch.volumen) AS volumen_trimestre
    FROM Cotizacion_Historica ch
    JOIN Instrumento_Financiero i ON i.id_instrumento = ch.id_instrumento
    WHERE ch.fecha >= CURRENT_DATE - INTERVAL 3 MONTH
    GROUP BY i.id_instrumento, i.ticker
) AS resumen
WHERE resumen.volumen_trimestre > 0
ORDER BY resumen.volumen_trimestre DESC
LIMIT 10;


-- ================================================================
-- NIVEL 5 FUNCIONES DE VENTANA
-- ================================================================

-- ==============================================
-- N5-01: Cómo se ranquean los clientes por monto total invertido
-- (posiciones abiertas), dentro de su propio perfil de riesgo?
-- ==============================================
SELECT cl.nombre_completo, cl.perfil_riesgo,
       ROUND(SUM(p.cantidad * p.precio_promedio_compra), 2) AS monto_invertido,
       RANK() OVER (
           PARTITION BY cl.perfil_riesgo
           ORDER BY SUM(p.cantidad * p.precio_promedio_compra) DESC
       ) AS ranking_en_su_perfil
FROM Posicion p
JOIN Cuenta_Inversion cu ON cu.id_cuenta = p.id_cuenta
JOIN Cliente cl ON cl.id_cliente = cu.id_cliente
GROUP BY cl.id_cliente, cl.nombre_completo, cl.perfil_riesgo
ORDER BY cl.perfil_riesgo, ranking_en_su_perfil;

-- ==============================================
-- N5-02: Día a día, cuánto varió porcentualmente el precio de
-- cierre de cada instrumento frente al día anterior? (LAG)
-- ==============================================
CREATE INDEX idx_cotizacion_instrumento_fecha
ON Cotizacion_Historica (id_instrumento, fecha);
-- (si ya la creaste para la consulta 1, esta línea es la misma, no la dupliques)

-- Reescritura de la consulta N5-02
WITH precios_con_lag AS (
    SELECT
        ch.id_instrumento,
        ch.fecha,
        ch.precio_cierre,
        LAG(ch.precio_cierre) OVER (
            PARTITION BY ch.id_instrumento ORDER BY ch.fecha
        ) AS precio_cierre_dia_anterior
    FROM Cotizacion_Historica ch
)
SELECT
    i.ticker,
    p.fecha,
    p.precio_cierre,
    p.precio_cierre_dia_anterior,
    ROUND(
        100 * (p.precio_cierre - p.precio_cierre_dia_anterior)
        / p.precio_cierre_dia_anterior, 2
    ) AS variacion_porcentual
FROM precios_con_lag p
JOIN Instrumento_Financiero i ON i.id_instrumento = p.id_instrumento
ORDER BY i.ticker, p.fecha;
-- ==============================================
-- N5-03: Para cada cuenta, cuál es el acumulado de comisiones
-- pagadas a lo largo del tiempo? (suma acumulada con SUM() OVER)
-- ==============================================
SELECT cu.id_cuenta, cl.nombre_completo, t.fecha_hora, t.comision,
       SUM(t.comision) OVER (
           PARTITION BY cu.id_cuenta ORDER BY t.fecha_hora
       ) AS comision_acumulada
FROM Transaccion_Ejecutada t
JOIN Orden o ON o.id_orden = t.id_orden
JOIN Cuenta_Inversion cu ON cu.id_cuenta = o.id_cuenta
JOIN Cliente cl ON cl.id_cliente = cu.id_cliente
ORDER BY cu.id_cuenta, t.fecha_hora;


-- ================================================================
-- NIVEL 6 VISTAS
-- ================================================================

-- ==============================================
-- N6-01: Vista que encapsula el portafolio consolidado de cada
-- cliente (posiciones + valor en libros)
-- ==============================================
CREATE OR REPLACE VIEW vw_portafolio_cliente AS
SELECT cl.id_cliente, cl.nombre_completo, cu.id_cuenta, cu.tipo_cuenta,
       i.ticker, i.nombre AS instrumento, p.cantidad,
       p.precio_promedio_compra,
       ROUND(p.cantidad * p.precio_promedio_compra, 2) AS valor_en_libros,
       p.fecha_primera_compra
FROM Posicion p
JOIN Cuenta_Inversion cu ON cu.id_cuenta = p.id_cuenta
JOIN Cliente cl ON cl.id_cliente = cu.id_cliente
JOIN Instrumento_Financiero i ON i.id_instrumento = p.id_instrumento;

-- Ejemplo de uso de la vista:
-- SELECT * FROM vw_portafolio_cliente WHERE id_cliente = 1;

-- ==============================================
-- N6-02: Vista que resume, por instrumento, cuántas órdenes hay en
-- cada estado para simplificar el monitoreo operativo
-- ==============================================
CREATE OR REPLACE VIEW vw_resumen_ordenes_por_instrumento AS
SELECT i.ticker, i.nombre AS instrumento, o.estado,
       COUNT(*) AS cantidad_ordenes,
       SUM(o.cantidad) AS unidades_totales,
       ROUND(AVG(o.precio_limite), 4) AS precio_limite_promedio
FROM Orden o
JOIN Instrumento_Financiero i ON i.id_instrumento = o.id_instrumento
GROUP BY i.id_instrumento, i.ticker, i.nombre, o.estado;

-- Ejemplo de uso de la vista:
-- SELECT * FROM vw_resumen_ordenes_por_instrumento WHERE estado = 'PENDIENTE';
-- ================================================================
-- OPTIMIZACIÓN: ÍNDICES RECOMENDADOS PARA ESTA BATERÍA
-- Ejecuta esto si notas lentitud en la carga de datos masiva
-- ================================================================
CREATE INDEX idx_orden_busqueda ON Orden (estado, precio_limite, fecha_hora);
CREATE INDEX idx_cliente_riesgo_fecha ON Cliente (perfil_riesgo, fecha_registro);
CREATE INDEX idx_cuenta_tipo_saldo ON Cuenta_Inversion (tipo_cuenta, saldo_disponible);
CREATE INDEX idx_cotizacion_volumen ON Cotizacion_Historica (id_instrumento, volumen);
