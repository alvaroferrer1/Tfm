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
    _is_dev = env in ("dev", "development")  # acepta ambas variantes

    # En dev, si no hay credenciales configuradas, modo permisivo para pruebas
    if _is_dev:
        supabase_url = os.getenv("SUPABASE_URL", "")
        if not supabase_url or supabase_url.startswith("https://xxxx"):
            logger.warning("[auth] DEV MODE sin Supabase — bypass activo, NO usar en producción")
            return {"sub": "dev-user", "role": "authenticated", "dev_mode": True}

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida. Incluye el token en el header Authorization.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Token de bypass para desarrollo (APP_ENV=dev o development)
    if _is_dev and token == "dev-bypass":
        logger.debug("[auth] dev-bypass token usado — solo válido en entorno de desarrollo")
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


def require_role(*allowed_roles: str):
    """Dependencia que exige que el usuario tenga uno de los roles indicados en la tabla users."""
    from fastapi import Depends

    def _check(auth: dict = Depends(verify_token)) -> dict:
        if auth.get("dev_mode"):
            return auth
        user_id = auth.get("sub", "")
        try:
            db = database_module().get_db()
            row = db.table("users").select("role").eq("id", user_id).maybe_single().execute()
            role = (row.data or {}).get("role", "")
        except Exception as _e:
            logger.warning(f"[auth] role lookup failed for {user_id}: {_e}")
            role = ""
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Se requiere rol: {', '.join(allowed_roles)}.",
            )
        auth["user_role"] = role
        return auth

    return _check


# Dependencia opcional — para endpoints que funcionan con o sin auth
def optional_token(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> dict | None:
    """Como verify_token pero devuelve None en lugar de lanzar excepción."""
    try:
        return verify_token(credentials)
    except Exception:
        return None
