DROP DATABASE IF EXISTS brokerhub;
CREATE DATABASE brokerhub;
USE brokerhub;

-- ============================================================
-- 1. ENTIDADES MAESTRAS
-- ============================================================

CREATE TABLE Cliente (
    id_cliente          INT AUTO_INCREMENT PRIMARY KEY,
    nombre_completo     VARCHAR(120) NOT NULL,
    tipo_cliente        CHAR(1) NOT NULL,
    documento_identidad VARCHAR(20) NOT NULL UNIQUE,
    correo              VARCHAR(120) NOT NULL UNIQUE,
    perfil_riesgo       VARCHAR(15),
    fecha_registro      DATE NOT NULL DEFAULT (CURRENT_DATE),
    CONSTRAINT chk_tipo_cliente CHECK (tipo_cliente IN ('N','J')),
    CONSTRAINT chk_perfil_riesgo CHECK (perfil_riesgo IN ('CONSERVADOR','MODERADO','AGRESIVO'))
);

CREATE TABLE Credencial (
    id_credencial     INT AUTO_INCREMENT PRIMARY KEY,
    id_cliente        INT NOT NULL UNIQUE,
    usuario           VARCHAR(50) NOT NULL UNIQUE,
    contrasena_hash   VARCHAR(255) NOT NULL,
    fecha_creacion    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ultimo_acceso     TIMESTAMP NULL,
    FOREIGN KEY (id_cliente) REFERENCES Cliente(id_cliente)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE TABLE Mercado_Bolsa (
    id_mercado          INT AUTO_INCREMENT PRIMARY KEY,
    nombre              VARCHAR(80) NOT NULL,
    pais                VARCHAR(60) NOT NULL,
    zona_horaria        VARCHAR(50) NOT NULL
);

CREATE TABLE Emisor (
    id_emisor           INT AUTO_INCREMENT PRIMARY KEY,
    razon_social        VARCHAR(150) NOT NULL,
    sector_economico    VARCHAR(80) NOT NULL,
    pais_origen         VARCHAR(80) NOT NULL
);

CREATE TABLE Categoria_Instrumento (
    id_categoria            INT AUTO_INCREMENT PRIMARY KEY,
    nombre                  VARCHAR(80) NOT NULL,
    nivel_riesgo            VARCHAR(15) NOT NULL,
    id_categoria_padre      INT NULL,
    CONSTRAINT chk_nivel_riesgo CHECK (nivel_riesgo IN ('BAJO','MEDIO','ALTO')),
    CONSTRAINT fk_categoria_padre
        FOREIGN KEY (id_categoria_padre) REFERENCES Categoria_Instrumento(id_categoria)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);

CREATE TABLE Instrumento_Financiero (
    id_instrumento       INT AUTO_INCREMENT PRIMARY KEY,
    ticker               VARCHAR(15) NOT NULL UNIQUE,
    nombre               VARCHAR(120) NOT NULL,
    tipo                 VARCHAR(10) NOT NULL DEFAULT 'ACCION',
    id_emisor            INT NOT NULL,
    id_categoria         INT NOT NULL,
    fecha_listado        DATETIME NOT NULL,
    CONSTRAINT chk_tipo CHECK (tipo = 'ACCION'),
    FOREIGN KEY (id_emisor) REFERENCES Emisor(id_emisor)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,
    FOREIGN KEY (id_categoria) REFERENCES Categoria_Instrumento(id_categoria)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);

CREATE TABLE Cuenta_Inversion (
    id_cuenta            INT AUTO_INCREMENT PRIMARY KEY,
    id_cliente           INT NOT NULL,
    tipo_cuenta          VARCHAR(15) NOT NULL,
    saldo_disponible     NUMERIC(16,2) NOT NULL DEFAULT 0,
    fecha_apertura       DATE NOT NULL DEFAULT (CURRENT_DATE),
    estado               CHAR(1) NOT NULL DEFAULT 'A',
    FOREIGN KEY (id_cliente) REFERENCES Cliente(id_cliente)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,
    CONSTRAINT chk_tipo_cuenta CHECK (tipo_cuenta IN ('ORDINARIA','RETIRO','FIDUCIARIA')),
    CONSTRAINT chk_estado_cuenta CHECK (estado IN ('A','I'))
);

-- ============================================================
-- 2. ENTIDADES TRANSACCIONALES
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
    FOREIGN KEY (id_instrumento) REFERENCES Instrumento_Financiero(id_instrumento)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    UNIQUE (id_instrumento, fecha)
);

