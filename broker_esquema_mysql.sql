-- ============================================================
-- PROYECTO FINAL - BASES DE DATOS
-- Dominio: Plataforma de Corretaje de Inversiones (Broker Bursátil)
-- Script de creación de tablas (DDL) - Sintaxis MySQL 8.0+
-- ============================================================

-- ============================================================
-- 1. ENTIDADES MAESTRAS
-- ============================================================

CREATE TABLE Cliente (
    id_cliente          INT AUTO_INCREMENT PRIMARY KEY,
    nombre_completo     VARCHAR(120) NOT NULL,
    tipo_cliente        CHAR(1) NOT NULL CHECK (tipo_cliente IN ('N','J')),
    documento_identidad VARCHAR(20) NOT NULL UNIQUE,
    perfil_riesgo       VARCHAR(15) NOT NULL CHECK (perfil_riesgo IN ('CONSERVADOR','MODERADO','AGRESIVO')),
    correo              VARCHAR(120) NOT NULL UNIQUE,
    fecha_registro      DATE NOT NULL DEFAULT (CURRENT_DATE)
);

CREATE TABLE Mercado_Bolsa (
    id_mercado          INT AUTO_INCREMENT PRIMARY KEY,
    nombre              VARCHAR(80) NOT NULL,
    pais                VARCHAR(60) NOT NULL,
    zona_horaria        VARCHAR(40) NOT NULL
);

CREATE TABLE Emisor (
    id_emisor           INT AUTO_INCREMENT PRIMARY KEY,
    razon_social        VARCHAR(150) NOT NULL,
    sector_economico    VARCHAR(80) NOT NULL,
    pais_origen         VARCHAR(60) NOT NULL
);

-- JERARQUÍA: categorías de instrumentos con estructura recursiva
CREATE TABLE Categoria_Instrumento (
    id_categoria            INT AUTO_INCREMENT PRIMARY KEY,
    nombre                  VARCHAR(80) NOT NULL,
    nivel_riesgo            VARCHAR(15) NOT NULL CHECK (nivel_riesgo IN ('BAJO','MEDIO','ALTO')),
    id_categoria_padre      INT NULL,
    CONSTRAINT fk_categoria_padre
        FOREIGN KEY (id_categoria_padre) REFERENCES Categoria_Instrumento(id_categoria)
);

CREATE TABLE Instrumento_Financiero (
    id_instrumento       INT AUTO_INCREMENT PRIMARY KEY,
    ticker               VARCHAR(15) NOT NULL UNIQUE,
    nombre               VARCHAR(120) NOT NULL,
    tipo                 VARCHAR(20) NOT NULL DEFAULT 'ACCION' CHECK (tipo = 'ACCION'),
    id_emisor            INT NOT NULL,
    id_categoria         INT NOT NULL,
    fecha_listado        DATE NOT NULL,
    CONSTRAINT fk_instrumento_emisor
        FOREIGN KEY (id_emisor) REFERENCES Emisor(id_emisor),
    CONSTRAINT fk_instrumento_categoria
        FOREIGN KEY (id_categoria) REFERENCES Categoria_Instrumento(id_categoria)
);

CREATE TABLE Cuenta_Inversion (
    id_cuenta            INT AUTO_INCREMENT PRIMARY KEY,
    id_cliente           INT NOT NULL,
    tipo_cuenta          VARCHAR(20) NOT NULL CHECK (tipo_cuenta IN ('ORDINARIA','RETIRO','FIDUCIARIA')),
    saldo_disponible     NUMERIC(16,2) NOT NULL DEFAULT 0 CHECK (saldo_disponible >= 0),
    fecha_apertura       DATE NOT NULL DEFAULT (CURRENT_DATE),
    estado               CHAR(1) NOT NULL DEFAULT 'A' CHECK (estado IN ('A','I')),
    CONSTRAINT fk_cuenta_cliente
        FOREIGN KEY (id_cliente) REFERENCES Cliente(id_cliente)
);

-- ============================================================
-- 2. ENTIDADES TRANSACCIONALES (dimensión temporal)
-- ============================================================

CREATE TABLE Cotizacion_Historica (
    id_cotizacion        INT AUTO_INCREMENT PRIMARY KEY,
    id_instrumento       INT NOT NULL,
    fecha                DATE NOT NULL,
    precio_apertura      NUMERIC(14,4) NOT NULL,
    precio_cierre        NUMERIC(14,4) NOT NULL,
    precio_maximo        NUMERIC(14,4) NOT NULL,
    precio_minimo        NUMERIC(14,4) NOT NULL,
    volumen              BIGINT NOT NULL,
    CONSTRAINT fk_cotizacion_instrumento
        FOREIGN KEY (id_instrumento) REFERENCES Instrumento_Financiero(id_instrumento),
    UNIQUE (id_instrumento, fecha)
);

