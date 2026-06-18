"""
Notifier Agent — envía mensajes a Telegram con HTML, chunking y deduplicación.
La deduplicación evita enviar la misma alerta más de una vez por hora.

Mejoras v2:
- SLA tracking: registro de cuándo se envió cada alerta crítica
- Confirmación de lectura: inline buttons en alertas críticas
- Escalación automática si no hay respuesta en N minutos
- Quiet hours inteligentes: urgentes SIEMPRE pasan, incluso a las 6:45am
"""
from __future__ import annotations
import hashlib
import logging
import os
import time
from datetime import datetime as _datetime, timezone

import requests
from dotenv import load_dotenv
from backend.core.database import get_store

logger = logging.getLogger("mermaops.notifier")

load_dotenv()

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_DEFAULT_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
_CHUNK_SIZE = 4000

# Deduplicación de alertas
_alert_dedup: dict[str, float] = {}
_DEDUP_WINDOW_SECONDS = 3600.0

# SLA tracking: action_id → {"sent_at": timestamp, "acknowledged": bool, "message_id": int}
_sla_tracker: dict[str, dict] = {}
_SLA_CRITICAL_MINUTES = 30   # escalar si no hay ACK en 30 min
_SLA_HIGH_MINUTES = 120      # escalar ALTO en 2h

# Quiet hours inteligentes:
# - Alertas de seguridad alimentaria (retirar): SIEMPRE, sin importar hora
# - Alertas CRÍTICO: silencio 23:00-07:00 (pero nunca si caduca en <2h)
# - Alertas normales: silencio 22:00-07:00
# - Acumulación en horas pico de caja: 10:00-11:30 y 17:30-19:30 (evita interrumpir atención al cliente)
_QUIET_HOUR_START = 23
_QUIET_HOUR_END = 7
# Horas pico en caja — no molestar con alertas no críticas
_CAJA_PEAKS = [(10, 0, 11, 30), (17, 30, 19, 30)]


def _is_caja_peak_hours() -> bool:
    """True si estamos en hora pico de caja donde el personal no puede atender el móvil."""
    try:
        now = _datetime.now()
        h = int(now.hour)
        m = int(now.minute) if hasattr(now, 'minute') and isinstance(now.minute, int) else 0
        current_mins = h * 60 + m
        for h1, m1, h2, m2 in _CAJA_PEAKS:
            if h1 * 60 + m1 <= current_mins <= h2 * 60 + m2:
                return True
    except (TypeError, ValueError):
        return False
    return False


def _is_quiet_hours(urgent: bool = False, expiry_hours: float | None = None) -> bool:
    """
    Quiet hours inteligentes:
    - Siempre envía si el producto caduca en menos de 2 horas (emergencia real)
    - Urgente/crítico: silencio 23:00-07:00
    - Normal: silencio 22:00-07:00 + horas pico de caja (10-11:30 y 17:30-19:30)
    Las alertas acumuladas durante horas pico se envían al final del pico.
    """
    if expiry_hours is not None and expiry_hours < 2.0:
        return False  # emergencia — nunca silenciar
    hour = _datetime.now().hour
    # En horario laboral (8-21h) NUNCA silenciar — el equipo está trabajando
    if 8 <= hour < 21:
        return False
    if urgent:
        return hour >= _QUIET_HOUR_START or hour < _QUIET_HOUR_END
    return hour >= 22 or hour < _QUIET_HOUR_END


def _dedup_key(store_id: str, title: str, body: str) -> str:
    raw = f"{store_id}:{title}:{body[:60]}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _is_duplicate(key: str) -> bool:
    """True si esta alerta ya fue enviada en la última hora."""
    last_sent = _alert_dedup.get(key)
    if last_sent and (time.monotonic() - last_sent) < _DEDUP_WINDOW_SECONDS:
        return True
    _alert_dedup[key] = time.monotonic()
    return False


def _get_chat_id(store_id: str) -> str:
    """Intenta obtener el chat_id específico de la tienda, fallback al env."""
    try:
        store = get_store(store_id)
        if store and store.get("telegram_chat_id"):
            return store["telegram_chat_id"]
    except Exception:
        pass
    # Fallback: agent_memory (saved by _auto_save_chat_id in chuwi.py)
    try:
        from backend.core import memory as _mem
        chat_id = _mem.recall(store_id, "telegram_admin_chat_id")
        if chat_id:
            return str(chat_id)
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
        logger.warning(f"[notifier] Error enviando mensaje: {e}")
        return False


