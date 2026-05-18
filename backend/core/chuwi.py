"""
Chuwi — agente conversacional de MermaOps.

Filosofía: NO es un bot de comandos. Es un agente que entiende intención,
razona con datos reales y responde como lo haría un encargado experto.
Basado en el patrón Jeffrey del máster: typing loop, historial comprimido,
teclados inline para navegación, voz via Whisper.

El agente tiene 4 modos:
  1. Conversación libre — cualquier pregunta sobre la tienda
  2. Menú de capacidades — cuando pregunta qué puede hacer
  3. Comandos de acción rápida — accesibles desde el menú inline
  4. Modo ruta activa — guía al empleado acción por acción
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
import tempfile
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from backend.core import llm, database, memory as _mem
from backend.agents import supervisor

load_dotenv()

logger = logging.getLogger("mermaops.chuwi")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
STORE_ID = os.getenv("STORE_ID", "demo-store-001")
MAX_HISTORY = 30

# Fallback al JSON si Supabase falla
_history_file = Path(__file__).parent.parent.parent / ".tmp" / "chuwi_history.json"
_history_file.parent.mkdir(exist_ok=True)

# Estado de conversación por usuario (en memoria del proceso — ligero)
# user_id (str) → {"mode": str, "data": dict}
# modes: "idle", "route_active", "completing_action", "donation_flow"
_conv_state: dict[str, dict] = {}


# ── OpenAI / Whisper (opcional) ───────────────────────────────────────────────

_openai_client = None


def _get_openai():
    global _openai_client
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return None
    if _openai_client is None:
        try:
            from openai import OpenAI
            _openai_client = OpenAI(api_key=key)
        except ImportError:
            return None
    return _openai_client


# ── System prompt ─────────────────────────────────────────────────────────────

CHUWI_SYSTEM = """Eres Chuwi, el agente operativo de MermaOps para el Super Martinez.
Hablas con empleados y encargados de supermercado en sus turnos de trabajo.

PERSONALIDAD:
- Directo, claro y práctico. Sin rodeos.
- Nunca usas asteriscos ni markdown — texto limpio, como un WhatsApp profesional.
- Cuando haces listas, usas guiones o números.
- Mayúsculas para énfasis: CRÍTICO, REBAJAR, RETIRAR.
- Respondes en el idioma del empleado (español por defecto).

CAPACIDADES REALES que tienes — úsalas cuando el contexto lo pida:
- Ver el brief del día (resumen de apertura, acciones prioritarias)
- Analizar un producto por su código de barras
- ANALIZAR FOTOS de productos con IA visual — detecta frescura, daños, fechas visibles
- Calcular la ruta óptima del día por pasillos
- Ver acciones pendientes con su prioridad
- Consultar merma de los últimos 7 días
- Ver impacto ESG — CO2 evitado, agua ahorrada, puntuación sostenibilidad
- Ver impacto social de donaciones del mes y deducción fiscal estimada
- Ver predicciones de merma para los próximos 5-7 días con clima
- Ver ficha de proveedores con su tasa de merma (solo encargados)
- Ver sugerencias de pedido semanal (solo encargados)
- Generar el brief manualmente en cualquier momento (solo encargados)
- Responder preguntas generales sobre gestión de merma y caducidades

