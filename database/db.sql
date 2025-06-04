DROP DATABASE IF EXISTS db_poo;

CREATE DATABASE db_poo;
USE db_poo;

-- Tabla empresas
CREATE TABLE empresas (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    plan ENUM('Personalizado', 'Avanzado', 'Intermedio', 'Basico') NOT NULL,
    limite_usuarios INT DEFAULT 3,
    limite_reportes INT DEFAULT 5
);

-- Tabla usuarios
CREATE TABLE usuarios (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    contrasena TEXT NOT NULL,
    rol ENUM('admin_superior', 'admin_medio', 'usuario') NOT NULL DEFAULT 'usuario',
    empresa_id BIGINT UNSIGNED,
    activo BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id)
);

-- Tabla reportes
CREATE TABLE reportes (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    usuario_id BIGINT UNSIGNED NOT NULL,
    empresa_id BIGINT UNSIGNED,
    nombre_pdf VARCHAR(255),
    nombre_candidato VARCHAR(255),
    tipo_reporte ENUM('individual', 'resumido', 'comparativo') NOT NULL DEFAULT 'individual',
    origen_documento VARCHAR(50),
    nombre_documento_origen VARCHAR(255),
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    FOREIGN KEY (empresa_id) REFERENCES empresas(id)
);

INSERT INTO empresas(nombre, plan, limite_usuarios, limite_reportes)
VALUES ('UTEC', 'Personalizado', 3, 5);
INSERT INTO empresas(nombre, plan, limite_usuarios, limite_reportes)
VALUES ('HIRENOTES AI', 'Avanzado', 1000, 1000);


INSERT INTO usuarios(nombre, email, contrasena, rol, empresa_id)
VALUES ('Favian Huarca', 'favhu@gmail.com', '123', 'usuario', 1);
INSERT INTO usuarios(nombre, email, contrasena, rol, empresa_id)
VALUES ('Eddy Caceres', 'eddcac@gmail.com', '123', 'usuario', 1);
INSERT INTO usuarios(nombre, email, contrasena, rol, empresa_id)
VALUES ('Anthony Chavez', 'antcha@gmail.com', '123', 'usuario', 1);

INSERT INTO usuarios(nombre, email, contrasena, rol, empresa_id)
VALUES ('Dylan Huarcaya', 'dylhu@gmail.com', '123', 'admin_medio', 1);
INSERT INTO usuarios(nombre, email, contrasena, rol, empresa_id)
VALUES ('Edynson Chipana', 'edichi@gmail.com', '123', 'admin_medio', 2);

INSERT INTO usuarios(nombre, email, contrasena, rol, empresa_id)
VALUES ('Alex Mendoza', 'alexme@gmail.com', '123', 'admin_superior', 2);


-- Vista auxiliar para conteo
CREATE VIEW reportes_por_empresa AS
SELECT e.id AS empresa_id, COUNT(r.id) AS total_reportes
FROM empresas e
JOIN usuarios u ON u.empresa_id = e.id
JOIN reportes r ON r.usuario_id = u.id
GROUP BY e.id;