CREATE TABLE Precio_Tiempo_Real (
    id_instrumento       INT NOT NULL,
    fecha_hora           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    precio_actual        NUMERIC(15,4) NOT NULL,
    volumen_tick         BIGINT,
    PRIMARY KEY (id_instrumento, fecha_hora),
    FOREIGN KEY (id_instrumento) REFERENCES Instrumento_Financiero(id_instrumento)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE TABLE Orden (
    id_orden             INT AUTO_INCREMENT PRIMARY KEY,
    id_cuenta            INT NOT NULL,
    id_instrumento       INT NOT NULL,
    tipo_orden           VARCHAR(6) NOT NULL,
    cantidad             INT NOT NULL,
    precio_limite        NUMERIC(14,4) NOT NULL,
    fecha_hora           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado               VARCHAR(25) NOT NULL DEFAULT 'PENDIENTE',
    CONSTRAINT chk_tipo_orden CHECK (tipo_orden IN ('COMPRA','VENTA')),
    CONSTRAINT chk_cantidad CHECK (cantidad > 0),
    CONSTRAINT chk_estados CHECK (estado IN ('PENDIENTE','PARCIALMENTE_EJECUTADA','EJECUTADA','CANCELADA')),
    FOREIGN KEY (id_cuenta) REFERENCES Cuenta_Inversion(id_cuenta)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,
    FOREIGN KEY (id_instrumento) REFERENCES Instrumento_Financiero(id_instrumento)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);

CREATE TABLE Transaccion_Ejecutada (
    id_transaccion       INT AUTO_INCREMENT PRIMARY KEY,
    id_orden             INT NOT NULL,
    cantidad_ejecutada   INT NOT NULL,
    precio_ejecucion     NUMERIC(14,4) NOT NULL,
    fecha_hora           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    comision             NUMERIC(10,2) NOT NULL DEFAULT 0,
    FOREIGN KEY (id_orden) REFERENCES Orden(id_orden)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

-- ============================================================
-- 3. RELACIONES M:N CON ATRIBUTOS PROPIOS
-- ============================================================

CREATE TABLE Posicion (
    id_cuenta                INT NOT NULL,
    id_instrumento           INT NOT NULL,
    cantidad                 INT NOT NULL,
    precio_promedio_compra   NUMERIC(14,4) NOT NULL,
    fecha_primera_compra     DATE NOT NULL,
    PRIMARY KEY (id_cuenta, id_instrumento),
    CONSTRAINT chk_cantidad_posicion CHECK (cantidad > 0),
    FOREIGN KEY (id_instrumento) REFERENCES Instrumento_Financiero(id_instrumento)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,
    FOREIGN KEY (id_cuenta) REFERENCES Cuenta_Inversion(id_cuenta)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE TABLE Listado_Mercado (
    id_instrumento        INT NOT NULL,
    id_mercado            INT NOT NULL,
    ticker_local          VARCHAR(15) NOT NULL,
    moneda                VARCHAR(10) NOT NULL,
    fecha_listado         DATE NOT NULL,
    PRIMARY KEY (id_instrumento, id_mercado),
    FOREIGN KEY (id_instrumento) REFERENCES Instrumento_Financiero(id_instrumento)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    FOREIGN KEY (id_mercado) REFERENCES Mercado_Bolsa(id_mercado)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);