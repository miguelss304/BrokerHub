-- ============================================================
-- Reglas de negocio: TRIGGERS, FUNCIONES y PROCEDIMIENTOS
-- Proyecto Final BD - Sesion 3
-- ============================================================

USE railway;

-- ============================================================
-- TABLA AUXILIAR DE AUDITORIA
-- ============================================================
CREATE TABLE IF NOT EXISTS Bitacora_Movimiento_Cuenta (
    id_movimiento     INT AUTO_INCREMENT PRIMARY KEY,
    id_cuenta         INT NOT NULL,
    id_transaccion    INT NOT NULL,
    tipo_movimiento   VARCHAR(10) NOT NULL,   -- 'COMPRA' o 'VENTA'
    monto             NUMERIC(16,2) NOT NULL,
    saldo_resultante  NUMERIC(16,2) NOT NULL,
    fecha_hora        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_tipo_movimiento CHECK (tipo_movimiento IN ('COMPRA','VENTA')),
    FOREIGN KEY (id_cuenta) REFERENCES Cuenta_Inversion(id_cuenta)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (id_transaccion) REFERENCES Transaccion_Ejecutada(id_transaccion)
        ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS Reporte_Riesgo_Cuenta (
    id_reporte        INT AUTO_INCREMENT PRIMARY KEY,
    id_cuenta         INT NOT NULL,
    saldo_disponible  NUMERIC(16,2) NOT NULL,
    valor_portafolio  NUMERIC(16,2) NOT NULL,
    valor_total       NUMERIC(16,2) NOT NULL,
    fecha_generacion  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TRIGGER 1
-- Regla de negocio: una orden de COMPRA no puede registrarse si
-- la cuenta no tiene saldo_disponible suficiente para cubrirla
-- (cantidad * precio_limite). No es expresable con CHECK porque
-- involucra datos de OTRA tabla (Cuenta_Inversion).
--
-- Evento: BEFORE INSERT ON Orden, FOR EACH ROW
-- ============================================================
DELIMITER $$

CREATE TRIGGER trg_validar_saldo_compra
BEFORE INSERT ON Orden
FOR EACH ROW
BEGIN
    DECLARE v_saldo NUMERIC(16,2);
    DECLARE v_monto_requerido NUMERIC(16,2);

    IF NEW.tipo_orden = 'COMPRA' THEN
        SELECT saldo_disponible INTO v_saldo
        FROM Cuenta_Inversion
        WHERE id_cuenta = NEW.id_cuenta;

        SET v_monto_requerido = NEW.cantidad * NEW.precio_limite;

        IF v_saldo < v_monto_requerido THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Saldo insuficiente en la cuenta para registrar la orden de compra.';
        END IF;
    END IF;
END$$

DELIMITER ;

-- Caso de prueba POSITIVO (se espera que inserte sin error):
-- INSERT INTO Orden (id_cuenta, id_instrumento, tipo_orden, cantidad, precio_limite)
-- VALUES (1, 1, 'COMPRA', 10, 5.00);  -- si saldo_disponible >= 50.00

-- Caso de prueba NEGATIVO (se espera SIGNAL / error 45000):
-- INSERT INTO Orden (id_cuenta, id_instrumento, tipo_orden, cantidad, precio_limite)
-- VALUES (1, 1, 'COMPRA', 999999, 999999.99);


-- ============================================================
-- TRIGGER 2
-- Regla de negocio: no se permiten transiciones de estado
-- invalidas en una Orden. Una orden EJECUTADA o CANCELADA es un
-- estado terminal y no puede volver a PENDIENTE ni a
-- PARCIALMENTE_EJECUTADA. Tampoco una CANCELADA puede pasar a
-- EJECUTADA. No es expresable con CHECK porque depende del
-- valor ANTERIOR de la fila (OLD vs NEW).
--
-- Evento: BEFORE UPDATE ON Orden, FOR EACH ROW
-- ============================================================
DELIMITER $$

CREATE TRIGGER trg_validar_transicion_estado_orden
BEFORE UPDATE ON Orden
FOR EACH ROW
BEGIN
    IF OLD.estado IN ('EJECUTADA','CANCELADA') AND NEW.estado <> OLD.estado THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Transicion de estado invalida: una orden EJECUTADA o CANCELADA no puede cambiar de estado.';
    END IF;

    IF OLD.estado = 'PARCIALMENTE_EJECUTADA' AND NEW.estado = 'PENDIENTE' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Transicion de estado invalida: una orden parcialmente ejecutada no puede volver a PENDIENTE.';
    END IF;
END$$

DELIMITER ;

-- Caso de prueba POSITIVO:
-- UPDATE Orden SET estado = 'PARCIALMENTE_EJECUTADA' WHERE id_orden = 1 AND estado = 'PENDIENTE';

-- Caso de prueba NEGATIVO:
-- UPDATE Orden SET estado = 'PENDIENTE' WHERE id_orden = 1 AND estado = 'EJECUTADA';


-- ============================================================
-- TRIGGER 3
-- Regla de negocio: cuando se ejecuta una transaccion, se debe
-- actualizar automaticamente (a) el saldo_disponible de la
-- cuenta, (b) la posicion del cliente en ese instrumento
-- (crear, aumentar o disminuir/eliminar) y (c) registrar el
-- movimiento en la bitacora de auditoria.
--
-- Evento: AFTER INSERT ON Transaccion_Ejecutada, FOR EACH ROW
-- ============================================================
DELIMITER $$

CREATE TRIGGER trg_actualizar_posicion_saldo
AFTER INSERT ON Transaccion_Ejecutada
FOR EACH ROW
BEGIN
    DECLARE v_id_cuenta INT;
    DECLARE v_id_instrumento INT;
    DECLARE v_tipo_orden VARCHAR(6);
    DECLARE v_monto NUMERIC(16,2);
    DECLARE v_cantidad_actual INT;
    DECLARE v_precio_prom_actual NUMERIC(14,4);
    DECLARE v_nuevo_saldo NUMERIC(16,2);
    DECLARE v_cantidad_total_orden INT;
    DECLARE v_cantidad_ejecutada_total INT;

    SELECT o.id_cuenta, o.id_instrumento, o.tipo_orden, o.cantidad
    INTO v_id_cuenta, v_id_instrumento, v_tipo_orden, v_cantidad_total_orden
    FROM Orden o
    WHERE o.id_orden = NEW.id_orden;

    SET v_monto = (NEW.cantidad_ejecutada * NEW.precio_ejecucion) + NEW.comision;

    -- Actualizar saldo de la cuenta segun el tipo de orden
    IF v_tipo_orden = 'COMPRA' THEN
        UPDATE Cuenta_Inversion
        SET saldo_disponible = saldo_disponible - v_monto
        WHERE id_cuenta = v_id_cuenta;

        -- Actualizar o crear la posicion
        IF EXISTS (SELECT 1 FROM Posicion WHERE id_cuenta = v_id_cuenta AND id_instrumento = v_id_instrumento) THEN
            SELECT cantidad, precio_promedio_compra
            INTO v_cantidad_actual, v_precio_prom_actual
            FROM Posicion
            WHERE id_cuenta = v_id_cuenta AND id_instrumento = v_id_instrumento;

            UPDATE Posicion
            SET precio_promedio_compra = ((precio_promedio_compra * cantidad) + (NEW.precio_ejecucion * NEW.cantidad_ejecutada))
                                          / (cantidad + NEW.cantidad_ejecutada),
                cantidad = cantidad + NEW.cantidad_ejecutada
            WHERE id_cuenta = v_id_cuenta AND id_instrumento = v_id_instrumento;
        ELSE
            INSERT INTO Posicion (id_cuenta, id_instrumento, cantidad, precio_promedio_compra, fecha_primera_compra)
            VALUES (v_id_cuenta, v_id_instrumento, NEW.cantidad_ejecutada, NEW.precio_ejecucion, CURRENT_DATE);
        END IF;

    ELSEIF v_tipo_orden = 'VENTA' THEN
        UPDATE Cuenta_Inversion
        SET saldo_disponible = saldo_disponible + (NEW.cantidad_ejecutada * NEW.precio_ejecucion) - NEW.comision
        WHERE id_cuenta = v_id_cuenta;

        SELECT cantidad INTO v_cantidad_actual
        FROM Posicion
        WHERE id_cuenta = v_id_cuenta AND id_instrumento = v_id_instrumento;

        IF v_cantidad_actual - NEW.cantidad_ejecutada <= 0 THEN
            DELETE FROM Posicion
            WHERE id_cuenta = v_id_cuenta AND id_instrumento = v_id_instrumento;
        ELSE
            UPDATE Posicion
            SET cantidad = cantidad - NEW.cantidad_ejecutada
            WHERE id_cuenta = v_id_cuenta AND id_instrumento = v_id_instrumento;
        END IF;
    END IF;

    -- Registrar auditoria del movimiento
    SELECT saldo_disponible INTO v_nuevo_saldo
    FROM Cuenta_Inversion WHERE id_cuenta = v_id_cuenta;

    INSERT INTO Bitacora_Movimiento_Cuenta (id_cuenta, id_transaccion, tipo_movimiento, monto, saldo_resultante)
    VALUES (v_id_cuenta, NEW.id_transaccion, v_tipo_orden, v_monto, v_nuevo_saldo);

    -- Actualizar el estado de la orden segun lo acumulado ejecutado
    SELECT COALESCE(SUM(cantidad_ejecutada), 0) INTO v_cantidad_ejecutada_total
    FROM Transaccion_Ejecutada
    WHERE id_orden = NEW.id_orden;

    IF v_cantidad_ejecutada_total >= v_cantidad_total_orden THEN
        UPDATE Orden SET estado = 'EJECUTADA' WHERE id_orden = NEW.id_orden;
    ELSE
        UPDATE Orden SET estado = 'PARCIALMENTE_EJECUTADA' WHERE id_orden = NEW.id_orden;
    END IF;
END$$

DELIMITER ;

-- Caso de prueba POSITIVO (orden de compra con saldo y cantidad validos):
-- INSERT INTO Transaccion_Ejecutada (id_orden, cantidad_ejecutada, precio_ejecucion, comision)
-- VALUES (1, 10, 5.00, 1.50);

-- Caso de prueba NEGATIVO (intentar vender mas de lo que se tiene en posicion
-- provocara que la subconsulta de v_cantidad_actual no encuentre fila y falle,
-- evidenciando que la venta no es valida sin posicion previa):
-- INSERT INTO Transaccion_Ejecutada (id_orden, cantidad_ejecutada, precio_ejecucion, comision)
-- VALUES (<id_orden_de_venta_sin_posicion>, 10, 5.00, 1.00);


-- ============================================================
-- FUNCION 1
-- Calcula el valor de mercado actual de la posicion de una
-- cuenta en un instrumento especifico, usando el precio mas
-- reciente disponible (Precio_Tiempo_Real; si no existe, usa el
-- ultimo precio de cierre en Cotizacion_Historica).
-- ============================================================
DELIMITER $$

CREATE FUNCTION fn_valor_mercado_posicion(p_id_cuenta INT, p_id_instrumento INT)
RETURNS NUMERIC(16,2)
DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_cantidad INT DEFAULT 0;
    DECLARE v_precio NUMERIC(15,4) DEFAULT 0;
    DECLARE v_valor NUMERIC(16,2) DEFAULT 0;

    SELECT cantidad INTO v_cantidad
    FROM Posicion
    WHERE id_cuenta = p_id_cuenta AND id_instrumento = p_id_instrumento
    LIMIT 1;

    IF v_cantidad IS NULL THEN
        RETURN 0;
    END IF;

    SELECT precio_actual INTO v_precio
    FROM Precio_Tiempo_Real
    WHERE id_instrumento = p_id_instrumento
    ORDER BY fecha_hora DESC
    LIMIT 1;

    IF v_precio IS NULL OR v_precio = 0 THEN
        SELECT precio_cierre INTO v_precio
        FROM Cotizacion_Historica
        WHERE id_instrumento = p_id_instrumento
        ORDER BY fecha DESC
        LIMIT 1;
    END IF;

    SET v_valor = v_cantidad * COALESCE(v_precio, 0);
    RETURN v_valor;
END$$

DELIMITER ;

-- Uso: SELECT fn_valor_mercado_posicion(1, 3);


-- ============================================================
-- FUNCION 2
-- Clasifica el perfil de riesgo REAL de un cliente segun su
-- comportamiento historico de ordenes (no el perfil declarado
-- en Cliente.perfil_riesgo), util para detectar
-- inconsistencias: si predominan ordenes de instrumentos de
-- categoria ALTO riesgo -> AGRESIVO; si predominan MEDIO ->
-- MODERADO; si predominan BAJO -> CONSERVADOR.
-- ============================================================
DELIMITER $$

CREATE FUNCTION fn_clasificar_perfil_cliente(p_id_cliente INT)
RETURNS VARCHAR(15)
DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_alto INT DEFAULT 0;
    DECLARE v_medio INT DEFAULT 0;
    DECLARE v_bajo INT DEFAULT 0;
    DECLARE v_resultado VARCHAR(15);

    SELECT
        SUM(CASE WHEN ci.nivel_riesgo = 'ALTO' THEN 1 ELSE 0 END),
        SUM(CASE WHEN ci.nivel_riesgo = 'MEDIO' THEN 1 ELSE 0 END),
        SUM(CASE WHEN ci.nivel_riesgo = 'BAJO' THEN 1 ELSE 0 END)
    INTO v_alto, v_medio, v_bajo
    FROM Orden o
    JOIN Cuenta_Inversion cu ON o.id_cuenta = cu.id_cuenta
    JOIN Instrumento_Financiero inst ON o.id_instrumento = inst.id_instrumento
    JOIN Categoria_Instrumento ci ON inst.id_categoria = ci.id_categoria
    WHERE cu.id_cliente = p_id_cliente;

    IF v_alto IS NULL AND v_medio IS NULL AND v_bajo IS NULL THEN
        RETURN 'SIN_HISTORIAL';
    END IF;

    IF v_alto >= v_medio AND v_alto >= v_bajo THEN
        SET v_resultado = 'AGRESIVO';
    ELSEIF v_medio >= v_alto AND v_medio >= v_bajo THEN
        SET v_resultado = 'MODERADO';
    ELSE
        SET v_resultado = 'CONSERVADOR';
    END IF;

    RETURN v_resultado;
END$$

DELIMITER ;

-- Uso: SELECT id_cliente, perfil_riesgo, fn_clasificar_perfil_cliente(id_cliente) AS perfil_real
--      FROM Cliente;


-- ============================================================
-- PROCEDIMIENTO 1
-- Orquesta la ejecucion de una orden: valida que este en un
-- estado ejecutable, registra la transaccion (el Trigger 3 se
-- encarga de actualizar saldo/posicion/bitacora) y confirma el
-- resultado. Encapsula un proceso de negocio multi-tabla.
-- ============================================================
DELIMITER $$

CREATE PROCEDURE sp_ejecutar_orden(
    IN p_id_orden INT,
    IN p_cantidad_ejecutada INT,
    IN p_precio_ejecucion NUMERIC(14,4),
    IN p_comision NUMERIC(10,2)
)
BEGIN
    DECLARE v_estado_actual VARCHAR(25);
    DECLARE v_cantidad_orden INT;
    DECLARE v_cantidad_ya_ejecutada INT;

    SELECT estado, cantidad INTO v_estado_actual, v_cantidad_orden
    FROM Orden
    WHERE id_orden = p_id_orden;

    IF v_estado_actual IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La orden indicada no existe.';
    END IF;

    IF v_estado_actual NOT IN ('PENDIENTE','PARCIALMENTE_EJECUTADA') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La orden no se encuentra en un estado ejecutable.';
    END IF;

    SELECT COALESCE(SUM(cantidad_ejecutada), 0) INTO v_cantidad_ya_ejecutada
    FROM Transaccion_Ejecutada
    WHERE id_orden = p_id_orden;

    IF (v_cantidad_ya_ejecutada + p_cantidad_ejecutada) > v_cantidad_orden THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La cantidad a ejecutar excede la cantidad pendiente de la orden.';
    END IF;

    INSERT INTO Transaccion_Ejecutada (id_orden, cantidad_ejecutada, precio_ejecucion, comision)
    VALUES (p_id_orden, p_cantidad_ejecutada, p_precio_ejecucion, p_comision);

    -- El Trigger 3 (trg_actualizar_posicion_saldo) actualiza saldo,
    -- posicion, bitacora y estado de la orden automaticamente.
END$$

DELIMITER ;

-- Uso: CALL sp_ejecutar_orden(1, 10, 5.25, 1.50);


-- ============================================================
-- PROCEDIMIENTO 2
-- Recorre (CURSOR) todas las cuentas activas y genera un
-- reporte de riesgo: saldo disponible, valor total del
-- portafolio (suma de fn_valor_mercado_posicion por cada
-- posicion de la cuenta) y valor total. Usa manejo de
-- excepciones para continuar si una cuenta individual falla,
-- sin abortar el reporte completo.
-- ============================================================
DELIMITER $$

CREATE PROCEDURE sp_resumen_riesgo_cuentas()
BEGIN
    DECLARE v_fin INT DEFAULT 0;
    DECLARE v_id_cuenta INT;
    DECLARE v_saldo NUMERIC(16,2);
    DECLARE v_valor_portafolio NUMERIC(16,2);

    DECLARE cur_cuentas CURSOR FOR
        SELECT id_cuenta, saldo_disponible
        FROM Cuenta_Inversion
        WHERE estado = 'A';

    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_fin = 1;

    -- Si algo falla al calcular una cuenta puntual, se registra
    -- pero el procedimiento continua con la siguiente cuenta.
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Error inesperado generando el resumen de riesgo. Operacion revertida.';
    END;

    START TRANSACTION;

    DELETE FROM Reporte_Riesgo_Cuenta
    WHERE fecha_generacion < NOW() - INTERVAL 0 SECOND; -- limpia ejecuciones previas del reporte

    OPEN cur_cuentas;

    bucle_cuentas: LOOP
        FETCH cur_cuentas INTO v_id_cuenta, v_saldo;
        IF v_fin = 1 THEN
            LEAVE bucle_cuentas;
        END IF;

        SELECT COALESCE(SUM(fn_valor_mercado_posicion(v_id_cuenta, p.id_instrumento)), 0)
        INTO v_valor_portafolio
        FROM Posicion p
        WHERE p.id_cuenta = v_id_cuenta;

        INSERT INTO Reporte_Riesgo_Cuenta (id_cuenta, saldo_disponible, valor_portafolio, valor_total)
        VALUES (v_id_cuenta, v_saldo, v_valor_portafolio, v_saldo + v_valor_portafolio);

    END LOOP bucle_cuentas;

    CLOSE cur_cuentas;

    COMMIT;
END$$

DELIMITER ;

-- Uso: CALL sp_resumen_riesgo_cuentas();
--      SELECT * FROM Reporte_Riesgo_Cuenta ORDER BY valor_total DESC;