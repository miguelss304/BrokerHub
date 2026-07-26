"""
Autenticación para BrokerHub.

- bcrypt para el hash de contraseñas (a diferencia de generador_faker.py,
  que usa SHA-256 simple porque ahí solo se necesitan datos de PRUEBA con
  apariencia de hash real -- aquí sí es autenticación real de usuarios).
- JWT (python-jose) para el token de sesión que el frontend (Streamlit)
  guarda y reenvía en cada request.

"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "cambia-esto-en-produccion")
ALGORITMO = "HS256"
MINUTOS_EXPIRACION_TOKEN = 60 * 8  # 8 horas de sesión


# ------------------------------------------------------------------
# Contraseñas
# ------------------------------------------------------------------

def hash_contrasena(contrasena_plana: str) -> str:
    """Genera el hash bcrypt (incluye salt aleatorio automáticamente)."""
    return bcrypt.hashpw(contrasena_plana.encode(), bcrypt.gensalt()).decode()


def verificar_contrasena(contrasena_plana: str, contrasena_hash: str) -> bool:
    """Compara una contraseña en texto plano contra su hash guardado."""
    return bcrypt.checkpw(contrasena_plana.encode(), contrasena_hash.encode())


# ------------------------------------------------------------------
# Tokens JWT
# ------------------------------------------------------------------

def crear_token(id_cliente: int, usuario: str) -> str:
    expiracion = datetime.now(timezone.utc) + timedelta(minutes=MINUTOS_EXPIRACION_TOKEN)
    payload = {
        "id_cliente": id_cliente,
        "usuario": usuario,
        "exp": expiracion,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITMO)


def verificar_token(token: str) -> dict:
    """Devuelve el payload decodificado si el token es válido.
    Lanza JWTError si expiró o fue manipulado (main.py lo traduce a 401)."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITMO])