"""
Autenticación JWT — verifica tokens de Supabase en los endpoints de la API.
Middleware ligero: extrae el JWT del header Authorization y valida con Supabase.
"""
from __future__ import annotations
import os
import logging
from functools import lru_cache

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger("mermaops.auth")

_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _get_supabase_jwt_secret() -> str:
    """JWT secret de Supabase — está en el panel Settings > API > JWT Secret."""
    return os.getenv("SUPABASE_JWT_SECRET", "")


def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> dict:
    """
    Verifica el JWT de Supabase y devuelve el payload del token.
    Lanza 401 si el token es inválido o falta.

    En modo desarrollo (APP_ENV=dev) admite un token especial 'dev-bypass'
    para facilitar pruebas sin credenciales reales.
    """
    env = os.getenv("APP_ENV", "dev")

    # En dev, si no hay credenciales configuradas, modo permisivo para pruebas
    if env == "dev":
        supabase_url = os.getenv("SUPABASE_URL", "")
        if not supabase_url or supabase_url.startswith("https://xxxx"):
            # BD no configurada — no tiene sentido validar tokens
            return {"sub": "dev-user", "role": "authenticated", "dev_mode": True}

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida. Incluye el token en el header Authorization.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Token de bypass para desarrollo
    if env == "dev" and token == "dev-bypass":
        return {"sub": "dev-user", "role": "authenticated", "dev_mode": True}

    # Verificación real con Supabase usando el cliente existente
    try:
        db = database_module().get_db()
        user_response = db.auth.get_user(jwt=token)
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido o expirado.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = user_response.user
        return {
            "sub": user.id,
            "email": user.email,
            "role": "authenticated",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[auth] Error verificando token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se pudo verificar la autenticación.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def database_module():
    from backend.core import database
    return database


# Dependencia opcional — para endpoints que funcionan con o sin auth
def optional_token(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> dict | None:
    """Como verify_token pero devuelve None en lugar de lanzar excepción."""
    try:
        return verify_token(credentials)
    except HTTPException:
        return None
