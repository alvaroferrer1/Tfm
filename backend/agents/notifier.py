"""
Notifier Agent — envía mensajes a Telegram con HTML y chunking correcto.
"""
from __future__ import annotations
import os
import requests
from dotenv import load_dotenv
from backend.core.database import get_store

load_dotenv()

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_DEFAULT_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
_CHUNK_SIZE = 4000


def _get_chat_id(store_id: str) -> str:
    """Intenta obtener el chat_id específico de la tienda, fallback al env."""
    try:
        store = get_store(store_id)
        if store and store.get("telegram_chat_id"):
            return store["telegram_chat_id"]
    except Exception:
        pass
    return _DEFAULT_CHAT_ID


def _send_chunk(chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    url = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        if resp.status_code != 200:
            # Retry without parse_mode if HTML fails
            if parse_mode == "HTML":
                resp = requests.post(
                    url,
                    json={"chat_id": chat_id, "text": text[:4096]},
                    timeout=10,
                )
        return resp.status_code == 200
    except Exception as e:
        print(f"[notifier] Error: {e}")
        return False


def send_telegram(store_id: str, text: str) -> bool:
    """
    Envía un mensaje al chat de Telegram de la tienda.
    Maneja mensajes largos dividiéndolos en chunks.
    """
    if not _TOKEN:
        print("[notifier] TELEGRAM_BOT_TOKEN no configurado")
        return False

    chat_id = _get_chat_id(store_id)
    if not chat_id:
        print("[notifier] TELEGRAM_CHAT_ID no configurado")
        return False

    # Split por párrafos para no cortar en medio de una línea
    if len(text) <= _CHUNK_SIZE:
        return _send_chunk(chat_id, text)

    chunks = []
    current = []
    current_len = 0
    for line in text.split("\n"):
        line_len = len(line) + 1
        if current_len + line_len > _CHUNK_SIZE and current:
            chunks.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len
    if current:
        chunks.append("\n".join(current))

    success = True
    for chunk in chunks:
        if not _send_chunk(chat_id, chunk):
            success = False
    return success


def send_alert(store_id: str, title: str, body: str, urgent: bool = False) -> bool:
    """Envía una alerta formateada."""
    prefix = "URGENTE: " if urgent else ""
    message = f"{prefix}{title}\n\n{body}"
    return send_telegram(store_id, message)


def send_alert_with_buttons(
    store_id: str,
    text: str,
    buttons: list[list[tuple[str, str]]],
) -> bool:
    """
    Envía mensaje con teclado inline de confirmación.
    buttons: lista de filas, cada fila es lista de (label, callback_data).
    Permite que el encargado confirme donaciones con un solo toque.
    """
    if not _TOKEN:
        return False
    chat_id = _get_chat_id(store_id)
    if not chat_id:
        return False

    inline_keyboard = [
        [{"text": label, "callback_data": cb} for label, cb in row]
        for row in buttons
    ]
    url = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text[:4096],
                "reply_markup": {"inline_keyboard": inline_keyboard},
            },
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[notifier] send_alert_with_buttons error: {e}")
        return False


def send_dm(telegram_user_id: str, text: str) -> bool:
    """Envía un mensaje directo a un usuario de Telegram por su ID numérico."""
    if not _TOKEN or not telegram_user_id:
        return False
    return _send_chunk(str(telegram_user_id), text)


def notify_critical_action(store_id: str, action: dict) -> None:
    """
    DM proactivo a todos los empleados vinculados a Telegram cuando se crea
    una acción con score >= 85. Complementa el mensaje al grupo de la tienda.
    """
    if not _TOKEN:
        return

    try:
        from backend.core.database import get_db
        result = (
            get_db().table("users")
            .select("telegram_user_id, email")
            .eq("store_id", store_id)
            .not_.is_("telegram_user_id", "null")
            .execute()
        )
        users = result.data or []
    except Exception as e:
        print(f"[notifier] notify_critical_action — no users: {e}")
        return

    if not users:
        return

    batch = action.get("batches") or {}
    product = (batch.get("products") or {}) if isinstance(batch, dict) else {}
    name = product.get("name", "Producto")
    pasillo = product.get("pasillo", "?")
    action_type = (action.get("action_type") or "").upper()
    score = action.get("priority_score", 0)
    notes = (action.get("notes") or "")[:120]
    expiry = (batch.get("expiry_date") or "") if isinstance(batch, dict) else ""

    lines = [
        f"CRITICO — Acción urgente en tienda",
        "",
        f"Producto: {name}",
        f"Pasillo: {pasillo}",
        f"Acción: {action_type}",
        f"Urgencia: {score}/100",
    ]
    if expiry:
        lines.append(f"Caduca: {expiry}")
    if notes:
        lines.append(f"Nota: {notes}")
    lines += ["", "Responde a Chuwi con 'listo' cuando lo hayas hecho."]

    text = "\n".join(lines)

    for u in users:
        tg_id = u.get("telegram_user_id")
        if tg_id:
            try:
                _send_chunk(str(tg_id), text)
            except Exception:
                pass