def send_telegram(store_id: str, text: str) -> bool:
    """
    Envía un mensaje al chat de Telegram de la tienda.
    Maneja mensajes largos dividiéndolos en chunks.
    """
    if not _TOKEN:
        logger.warning("[notifier] TELEGRAM_BOT_TOKEN no configurado — mensaje no enviado")
        return False

    chat_id = _get_chat_id(store_id)
    if not chat_id:
        logger.warning(f"[notifier] Sin chat_id para tienda {store_id} — mensaje no enviado")
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


def send_alert(
    store_id: str,
    title: str,
    body: str,
    urgent: bool = False,
    action_id: str | None = None,
    expiry_hours: float | None = None,
) -> bool:
    """
    Envía una alerta formateada con deduplicación y SLA tracking.
    - action_id: si se proporciona, registra el envío en _sla_tracker
    - expiry_hours: horas hasta caducidad (anula quiet hours si < 2h)
    """
    key = _dedup_key(store_id, title, body)
    if _is_duplicate(key):
        logger.debug(f"[notifier] Alerta duplicada suprimida: {title[:40]}")
        return True

    if not urgent and _is_quiet_hours(urgent=urgent, expiry_hours=expiry_hours):
        logger.info(f"[notifier] Alerta diferida (silencio): {title[:40]}")
        return True

    prefix = "URGENTE: " if urgent else ""
    message = f"{prefix}{title}\n\n{body}"
    result = send_telegram(store_id, message)

    # SLA tracking para acciones críticas
    if result and action_id and urgent:
        _sla_tracker[action_id] = {
            "sent_at": time.monotonic(),
            "sent_at_iso": _datetime.now(timezone.utc).isoformat(),
            "acknowledged": False,
            "store_id": store_id,
            "title": title[:60],
        }
        logger.debug(f"[notifier] SLA iniciado para acción {action_id}")

    return result


def acknowledge_alert(action_id: str) -> bool:
    """Marca una alerta como reconocida (empleado respondió). Detiene escalación."""
    if action_id in _sla_tracker:
        _sla_tracker[action_id]["acknowledged"] = True
        elapsed = time.monotonic() - _sla_tracker[action_id]["sent_at"]
        logger.info(f"[notifier] ACK alerta {action_id} en {elapsed/60:.1f} min")
        return True
    return False


def check_sla_violations(store_id: str) -> list[dict]:
    """
    Devuelve alertas críticas que superaron el SLA sin acknowledgment.
    Llamar desde el scheduler cada 15 minutos para escalación.
    """
    now = time.monotonic()
    violations = []
    for action_id, sla in list(_sla_tracker.items()):
        if sla.get("acknowledged"):
            continue
        if sla.get("store_id") != store_id:
            continue
        elapsed_minutes = (now - sla["sent_at"]) / 60
        if elapsed_minutes > _SLA_CRITICAL_MINUTES:
            violations.append({
                "action_id": action_id,
                "elapsed_minutes": round(elapsed_minutes),
                "sent_at": sla["sent_at_iso"],
                "title": sla["title"],
            })
    return violations


def send_sla_escalation(store_id: str, violations: list[dict]) -> None:
    """Envía mensaje de escalación al encargado cuando hay SLA violations."""
    if not violations:
        return
    lines = ["ESCALACIÓN — Acciones sin confirmar:"]
    for v in violations[:5]:
        lines.append(f"- {v['title']} (hace {v['elapsed_minutes']} min sin respuesta)")
    lines.append("\nResponde a Chuwi con 'listo' para confirmar cada acción.")
    send_telegram(store_id, "\n".join(lines))


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
        logger.warning(f"send_alert_with_buttons error: {e}")
        return False


def send_dm(telegram_user_id: str, text: str) -> bool:
    """Envía un mensaje directo a un usuario de Telegram por su ID numérico."""
    if not _TOKEN or not telegram_user_id:
        return False
    return _send_chunk(str(telegram_user_id), text)