-- Tabla alimentada en tiempo real por el stream WebSocket de Finnhub
CREATE TABLE Precio_Tiempo_Real (
    id_instrumento       INT NOT NULL,
    precio_actual        NUMERIC(14,4) NOT NULL,
    volumen_tick         BIGINT,
    fecha_hora           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_instrumento, fecha_hora),
    CONSTRAINT fk_preciotr_instrumento
        FOREIGN KEY (id_instrumento) REFERENCES Instrumento_Financiero(id_instrumento)
);

CREATE TABLE Orden (
    id_orden             INT AUTO_INCREMENT PRIMARY KEY,
    id_cuenta            INT NOT NULL,
    id_instrumento       INT NOT NULL,
    tipo_orden           VARCHAR(10) NOT NULL CHECK (tipo_orden IN ('COMPRA','VENTA')),
    cantidad             INT NOT NULL CHECK (cantidad > 0),
    precio_limite        NUMERIC(14,4) NOT NULL,
    fecha_hora           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado               VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
                          CHECK (estado IN ('PENDIENTE','PARCIALMENTE_EJECUTADA','EJECUTADA','CANCELADA')),
    CONSTRAINT fk_orden_cuenta
        FOREIGN KEY (id_cuenta) REFERENCES Cuenta_Inversion(id_cuenta),
    CONSTRAINT fk_orden_instrumento
        FOREIGN KEY (id_instrumento) REFERENCES Instrumento_Financiero(id_instrumento)
);

CREATE TABLE Transaccion_Ejecutada (
    id_transaccion       INT AUTO_INCREMENT PRIMARY KEY,
    id_orden             INT NOT NULL,
    cantidad_ejecutada   INT NOT NULL CHECK (cantidad_ejecutada > 0),
    precio_ejecucion     NUMERIC(14,4) NOT NULL,
    fecha_hora           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    comision             NUMERIC(10,2) NOT NULL DEFAULT 0,
    CONSTRAINT fk_transaccion_orden
        FOREIGN KEY (id_orden) REFERENCES Orden(id_orden)
);

-- ============================================================
-- 3. RELACIONES MUCHOS-A-MUCHOS CON ATRIBUTOS PROPIOS
-- ============================================================

-- M:N #1 -> Cliente <-> Instrumento_Financiero (posiciones que posee cada cliente)
CREATE TABLE Posicion (
    id_cliente               INT NOT NULL,
    id_instrumento            INT NOT NULL,
    cantidad                  INT NOT NULL CHECK (cantidad >= 0),
    precio_promedio_compra    NUMERIC(14,4) NOT NULL,
    fecha_primera_compra      DATE NOT NULL,
    PRIMARY KEY (id_cliente, id_instrumento),
    CONSTRAINT fk_posicion_cliente
        FOREIGN KEY (id_cliente) REFERENCES Cliente(id_cliente),
    CONSTRAINT fk_posicion_instrumento
        FOREIGN KEY (id_instrumento) REFERENCES Instrumento_Financiero(id_instrumento)
);

-- M:N #2 -> Instrumento_Financiero <-> Mercado_Bolsa (dual-listing)
CREATE TABLE Listado_Mercado (
    id_instrumento        INT NOT NULL,
    id_mercado            INT NOT NULL,
    ticker_local          VARCHAR(15) NOT NULL,
    moneda                VARCHAR(10) NOT NULL,
    fecha_listado         DATE NOT NULL,
    PRIMARY KEY (id_instrumento, id_mercado),
    CONSTRAINT fk_listado_instrumento
        FOREIGN KEY (id_instrumento) REFERENCES Instrumento_Financiero(id_instrumento),
    CONSTRAINT fk_listado_mercado
        FOREIGN KEY (id_mercado) REFERENCES Mercado_Bolsa(id_mercado)
);

-- ============================================================
-- Notas de diseño:
-- - Jerarquía/auto-relación: Categoria_Instrumento.id_categoria_padre
--   permite anidar categorías (ej. Acciones -> Tecnología -> Blue Chip).
-- - M:N con atributos propios: Posicion (Cliente <-> Instrumento_Financiero)
--   y Listado_Mercado (Instrumento_Financiero <-> Mercado_Bolsa).
-- - Dimensión temporal: Cotizacion_Historica (histórico diario) y
--   Precio_Tiempo_Real (streaming en vivo vía Finnhub) permiten
--   consultas por rango de fechas e históricos.
-- - Requiere MySQL 8.0.16+ para que los CHECK se apliquen realmente.
-- ============================================================