REGLAS:
- Si el usuario pregunta qué puedes hacer, explica con ejemplos concretos.
- Si el usuario manda una foto, analizarla visualmente SIN QUE LO PIDA — es tu comportamiento por defecto.
- Si la información necesita acceder a la BD, indícalo y hazlo.
- Si no sabes algo, dilo. No inventes datos.
- Si el empleado no está registrado, explica cómo vincularse."""


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
    if len(history) <= MAX_HISTORY:
        return history
    old = history[:-MAX_HISTORY + 4]
    recent = history[-MAX_HISTORY + 4:]
    summary = (
        f"[Resumen de {len(old)} mensajes anteriores sobre operaciones "
        f"del Super Martinez, gestión de merma y productos.]"
    )
    return [{"role": "user", "content": summary}] + recent


# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_user(telegram_user_id: int) -> Optional[dict]:
    try:
        return database.get_user_by_telegram_id(str(telegram_user_id))
    except Exception:
        return None


def _is_manager(user: Optional[dict]) -> bool:
    return user is not None and user.get("role") in ("admin", "manager")


# ── Formato HTML para Telegram ────────────────────────────────────────────────

def _md_to_html(text: str) -> str:
    text = html.escape(text)
    placeholders: dict[str, str] = {}
    counter = 0

    def protect(tag: str) -> str:
        nonlocal counter
        key = f"\x00{counter}\x00"
        counter += 1
        placeholders[key] = tag
        return key

    text = re.sub(
        r"```(?:\w+)?\n?(.*?)```",
        lambda m: protect("<pre><code>" + m.group(1).strip() + "</code></pre>"),
        text, flags=re.DOTALL,
    )
    text = re.sub(
        r"`([^`\n]+)`",
        lambda m: protect("<code>" + m.group(1) + "</code>"),
        text,
    )
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"\*([^*\n]+)\*", r"<i>\1</i>", text)
    text = re.sub(r"_([^_\n]+)_", r"<i>\1</i>", text)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    for key, value in placeholders.items():
        text = text.replace(key, value)
    return text


# ── Typing loop (patrón Jeffrey) ──────────────────────────────────────────────

async def _typing_loop(bot, chat_id: int, done: asyncio.Event) -> None:
    try:
        while not done.is_set():
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            try:
                await asyncio.wait_for(done.wait(), timeout=4)
            except asyncio.TimeoutError:
                pass
    except (asyncio.CancelledError, Exception):
        pass


# ── Send helpers ──────────────────────────────────────────────────────────────

async def _safe_edit(message, text: str, reply_markup=None) -> None:
    formatted = _md_to_html(text)
    limit = 4096
    try:
        if len(formatted) <= limit:
            await message.edit_text(
                formatted, parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
        else:
            await message.edit_text(
                formatted[:limit], parse_mode=ParseMode.HTML,
            )
            for i in range(limit, len(formatted), limit):
                await message.get_bot().send_message(
                    message.chat_id, formatted[i:i + limit], parse_mode=ParseMode.HTML,
                )
    except Exception:
        try:
            await message.edit_text(text[:limit], reply_markup=reply_markup)
        except Exception:
            pass


async def _send(update: Update, text: str, reply_markup=None) -> None:
    formatted = _md_to_html(text)
    limit = 4096
    try:
        chunks = [formatted[i:i + limit] for i in range(0, len(formatted), limit)]
        for i, chunk in enumerate(chunks):
            await update.message.reply_text(
                chunk,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup if i == len(chunks) - 1 else None,
            )
    except Exception:
        await update.message.reply_text(text[:limit], reply_markup=reply_markup)


# ── Teclados inline ───────────────────────────────────────────────────────────

def _main_menu_keyboard(is_manager: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("📋 Brief del día", callback_data="cmd:brief"),
            InlineKeyboardButton("⚡ Acciones", callback_data="cmd:acciones"),
        ],
        [
            InlineKeyboardButton("🗺 Ruta del día", callback_data="cmd:ruta"),
            InlineKeyboardButton("📊 Merma 7 días", callback_data="cmd:merma"),
        ],
        [
            InlineKeyboardButton("❤️ Donaciones", callback_data="cmd:donaciones"),
            InlineKeyboardButton("🤝 Registrar donación", callback_data="cmd:donar_flow"),
        ],
        [
            InlineKeyboardButton("🔍 Escanear", callback_data="cmd:scan_help"),
            InlineKeyboardButton("📈 Dashboard", callback_data="cmd:stats"),
        ],
    ]
    if is_manager:
        rows.append([
            InlineKeyboardButton("📦 Proveedores", callback_data="cmd:proveedores"),
            InlineKeyboardButton("🛒 Pedido semanal", callback_data="cmd:pedido"),
        ])
        rows.append([
            InlineKeyboardButton("🌱 ESG / Impacto", callback_data="cmd:esg"),
            InlineKeyboardButton("🔮 Predicciones", callback_data="cmd:prediccion"),
        ])
        rows.append([
            InlineKeyboardButton("⚙️ Generar brief ahora", callback_data="cmd:runbrief"),
            InlineKeyboardButton("📖 Normativa citada", callback_data="cmd:citar"),
        ])
    rows.append([
        InlineKeyboardButton("❓ ¿Qué puedo preguntarte?", callback_data="cmd:ayuda"),
        InlineKeyboardButton("🎯 Cómo funciona todo", callback_data="cmd:tour"),
    ])
    return InlineKeyboardMarkup(rows)


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("↩ Menú principal", callback_data="cmd:menu"),
    ]])


def _smart_keyboard(response_text: str, is_manager: bool) -> InlineKeyboardMarkup:
    """
    Teclado contextual inteligente basado en el contenido de la respuesta.
    En lugar de siempre mostrar "← Volver", muestra botones relevantes.
    """
    text_lower = response_text.lower()
    buttons = []

    if any(w in text_lower for w in ["caduca", "crítico", "critico", "rebajar", "retirar", "urgente"]):
        buttons.append(InlineKeyboardButton("⚡ Ver acciones", callback_data="cmd:acciones"))
    if any(w in text_lower for w in ["ruta", "pasillo", "recorrido", "orden"]):
        buttons.append(InlineKeyboardButton("🗺 Ver ruta", callback_data="cmd:ruta"))
    if any(w in text_lower for w in ["merma", "pérdida", "perdida", "valor perdido"]):
        buttons.append(InlineKeyboardButton("📊 Ver merma", callback_data="cmd:merma"))
    if any(w in text_lower for w in ["donaci", "banco de alimentos", "cáritas"]):
        buttons.append(InlineKeyboardButton("❤️ Donaciones", callback_data="cmd:donaciones"))
    if any(w in text_lower for w in ["proveedor", "suministrador"]) and is_manager:
        buttons.append(InlineKeyboardButton("📦 Proveedores", callback_data="cmd:proveedores"))
    if any(w in text_lower for w in ["brief", "resumen", "apertura", "mañana"]):
        buttons.append(InlineKeyboardButton("📋 Ver brief", callback_data="cmd:brief"))
    if any(w in text_lower for w in ["pedido", "pedir", "reposic"]) and is_manager:
        buttons.append(InlineKeyboardButton("🛒 Pedido", callback_data="cmd:pedido"))

    menu_btn = InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")

    if not buttons:
        return _back_keyboard()

    rows = [buttons[i:i + 2] for i in range(0, min(len(buttons), 4), 2)]
    rows.append([menu_btn])
    return InlineKeyboardMarkup(rows)


def _scan_result_keyboard(response_text: str, barcode: str) -> InlineKeyboardMarkup:
    """
    Teclado post-escaneo: acciones directas según lo que Chuwi recomienda.
    El empleado confirma desde Telegram sin abrir la app.
    """
    text_lower = response_text.lower()
    rows = []

    if "rebajar" in text_lower:
        rows.append([
            InlineKeyboardButton(
                "✅ He rebajado el precio",
                callback_data=f"scan_done:rebajar:{barcode}"
            ),
        ])
        rows.append([
            InlineKeyboardButton("📸 Ver acciones en app", callback_data="cmd:acciones"),
            InlineKeyboardButton("↩ Menú", callback_data="cmd:menu"),
        ])
    elif "retirar" in text_lower:
        rows.append([
            InlineKeyboardButton(
                "✅ Producto retirado",
                callback_data=f"scan_done:retirar:{barcode}"
            ),
            InlineKeyboardButton(
                "❤️ Donar en vez de retirar",
                callback_data=f"scan_done:donar:{barcode}"
            ),
        ])
        rows.append([InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")])
    elif "donar" in text_lower:
        rows.append([
            InlineKeyboardButton(
                "✅ Banco de Alimentos",
                callback_data=f"scan_done:donar_banco:{barcode}"
            ),
            InlineKeyboardButton(
                "✅ Cáritas",
                callback_data=f"scan_done:donar_caritas:{barcode}"
            ),
        ])
        rows.append([
            InlineKeyboardButton(
                "✅ Cruz Roja",
                callback_data=f"scan_done:donar_cruzroja:{barcode}"
            ),
            InlineKeyboardButton("↩ Menú", callback_data="cmd:menu"),
        ])
    else:
        rows = [[InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")]]

    return InlineKeyboardMarkup(rows)


def _route_action_keyboard(action_id: str, remaining: int) -> InlineKeyboardMarkup:
    """Teclado durante el modo ruta activa: confirmar y pasar al siguiente."""
    rows = [
        [
            InlineKeyboardButton("✅ Hecho", callback_data=f"route_done:{action_id}"),
            InlineKeyboardButton("⏭ Saltar", callback_data=f"route_skip:{action_id}"),
        ],
        [
            InlineKeyboardButton("🛑 Pausar ruta", callback_data="route_pause"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


# ── Detección de intenciones y estado ─────────────────────────────────────────

_INTENT_KEYWORDS: dict[str, list[str]] = {
    "brief": ["brief", "resumen", "apertura", "hoy", "mañana", "día"],
    "acciones": ["accion", "acción", "pendiente", "urgente", "critico", "crítico", "tarea"],
    "ruta": ["ruta", "pasillo", "recorrido", "orden", "camino"],
    "merma": ["merma", "perdida", "pérdida", "caducado", "vencido", "tirado"],
    "donaciones": ["donacion", "donación", "banco de alimentos", "impacto", "social"],
    "scan": ["escanear", "escanea", "codigo", "código", "barcode", "barras", "/scan"],
    "proveedores": ["proveedor", "suministrador"],
    "pedido": ["pedido", "pedir", "reposicion", "reposición", "comprar"],
    "ayuda": ["ayuda", "qué puedes", "que puedes", "qué sabes", "que sabes", "capacidades"],
    "stats": ["stats", "dashboard", "kpi", "kpis", "resumen tienda", "cuadro de mando"],
    "citar": ["normativa", "por qué", "porque hay que", "citar", "justifica", "reglamento", "regla"],
}

_COMPLETION_WORDS = [
    "listo", "hecho", "terminé", "termine", "completé", "complete",
    "ya está", "ya esta", "lo hice", "lo he hecho", "ya lo hice",
    "está hecho", "esta hecho", "hice el", "hice la", "he hecho",
    "realizado", "ya", "done", "ok listo",
]

_ROUTE_START_WORDS = [
    "iniciar ruta", "empezar ruta", "comenzar ruta", "hacer la ruta",
    "voy a hacer la ruta", "dame la ruta", "empiezo la ruta",
    "seguir la ruta", "modo ruta",
]


def _detect_intent(text: str) -> Optional[str]:
    text_lower = text.lower()
    for intent, keywords in _INTENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return intent
    return None


def _is_completion_message(text: str) -> bool:
    text_lower = text.lower().strip()
    return any(w in text_lower for w in _COMPLETION_WORDS)


def _is_route_start(text: str) -> bool:
    text_lower = text.lower().strip()
    return any(w in text_lower for w in _ROUTE_START_WORDS)


def _get_conv_state(user_id: str) -> dict:
    return _conv_state.get(user_id, {"mode": "idle", "data": {}})


def _set_conv_state(user_id: str, mode: str, data: dict = None) -> None:
    _conv_state[user_id] = {"mode": mode, "data": data or {}}


def _clear_conv_state(user_id: str) -> None:
    _conv_state.pop(user_id, None)


# ── Respuesta de bienvenida ───────────────────────────────────────────────────

def _welcome_text(name: str, is_manager: bool) -> str:
    role_extra = (
        "\n\nComo encargado tienes acceso a: proveedores, pedido semanal, "
        "generar brief manualmente y ver estadísticas completas."
        if is_manager else ""
    )
    return (
        f"Hola {name}. Soy Chuwi, tu agente de MermaOps.\n\n"
        f"Puedo ayudarte con cualquier cosa sobre la tienda: qué caduca hoy, "
        f"qué acciones hay pendientes, cómo está la merma, qué rutas seguir...\n\n"
        f"Escríbeme en lenguaje natural o usa el menú de abajo.{role_extra}"
    )


# ── Núcleo del agente — respuesta conversacional ──────────────────────────────

def _agent_respond(chat_history: list, user_text: str, user: Optional[dict]) -> str:
    """
    Fallback síncrono del agente — usado cuando el streaming no está disponible.
    El path normal pasa por _agent_stream (streaming progresivo).
    """
    system_extra = _build_agent_system(user)
    messages = _compact_history(list(chat_history))
    messages.append({"role": "user", "content": user_text})
    return llm.call_with_history(messages, system_extra=system_extra, max_tokens=1024)


# ── Modo ruta activa ──────────────────────────────────────────────────────────

def _get_route_actions() -> list:
    """Obtiene las acciones pendientes ordenadas para modo ruta (FEFO + score)."""
    try:
        pending = database.get_pending_actions(STORE_ID)
        return sorted(pending, key=lambda a: -a.get("priority_score", 0))
    except Exception:
        return []


def _format_route_action(action: dict, index: int, total: int) -> str:
    """Formatea una acción para el modo ruta activa."""
    batch = action.get("batches") or {}
    product = (batch.get("products") or {}) if batch else {}
    name = product.get("name", "Producto")
    pasillo = product.get("pasillo", "?")
    estanteria = product.get("estanteria", "?")
    nivel = product.get("nivel", "?")
    action_type = action.get("action_type", "").upper()
    score = action.get("priority_score", 0)
    notes = action.get("notes", "")
    new_price = action.get("new_price")
    expiry = (batch.get("expiry_date") or "")

    urgency = "🔴" if score >= 85 else "🟡" if score >= 65 else "🟢"

    lines = [
        f"{urgency} ACCIÓN {index}/{total}",
        "",
        f"Producto: {name}",
        f"Ubicación: Pasillo {pasillo} — Estantería {estanteria} — Nivel {nivel}",
        f"Acción: {action_type}",
    ]
    if expiry:
        try:
            days = (date.fromisoformat(expiry) - date.today()).days
            lines.append(f"Caduca: {expiry} ({days} días)")
        except Exception:
            lines.append(f"Caduca: {expiry}")
    if new_price:
        lines.append(f"Nuevo precio: {new_price:.2f}€")
    if notes:
        lines.append(f"Nota: {notes[:100]}")

    return "\n".join(lines)


async def _start_route_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, user: Optional[dict]) -> None:
    """Inicia el modo ruta activa — guía al empleado acción por acción."""
    actions = _get_route_actions()

    if not actions:
        await update.message.reply_text(
            "Sin acciones pendientes para hacer la ruta. Todo en orden.",
            reply_markup=_back_keyboard()
        )
        return

    user_id = str(update.effective_user.id)
    action_ids = [a.get("id") for a in actions if a.get("id")]
    _set_conv_state(user_id, "route_active", {
        "action_ids": action_ids,
        "current_index": 0,
        "skipped": [],
        "completed": [],
    })

    first = actions[0]
    text = (
        f"🗺 MODO RUTA ACTIVA — {len(actions)} acciones pendientes\n\n"
        + _format_route_action(first, 1, len(actions))
        + "\n\n¿Listo para empezar?"
    )
    keyboard = _route_action_keyboard(first.get("id", ""), len(actions))
    await update.message.reply_text(_md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard)


# ── Completar acción desde Telegram ──────────────────────────────────────────

async def _handle_action_complete(update: Update, context: ContextTypes.DEFAULT_TYPE, user: Optional[dict]) -> None:
    """
    El empleado dice 'listo' o 'hecho'.
    Muestra las acciones pendientes para que confirme cuál fue.
    """
    try:
        pending = database.get_pending_actions(STORE_ID)
        if not pending:
            await update.message.reply_text(
                "No hay acciones pendientes registradas. ¡Todo resuelto!",
                reply_markup=_back_keyboard()
            )
            return

        # Mostrar primero las críticas
        sorted_pending = sorted(pending, key=lambda a: -a.get("priority_score", 0))
        show = sorted_pending[:6]

        text = "¿Qué acción has completado?"
        buttons = []
        for action in show:
            batch = action.get("batches") or {}
            product = (batch.get("products") or {}) if batch else {}
            name = (product.get("name") or "Producto")[:22]
            action_type = (action.get("action_type") or "").upper()
            score = action.get("priority_score", 0)
            icon = "🔴" if score >= 85 else "🟡" if score >= 65 else "🟢"
            action_id = action.get("id", "")
            label = f"{icon} {action_type} — {name}"
            buttons.append([InlineKeyboardButton(label, callback_data=f"complete_action:{action_id}")])

        if len(pending) > 6:
            buttons.append([InlineKeyboardButton(
                f"... y {len(pending) - 6} más en la app",
                callback_data="cmd:acciones"
            )])
        buttons.append([InlineKeyboardButton("↩ Ninguna / Cancelar", callback_data="cmd:menu")])

        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    except Exception as e:
        await update.message.reply_text(
            f"Error al cargar acciones: {e}",
            reply_markup=_back_keyboard()
        )


# ── Acciones del menú ─────────────────────────────────────────────────────────

async def _action_brief(update_or_query, context, user: Optional[dict], is_callback=False):
    brief = database.get_latest_brief(STORE_ID)
    keyboard = _back_keyboard()
    if not brief:
        text = (
            "No hay brief para hoy todavía.\n\n"
            "Se genera automáticamente a las 07:30, o puedes generarlo ahora "
            "si eres encargado."
        )
        if _is_manager(user):
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("⚙️ Generar ahora", callback_data="cmd:runbrief"),
                InlineKeyboardButton("↩ Volver", callback_data="cmd:menu"),
            ]])
    else:
        summary = brief.get("summary", "")
        text = f"BRIEF DEL {brief.get('date', 'hoy').upper()}:\n\n{summary}"
        keyboard = _smart_keyboard(summary, _is_manager(user))

    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_acciones(update_or_query, context, user: Optional[dict], is_callback=False):
    pending = database.get_pending_actions(STORE_ID)

    if not pending:
        text = "Sin acciones pendientes. Todo en orden."
        keyboard = _back_keyboard()
    else:
        critical = [a for a in pending if a.get("priority_score", 0) >= 85]
        other = [a for a in pending if a.get("priority_score", 0) < 85]
        lines = [f"ACCIONES PENDIENTES — {len(pending)} total:"]

        if critical:
            lines.append(f"\nCRITICAS ({len(critical)}):")
            for a in critical[:5]:
                batch = a.get("batches") or {}
                product = (batch.get("products") or {}) if batch else {}
                name = product.get("name", "Producto")
                pasillo = product.get("pasillo", "?")
                notes = (a.get("notes") or "")[:60]
                lines.append(f"  !!! {name} | Pasillo {pasillo} | {notes}")
        if other:
            lines.append(f"\nOTRAS ({len(other)}):")
            for a in other[:5]:
                batch = a.get("batches") or {}
                product = (batch.get("products") or {}) if batch else {}
                name = product.get("name", "Producto")
                action_type = a.get("action_type", "")
                lines.append(f"  - {name} | {action_type.upper()}")
        if len(pending) > 10:
            lines.append(f"\n... y {len(pending) - 10} más. Ver lista completa en la app.")

        text = "\n".join(lines)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🗺 Iniciar ruta", callback_data="cmd:iniciar_ruta"),
                InlineKeyboardButton("✅ Marcar hecha", callback_data="cmd:marcar_hecha"),
            ],
            [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
        ])

    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_ruta(update_or_query, context, user: Optional[dict], is_callback=False):
    async def _build():
        from backend.agents import evaluator as ev, route as rt
        loop = asyncio.get_running_loop()

        def _sync():
            batches = database.get_batches_expiring_soon(STORE_ID, days=7)
            if not batches:
                return "Sin productos próximos a caducar esta semana."
            risk_reports = []
            for batch in batches:
                product = batch.get("products") or {}
                risk = ev.evaluate(product, [batch])
                risk_reports.append((batch, risk))
            daily_route = rt.generate(STORE_ID, risk_reports)
            return rt.format_route_message(daily_route)

        return await loop.run_in_executor(None, _sync)

    try:
        response = await _build()
    except Exception as e:
        response = f"Error generando la ruta: {e}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Iniciar modo ruta guiada", callback_data="cmd:iniciar_ruta")],
        [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
    ])

    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(response), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, response, reply_markup=keyboard)


async def _action_stats(update_or_query, context, user: Optional[dict], is_callback=False):
    """Dashboard KPIs en Telegram — resumen ejecutivo de la tienda en un mensaje."""
    try:
        pending = database.get_pending_actions(STORE_ID)
        batches = database.get_batches_expiring_soon(STORE_ID, days=7)
        merma_7d = database.get_merma_history(STORE_ID, days=7)
        donations = database.get_donation_stats(STORE_ID, days=30)

        critical = sum(1 for a in pending if a.get("priority_score", 0) >= 85)
        high = sum(1 for a in pending if 65 <= a.get("priority_score", 0) < 85)
        value_at_risk = sum(
            b.get("quantity", 0) * (b.get("products") or {}).get("price", 0)
            for b in batches
        )
        merma_value = sum(float(l.get("value_lost", 0)) for l in merma_7d)
        donated_qty = donations.get("total_quantity", 0)
        donated_value = donations.get("total_value_donated", 0.0)

        # Indicadores semáforo
        def _semaforo(critical_count):
            if critical_count >= 5:
                return "ROJO"
            if critical_count >= 2:
                return "AMARILLO"
            return "VERDE"

        estado = _semaforo(critical)
        lines = [
            f"DASHBOARD — Super Martínez | {estado}",
            "",
            f"Acciones pendientes: {len(pending)}",
            f"  CRÍTICAS (score ≥ 85):  {critical}",
            f"  ALTAS (65-84):          {high}",
            "",
            f"Lotes caducando en 7d:  {len(batches)}",
            f"Valor en riesgo:        {value_at_risk:.2f} euros",
            "",
            f"Merma últimos 7 días:   {merma_value:.2f} euros",
            f"Donaciones este mes:    {donated_qty} uds ({donated_value:.2f} euros)",
        ]
        text = "\n".join(lines)
    except Exception as e:
        text = f"Error al obtener KPIs: {e}"

    keyboard = _smart_keyboard(text, _is_manager(user))
    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_merma(update_or_query, context, user: Optional[dict], is_callback=False):
    try:
        logs = database.get_merma_history(STORE_ID, days=7)
        if not logs:
            text = "Sin merma registrada en los últimos 7 días."
        else:
            total_value = sum(float(l.get("value_lost", 0)) for l in logs)
            total_qty = sum(int(l.get("quantity_lost", 0)) for l in logs)
            lines = [
                "MERMA — últimos 7 días:",
                "",
                f"  {total_qty} unidades perdidas",
                f"  {total_value:.2f} euros de valor",
                "",
            ]
            for log in logs[:5]:
                batch = log.get("batches") or {}
                product = (batch.get("products") or {}) if batch else {}
                name = product.get("name", log.get("reason", "Sin motivo")[:30])
                lines.append(
                    f"  - {log.get('date', '?')} | {name[:40]} | {log.get('quantity_lost', 0)} uds"
                )
            if len(logs) > 5:
                lines.append(f"  ... y {len(logs) - 5} entradas más en la app.")
            text = "\n".join(lines)
    except Exception as e:
        text = f"Error al obtener merma: {e}"

    keyboard = _smart_keyboard(text, _is_manager(user))
    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_donaciones(update_or_query, context, user: Optional[dict], is_callback=False):
    try:
        stats = database.get_donation_stats(STORE_ID, days=30)
        if stats["total_donations"] == 0:
            text = (
                "Sin donaciones registradas este mes.\n"
                "Cuando registres una donación desde la app, aparecerá aquí."
            )
        else:
            lines = [
                "IMPACTO SOCIAL — este mes:",
                "",
                f"  {stats['total_donations']} donaciones realizadas",
                f"  {stats['total_quantity']} unidades donadas",
                f"  {stats['total_value_donated']:.2f} euros de valor entregado",
                "",
                "Por entidad:",
            ]
            for entity, qty in sorted(stats["by_entity"].items(), key=lambda x: -x[1]):
                lines.append(f"  - {entity}: {qty} uds")
            lines += ["", "Cada unidad donada es merma evitada y ayuda a quien lo necesita."]
            text = "\n".join(lines)
    except Exception as e:
        text = f"Error al obtener donaciones: {e}"

    keyboard = _back_keyboard()
    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_proveedores(update_or_query, context, user: Optional[dict], is_callback=False):
    keyboard = _back_keyboard()
    if not _is_manager(user):
        text = "La ficha de proveedores es solo para encargados."
        if is_callback:
            await update_or_query.edit_message_text(text, reply_markup=keyboard)
        else:
            await _send(update_or_query, text, reply_markup=keyboard)
        return

    try:
        stats = database.get_supplier_stats(STORE_ID)
        if not stats:
            text = "Sin datos de proveedores todavía."
        else:
            lines = ["FICHA DE PROVEEDORES (merma promedio):", ""]
            for s in stats:
                icon = "!!!" if s["risk"] == "ALTO" else "!" if s["risk"] == "MEDIO" else "-"
                lines.append(
                    f"  {icon} {s['name']}"
                    f" | {s['avg_merma_pct']}% merma"
                    f" | {s['product_count']} productos"
                    f" | Riesgo {s['risk']}"
                )
                if s["risk"] == "ALTO":
                    lines.append("    -> Revisar condiciones de entrega con este proveedor")
            text = "\n".join(lines)
    except Exception as e:
        text = f"Error al obtener proveedores: {e}"

    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_pedido(update_or_query, context, user: Optional[dict], is_callback=False):
    keyboard = _back_keyboard()
    if not _is_manager(user):
        text = "La sugerencia de pedido es solo para encargados."
        if is_callback:
            await update_or_query.edit_message_text(text, reply_markup=keyboard)
        else:
            await _send(update_or_query, text, reply_markup=keyboard)
        return

    try:
        suggestions = database.get_order_suggestions(STORE_ID)
        if not suggestions:
            text = (
                "Sin sugerencias de pedido todavía.\n"
                "Se generan con al menos 7 días de historial de merma."
            )
        else:
            total_value = sum(s.get("estimated_value", 0) for s in suggestions)
            lines = [
                f"PEDIDO SEMANAL SUGERIDO ({len(suggestions)} productos):",
                f"Valor estimado total: {total_value:.2f} euros",
                "",
            ]
            for s in suggestions[:10]:
                lines.append(
                    f"  - {s['product_name']} | {s['order_qty']} uds"
                    f" | almacén: {s['current_warehouse_stock']} | {s['estimated_value']:.2f} euros"
                )
            if len(suggestions) > 10:
                lines.append(f"  ... y {len(suggestions) - 10} más en la app.")
            lines += ["", "Basado en merma histórica de los últimos 30 días."]
            text = "\n".join(lines)
    except Exception as e:
        text = f"Error al calcular pedido: {e}"

    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_runbrief(update_or_query, context, user: Optional[dict], is_callback=False):
    keyboard = _back_keyboard()
    if not _is_manager(user):
        text = "Solo los encargados pueden generar el brief manualmente."
        if is_callback:
            await update_or_query.edit_message_text(text, reply_markup=keyboard)
        else:
            await _send(update_or_query, text, reply_markup=keyboard)
        return

    confirm_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Generar brief ahora", callback_data="confirm:runbrief"),
        InlineKeyboardButton("❌ Cancelar", callback_data="cmd:menu"),
    ]])
    text = (
        "Generar el brief analiza todos los productos de la tienda con IA.\n\n"
        "Puede tardar entre 30 y 90 segundos. ¿Continuar?"
    )
    if is_callback:
        await update_or_query.edit_message_text(text, reply_markup=confirm_keyboard)
    else:
        await _send(update_or_query, text, reply_markup=confirm_keyboard)


async def _action_scan_help(update_or_query, context, user: Optional[dict], is_callback=False):
    keyboard = _back_keyboard()
    text = (
        "Para analizar un producto por código de barras:\n\n"
        "1. Comando directo: /scan 8410031001001\n\n"
        "2. O escribe el código directamente: 8410031001001\n\n"
        "3. O escribe: escanear 8410031001001\n\n"
        "4. O desde la app, usa el escáner de cámara.\n\n"
        "El sistema te dirá: ubicación, días hasta caducidad, "
        "acción recomendada y si hay que reponer.\n\n"
        "Después del análisis podrás confirmar la acción directamente desde aquí."
    )
    if is_callback:
        await update_or_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_ayuda(update_or_query, context, user: Optional[dict], is_callback=False):
    keyboard = _back_keyboard()
    text = (
        "Soy Chuwi, el agente de MermaOps. Hablo contigo en lenguaje natural.\n\n"
        "LO QUE PUEDES HACER AQUÍ:\n\n"
        "📋 Brief del día — resumen de apertura generado por IA: qué caduca, qué es crítico, qué acciones son prioritarias\n\n"
        "⚡ Acciones — lista de todas las acciones pendientes ordenadas por urgencia (REBAJAR, RETIRAR, DONAR, REPONER)\n\n"
        "🗺 Ruta del día — ruta optimizada por pasillos. Puedes iniciar el MODO RUTA para que te guíe acción por acción, como un GPS de tienda\n\n"
        "📊 Merma 7 días — cuánto valor se ha perdido esta semana y por qué productos\n\n"
        "❤️ Donaciones — impacto social del mes: cuántas unidades se donaron al Banco de Alimentos\n\n"
        "🤝 Registrar donación (/donar) — flujo guiado: selecciona producto → entidad → cantidad → confirmar. Sin abrir la app.\n\n"
        "🔍 Escanear — escribe el código de barras (ej: 8410031001001) y en segundos tienes: pasillo, días hasta caducidad, acción recomendada, precio de rebaja exacto\n\n"
        "📈 Dashboard (/stats) — KPIs de la tienda en tiempo real: acciones críticas, valor en riesgo, merma 7 días, donaciones del mes, semáforo ROJO/AMARILLO/VERDE\n\n"
        "📦 Proveedores (encargado) — qué proveedor tiene más merma histórica, quién revisar primero\n\n"
        "🛒 Pedido semanal (encargado) — cuántas unidades pedir de cada producto basado en velocidad de merma\n\n"
        "🌱 ESG / Impacto (encargado) — CO2 evitado, agua ahorrada, deducción fiscal por donaciones\n\n"
        "🔮 Predicciones (encargado) — riesgo de merma en los próximos 5 días con previsión meteorológica\n\n"
        "⚙️ Generar brief (encargado) — lanza el análisis completo de la tienda ahora mismo\n\n"
        "✅ MARCAR COMPLETADA — di 'listo', 'hecho' o 'terminé' y selecciona qué acción completaste. Sin abrir la app.\n\n"
        "PREGUNTAS EN LENGUAJE NATURAL:\n\n"
        "- ¿Qué pasa con los lácteos esta semana?\n"
        "- ¿Cuánto hemos perdido en carne desde el lunes?\n"
        "- ¿Qué proveedor nos da más problemas?\n"
        "- ¿Hay algo que caduca hoy mismo?\n"
        "- ¿Qué debería revisar primero al abrir?\n\n"
        "También acepto NOTAS DE VOZ — las transcribo y respondo igual."
    )
    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_tour(update_or_query, context, user: Optional[dict], is_callback=False):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 Ver los 11 agentes de IA", callback_data="cmd:tour_agentes")],
        [InlineKeyboardButton("📱 Ver funciones de la app", callback_data="cmd:tour_app")],
        [InlineKeyboardButton("↩ Menú principal", callback_data="cmd:menu")],
    ])
    text = (
        "MermaOps — Sistema multiagente de reducción de merma alimentaria\n\n"
        "QUÉ ES:\n"
        "Sistema de IA que ayuda a supermercados a reducir la merma de producto fresco. "
        "Detecta productos en riesgo, recomienda acciones y aprende de los patrones históricos.\n\n"
        "RESULTADO REAL:\n"
        "- Priorización automática de acciones por urgencia y valor económico\n"
        "- Brief diario generado por IA a las 07:30 sin que nadie lo pida\n"
        "- Análisis de riesgo con razonamiento interno (extended thinking de Claude)\n"
        "- Agente conversacional disponible 24h en Telegram\n\n"
        "TECNOLOGÍA:\n"
        "- 11 agentes especializados coordinados por un Supervisor\n"
        "- Claude (Anthropic) con extended thinking para productos críticos\n"
        "- Consenso de 3 agentes en paralelo para casos extremos\n"
        "- Memoria episódica: recuerda qué pasó la semana anterior\n"
        "- App Flutter + Backend FastAPI + Supabase + Telegram\n\n"
        "Selecciona una opción para ver más detalle:"
    )
    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_tour_agentes(update_or_query, context, user: Optional[dict], is_callback=False):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("← Volver al tour", callback_data="cmd:tour")],
        [InlineKeyboardButton("← Menú principal", callback_data="cmd:menu")],
    ])
    text = (
        "LOS 11 AGENTES DE MERMAOPS:\n\n"
        "1. SUPERVISOR — el cerebro. Loop agéntico con 25 herramientas. "
        "Decide qué investigar, en qué orden y cuándo escalar.\n\n"
        "2. EVALUATOR — análisis de riesgo profundo. Usa extended thinking "
        "(Claude razona internamente antes de responder). Para casos extremos "
        "activa consenso de 3 instancias en paralelo.\n\n"
        "3. VALIDATOR — adversarial. Revisa las decisiones del Evaluador. "
        "Detecta pasillos sin revisar y lanza alertas a las 12:00.\n\n"
        "4. PRICE — calcula el descuento exacto que maximiza ingresos "
        "sin romper el margen mínimo sobre coste.\n\n"
        "5. STOCK — decisiones de reposición con lógica FEFO "
        "(First Expired First Out).\n\n"
        "6. ROUTE — genera la ruta diaria optimizada por pasillos "
        "según urgencia y carga de trabajo.\n\n"
        "7. REPORTER — redacta el brief diario, informe semanal e "
        "informe mensual para el dueño.\n\n"
        "8. NOTIFIER — envía alertas a Telegram con chunking para "
        "no superar el límite de caracteres.\n\n"
        "9. SCANNER — consulta OpenFoodFacts para enriquecer datos "
        "de productos escaneados.\n\n"
        "10. PARALLEL EVALUATOR — evalúa todos los lotes activos en "
        "paralelo (ThreadPoolExecutor) para el dashboard.\n\n"
        "11. CONSENSUS — votación de mayoría entre 3 perspectivas "
        "independientes para productos con score >= 90 y > 30€ en riesgo.\n\n"
        "FLUJO TÍPICO:\n"
        "Supervisor → Evaluator (con Validator) → Price/Stock/Route "
        "→ Reporter → Notifier → Telegram/App"
    )
    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_tour_app(update_or_query, context, user: Optional[dict], is_callback=False):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("← Volver al tour", callback_data="cmd:tour")],
        [InlineKeyboardButton("← Menú principal", callback_data="cmd:menu")],
    ])
    text = (
        "LA APP FLUTTER — 6 pantallas:\n\n"
        "📊 DASHBOARD — KPIs en tiempo real: acciones pendientes, valor en riesgo, "
        "merma 7 días (sparkline), impacto social de donaciones, comparativa entre tiendas.\n\n"
        "🔍 ESCANEAR — abre la cámara, lee el código de barras y en 5-10 segundos "
        "Claude devuelve: pasillo, días hasta caducidad, acción recomendada, "
        "precio de rebaja exacto y razonamiento.\n\n"
        "✅ ACCIONES — lista priorizada de todo lo que hay que hacer. "
        "Separadas en CRÍTICAS y OTRAS. Puedes adjuntar foto como evidencia "
        "al marcar completada.\n\n"
        "🗺 MAPA — mapa de pasillos con código de colores por urgencia. "
        "QR por sección para acceso rápido. Lista FEFO de productos.\n\n"
        "📈 INFORMES — 6 pestañas: Diarios, Semanales, Mensual, "
        "Merma+CSV, Proveedores, Pedidos. Export CSV con un toque.\n\n"
        "👤 PERFIL — vincular cuenta de Telegram con la app para que "
        "Chuwi te reconozca por nombre y rol.\n\n"
        "TAMBIÉN:\n"
        "- Import CSV desde TPV (código de barras + caducidad)\n"
        "- Multi-idioma ES/EN\n"
        "- Etiqueta de descuento lista para imprimir\n"
        "- Foto de evidencia al completar una acción"
    )
    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_marcar_hecha(update_or_query, context, user: Optional[dict], is_callback=False):
    """Shortcut para marcar acción como hecha desde el menú."""
    try:
        pending = database.get_pending_actions(STORE_ID)
        if not pending:
            text = "No hay acciones pendientes registradas."
            if is_callback:
                await update_or_query.edit_message_text(text, reply_markup=_back_keyboard())
            else:
                await _send(update_or_query, text, reply_markup=_back_keyboard())
            return

        sorted_pending = sorted(pending, key=lambda a: -a.get("priority_score", 0))
        show = sorted_pending[:6]

        text = "¿Cuál has completado?"
        buttons = []
        for action in show:
            batch = action.get("batches") or {}
            product = (batch.get("products") or {}) if batch else {}
            name = (product.get("name") or "Producto")[:22]
            action_type = (action.get("action_type") or "").upper()
            score = action.get("priority_score", 0)
            icon = "🔴" if score >= 85 else "🟡" if score >= 65 else "🟢"
            action_id = action.get("id", "")
            buttons.append([InlineKeyboardButton(
                f"{icon} {action_type} — {name}",
                callback_data=f"complete_action:{action_id}"
            )])

        buttons.append([InlineKeyboardButton("↩ Cancelar", callback_data="cmd:menu")])
        keyboard = InlineKeyboardMarkup(buttons)

        if is_callback:
            await update_or_query.edit_message_text(text, reply_markup=keyboard)
        else:
            await _send(update_or_query, text, reply_markup=keyboard)

    except Exception as e:
        text = f"Error: {e}"
        if is_callback:
            await update_or_query.edit_message_text(text, reply_markup=_back_keyboard())
        else:
            await _send(update_or_query, text, reply_markup=_back_keyboard())


# ── Confirmación de escaneo — registra en BD ─────────────────────────────────

async def _confirm_scan_action(barcode: str, action_type: str, user: Optional[dict]) -> str:
    """
    Cuando el empleado confirma una acción post-escaneo desde Telegram,
    registra la operación en la BD: completa la acción pendiente + loguea merma/donación.
    Devuelve el nombre del producto para el mensaje de confirmación.
    """
    try:
        loop = asyncio.get_running_loop()

        def _sync() -> str:
            from datetime import date as _date, datetime as _dt
            product = database.get_product_by_barcode(STORE_ID, barcode)
            if not product:
                return barcode

            product_id = product.get("id")
            product_name = product.get("name", barcode)
            price = float(product.get("price", 0))

            batches = database.get_batches_by_product(STORE_ID, product_id)
            batch = batches[0] if batches else None
            batch_id = batch.get("id") if batch else None
            qty = int(batch.get("quantity", 1)) if batch else 1

            u_label = (user.get("email") or user.get("id", "unknown")) if user else "chuwi"

            # Completar acción pendiente relacionada si existe
            try:
                pending = database.get_pending_actions(STORE_ID)
                type_map = {
                    "rebajar": "rebajar", "retirar": "retirar",
                    "donar": "donar", "donar_banco": "donar",
                    "donar_caritas": "donar", "donar_cruzroja": "donar",
                }
                mapped = type_map.get(action_type, action_type)
                for a in pending:
                    a_batch = a.get("batches") or {}
                    a_product = (a_batch.get("products") or {}) if a_batch else {}
                    if (a_product.get("id") == product_id
                            and mapped in (a.get("action_type") or "").lower()):
                        database.complete_action(a.get("id", ""), u_label)
                        break
            except Exception as ex:
                logger.warning(f"complete_action fallback: {ex}")

            # Registrar en BD según tipo de acción
            if batch_id:
                if action_type == "rebajar":
                    database.log_merma({
                        "store_id": STORE_ID,
                        "batch_id": batch_id,
                        "date": _date.today().isoformat(),
                        "reason": "precio rebajado",
                        "quantity_lost": 0,
                        "value_lost": 0,
                    })
                elif action_type == "retirar":
                    database.log_merma({
                        "store_id": STORE_ID,
                        "batch_id": batch_id,
                        "date": _date.today().isoformat(),
                        "reason": "retirado por caducidad",
                        "quantity_lost": qty,
                        "value_lost": round(qty * price, 2),
                    })
                elif action_type.startswith("donar"):
                    entity_map = {
                        "donar": "General",
                        "donar_banco": "Banco de Alimentos",
                        "donar_caritas": "Cáritas",
                        "donar_cruzroja": "Cruz Roja",
                    }
                    database.log_donation({
                        "store_id": STORE_ID,
                        "batch_id": batch_id,
                        "entity": entity_map.get(action_type, "Otro"),
                        "quantity": qty,
                        "value_donated": round(qty * price, 2),
                        "donated_at": _dt.utcnow().isoformat(),
                        "donated_by": u_label,
                    })

            return product_name

        return await loop.run_in_executor(None, _sync)
    except Exception as e:
        logger.warning(f"_confirm_scan_action error: {e}")
        return barcode


# Mapa de acciones para callbacks
_DONATION_ENTITIES = [
    ("Banco de Alimentos", "banco_alimentos"),
    ("Cáritas", "caritas"),
    ("Cruz Roja", "cruzroja"),
    ("Comedor Social", "comedor_social"),
]


async def _action_donar_flow(update_or_query, context, user: Optional[dict], is_callback=False):
    """Inicia el flujo multi-step de donación: product → entity → quantity → confirm."""
    try:
        actions = database.get_pending_actions(STORE_ID)
        donar_actions = [a for a in actions if a.get("action_type") == "donar"]
    except Exception as e:
        text = f"Error al obtener acciones de donación: {e}"
        kb = _back_keyboard()
        if is_callback:
            await update_or_query.edit_message_text(text, reply_markup=kb)
        else:
            await _send(update_or_query, text, reply_markup=kb)
        return

    if not donar_actions:
        text = (
            "No hay acciones de donación pendientes en este momento.\n\n"
            "Cuando el sistema identifique un producto listo para donar, aparecerá aquí.\n"
            "También puedes escanear un barcode y elegir la opción Donar."
        )
        kb = _back_keyboard()
        if is_callback:
            await update_or_query.edit_message_text(text, reply_markup=kb)
        else:
            await _send(update_or_query, text, reply_markup=kb)
        return

    # Construir teclado con los productos disponibles para donar
    rows = []
    for a in donar_actions[:8]:
        batch_data = a.get("batches") or {}
        product_data = batch_data.get("products") or {}
        product_name = (product_data.get("name") or a.get("product_name", "Producto desconocido"))[:35]
        qty = a.get("donation_quantity") or batch_data.get("quantity") or "?"
        action_id = a.get("id", "")
        rows.append([InlineKeyboardButton(
            f"🤝 {product_name} ({qty} uds)",
            callback_data=f"donation_step:select_entity:{action_id}"
        )])
    rows.append([InlineKeyboardButton("↩ Volver", callback_data="cmd:menu")])

    text = (
        f"DONACIÓN — {len(donar_actions)} productos disponibles\n\n"
        "Selecciona el producto que vas a donar:"
    )
    kb = InlineKeyboardMarkup(rows)
    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=kb
        )
    else:
        await _send(update_or_query, text, reply_markup=kb)


async def _action_esg(update_or_query, context, user: Optional[dict], is_callback=False):
    """Métricas ESG de la tienda (CO2, agua, deducción fiscal)."""
    keyboard = _back_keyboard()
    try:
        from backend.agents.esg import get_store_esg_summary
        loop = asyncio.get_running_loop()
        esg = await loop.run_in_executor(None, get_store_esg_summary, STORE_ID, 30)

        co2 = esg.get("estimated_co2_avoided_kg", 0)
        water = esg.get("estimated_water_avoided_liters", 0)
        value = esg.get("value_recovered_eur", 0)
        donated = esg.get("donated_value_eur", 0)
        tax = esg.get("tax_deduction_estimate_eur", 0)
        score = esg.get("esg_score", 0)
        eq = esg.get("equivalences", {})
        km = eq.get("km_car_avoided", 0)
        showers = eq.get("shower_days_equivalent", 0)
        actions = esg.get("actions_completed", 0)

        score_label = "EXCELENTE" if score >= 70 else "BUENO" if score >= 40 else "MEJORABLE"

        lines = [
            f"IMPACTO ESG — últimos 30 días",
            f"Puntuación: {score}/100 ({score_label})",
            "",
            f"Medioambiente:",
            f"  CO2 evitado: {co2:.1f} kg (aprox. {km:.0f} km en coche)",
            f"  Agua ahorrada: {water/1000:.1f} m3 (aprox. {showers:.0f} duchas)",
            "",
            f"Económico:",
            f"  Valor recuperado: {value:.2f} euros ({actions} acciones)",
            f"  Donaciones: {donated:.2f} euros",
            f"  Deducción fiscal estimada: {tax:.2f} euros (Ley 49/2002, 35%)",
            "",
            "El reporting ESG será obligatorio para PYMEs en 2026 (CSRD).",
            "Ver informe completo en la app: Informes → ESG.",
        ]
        text = "\n".join(lines)
    except Exception as e:
        text = f"Error al obtener datos ESG: {e}"

    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_prediccion(update_or_query, context, user: Optional[dict], is_callback=False):
    """Predicción de merma para los próximos días con datos meteorológicos."""
    keyboard = _back_keyboard()
    try:
        from backend.agents.predictor import predict_merma_risk, get_weather_forecast
        loop = asyncio.get_running_loop()
        predictions = await loop.run_in_executor(None, predict_merma_risk, STORE_ID, 5)
        forecast = await loop.run_in_executor(None, get_weather_forecast)

        if not predictions:
            text = (
                "Sin riesgos predictivos detectados para los próximos 5 días.\n\n"
                "El sistema revisa todos los lotes con suficiente antelación. "
                "Cuando algo vaya a ser un problema, aparecerá aquí antes de que el sistema normal lo detecte."
            )
        else:
            hot_days = sum(1 for f in forecast if f.get("is_hot"))
            rain_days = sum(1 for f in forecast if f.get("is_rainy"))

            weather_line = "Tiempo estable esta semana."
            if hot_days >= 2:
                weather_line = f"ATENCION: {hot_days} dias con temperatura alta (>30C) — mayor riesgo en frescos."
            elif rain_days >= 3:
                weather_line = f"Lluvia prevista {rain_days} dias — esperar menos clientes de lo habitual."

            high = [p for p in predictions if p["risk_score"] >= 60]
            medium = [p for p in predictions if 40 <= p["risk_score"] < 60]

            lines = [
                f"PREDICCION DE MERMA — proximos 5 dias",
                f"Meteorologia: {weather_line}",
                "",
                f"{len(high)} productos de riesgo ALTO / {len(medium)} de riesgo MEDIO",
                "",
                "Top productos en riesgo (aun no en alerta pero lo estarán):",
            ]
            for p in predictions[:6]:
                icon = "!!!" if p["risk_score"] >= 60 else "!"
                factors = " / ".join(p["risk_factors"][:1])
                lines.append(
                    f"  {icon} {p['product_name']} | caduca en {p['days_until_expiry']}d "
                    f"| riesgo {p['risk_score']}/100 | {factors}"
                )
                lines.append(f"     -> {p['recommended_preemptive_action']}")

            lines += [
                "",
                "Ver analisis completo en la app: Informes → Predicciones.",
            ]
            text = "\n".join(lines)
    except Exception as e:
        text = f"Error al calcular predicciones: {e}"

    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


_CAT_MAP = {
    "carne": "carne", "pollo": "carne", "ternera": "carne", "cerdo": "carne", "picada": "carne",
    "pescado": "pescado", "merluza": "pescado", "salmon": "pescado", "atun": "pescado", "bacalao": "pescado",
    "yogur": "lacteos", "leche": "lacteos", "nata": "lacteos", "queso": "lacteos", "kefir": "lacteos",
    "pan": "panaderia", "baguette": "panaderia", "croissant": "panaderia", "bolleria": "panaderia",
    "fruta": "fruta", "verdura": "verdura", "fresa": "fruta", "ensalada": "verdura",
}


async def _action_citar(update_or_query, context, user: Optional[dict], is_callback=False, cmd_args: list | None = None):
    """Justificación normativa citada — muestra la normativa exacta usada para la decisión."""
    from backend.core import knowledge as _knowledge

    categoria_raw = (cmd_args[0].lower() if cmd_args else "").strip()
    dias = 2
    if cmd_args and len(cmd_args) >= 2:
        try:
            dias = int(cmd_args[1])
        except ValueError:
            pass

    cat_key = _CAT_MAP.get(categoria_raw, categoria_raw or "lacteos")
    if dias <= 0:
        accion = "retirar"
    elif dias == 1:
        accion = "donar"
    else:
        accion = "rebajar"

    product_label = categoria_raw.title() if categoria_raw else "Producto"

    if not categoria_raw:
        text = (
            "NORMATIVA CITADA — Uso:\n\n"
            "/citar <categoria> [dias]\n\n"
            "Categorías: carne, pescado, lacteos, panaderia, fruta, verdura\n\n"
            "Ejemplos:\n"
            "/citar lacteos 2\n"
            "/citar carne 1\n"
            "/citar pescado 0\n\n"
            "Devuelve la normativa exacta de seguridad alimentaria que justifica la decisión."
        )
    else:
        try:
            result = _knowledge.get_cited_decision(product_label, cat_key, dias, accion)
            cited = result.format_with_citations()
            text = f"NORMATIVA — {product_label.upper()} ({dias}d)\n\n{cited}"
        except RuntimeError as e:
            # No API key — fallback a knowledge base plain text
            ctx_text = _knowledge.get_context_for_decision(cat_key, dias, accion)
            text = f"NORMATIVA — {product_label.upper()} ({dias}d)\n\n{ctx_text}\n\n(Citations API no activa — configura ANTHROPIC_API_KEY para citas exactas)"
        except Exception as e:
            text = f"Error al consultar normativa: {e}"

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")]])
    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


_ACTION_MAP = {
    "brief": _action_brief,
    "stats": _action_stats,
    "acciones": _action_acciones,
    "ruta": _action_ruta,
    "merma": _action_merma,
    "donaciones": _action_donaciones,
    "proveedores": _action_proveedores,
    "pedido": _action_pedido,
    "runbrief": _action_runbrief,
    "scan_help": _action_scan_help,
    "ayuda": _action_ayuda,
    "tour": _action_tour,
    "tour_agentes": _action_tour_agentes,
    "tour_app": _action_tour_app,
    "marcar_hecha": _action_marcar_hecha,
    "esg": _action_esg,
    "prediccion": _action_prediccion,
    "donar_flow": _action_donar_flow,
    "citar": _action_citar,
}


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _get_user(update.effective_user.id)
    tg_name = update.effective_user.first_name or "empleado"

    if not user:
        await update.message.reply_text(
            f"Hola {tg_name}, soy Chuwi el agente de MermaOps.\n\n"
            "Para usarme necesitas vincular tu cuenta:\n\n"
            "1. Abre la app MermaOps y haz login\n"
            "2. Ve a tu perfil → sección Telegram\n"
            "3. Pega tu ID de Telegram (el de abajo) y pulsa Vincular\n\n"
            f"Tu ID de Telegram es: <code>{update.effective_user.id}</code>\n\n"
            "Una vez vinculado, escribe /start de nuevo para empezar.",
            parse_mode=ParseMode.HTML,
        )
        return

    manager = _is_manager(user)
    keyboard = _main_menu_keyboard(manager)
    await update.message.reply_text(
        _welcome_text(tg_name, manager),
        reply_markup=keyboard,
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text(
            "Primero debes vincular tu cuenta. Escribe /start para ver las instrucciones."
        )
        return
    keyboard = _main_menu_keyboard(_is_manager(user))
    await update.message.reply_text("¿Qué necesitas?", reply_markup=keyboard)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestiona todos los teclados inline."""
    query = update.callback_query
    await query.answer()

    user = _get_user(update.effective_user.id)
    user_id = str(update.effective_user.id)
    data = query.data or ""

    # ── Menú principal ──
    if data == "cmd:menu":
        manager = _is_manager(user)
        _clear_conv_state(user_id)
        keyboard = _main_menu_keyboard(manager)
        await query.edit_message_text("¿Qué necesitas?", reply_markup=keyboard)
        return

    # ── Confirmación de brief ──
    if data == "confirm:runbrief":
        await query.edit_message_text("Generando brief... esto puede tardar hasta 90 segundos.")
        done = asyncio.Event()
        typing_task = asyncio.create_task(
            _typing_loop(context.bot, query.message.chat_id, done)
        )
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, supervisor.run_daily_brief, STORE_ID)
        except Exception as e:
            result = f"Error al generar el brief: {e}"
        finally:
            done.set()
            await typing_task

        keyboard = _smart_keyboard(result, _is_manager(user))
        await _safe_edit(query.message, result, reply_markup=keyboard)
        return

    # ── Marcar acción completada ──
    if data.startswith("complete_action:"):
        action_id = data[16:]
        try:
            u_id = user.get("id", "") if user else ""
            u_name = user.get("email", "empleado").split("@")[0] if user else "empleado"
            database.complete_action(action_id, u_id)
            await query.edit_message_text(
                f"✅ Acción marcada como completada por {u_name}.\n\nBuen trabajo.",
                reply_markup=_main_menu_keyboard(_is_manager(user))
            )
        except Exception as e:
            await query.edit_message_text(
                f"Error al marcar la acción: {e}",
                reply_markup=_back_keyboard()
            )
        return

    # ── Modo ruta: confirmar acción completada ──
    if data.startswith("route_done:"):
        action_id = data[11:]
        state = _get_conv_state(user_id)
        if state["mode"] == "route_active":
            # Marcar como completada
            try:
                u_id = user.get("id", "") if user else ""
                database.complete_action(action_id, u_id)
                state["data"]["completed"].append(action_id)
                state["data"]["current_index"] = state["data"].get("current_index", 0) + 1
            except Exception:
                pass

            action_ids = state["data"].get("action_ids", [])
            current_idx = state["data"].get("current_index", 0)

            if current_idx >= len(action_ids):
                _clear_conv_state(user_id)
                completed = len(state["data"].get("completed", []))
                skipped = len(state["data"].get("skipped", []))
                await query.edit_message_text(
                    f"🏁 RUTA COMPLETADA\n\n"
                    f"✅ {completed} acciones completadas\n"
                    f"⏭ {skipped} saltadas\n\n"
                    "Buen trabajo. Las acciones saltadas siguen pendientes en la app.",
                    reply_markup=_back_keyboard()
                )
            else:
                # Siguiente acción
                _set_conv_state(user_id, "route_active", state["data"])
                actions = _get_route_actions()
                remaining_actions = [a for a in actions if a.get("id") in action_ids[current_idx:]]
                if remaining_actions:
                    next_action = remaining_actions[0]
                    total = len(action_ids)
                    text = (
                        f"✅ Hecho. Siguiente:\n\n"
                        + _format_route_action(next_action, current_idx + 1, total)
                    )
                    keyboard = _route_action_keyboard(next_action.get("id", ""), total - current_idx - 1)
                    await query.edit_message_text(
                        _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
                    )
                else:
                    _clear_conv_state(user_id)
                    await query.edit_message_text(
                        "✅ Ruta completada.",
                        reply_markup=_back_keyboard()
                    )
        return

    # ── Modo ruta: saltar acción ──
    if data.startswith("route_skip:"):
        action_id = data[11:]
        state = _get_conv_state(user_id)
        if state["mode"] == "route_active":
            state["data"]["skipped"].append(action_id)
            state["data"]["current_index"] = state["data"].get("current_index", 0) + 1
            _set_conv_state(user_id, "route_active", state["data"])

            action_ids = state["data"].get("action_ids", [])
            current_idx = state["data"]["current_index"]

            if current_idx >= len(action_ids):
                _clear_conv_state(user_id)
                await query.edit_message_text(
                    "Ruta terminada. Tienes acciones saltadas pendientes en la app.",
                    reply_markup=_back_keyboard()
                )
            else:
                actions = _get_route_actions()
                remaining = [a for a in actions if a.get("id") in action_ids[current_idx:]]
                if remaining:
                    next_action = remaining[0]
                    total = len(action_ids)
                    text = (
                        f"⏭ Saltada. Siguiente:\n\n"
                        + _format_route_action(next_action, current_idx + 1, total)
                    )
                    keyboard = _route_action_keyboard(next_action.get("id", ""), total - current_idx - 1)
                    await query.edit_message_text(
                        _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
                    )
                else:
                    _clear_conv_state(user_id)
                    await query.edit_message_text("Ruta terminada.", reply_markup=_back_keyboard())
        return

    # ── Pausar ruta ──
    if data == "route_pause":
        _clear_conv_state(user_id)
        await query.edit_message_text(
            "Ruta pausada. Las acciones pendientes siguen en la app.\n\n"
            "Cuando quieras continuar, escribe 'iniciar ruta' o pulsa el menú.",
            reply_markup=_main_menu_keyboard(_is_manager(user))
        )
        return

    # ── Scan confirmado desde Telegram ──
    if data.startswith("scan_done:"):
        parts = data[10:].split(":", 1)
        action_type = parts[0] if parts else ""
        barcode = parts[1] if len(parts) > 1 else ""

        action_labels = {
            "rebajar": "Precio rebajado",
            "retirar": "Producto retirado",
            "donar": "Donación registrada",
            "donar_banco": "Donado al Banco de Alimentos",
            "donar_caritas": "Donado a Cáritas",
            "donar_cruzroja": "Donado a Cruz Roja",
        }
        action_text = action_labels.get(action_type, "Acción registrada")

        await query.edit_message_text("Registrando...")
        product_name = await _confirm_scan_action(barcode, action_type, user)

        label = product_name if product_name != barcode else barcode
        await query.edit_message_text(
            f"✅ {action_text} — {label}.\n\nRegistrado en el historial de la app.",
            reply_markup=_main_menu_keyboard(_is_manager(user))
        )
        return

    # ── Callbacks de análisis visual (foto) ──
    if data.startswith("vision_done:"):
        action_type = data[12:]  # rebajar | retirar | donar
        action_labels = {
            "rebajar": "Precio rebajado y etiquetado",
            "retirar": "Producto retirado de la estantería",
            "donar": "Donación registrada",
        }
        label = action_labels.get(action_type, "Acción registrada")
        u_name = user.get("email", "empleado").split("@")[0] if user else "empleado"
        await query.edit_message_text(
            f"✅ {label}.\n\nRegistrado por {u_name}.\n\n"
            "Si tienes el código de barras del producto, escanéalo para "
            "registrar el lote exacto en el historial.",
            reply_markup=_main_menu_keyboard(_is_manager(user))
        )
        return

    if data == "vision_scan":
        await query.edit_message_text(
            "Escribe el código de barras del producto para analizarlo:\n\n"
            "Ejemplo: 8410031001001\n\n"
            "O escanéalo desde la app con la cámara.",
            reply_markup=_back_keyboard()
        )
        return

    # ── Flujo multi-step de donación ──
    if data.startswith("donation_step:"):
        parts = data.split(":", 2)
        step = parts[1] if len(parts) > 1 else ""
        payload = parts[2] if len(parts) > 2 else ""

        if step == "select_entity":
            # payload = action_id
            action_id = payload
            try:
                actions = database.get_pending_actions(STORE_ID)
                action = next((a for a in actions if a.get("id") == action_id), None)
            except Exception:
                action = None

            if not action:
                await query.edit_message_text(
                    "Acción no encontrada. Puede que ya haya sido completada.",
                    reply_markup=_back_keyboard()
                )
                return

            batch_data = action.get("batches") or {}
            product_data = batch_data.get("products") or {}
            product_name = product_data.get("name") or action.get("product_name", "Producto desconocido")
            max_qty = action.get("donation_quantity") or batch_data.get("quantity") or 1
            _set_conv_state(user_id, "donation_flow", {
                "step": "select_entity",
                "action_id": action_id,
                "product_name": product_name,
                "max_quantity": max_qty,
                "entity": "",
                "quantity": 0,
            })

            rows = [
                [InlineKeyboardButton(f"❤️ {name}", callback_data=f"donation_step:enter_qty:{action_id}:{key}")]
                for name, key in _DONATION_ENTITIES
            ]
            rows.append([InlineKeyboardButton("↩ Volver", callback_data="cmd:donar_flow")])
            await query.edit_message_text(
                f"Donando: {product_name}\n\n¿A qué entidad vas a donar?",
                reply_markup=InlineKeyboardMarkup(rows)
            )
            return

        if step == "enter_qty":
            # payload = action_id:entity_key
            sub = payload.split(":", 1)
            action_id = sub[0]
            entity_key = sub[1] if len(sub) > 1 else ""
            entity_name = next((n for n, k in _DONATION_ENTITIES if k == entity_key), entity_key)

            state = _get_conv_state(user_id)
            state_data = state.get("data", {})
            state_data.update({"step": "enter_quantity", "entity": entity_key})
            _set_conv_state(user_id, "donation_flow", state_data)

            product_name = state_data.get("product_name", "Producto")
            max_qty = state_data.get("max_quantity", "?")

            await query.edit_message_text(
                f"Donando a {entity_name}: {product_name}\n\n"
                f"¿Cuántas unidades donas? (máximo {max_qty})\n\n"
                "Escribe el número a continuación:"
            )
            return

        if step == "confirm":
            # payload = action_id
            state = _get_conv_state(user_id)
            state_data = state.get("data", {})
            action_id = payload
            entity_key = state_data.get("entity", "")
            entity_name = next((n for n, k in _DONATION_ENTITIES if k == entity_key), entity_key)
            quantity = state_data.get("quantity", 0)
            product_name = state_data.get("product_name", "Producto")
            u_name = user.get("email", "empleado").split("@")[0] if user else "empleado"

            try:
                database.complete_action(action_id, user.get("id", u_name))
                database.log_donation({
                    "store_id": STORE_ID,
                    "action_id": action_id,
                    "entity": entity_name,
                    "quantity": quantity,
                    "product_name": product_name,
                    "donated_by": user.get("email", u_name),
                })
                _clear_conv_state(user_id)
                await query.edit_message_text(
                    f"✅ Donación registrada\n\n"
                    f"Producto: {product_name}\n"
                    f"Entidad: {entity_name}\n"
                    f"Cantidad: {quantity} unidades\n"
                    f"Registrado por: {u_name}\n\n"
                    "Gracias. Cada donación evita merma y ayuda a quien lo necesita.",
                    reply_markup=_main_menu_keyboard(_is_manager(user))
                )
            except Exception as e:
                await query.edit_message_text(
                    f"Error al registrar la donación: {e}",
                    reply_markup=_back_keyboard()
                )
            return

        if step == "cancel":
            _clear_conv_state(user_id)
            await query.edit_message_text(
                "Donación cancelada.",
                reply_markup=_main_menu_keyboard(_is_manager(user))
            )
            return

    # ── Iniciar modo ruta desde callback ──
    if data == "cmd:iniciar_ruta":
        actions = _get_route_actions()
        if not actions:
            await query.edit_message_text(
                "Sin acciones pendientes para la ruta.",
                reply_markup=_back_keyboard()
            )
            return

        action_ids = [a.get("id") for a in actions if a.get("id")]
        _set_conv_state(user_id, "route_active", {
            "action_ids": action_ids,
            "current_index": 0,
            "skipped": [],
            "completed": [],
        })

        first = actions[0]
        text = (
            f"🗺 MODO RUTA ACTIVA — {len(actions)} acciones pendientes\n\n"
            + _format_route_action(first, 1, len(actions))
        )
        keyboard = _route_action_keyboard(first.get("id", ""), len(actions))
        await query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
        return

    # ── Acciones del menú estándar ──
    if data.startswith("cmd:"):
        action_key = data[4:]
        if action_key in _ACTION_MAP:
            if action_key in ("ruta", "runbrief"):
                await query.edit_message_text("Un momento...")
                done = asyncio.Event()
                typing_task = asyncio.create_task(
                    _typing_loop(context.bot, query.message.chat_id, done)
                )
                try:
                    await _ACTION_MAP[action_key](query, context, user, is_callback=True)
                finally:
                    done.set()
                    await typing_task
            else:
                await _ACTION_MAP[action_key](query, context, user, is_callback=True)
        else:
            await query.edit_message_text(
                f"Acción no reconocida: {action_key}",
                reply_markup=_back_keyboard(),
            )


