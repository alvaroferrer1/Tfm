"""
chuwi_persistence — estado de sesión e historial de conversaciones.

Centraliza:
  - Shared in-memory state (conv_state, conv_id_cache, session_cache, user_cache)
  - Historial de conversación (Supabase agent_memory → JSON fallback)
  - Compactación de historial con Haiku
  - Caché de usuario (TTL 60s)
  - Conv state por usuario (idle / route_active / completing_action / donation_flow)
  - _upsert_telegram_user / _persist_conversation_message → Supabase
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from backend.core import database, llm
from backend.core import memory as _mem

logger = logging.getLogger("mermaops.chuwi")

STORE_ID = os.getenv("STORE_ID", "demo-store-001")
MAX_HISTORY = 30

# ── Shared in-memory state ────────────────────────────────────────────────────

# Fallback al JSON si Supabase falla
_history_file = Path(__file__).parent.parent.parent / ".tmp" / "chuwi_history.json"
_history_file.parent.mkdir(exist_ok=True)

# user_id (str) → {"mode": str, "data": dict}
# modes: "idle", "route_active", "completing_action", "donation_flow"
_conv_state: dict[str, dict] = {}

# chat_key → conversation_id en Supabase
_conv_id_cache: dict[str, str] = {}

# user_id → session_id
_session_cache: dict[str, str] = {}

# Rate limiting
_user_last_msg: dict[str, float] = {}
_RATE_LIMIT_SECONDS = 2.0

# Cache TTL (24h)
_CACHE_TTL_SECONDS = 86400.0
_last_cleanup: float = 0.0

# Cache de usuarios por telegram_user_id
_user_cache: dict[str, tuple[Optional[dict], float]] = {}
_USER_CACHE_TTL = 60.0


# ── Cache cleanup ─────────────────────────────────────────────────────────────

def _cleanup_stale_caches() -> None:
    """Elimina entradas antiguas de los dicts en memoria para evitar memory leak."""
    global _last_cleanup
    now = time.monotonic()
    if now - _last_cleanup < 3600:
        return
    _last_cleanup = now
    cutoff = now - _CACHE_TTL_SECONDS
    stale_users = [k for k, v in _user_last_msg.items() if v < cutoff]
    for k in stale_users:
        _user_last_msg.pop(k, None)
        _conv_state.pop(k, None)
        _conv_id_cache.pop(k, None)
        _session_cache.pop(k, None)
    if stale_users:
        logger.debug(f"[chuwi] cache cleanup: {len(stale_users)} usuarios eliminados")


# ── Historial — Supabase primero, JSON como fallback ─────────────────────────

def _history_db_key(chat_key: str) -> str:
    return f"chuwi_conv_{chat_key}"


def _load_history_db(chat_key: str) -> Optional[list]:
    """Intenta cargar historial desde Supabase agent_memory."""
    try:
        val = _mem.recall(STORE_ID, _history_db_key(chat_key))
        if val:
            return json.loads(val)
    except Exception:
        pass
    return None


def _save_history_db(chat_key: str, history: list) -> bool:
    """Guarda historial en Supabase agent_memory. Returns True si éxito."""
    try:
        _mem.remember(STORE_ID, _history_db_key(chat_key),
                      json.dumps(history, ensure_ascii=False))
        return True
    except Exception:
        return False


def _load_history() -> dict:
    """Carga todos los historiales (archivo JSON, legacy fallback)."""
    if _history_file.exists():
        try:
            return json.loads(_history_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_history(history: dict) -> None:
    try:
        _history_file.write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _get_chat_history(chat_key: str) -> list:
    """Obtiene historial: Supabase → JSON file → vacío."""
    db_hist = _load_history_db(chat_key)
    if db_hist is not None:
        return db_hist
    history = _load_history()
    return history.get(chat_key, [])


def _persist_chat_history(chat_key: str, history: list) -> None:
    """Guarda historial: intenta Supabase, fallback a JSON."""
    if not _save_history_db(chat_key, history):
        all_history = _load_history()
        all_history[chat_key] = history
        _save_history(all_history)


def _compact_history(history: list) -> list:
    """
    Compacta el historial usando Haiku para resumir los turnos antiguos.
    Preserva datos operativos clave: acciones, productos, precios, decisiones.
    Cae en truncación simple si la llamada LLM falla.
    """
    if len(history) <= MAX_HISTORY:
        return history
    keep = MAX_HISTORY - 6
    old = history[:-keep]
    recent = history[-keep:]

    old_lines = []
    for m in old:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, str) and content.strip():
            old_lines.append(f"{role.upper()}: {content[:250]}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    old_lines.append(f"{role.upper()}: {block['text'][:200]}")

    if not old_lines:
        return [{"role": "user", "content": f"[{len(old)} mensajes anteriores omitidos.]"}] + recent

    old_text = "\n".join(old_lines[:60])

    try:
        summary = llm.call_fast(
            f"""Resume este historial de conversación sobre gestión de merma en un supermercado.