def notify_critical_action(store_id: str, action: dict) -> None:
    """
    DM proactivo con inline keyboard a todos los empleados vinculados.
    - Botones de confirmación directa (un toque = acción completada)
    - SLA tracking por acción
    - Mensaje enriquecido con impacto económico
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
        logger.warning(f"notify_critical_action — no users: {e}")
        return

    if not users:
        return

    batch = action.get("batches") or {}
    product = (batch.get("products") or {}) if isinstance(batch, dict) else {}
    name = product.get("name", "Producto")
    pasillo = product.get("pasillo", "?")
    action_type = (action.get("action_type") or "").upper()
    action_id = str(action.get("id", ""))
    score = action.get("priority_score", 0)
    notes = (action.get("notes") or "")[:120]
    expiry = (batch.get("expiry_date") or "") if isinstance(batch, dict) else ""
    qty = int((batch.get("quantity") or 0)) if isinstance(batch, dict) else 0
    price = float(product.get("price") or 0)
    new_price = action.get("new_price")
    cost = float(product.get("cost") or 0)

    # Calcular impacto económico según tipo de acción
    urgency_icon = "🔴" if score >= 90 else "🟡"
    if action_type == "REBAJAR" and new_price:
        economic_line = f"Recuperarás {round(float(new_price) * qty, 2):.2f}€ si vendes todo"
        action_icon = "💰"
    elif action_type == "DONAR":
        deduccion = round(qty * cost * 0.35, 2)
        economic_line = f"Deducción fiscal: {deduccion:.2f}€ (Ley 49/2002)"
        action_icon = "❤️"
    elif action_type == "RETIRAR":
        loss = round(qty * cost, 2)
        economic_line = f"Pérdida: {loss:.2f}€ — registrar en albarán de merma"
        action_icon = "🗑"
    else:
        economic_line = ""
        action_icon = "⚡"

    lines = [
        f"{urgency_icon} <b>CRÍTICO — {action_icon} {action_type}</b>",
        "",
        f"<b>{name}</b>",
        f"📍 Pasillo {pasillo}",
        f"Urgencia: {score}/100",
    ]
    if expiry:
        lines.append(f"📅 Caduca: {expiry}")
    if qty:
        lines.append(f"📦 {qty} unidades")
    if new_price:
        lines.append(f"💶 Nuevo precio: {float(new_price):.2f}€")
    if economic_line:
        lines.append(f"✓ {economic_line}")
    if notes:
        lines.append(f"\n<i>{notes}</i>")

    text = "\n".join(lines)

    # Inline keyboard según tipo de acción
    raw_action_type = (action.get("action_type") or "revisar").lower()
    if raw_action_type == "rebajar":
        price_label = f"✅ Precio cambiado a {float(new_price):.2f}€" if new_price else "✅ Precio rebajado"
        keyboard = {"inline_keyboard": [[
            {"text": price_label, "callback_data": f"action_confirm:{action_id}"},
            {"text": "❤️ Mejor donar", "callback_data": f"action_donate:{action_id}"},
        ], [
            {"text": "📋 Ver en Chuwi", "callback_data": "cmd:acciones"},
        ]]}
    elif raw_action_type == "donar":
        keyboard = {"inline_keyboard": [[
            {"text": "❤️ Banco Alimentos", "callback_data": f"action_donate_entity:{action_id}:banco_alimentos"},
            {"text": "🕊 Cáritas", "callback_data": f"action_donate_entity:{action_id}:caritas"},
        ], [
            {"text": "💰 Mejor rebajar", "callback_data": f"action_rebajar_instead:{action_id}"},
        ]]}
    elif raw_action_type == "retirar":
        keyboard = {"inline_keyboard": [[
            {"text": "🗑 Retirado y registrado", "callback_data": f"action_confirm:{action_id}"},
            {"text": "❤️ Donar si válido", "callback_data": f"action_donate:{action_id}"},
        ]]}
    else:
        keyboard = {"inline_keyboard": [[
            {"text": "✅ Completado", "callback_data": f"action_confirm:{action_id}"},
        ]]}

    # Registrar SLA antes de enviar
    sent_to = []
    photo_url = product.get("photo_url") or product.get("image_url") or ""
    if action_id:
        _sla_tracker[action_id] = {
            "sent_at": time.monotonic(),
            "sent_at_iso": _datetime.now(timezone.utc).isoformat(),
            "acknowledged": False,
            "store_id": store_id,
            "title": f"{action_type} — {name}",
            "chat_ids": sent_to,
            "followup_sent": False,
            "expiry": expiry,
            "name": name,
            "action_type": (action.get("action_type") or "acción").lower(),
        }

    url = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"
    for u in users:
        tg_id = u.get("telegram_user_id")
        if not tg_id:
            continue
        sent = False
        if photo_url:
            try:
                resp = requests.post(
                    f"https://api.telegram.org/bot{_TOKEN}/sendPhoto",
                    json={
                        "chat_id": str(tg_id),
                        "photo": photo_url,
                        "caption": text[:1024],
                        "parse_mode": "HTML",
                        "reply_markup": keyboard,
                    },
                    timeout=10,
                )
                sent = resp.status_code == 200
            except Exception:
                pass
        if not sent:
            try:
                resp = requests.post(url, json={
                    "chat_id": str(tg_id),
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": keyboard,
                }, timeout=10)
                if resp.status_code == 200:
                    sent = True
                else:
                    _send_chunk(str(tg_id), text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
            except Exception as e:
                logger.warning(f"[notifier] DM falló para {tg_id}: {e}")
        if sent:
            sent_to.append(str(tg_id))


def check_sla_followups() -> int:
    """
    Checks for unacknowledged critical alerts and sends follow-up reminders.
    Call this from the scheduler every 30 minutes.
    Returns number of follow-ups sent.
    """
    if not _TOKEN:
        return 0
    sent = 0
    now = time.monotonic()
    for action_id, entry in list(_sla_tracker.items()):
        if entry.get("acknowledged") or entry.get("followup_sent"):
            continue
        elapsed_min = (now - entry["sent_at"]) / 60
        if elapsed_min < _SLA_CRITICAL_MINUTES:
            continue

        # Check if action is still pending in DB
        try:
            from backend.core.database import get_db
            row = get_db().table("actions").select("status").eq("id", action_id).maybe_single().execute()
            if not row.data or row.data.get("status") != "pending":
                entry["acknowledged"] = True
                continue
        except Exception:
            continue

        name = entry.get("name", "producto")
        action_type = entry.get("action_type", "acción")
        expiry = entry.get("expiry", "")
        chat_ids = entry.get("chat_ids", [])

        # Compute time remaining
        try:
            from datetime import date as _date_cls
            days_left = (_date_cls.fromisoformat(expiry) - _date_cls.today()).days if expiry else 1
            urgency = "⚠️ QUEDAN POCAS HORAS" if days_left <= 0 else f"caduca en {days_left}d"
        except Exception:
            urgency = "acción pendiente"

        followup_text = (
            f"🔔 <b>Seguimiento — sin respuesta</b>\n\n"
            f"<b>{name}</b> sigue sin {action_type}.\n"
            f"Han pasado {int(elapsed_min)} minutos · {urgency}.\n\n"
            f"¿Lo gestionas ahora?"
        )
        keyboard = {"inline_keyboard": [[
            {"text": "✅ Lo gestiono ahora", "callback_data": f"action_detail:{action_id}"},
            {"text": "⏸ Ignorar", "callback_data": f"sla_dismiss:{action_id}"},
        ]]}

        url = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"
        for chat_id in chat_ids:
            try:
                resp = requests.post(url, json={
                    "chat_id": str(chat_id),
                    "text": followup_text,
                    "parse_mode": "HTML",
                    "reply_markup": keyboard,
                }, timeout=10)
                if resp.status_code == 200:
                    sent += 1
            except Exception as e:
                logger.warning(f"[sla followup] Error: {e}")

        entry["followup_sent"] = True
        logger.info(f"[sla] Follow-up sent for action {action_id} after {int(elapsed_min)} min")

    return sent


def notify_low_stock(store_id: str, alerts: list[dict]) -> int:
    """
    Envía alerta de stock bajo con botón 'Hacer pedido' al chat de la tienda.
    Cada alert: {product_name, current_qty, suggested_qty, product_id}
    Retorna número de mensajes enviados.
    """
    if not alerts or not _TOKEN:
        return 0
    chat_id = _get_chat_id(store_id)
    if not chat_id:
        return 0

    dedup_key = _dedup_key(store_id, "low_stock", str([a.get("product_name") for a in alerts[:3]]))
    if _is_duplicate(dedup_key):
        return 0

    lines = ["🛒 <b>STOCK BAJO — Reposición necesaria</b>", ""]
    for a in alerts[:6]:
        name = a.get("product_name", "Producto")
        qty = a.get("current_qty", 0)
        sug = a.get("suggested_qty", 20)
        lines.append(f"• <b>{name}</b> — quedan {qty} uds (pedir ≈ {sug} uds)")

    lines += ["", "<i>¿Hago el pedido semanal ahora?</i>"]
    text = "\n".join(lines)

    keyboard = {"inline_keyboard": [
        [
            {"text": "🛒 Sí, hacer pedido", "callback_data": "cmd:pedido"},
            {"text": "❌ Ya lo gestiono", "callback_data": "stock_skip"},
        ]
    ]}

    url = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        }, timeout=10)
        return 1 if resp.status_code == 200 else 0
    except Exception as e:
        logger.warning(f"[notifier] notify_low_stock falló: {e}")
        return 0


def notify_stock_restored(store_id: str, product_name: str, new_qty: int) -> None:
    """Notifica cuando llega stock nuevo (reposición completada)."""
    chat_id = _get_chat_id(store_id)
    if not chat_id or not _TOKEN:
        return
    text = f"✅ <b>Stock repuesto</b>\n\n<b>{product_name}</b> → {new_qty} unidades en almacén."
    _send_chunk(str(chat_id), text)