async def _process_barcode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: Optional[dict],
    barcode: str,
    chat_id: int | None = None,
) -> None:
    """Flujo completo de análisis de un código de barras. Llamado desde handle_message y /scan."""
    if chat_id is None:
        chat_id = update.effective_chat.id

    placeholder = await update.message.reply_text(f"Analizando código {barcode}...")
    done = asyncio.Event()
    task = asyncio.create_task(_typing_loop(context.bot, chat_id, done))

    try:
        loop = asyncio.get_running_loop()

        product_image_url = None
        product_name = barcode
        try:
            from backend.agents.scanner import lookup_barcode
            product_info = await loop.run_in_executor(None, lookup_barcode, barcode)
            if product_info and product_info.get("image_url"):
                product_image_url = product_info["image_url"]
                product_name = product_info.get("name", barcode)
        except Exception:
            pass

        response = await loop.run_in_executor(
            None, supervisor.run_scan, STORE_ID, barcode, (user or {}).get("id", "")
        )
    except Exception as e:
        response = f"Error al analizar el producto: {e}"
        product_image_url = None
    finally:
        done.set()
        await task

    if product_image_url:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=product_image_url,
                caption=f"📸 {product_name}",
            )
        except Exception:
            pass

    keyboard = _scan_result_keyboard(response, barcode)
    await _safe_edit(placeholder, response, reply_markup=keyboard)