Conserva exactamente: acciones tomadas, productos críticos mencionados (nombre, pasillo, fecha),
decisiones del encargado, precios acordados y cualquier dato numérico relevante.
Máximo 120 palabras. Escribe en español, tono operativo.

HISTORIAL:
{old_text}""",
            max_tokens=180,
        )
        return [{"role": "user", "content": f"[Contexto anterior (Kuine): {summary}]"}] + recent
    except Exception:
        return [{"role": "user", "content": f"[{len(old)} mensajes anteriores — operaciones Super Martínez.]"}] + recent


# ── User cache ────────────────────────────────────────────────────────────────

def _get_user(telegram_user_id: int) -> Optional[dict]:
    key = str(telegram_user_id)
    cached = _user_cache.get(key)
    if cached is not None and time.monotonic() - cached[1] < _USER_CACHE_TTL:
        return cached[0]
    try:
        result = database.get_user_by_telegram_id(key)
        _user_cache[key] = (result, time.monotonic())
        return result
    except Exception:
        return None


def _invalidate_user_cache(telegram_user_id: int) -> None:
    """Limpia la cache para forzar recarga tras vincular/desvincular cuenta."""
    _user_cache.pop(str(telegram_user_id), None)


def _is_manager(user: Optional[dict]) -> bool:
    return user is not None and user.get("role") in ("admin", "manager")


# ── Conv state ────────────────────────────────────────────────────────────────

def _get_conv_state(user_id: str) -> dict:
    return _conv_state.get(user_id, {"mode": "idle", "data": {}})


def _set_conv_state(user_id: str, mode: str, data: dict = None) -> None:
    _conv_state[user_id] = {"mode": mode, "data": data or {}}


def _clear_conv_state(user_id: str) -> None:
    _conv_state.pop(user_id, None)


# ── Supabase persistence ──────────────────────────────────────────────────────

def _upsert_telegram_user(
    telegram_user_id: str,
    telegram_username: Optional[str],
    telegram_chat_id: str,
    linked_user: Optional[dict],
) -> None:
    """Registra o actualiza al usuario de Telegram en la tabla telegram_users."""
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        data: dict = {
            "telegram_user_id": telegram_user_id,
            "telegram_username": telegram_username,
            "telegram_chat_id": telegram_chat_id,
            "last_seen_at": now,
        }
        if linked_user:
            data["user_id"] = linked_user.get("id")
            data["store_id"] = linked_user.get("store_id") or STORE_ID
            data["status"] = "linked"
            data["linked_at"] = now
        else:
            data["status"] = "pending"
        database.get_db().table("telegram_users").upsert(
            data, on_conflict="telegram_user_id"
        ).execute()
    except Exception:
        pass  # no bloquear el flujo por error de tracking


def _persist_conversation_message(
    chat_key: str,
    store_id: str,
    telegram_user_id: str,
    user_text: str,
    response: str,
    tools_used: list[str],
    intent_tag: str = "pregunta_libre",
) -> None:
    """
    Persiste el turno de conversación en Supabase:
    - Crea o recupera la conversation_id del cache
    - Inserta mensaje de usuario y respuesta de Chuwi en agent_messages
    - Fallback silencioso si Supabase falla
    """
    try:
        conv_id = _conv_id_cache.get(chat_key)
        if not conv_id:
            conv_id = database.get_active_conversation(store_id, telegram_user_id)
        if not conv_id:
            conv_id = database.create_agent_conversation(store_id, telegram_user_id)
        _conv_id_cache[chat_key] = conv_id

        database.log_agent_message(
            conversation_id=conv_id,
            store_id=store_id,
            role="user",
            content=user_text,
            intent_tag=intent_tag,
            agent_source="telegram",
        )
        database.log_agent_message(
            conversation_id=conv_id,
            store_id=store_id,
            role="assistant",
            content=response,
            tools_used=tools_used,
            intent_tag=intent_tag,
            agent_source="chuwi",
        )
        # Log explícito de coordinación Chuwi → Kuine cuando se delega análisis
        if "analyze_product" in tools_used:
            database.log_agent_message(
                conversation_id=conv_id,
                store_id=store_id,
                role="system",
                content="[coordinación] Chuwi delegó análisis de producto a Kuine (supervisor.run_scan)",
                agent_source="kuine",
            )
        if tools_used:
            logger.info(f"[chuwi] persisted conv {conv_id[:8]}, tools={tools_used}")
    except Exception as exc:
        logger.warning(f"[chuwi] persist_conversation fallback (Supabase no disponible): {exc}")
