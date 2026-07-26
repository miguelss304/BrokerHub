-- ============================================================
-- Reglas de negocio: TRIGGERS, FUNCIONES y PROCEDIMIENTOS
-- ORDEN DE EJECUCION: debe correrse DESPUES de crear el esquema y poblar las tablas
-- Proyecto Final BD - Sesion 3
-- ============================================================

USE railway;

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

-- ============================================================
-- TRIGGER 3
-- Actualiza saldo, posición y bitácora luego de insertar una
-- transacción ejecutada. Garantiza que el estado de la orden se
-- sincronice con el volumen ejecutado.
-- ============================================================
DELIMITER $$

CREATE TRIGGER trg_actualizar_saldo_posicion_bitacora
AFTER INSERT ON Transaccion_Ejecutada
FOR EACH ROW
BEGIN
    DECLARE v_id_cuenta INT;
    DECLARE v_tipo_orden VARCHAR(6);
    DECLARE v_id_instrumento INT;
    DECLARE v_cantidad_orden INT;
    DECLARE v_total_ejecutado INT;
    DECLARE v_cantidad_prev INT DEFAULT NULL;
    DECLARE v_precio_promedio NUMERIC(14,4) DEFAULT NULL;
    DECLARE v_nuevo_precio_promedio NUMERIC(14,4) DEFAULT 0;
    DECLARE v_valor_total NUMERIC(16,2);
    DECLARE v_saldo_resultante NUMERIC(16,2);
    DECLARE v_tipo_movimiento VARCHAR(10);
    DECLARE v_cantidad_restante INT;
    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_cantidad_prev = NULL, v_precio_promedio = NULL;

    SELECT o.id_cuenta, o.id_instrumento, o.tipo_orden, o.cantidad
    INTO v_id_cuenta, v_id_instrumento, v_tipo_orden, v_cantidad_orden
    FROM Orden o
    WHERE o.id_orden = NEW.id_orden;

    SELECT COALESCE(SUM(cantidad_ejecutada), 0)
    INTO v_total_ejecutado
    FROM Transaccion_Ejecutada
    WHERE id_orden = NEW.id_orden;

    SET v_valor_total = ROUND(NEW.precio_ejecucion * NEW.cantidad_ejecutada, 2);

    IF v_tipo_orden = 'COMPRA' THEN
        SET v_tipo_movimiento = 'COMPRA';
        UPDATE Cuenta_Inversion
        SET saldo_disponible = saldo_disponible - (v_valor_total + NEW.comision)
        WHERE id_cuenta = v_id_cuenta;
    ELSE
        SET v_tipo_movimiento = 'VENTA';
        UPDATE Cuenta_Inversion
        SET saldo_disponible = saldo_disponible + (v_valor_total - NEW.comision)
        WHERE id_cuenta = v_id_cuenta;
    END IF;

    SELECT saldo_disponible INTO v_saldo_resultante
    FROM Cuenta_Inversion
    WHERE id_cuenta = v_id_cuenta;

    SELECT cantidad, precio_promedio_compra
    INTO v_cantidad_prev, v_precio_promedio
    FROM Posicion
    WHERE id_cuenta = v_id_cuenta AND id_instrumento = v_id_instrumento
    LIMIT 1;

    IF v_tipo_orden = 'COMPRA' THEN
        IF v_cantidad_prev IS NULL OR v_cantidad_prev = 0 THEN
            INSERT INTO Posicion (id_cuenta, id_instrumento, cantidad, precio_promedio_compra, fecha_primera_compra)
            VALUES (v_id_cuenta, v_id_instrumento, NEW.cantidad_ejecutada, NEW.precio_ejecucion, CURRENT_DATE);
        ELSE
            SET v_nuevo_precio_promedio = ROUND((v_cantidad_prev * v_precio_promedio + v_valor_total) / (v_cantidad_prev + NEW.cantidad_ejecutada), 4);
            UPDATE Posicion
            SET cantidad = cantidad + NEW.cantidad_ejecutada,
                precio_promedio_compra = v_nuevo_precio_promedio
            WHERE id_cuenta = v_id_cuenta AND id_instrumento = v_id_instrumento;
        END IF;
    ELSE
        IF v_cantidad_prev IS NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Venta inválida: no existe posición previa para el instrumento.';
        ELSE
            SET v_cantidad_restante = v_cantidad_prev - NEW.cantidad_ejecutada;
            IF v_cantidad_restante < 0 THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Venta inválida: la cantidad ejecutada excede la posición existente.';
            ELSEIF v_cantidad_restante = 0 THEN
                DELETE FROM Posicion
                WHERE id_cuenta = v_id_cuenta AND id_instrumento = v_id_instrumento;
            ELSE
                UPDATE Posicion
                SET cantidad = v_cantidad_restante
                WHERE id_cuenta = v_id_cuenta AND id_instrumento = v_id_instrumento;
            END IF;
        END IF;
    END IF;

    IF v_total_ejecutado >= v_cantidad_orden THEN
        UPDATE Orden SET estado = 'EJECUTADA' WHERE id_orden = NEW.id_orden;
    ELSE
        UPDATE Orden SET estado = 'PARCIALMENTE_EJECUTADA' WHERE id_orden = NEW.id_orden;
    END IF;

    INSERT INTO Bitacora_Movimiento_Cuenta (id_cuenta, id_transaccion, tipo_movimiento, monto, saldo_resultante)
    VALUES (
        v_id_cuenta,
        NEW.id_transaccion,
        v_tipo_movimiento,
        CASE WHEN v_tipo_movimiento = 'COMPRA' THEN v_valor_total + NEW.comision ELSE v_valor_total - NEW.comision END,
        v_saldo_resultante
    );