def _build_agent_system(user: Optional[dict]) -> str:
    """Construye el system prompt de Chuwi con contexto en tiempo real."""
    context_lines = []
    try:
        pending = database.get_pending_actions(STORE_ID)
        critical = [a for a in pending if a.get("priority_score", 0) >= 85]
        context_lines.append(
            f"Estado actual: {len(pending)} acciones pendientes ({len(critical)} críticas)."
        )
    except Exception:
        pass
    try:
        brief = database.get_latest_brief(STORE_ID)
        if brief:
            context_lines.append(
                f"Último brief ({brief.get('date', '?')}): {brief.get('summary', '')[:200]}..."
            )
    except Exception:
        pass

    role_hint = ""
    if user:
        role = user.get("role", "staff")
        name = user.get("email", "").split("@")[0] or "empleado"
        if role in ("admin", "manager"):
            role_hint = f"\nHablas con {name}, encargado/gestor. Da respuestas con contexto estratégico y acceso completo."
        else:
            role_hint = f"\nHablas con {name}, personal de tienda. Da instrucciones concretas e inmediatas."

    context_block = "\n".join(context_lines)
    return (
        CHUWI_SYSTEM
        + role_hint
        + (f"\n\nCONTEXTO TIENDA AHORA:\n{context_block}" if context_block else "")
        + f"\n\nFecha y hora: {date.today().isoformat()} {datetime.now().strftime('%H:%M')}"
    )


async def _agent_stream(
    bot,
    placeholder,
    chat_history: list,
    user_text: str,
    user: Optional[dict],
) -> str:
    """
    Responde con streaming progresivo: edita el placeholder con el texto creciendo.
    Como escribir en WhatsApp — el encargado ve la respuesta aparecer letra a letra.
    Edita el mensaje cada EDIT_EVERY chars nuevos, throttleado para respetar límites de Telegram.
    """
    system_extra = _build_agent_system(user)
    messages = _compact_history(list(chat_history))
    messages.append({"role": "user", "content": user_text})

    buffer = ""
    last_edit_len = 0
    last_edit_time = time.monotonic()
    EDIT_EVERY_CHARS = 80
    EDIT_MIN_INTERVAL = 1.2  # segundos mínimos entre ediciones

    try:
        async for chunk in llm.stream_with_history(messages, system_extra=system_extra):
            buffer += chunk
            chars_since_edit = len(buffer) - last_edit_len
            time_since_edit = time.monotonic() - last_edit_time
            if chars_since_edit >= EDIT_EVERY_CHARS and time_since_edit >= EDIT_MIN_INTERVAL:
                try:
                    await placeholder.edit_text(
                        _md_to_html(buffer + " ▌"),
                        parse_mode=ParseMode.HTML,
                    )
                    last_edit_len = len(buffer)
                    last_edit_time = time.monotonic()
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"[chuwi] streaming error: {e}")
        if not buffer:
            try:
                buffer = _agent_respond(chat_history, user_text, user)
            except Exception as e2:
                buffer = f"Error: {e2}"

    return buffer or "Sin respuesta."


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja cualquier mensaje de texto — el núcleo conversacional del agente."""
    user = _get_user(update.effective_user.id)
    if not user:
        tg_id = update.effective_user.id
        await update.message.reply_text(
            f"Para usar MermaOps necesitas vincular tu cuenta.\n\n"
            f"Tu ID de Telegram es: <code>{tg_id}</code>\n"
            "Pásaselo al encargado para que lo vincule en la app.\n\n"
            "Escribe /start para más información.",
            parse_mode=ParseMode.HTML,
        )
        return

    chat_id = update.effective_chat.id
    chat_key = str(chat_id)
    user_id = str(update.effective_user.id)
    user_text = update.message.text.strip()

    if not user_text:
        return

    # ── Donation flow: captura de cantidad ──
    state = _get_conv_state(user_id)
    if state["mode"] == "donation_flow" and state["data"].get("step") == "enter_quantity":
        state_data = state["data"]
        try:
            qty = int(user_text.strip())
        except ValueError:
            await update.message.reply_text(
                f"Escribe un número entero. Por ejemplo: 5\n"
                f"Máximo disponible: {state_data.get('max_quantity', '?')}"
            )
            return

        max_qty = int(state_data.get("max_quantity", 999))
        if qty <= 0 or qty > max_qty:
            await update.message.reply_text(
                f"Cantidad inválida. Debe ser entre 1 y {max_qty}."
            )
            return

        state_data["quantity"] = qty
        _set_conv_state(user_id, "donation_flow", state_data)

        action_id = state_data.get("action_id", "")
        entity_key = state_data.get("entity", "")
        entity_name = next((n for n, k in _DONATION_ENTITIES if k == entity_key), entity_key)
        product_name = state_data.get("product_name", "Producto")

        confirm_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"✅ Confirmar donación de {qty} uds",
                callback_data=f"donation_step:confirm:{action_id}"
            )],
            [InlineKeyboardButton("❌ Cancelar", callback_data="donation_step:cancel:")],
        ])
        await update.message.reply_text(
            f"Resumen de donación:\n\n"
            f"Producto: {product_name}\n"
            f"Entidad: {entity_name}\n"
            f"Cantidad: {qty} unidades\n\n"
            "¿Confirmas?",
            reply_markup=confirm_kb
        )
        return

    # ── Inicio de modo ruta desde texto ──
    if _is_route_start(user_text):
        await _start_route_mode(update, context, user)
        return

    # ── Detección de escaneo de código de barras ──
    scan_match = re.search(r'(?:escanear?|scan)\s+(\d{6,14})', user_text, re.IGNORECASE)
    is_raw_barcode = user_text.isdigit() and 6 <= len(user_text) <= 14

    if scan_match or is_raw_barcode:
        barcode = scan_match.group(1) if scan_match else user_text
        await _process_barcode(update, context, user, barcode, chat_id)
        return

    # ── Detección de "listo" / "hecho" ──
    if _is_completion_message(user_text):
        await _handle_action_complete(update, context, user)
        return

    # ── Detección de intención para shortcuts sin LLM ──
    intent = _detect_intent(user_text)
    quick_actions = {"merma", "donaciones"}

    if intent in quick_actions:
        chat_history = _get_chat_history(chat_key)
        placeholder = await update.message.reply_text("...")
        done = asyncio.Event()
        task = asyncio.create_task(_typing_loop(context.bot, chat_id, done))
        try:
            loop = asyncio.get_running_loop()
            if intent == "merma":
                response = await loop.run_in_executor(None, _sync_merma_text)
            else:
                response = await loop.run_in_executor(None, _sync_donaciones_text)
        except Exception as e:
            response = f"Error: {e}"
        finally:
            done.set()
            await task

        chat_history.append({"role": "user", "content": user_text})
        chat_history.append({"role": "assistant", "content": response})
        _persist_chat_history(chat_key, _compact_history(chat_history))
        keyboard = _smart_keyboard(response, _is_manager(user))
        await _safe_edit(placeholder, response, reply_markup=keyboard)
        return

    # ── Conversación general — streaming progresivo (agente real, no bot) ──
    chat_history = _get_chat_history(chat_key)
    placeholder = await update.message.reply_text("⌛")
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    response = await _agent_stream(
        context.bot, placeholder, chat_history, user_text, user
    )

    chat_history.append({"role": "user", "content": user_text})
    chat_history.append({"role": "assistant", "content": response})
    _persist_chat_history(chat_key, _compact_history(chat_history))

    keyboard = _smart_keyboard(response, _is_manager(user))
    await _safe_edit(placeholder, response, reply_markup=keyboard)


def _sync_merma_text() -> str:
    logs = database.get_merma_history(STORE_ID, days=7)
    if not logs:
        return "Sin merma registrada en los últimos 7 días."
    total_value = sum(float(l.get("value_lost", 0)) for l in logs)
    total_qty = sum(int(l.get("quantity_lost", 0)) for l in logs)
    lines = [
        "MERMA — últimos 7 días:",
        f"  {total_qty} uds perdidas | {total_value:.2f} euros",
        "",
    ]
    for log in logs[:5]:
        lines.append(f"  - {log.get('date', '?')} | {log.get('quantity_lost', 0)} uds")
    return "\n".join(lines)


def _sync_donaciones_text() -> str:
    stats = database.get_donation_stats(STORE_ID, days=30)
    if stats["total_donations"] == 0:
        return "Sin donaciones registradas este mes."
    return (
        f"IMPACTO SOCIAL este mes:\n"
        f"  {stats['total_quantity']} unidades donadas\n"
        f"  {stats['total_value_donated']:.2f} euros de valor"
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Analiza visualmente la foto de un producto con Claude Vision.
    El empleado manda la foto — Chuwi detecta frescura, daños y fecha visible.
    No necesita barcode. Funciona solo con la imagen.
    """
    user = _get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text(
            "Primero debes vincular tu cuenta. Escribe /start."
        )
        return

    placeholder = await update.message.reply_text(
        "Analizando el producto con IA visual..."
    )

    try:
        # Obtener la foto de mayor resolución que envía Telegram
        photo = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        photo_bytes = await tg_file.download_as_bytearray()

        # Caption del mensaje como contexto adicional (si lo hay)
        caption = (update.message.caption or "").strip()

        loop = asyncio.get_running_loop()

        def run_vision():
            from backend.agents.vision import analyze_from_telegram_file, format_vision_result
            result = analyze_from_telegram_file(
                file_bytes=bytes(photo_bytes),
                product_name=caption or "",
            )
            return result, format_vision_result(result)

        result, formatted = await loop.run_in_executor(None, run_vision)

        # Teclado según acción recomendada
        action = result.get("action", "revisar")
        urgency = result.get("urgency", "normal")

        buttons = []
        if action == "rebajar":
            buttons.append(InlineKeyboardButton("✅ He rebajado", callback_data="vision_done:rebajar"))
        elif action == "retirar":
            buttons.append(InlineKeyboardButton("🗑 He retirado", callback_data="vision_done:retirar"))
        elif action == "donar":
            buttons.append(InlineKeyboardButton("🤝 He donado", callback_data="vision_done:donar"))
        buttons.append(InlineKeyboardButton("🔍 Analizar con barcode", callback_data="vision_scan"))

        keyboard = InlineKeyboardMarkup([buttons]) if buttons else None

        # Si la urgencia es inmediata, añadir prefijo de alerta
        prefix = "URGENTE — " if urgency == "inmediata" else ""
        await placeholder.edit_text(
            f"{prefix}{formatted}",
            reply_markup=keyboard,
        )

        # Guardar en historial
        chat_id = update.effective_chat.id
        chat_key = str(chat_id)
        hist = _get_chat_history(chat_key)
        hist.append({
            "role": "user",
            "content": f"[Foto de producto] {caption or 'sin descripción'}",
        })
        hist.append({
            "role": "assistant",
            "content": formatted,
        })
        _persist_chat_history(chat_key, _compact_history(hist))

    except Exception as e:
        logger.error(f"[chuwi] Error en análisis visual: {e}", exc_info=True)
        await placeholder.edit_text(
            f"No he podido analizar la foto: {e}\n\n"
            "Puedes escanear el código de barras escribiéndolo directamente."
        )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Transcribe nota de voz con Whisper y la procesa como mensaje de texto."""
    user = _get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text(
            "Primero debes vincular tu cuenta. Escribe /start."
        )
        return

    openai_client = _get_openai()
    if not openai_client:
        await update.message.reply_text(
            "El reconocimiento de voz no está disponible. "
            "Escribe tu pregunta en texto."
        )
        return

    placeholder = await update.message.reply_text("Escuchando tu nota de voz...")

    try:
        voice = update.message.voice or update.message.audio
        tg_file = await context.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await tg_file.download_to_drive(tmp_path)

        loop = asyncio.get_running_loop()

        def transcribe() -> str:
            with open(tmp_path, "rb") as f:
                result = openai_client.audio.transcriptions.create(
                    model="whisper-1", file=f, language="es"
                )
            return result.text.strip()

        transcription = await loop.run_in_executor(None, transcribe)
        Path(tmp_path).unlink(missing_ok=True)

        if not transcription:
            await placeholder.edit_text("No he podido entender el audio. Inténtalo de nuevo.")
            return

        await placeholder.edit_text(f"Escuché: {transcription}\n\nAnalizando...")

        chat_id = update.effective_chat.id
        chat_key = str(chat_id)
        chat_history = _get_chat_history(chat_key)

        done = asyncio.Event()
        task = asyncio.create_task(_typing_loop(context.bot, chat_id, done))
        try:
            response = await loop.run_in_executor(
                None, _agent_respond, chat_history, transcription, user
            )
        except Exception as e:
            response = f"Error: {e}"
        finally:
            done.set()
            await task

        chat_history.append({"role": "user", "content": f"[Voz] {transcription}"})
        chat_history.append({"role": "assistant", "content": response})
        _persist_chat_history(chat_key, _compact_history(chat_history))

        keyboard = _smart_keyboard(response, _is_manager(user))
        await placeholder.edit_text(
            _md_to_html(f"Escuché: {transcription}\n\n{response}"),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    except Exception as e:
        await placeholder.edit_text(f"Error procesando el audio: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

def run() -> None:
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no está definido en .env")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("menu", handle_menu))

    async def handle_tour(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = _get_user(update.effective_user.id)
        await _action_tour(update, ctx, user, is_callback=False)

    async def handle_ruta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = _get_user(update.effective_user.id)
        await _start_route_mode(update, ctx, user)

    app.add_handler(CommandHandler("tour", handle_tour))
    app.add_handler(CommandHandler("ruta", handle_ruta))

    async def handle_donar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = _get_user(update.effective_user.id)
        await _action_donar_flow(update, ctx, user, is_callback=False)

    async def handle_esg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = _get_user(update.effective_user.id)
        await _action_esg(update, ctx, user, is_callback=False)

    async def handle_prediccion(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = _get_user(update.effective_user.id)
        await _action_prediccion(update, ctx, user, is_callback=False)

    app.add_handler(CommandHandler("donar", handle_donar))
    app.add_handler(CommandHandler("esg", handle_esg))
    app.add_handler(CommandHandler("prediccion", handle_prediccion))

    async def handle_merma(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = _get_user(update.effective_user.id)
        await _action_merma(update, ctx, user, is_callback=False)

    async def handle_donaciones(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = _get_user(update.effective_user.id)
        await _action_donaciones(update, ctx, user, is_callback=False)

    async def handle_proveedores(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = _get_user(update.effective_user.id)
        await _action_proveedores(update, ctx, user, is_callback=False)

    async def handle_brief(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = _get_user(update.effective_user.id)
        await _action_brief(update, ctx, user, is_callback=False)

    async def handle_acciones(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = _get_user(update.effective_user.id)
        await _action_acciones(update, ctx, user, is_callback=False)

    async def handle_scan_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Permite /scan 8410031001001 directamente como comando Telegram."""
        user = _get_user(update.effective_user.id)
        if not user:
            await update.message.reply_text(
                "Para usar MermaOps necesitas vincular tu cuenta. Escribe /start."
            )
            return
        args = ctx.args
        if not args:
            await _action_scan_help(update, ctx, user, is_callback=False)
            return
        barcode = args[0].strip()
        if not barcode.isdigit() or not (6 <= len(barcode) <= 14):
            await update.message.reply_text(
                f"Código inválido: {barcode!r}\nEjemplo: /scan 8410031001001"
            )
            return
        await _process_barcode(update, ctx, user, barcode)

    async def handle_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = _get_user(update.effective_user.id)
        await _action_stats(update, ctx, user, is_callback=False)

    app.add_handler(CommandHandler("stats", handle_stats))
    app.add_handler(CommandHandler("merma", handle_merma))
    app.add_handler(CommandHandler("donaciones", handle_donaciones))
    app.add_handler(CommandHandler("proveedores", handle_proveedores))
    app.add_handler(CommandHandler("brief", handle_brief))
    app.add_handler(CommandHandler("acciones", handle_acciones))
    app.add_handler(CommandHandler("scan", handle_scan_cmd))

    async def handle_citar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = _get_user(update.effective_user.id)
        args = ctx.args or []
        await _action_citar(update, ctx, user, is_callback=False, cmd_args=args)

    app.add_handler(CommandHandler("citar", handle_citar))

    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("[chuwi] Agente activo. Esperando mensajes en Telegram...")
    app.run_polling(drop_pending_updates=True)