END$$

DELIMITER ;

-- Caso de prueba POSITIVO:
-- UPDATE Orden SET estado = 'PARCIALMENTE_EJECUTADA' WHERE id_orden = 1 AND estado = 'PENDIENTE';

-- Caso de prueba NEGATIVO:
-- UPDATE Orden SET estado = 'PENDIENTE' WHERE id_orden = 1 AND estado = 'EJECUTADA';

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

-- ============================================================
-- FUNCION 3
-- Calcula el valor total de una cuenta incluyendo saldo disponible
-- y el valor de mercado de sus posiciones.
-- ============================================================
DELIMITER $$

CREATE FUNCTION fn_valor_total_cuenta(p_id_cuenta INT)
RETURNS NUMERIC(16,2)
DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_saldo NUMERIC(16,2) DEFAULT 0;
    DECLARE v_valor_portafolio NUMERIC(16,2) DEFAULT 0;

    SELECT saldo_disponible INTO v_saldo
    FROM Cuenta_Inversion
    WHERE id_cuenta = p_id_cuenta;

    SELECT COALESCE(SUM(fn_valor_mercado_posicion(p_id_cuenta, id_instrumento)), 0)
    INTO v_valor_portafolio
    FROM Posicion
    WHERE id_cuenta = p_id_cuenta;

    RETURN v_saldo + v_valor_portafolio;
END$$

DELIMITER ;

-- ============================================================
-- PROCEDIMIENTO 3
-- Cancela una orden PENDIENTE. Útil para el módulo administrativo.
-- ============================================================
DELIMITER $$

CREATE PROCEDURE sp_cancelar_orden(IN p_id_orden INT)
BEGIN
    DECLARE v_estado_actual VARCHAR(25);
    DECLARE v_existe INT DEFAULT 0;

    SELECT COUNT(*) INTO v_existe
    FROM Orden
    WHERE id_orden = p_id_orden;

    IF v_existe = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La orden indicada no existe.';
    END IF;

    SELECT estado INTO v_estado_actual
    FROM Orden
    WHERE id_orden = p_id_orden;

    IF v_estado_actual <> 'PENDIENTE' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Solo se pueden cancelar órdenes en estado PENDIENTE.';
    END IF;

    UPDATE Orden
    SET estado = 'CANCELADA'
    WHERE id_orden = p_id_orden;
END$$

DELIMITER ;

-- ============================================================
-- PROCEDIMIENTO 4
-- Cambia el estado de una cuenta entre activa e inactiva.
-- ============================================================
DELIMITER $$

CREATE PROCEDURE sp_cambiar_estado_cuenta(IN p_id_cuenta INT, IN p_estado CHAR(1))
BEGIN
    DECLARE v_existe INT DEFAULT 0;

    SELECT COUNT(*) INTO v_existe
    FROM Cuenta_Inversion
    WHERE id_cuenta = p_id_cuenta;

    IF v_existe = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La cuenta indicada no existe.';
    END IF;

    IF p_estado NOT IN ('A', 'I') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Estado de cuenta inválido. Use "A" o "I".';
    END IF;

    UPDATE Cuenta_Inversion
    SET estado = p_estado
    WHERE id_cuenta = p_id_cuenta;
END$$

DELIMITER ;

-- ============================================================
-- PROCEDIMIENTO 5
-- Ajusta el saldo disponible de una cuenta. Solo para administración.
-- ============================================================
DELIMITER $$

CREATE PROCEDURE sp_ajustar_saldo_cuenta(IN p_id_cuenta INT, IN p_nuevo_saldo NUMERIC(16,2))
BEGIN
    DECLARE v_existe INT DEFAULT 0;

    SELECT COUNT(*) INTO v_existe
    FROM Cuenta_Inversion
    WHERE id_cuenta = p_id_cuenta;

    IF v_existe = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La cuenta indicada no existe.';
    END IF;

    IF p_nuevo_saldo < 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El saldo de la cuenta no puede ser negativo.';
    END IF;

    UPDATE Cuenta_Inversion
    SET saldo_disponible = p_nuevo_saldo
    WHERE id_cuenta = p_id_cuenta;
END$$

DELIMITER ;

-- ============================================================
-- PROCEDIMIENTO 6
-- Genera una notificación administrativa manual para un cliente.
-- ============================================================
DELIMITER $$

CREATE PROCEDURE sp_crear_notificacion_admin(
    IN p_id_cliente INT,
    IN p_tipo VARCHAR(30),
    IN p_titulo VARCHAR(150),
    IN p_mensaje TEXT
)
BEGIN
    INSERT INTO Notificacion (id_cliente, tipo, titulo, mensaje)
    VALUES (p_id_cliente, p_tipo, p_titulo, p_mensaje);
END$$

DELIMITER ;

-- Uso:
-- CALL sp_cancelar_orden(10);
-- CALL sp_cambiar_estado_cuenta(3, 'I');
-- CALL sp_ajustar_saldo_cuenta(3, 15000.00);
-- CALL sp_crear_notificacion_admin(2, 'ADMIN', 'Ajuste de cuenta', 'El saldo de su cuenta ha sido ajustado por administración.');