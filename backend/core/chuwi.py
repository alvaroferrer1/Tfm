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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from telegram import (
    BotCommand,
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
from backend.core import telegram_formatter as _fmt
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

# Cache de IDs de conversación por chat_key → conversation_id en Supabase
# Se rellena la primera vez que el usuario habla. Persiste mientras el proceso vive.
_conv_id_cache: dict[str, str] = {}

# Cache de sesiones activas por user_id → session_id
# Una sesión agrupa mensajes de una misma "visita" al agente.
_session_cache: dict[str, str] = {}


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

CHUWI_SYSTEM = """Eres Chuwi, el agente operativo de MermaOps para el Super Martínez.
Coordinado por Kuine (el sistema central de IA), eres la interfaz directa con el personal de tienda.

ERES UN AGENTE REAL — no un bot de comandos:
- Tienes herramientas con datos reales. Úsalas para responder con hechos, no con suposiciones.
- Antes de responder algo sobre el estado de la tienda, consulta los datos reales.
- Si alguien pregunta "¿cómo está la tienda?", llama get_store_overview SIEMPRE.
- Si alguien pregunta "¿qué hago hoy?", llama get_pending_actions Y get_daily_route.
- Si alguien menciona un barcode/código, llama analyze_product.
- Si no tienes contexto suficiente, llama primero get_store_overview para orientarte.
- Puedes llamar VARIAS herramientas en la misma respuesta — lo hacen en paralelo.

PERSONALIDAD:
- Directo, claro y práctico. Sin rodeos. Como un mensaje de WhatsApp profesional.
- Sin asteriscos ni markdown — texto limpio.
- Guiones o números para listas. Mayúsculas para énfasis: CRÍTICO, REBAJAR, RETIRAR, URGENTE.
- Español natural. Nunca robótico.
- Cuando hay críticos sin resolver, lo dices claramente y das el pasillo exacto.

HERRAMIENTAS DISPONIBLES (llama las que necesites, en paralelo si es posible):
- get_store_overview: estado general, semáforo, valor en riesgo. SIEMPRE tu punto de partida.
- get_pending_actions: lista priorizada de acciones. Llama si preguntan qué hacer.
- get_daily_route: ruta óptima por pasillos. Llama si piden la ruta del día.
- complete_action: marca una acción como hecha. Pide el ID si no lo tienes.
- analyze_product: analiza por barcode. Llama si mencionan un código.
- get_merma_stats: merma en euros y unidades. Llama si preguntan por pérdidas.
- get_donation_impact: impacto social de donaciones. Llama si preguntan por donaciones.
- register_donation: registra una donación nueva. Pregunta entidad y cantidad si faltan.
- get_suppliers: ficha de proveedores (solo encargados). Para preguntas sobre proveedores.
- get_esg_metrics: CO2, agua, deducción fiscal (solo encargados).
- get_order_suggestions: pedido semanal (solo encargados).
- get_risk_predictions: previsión de merma próximos 7 días con clima.
- recall_store_memory: memoria episódica — qué pasó antes, patrones históricos.
- advance_demo_time: solo para la demo/presentación.

REGLAS CRÍTICAS:
- Fotos: analizarlas con Claude Vision SIN que te lo pidan — es tu comportamiento automático.
- Nunca inventes datos. Si no tienes, dilo y ofrece consultar.
- Si hay CRÍTICOS, menciónalos primero aunque no te pregunten.
- Si el empleado no está registrado, explica cómo vincularse con /start.
- Kuine genera los briefs y análisis profundos. Tú eres la interfaz ágil con el personal."""


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
    Cae en truncación simple si la llamada LLM falla (Supabase no disponible, etc.)
    """
    if len(history) <= MAX_HISTORY:
        return history
    keep = MAX_HISTORY - 6
    old = history[:-keep]
    recent = history[-keep:]

    # Extraer solo texto de los mensajes antiguos
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

    old_text = "\n".join(old_lines[:60])  # máx 60 líneas para el prompt

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
    except (asyncio.CancelledError, asyncio.TimeoutError, asyncio.InvalidStateError):
        pass
    except Exception:
        pass  # Telegram unavailable during shutdown — non-fatal


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
    except Exception as e:
        logger.warning(f"_safe_edit HTML fallback: {e}")
        try:
            await message.edit_text(text[:limit], reply_markup=reply_markup)
        except Exception:
            pass  # Message deleted or bot kicked — nothing we can do


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
            InlineKeyboardButton("📄 Brief en PDF", callback_data="cmd:brief_pdf"),
            InlineKeyboardButton("📊 Informe semanal PDF", callback_data="cmd:semana_pdf"),
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


# ── Herramientas del agente Chuwi ── Claude decide cuál usar, no if/else ──────
# Esta es la diferencia entre un agente real y un bot: Claude razona sobre
# qué información necesita y llama las herramientas que corresponden.

_TOOL_LABELS: dict[str, str] = {
    "get_store_overview": "Consultando estado de la tienda",
    "get_pending_actions": "Cargando acciones pendientes",
    "get_daily_route": "Generando ruta del día",
    "complete_action": "Registrando acción completada",
    "analyze_product": "Analizando producto",
    "get_merma_stats": "Consultando estadísticas de merma",
    "get_donation_impact": "Calculando impacto social",
    "register_donation": "Registrando donación",
    "get_suppliers": "Cargando ficha de proveedores",
    "get_esg_metrics": "Calculando métricas ESG",
    "advance_demo_time": "Avanzando tiempo de simulación",
    "get_order_suggestions": "Calculando pedido semanal",
    "get_risk_predictions": "Calculando predicciones de riesgo",
    "recall_store_memory": "Consultando memoria episódica",
}

CHUWI_TOOLS = [
    {
        "name": "get_store_overview",
        "description": (
            "Estado general de la tienda: acciones pendientes, críticos, valor en riesgo y resumen del brief. "
            "Usar cuando el empleado pregunte por el estado de hoy, qué hay que hacer, si hay urgencias, "
            "o cuando necesites contexto antes de responder otra pregunta."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_pending_actions",
        "description": (
            "Lista detallada de todas las acciones pendientes ordenadas por prioridad. "
            "Usar cuando pregunten qué acciones hay, qué productos son críticos, "
            "qué hay que hacer hoy, o para saber qué acción completar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "default": 10, "description": "Número máximo de acciones"},
            },
        },
    },
    {
        "name": "get_daily_route",
        "description": (
            "Ruta óptima del día organizada por pasillos para hacer las acciones pendientes de forma eficiente. "
            "Usar cuando pidan la ruta del día, el recorrido, o cómo hacer las acciones en orden."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "complete_action",
        "description": (
            "Marca una acción como completada y lo registra en la base de datos. "
            "Usar cuando el empleado diga que ya hizo algo, que está listo, hecho, terminado. "
            "IMPORTANTE: si no sabes el action_id, primero llama a get_pending_actions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action_id": {"type": "string", "description": "ID de la acción a completar"},
                "notes": {"type": "string", "description": "Notas opcionales del empleado"},
            },
            "required": ["action_id"],
        },
    },
    {
        "name": "analyze_product",
        "description": (
            "Analiza un producto por código de barras: días hasta caducidad, precio, acción recomendada. "
            "Usar cuando el empleado mencione un código de barras o pida analizar un producto específico."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "barcode": {"type": "string", "description": "Código de barras del producto (6-14 dígitos)"},
            },
            "required": ["barcode"],
        },
    },
    {
        "name": "get_merma_stats",
        "description": (
            "Estadísticas de merma: valor perdido en euros, unidades, productos más problemáticos. "
            "Usar cuando pregunten sobre merma, pérdidas, qué se ha tirado, valor perdido."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7, "description": "Días hacia atrás (default: 7)"},
            },
        },
    },
    {
        "name": "get_donation_impact",
        "description": (
            "Impacto social de las donaciones al banco de alimentos y otras entidades. "
            "Usar cuando pregunten sobre donaciones, impacto social, CO2 evitado, cuánto se ha donado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 30, "description": "Días hacia atrás"},
            },
        },
    },
    {
        "name": "register_donation",
        "description": (
            "Registra una donación al banco de alimentos u otra entidad solidaria. "
            "Usar cuando el empleado confirme que va a donar o haya donado un producto. "
            "Si el empleado no especifica la entidad, preguntar antes de registrar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "enum": ["banco_alimentos", "caritas", "cruz_roja", "comedor_social"],
                    "description": "Entidad receptora de la donación",
                },
                "quantity": {"type": "integer", "minimum": 1, "description": "Unidades donadas"},
                "product_name": {"type": "string", "description": "Nombre del producto donado"},
                "batch_id": {"type": "string", "description": "ID del lote si se conoce"},
            },
            "required": ["entity", "quantity"],
        },
    },
    {
        "name": "get_suppliers",
        "description": (
            "Ficha de proveedores con tasa de merma histórica y nivel de riesgo. "
            "Solo accesible para encargados. Usar cuando pregunten por proveedores, suministradores o quién da más problemas."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_esg_metrics",
        "description": (
            "Métricas de impacto ambiental y social: CO2 evitado (kg), agua ahorrada (litros), "
            "deducción fiscal estimada por donaciones (Ley 49/2002). "
            "Usar cuando pregunten por sostenibilidad, impacto, ESG, CO2, deducciones."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_order_suggestions",
        "description": (
            "Sugerencias de pedido semanal basadas en historial de merma y stock actual. "
            "Solo encargados. Usar cuando pregunten qué pedir, cómo reponer stock."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "advance_demo_time",
        "description": (
            "Para la presentación: avanza N días en la simulación, actualizando caducidades, "
            "creando nuevas acciones urgentes y garantizando productos CRÍTICO/ALTO/BAJO visibles. "
            "Solo usar si el encargado lo pide explícitamente para la demo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "number",
                    "minimum": 0.5,
                    "maximum": 30,
                    "description": "Días a avanzar (puede ser decimal, ej: 1.5 = día y medio)",
                },
            },
            "required": ["days"],
        },
    },
    {
        "name": "get_risk_predictions",
        "description": (
            "Predicciones de riesgo de merma para los próximos 5-7 días con previsión meteorológica. "
            "Usa el Predictor Agent que analiza histórico + clima + día de semana. "
            "Usar cuando pregunten qué va a pasar esta semana, previsión de merma, "
            "qué productos habrá que vigilar pronto, o para planificación anticipada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7, "description": "Horizonte de predicción en días"},
            },
        },
    },
    {
        "name": "recall_store_memory",
        "description": (
            "Recupera patrones y aprendizajes guardados de la memoria episódica de la tienda. "
            "Usar cuando el empleado pregunte por algo histórico: qué pasó la semana pasada, "
            "qué proveedor falló antes, qué patrón hay en la merma de una categoría. "
            "También útil para dar contexto histórico antes de responder sobre riesgos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern_key": {
                    "type": "string",
                    "description": (
                        "Clave del patrón a recuperar. Ejemplos: "
                        "'merma_historica_semana', 'categoria_lacteos_tendencia', "
                        "'proveedor_riesgo', 'horas_pico_venta'"
                    ),
                },
            },
            "required": ["pattern_key"],
        },
        # cache_control en el ÚLTIMO tool: Anthropic cachea todas las definiciones de tools
        # anteriores a este punto → ahorro ~5-8K tokens en cada llamada (15 tools × ~500 tokens).
        "cache_control": {"type": "ephemeral"},
    },
]


def _execute_tool_sync(tool_name: str, tool_input: dict, user: Optional[dict]) -> dict:
    """
    Ejecuta una herramienta de Chuwi de forma síncrona.
    Llamado desde código async via run_in_executor.
    Claude llama a estas herramientas — no hay routing manual.
    """
    is_mgr = _is_manager(user)
    try:
        if tool_name == "get_store_overview":
            pending = database.get_pending_actions(STORE_ID)
            critical = [a for a in pending if (a.get("priority_score") or 0) >= 85]
            alto = [a for a in pending if 65 <= (a.get("priority_score") or 0) < 85]
            brief = database.get_latest_brief(STORE_ID)
            batches = database.get_batches_expiring_soon(STORE_ID, days=7)
            value_at_risk = sum(
                int(b.get("quantity", 0)) * float((b.get("products") or {}).get("price", 0))
                for b in batches
            )
            semaforo = "ROJO" if len(critical) >= 5 else "AMARILLO" if len(critical) >= 2 else "VERDE"
            return {
                "semaforo": semaforo,
                "pending_total": len(pending),
                "criticos": len(critical),
                "altos": len(alto),
                "value_at_risk_eur": round(value_at_risk, 2),
                "lotes_caducando_7d": len(batches),
                "brief_hoy": brief.get("summary", "") if brief else None,
                "brief_fecha": brief.get("date", "") if brief else None,
            }

        elif tool_name == "get_pending_actions":
            max_r = int(tool_input.get("max_results", 10))
            pending = database.get_pending_actions(STORE_ID)
            sorted_p = sorted(pending, key=lambda a: -(a.get("priority_score") or 0))
            actions = []
            for a in sorted_p[:max_r]:
                batch = a.get("batches") or {}
                product = (batch.get("products") or {}) if batch else {}
                exp = batch.get("expiry_date", "")
                try:
                    days_left = (date.fromisoformat(exp) - date.today()).days if exp else None
                except Exception:
                    days_left = None
                actions.append({
                    "id": a.get("id"),
                    "product": product.get("name", "?"),
                    "pasillo": product.get("pasillo", "?"),
                    "action_type": a.get("action_type", ""),
                    "priority_score": a.get("priority_score", 0),
                    "new_price": a.get("new_price"),
                    "days_left": days_left,
                    "notes": (a.get("notes") or "")[:120],
                })
            return {"total": len(pending), "mostrando": len(actions), "acciones": actions}

        elif tool_name == "get_daily_route":
            from backend.agents import evaluator as ev, route as rt
            batches = database.get_batches_expiring_soon(STORE_ID, days=7)
            if not batches:
                return {"ruta": "Sin productos próximos a caducar esta semana. Todo en orden."}
            risk_reports = [(b, ev.evaluate(b.get("products") or {}, [b])) for b in batches]
            daily_route = rt.generate(STORE_ID, risk_reports)
            return {"ruta": rt.format_route_message(daily_route)}

        elif tool_name == "complete_action":
            action_id = tool_input.get("action_id", "")
            u_name = (user.get("email") or user.get("id", "empleado")).split("@")[0] if user else "empleado"
            database.complete_action(action_id, u_name)
            return {"ok": True, "completada_por": u_name, "action_id": action_id}

        elif tool_name == "analyze_product":
            barcode = str(tool_input.get("barcode", ""))
            u_id = (user or {}).get("id", "")
            result = supervisor.run_scan(STORE_ID, barcode, u_id)
            return {"analisis": result}

        elif tool_name == "get_merma_stats":
            days = int(tool_input.get("days", 7))
            logs = database.get_merma_history(STORE_ID, days=days)
            total_value = sum(float(l.get("value_lost", 0)) for l in logs)
            total_qty = sum(int(l.get("quantity_lost", 0)) for l in logs)
            top = []
            for log in logs[:5]:
                batch = log.get("batches") or {}
                product = (batch.get("products") or {}) if batch else {}
                top.append({
                    "producto": product.get("name", log.get("reason", "?")[:30]),
                    "fecha": log.get("date", "?"),
                    "cantidad": log.get("quantity_lost", 0),
                    "valor_eur": round(float(log.get("value_lost", 0)), 2),
                })
            return {
                "dias": days,
                "valor_total_eur": round(total_value, 2),
                "unidades_total": total_qty,
                "registros": len(logs),
                "top_productos": top,
            }

        elif tool_name == "get_donation_impact":
            days = int(tool_input.get("days", 30))
            stats = database.get_donation_stats(STORE_ID, days=days)
            return stats

        elif tool_name == "register_donation":
            entity = tool_input.get("entity", "banco_alimentos")
            quantity = int(tool_input.get("quantity", 0))
            product_name = tool_input.get("product_name", "")
            batch_id = tool_input.get("batch_id")
            u_name = (user.get("email") or "empleado") if user else "empleado"
            entity_display = {
                "banco_alimentos": "Banco de Alimentos",
                "caritas": "Cáritas",
                "cruz_roja": "Cruz Roja",
                "comedor_social": "Comedor Social",
            }.get(entity, entity)
            donation_data = {
                "store_id": STORE_ID,
                "entity": entity_display,
                "quantity": quantity,
                "value_donated": 0.0,
                "donated_at": datetime.now(timezone.utc).isoformat(),
                "donated_by": u_name,
            }
            if batch_id:
                donation_data["batch_id"] = batch_id
            database.log_donation(donation_data)
            return {"ok": True, "entidad": entity_display, "cantidad": quantity, "producto": product_name}

        elif tool_name == "get_suppliers":
            if not is_mgr:
                return {"error": "Solo encargados pueden ver la ficha de proveedores."}
            stats = database.get_supplier_stats(STORE_ID)
            return {"proveedores": stats}

        elif tool_name == "get_esg_metrics":
            if not is_mgr:
                return {"error": "Solo encargados pueden ver las métricas ESG completas."}
            from backend.agents.esg import get_store_esg_summary
            return get_store_esg_summary(STORE_ID, 30)

        elif tool_name == "get_order_suggestions":
            if not is_mgr:
                return {"error": "Solo encargados pueden ver sugerencias de pedido."}
            suggestions = database.get_order_suggestions(STORE_ID)
            return {"sugerencias": suggestions[:15] if suggestions else []}

        elif tool_name == "advance_demo_time":
            if not is_mgr:
                return {"error": "Solo encargados pueden avanzar el tiempo de la demo."}
            days = float(tool_input.get("days", 1))
            from backend.data.advance_demo import advance as _adv
            result = _adv(days, store_id=STORE_ID, generate_brief=True)
            return {"ok": True, "dias_avanzados": days, **result}

        elif tool_name == "get_risk_predictions":
            days = int(tool_input.get("days", 7))
            try:
                from backend.agents.predictor import predict_merma_risk
                predictions = predict_merma_risk(STORE_ID, days=days)
                return {
                    "dias": days,
                    "productos_en_riesgo": len(predictions),
                    "predicciones": predictions[:10],
                }
            except Exception as e:
                return {"error": f"Predictor no disponible: {e}"}

        elif tool_name == "recall_store_memory":
            pattern_key = tool_input.get("pattern_key", "")
            from backend.core import memory as _mem_mod
            value = _mem_mod.recall(STORE_ID, pattern_key)
            return {
                "pattern_key": pattern_key,
                "found": value is not None,
                "value": value or "Sin datos históricos para esta clave.",
            }

        else:
            return {"error": f"Herramienta desconocida: {tool_name}"}

    except Exception as e:
        logger.error(f"[chuwi] tool error {tool_name}: {e}")
        return {"error": str(e)}


_COMPLEX_KEYWORDS = (
    "analiza", "compara", "por qué", "explica", "estrategia",
    "informe", "resumen", "qué harías", "recomendación", "decisión",
    "merma", "proveedor", "esg", "predicción", "semana", "mes",
)

MAX_AGENT_ITERATIONS = 6


def _is_complex_query(text: str) -> bool:
    t = text.lower()
    return len(text) > 120 or any(kw in t for kw in _COMPLEX_KEYWORDS)


# ── Fase 2: Clasificación de intención (sin LLM — zero tokens) ───────────────

_INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    # Orden importa: más específico primero
    ("registrar_donacion", [
        "donar", "donación", "donacion", "banco de alimentos", "banco alimentos",
        "food bank", "entidad benéfica", "ong",
    ]),
    ("registrar_merma", [
        "registrar merma", "apuntar merma", "anotar merma", "hubo merma",
        "se perdió", "se perdio", "tiré", "tire ",
    ]),
    ("pedir_ruta", [
        "ruta", "iniciar ruta", "empezar ruta", "comenzar ruta",
        "hacer la ruta", "dame la ruta", "modo ruta", "empiezo la ruta",
    ]),
    ("pedir_brief", [
        "brief", "resumen del día", "resumen del dia", "informe del día",
        "cómo estamos", "como estamos", "análisis de hoy", "analisis de hoy",
        "generar brief", "situación de hoy", "situacion de hoy",
    ]),
    ("completar_accion", [
        "completé", "complete ", "hice ", "listo", "terminé", "termine",
        "ya está", "ya esta", "lo hice", "ya lo hice", "done", "hecho",
        "realizé", "realize",
    ]),
    ("crear_accion", [
        "crear acción", "crear accion", "nueva acción", "nueva accion",
        "añadir acción", "crea una accion", "agregar acción",
    ]),
    ("consulta_estado", [
        "cuánto", "cuantos", "cuántos", "cuanta", "qué caduca", "que caduca",
        "qué hay", "que hay", "estado", "críticos", "criticos", "urgentes",
        "pendientes", "cuántas acciones", "cuantas acciones", "cuántos lotes",
        "productos caducados", "qué vence", "que vence",
    ]),
    ("configuracion", [
        "configurar", "cambiar ajuste", "ajustar", "ayuda", "help",
        "comandos", "commands", "qué puedes hacer", "que puedes hacer",
        "opciones", "menú", "menu",
    ]),
]


def _classify_intent(text: str) -> str:
    """
    Clasificador de intención basado en keywords. Sin LLM — 0 tokens.
    Orden de evaluación: más específico primero. Fallback: pregunta_libre.
    """
    t = text.lower().strip()
    for intent, keywords in _INTENT_PATTERNS:
        if any(kw in t for kw in keywords):
            return intent
    return "pregunta_libre"


def _build_intent_context(intent: str, store_id: str) -> str:
    """
    Genera contexto adicional según intención detectada.
    Se inyecta en el system prompt para ayudar al agente a responder más rápido.
    Falla silenciosamente si Supabase no está disponible.
    """
    try:
        if intent == "consulta_estado":
            pending = database.get_pending_actions(store_id)
            critical = [a for a in pending if a.get("priority_score", 0) >= 85]
            high = [a for a in pending if 65 <= a.get("priority_score", 0) < 85]
            return (
                f"\n[CONTEXTO AUTOMÁTICO — consulta_estado]\n"
                f"Acciones pendientes: {len(pending)} total, "
                f"{len(critical)} críticas (score≥85), {len(high)} altas (score≥65)\n"
            )
        elif intent == "pedir_brief":
            brief = database.get_latest_brief(store_id)
            if brief:
                return (
                    f"\n[CONTEXTO AUTOMÁTICO — pedir_brief]\n"
                    f"Último brief: {brief.get('date','?')}, "
                    f"valor en riesgo: {brief.get('value_at_risk', 0):.2f}€, "
                    f"acciones: {brief.get('actions_count', 0)}\n"
                )
        elif intent in ("completar_accion", "pedir_ruta"):
            pending = database.get_pending_actions(store_id)
            top = pending[:3] if pending else []
            lines = "\n".join(
                f"  - {(a.get('batches') or {}).get('products', {}).get('name','?')} "
                f"[score={a.get('priority_score',0)}]"
                for a in top
            )
            return (
                f"\n[CONTEXTO AUTOMÁTICO — {intent}]\n"
                f"Acciones pendientes: {len(pending)}\n"
                f"Top prioridad:\n{lines}\n"
            )
        elif intent == "registrar_donacion":
            stats = database.get_donation_stats(store_id, days=30)
            return (
                f"\n[CONTEXTO AUTOMÁTICO — registrar_donacion]\n"
                f"Donaciones este mes: {stats['total_donations']}, "
                f"total: {stats['total_quantity']} uds, "
                f"valor: {stats['total_value_donated']:.2f}€\n"
            )
    except Exception:
        pass
    return ""


async def _run_agent_loop(
    bot,
    placeholder,
    chat_history: list,
    user_text: str,
    user: Optional[dict],
    intent_tag: str = "pregunta_libre",
    intent_context: str = "",
) -> tuple[str, list[str]]:
    """
    Chuwi como agente REAL con multi-turn tool use.

    Loop agéntico (hasta MAX_AGENT_ITERATIONS):
      1. Claude razona con herramientas disponibles (streaming progresivo)
      2. Si llama herramientas → ejecutamos → devolvemos resultados → siguiente ronda
      3. Si responde con texto (end_turn) → fin del loop
      4. Extended thinking para preguntas complejas

    No hay if/else por keywords. Claude decide qué hacer y cuándo terminar.
    Devuelve (respuesta_texto, lista_de_tools_usadas).
    intent_context: datos de contexto pre-cargados según la intención (sin coste de LLM).
    """
    system_extra = _build_agent_system(user)
    if intent_context:
        system_extra = system_extra + intent_context
    from backend.core import reflexion as _reflexion
    _rfx_ctx = _reflexion.get_reflexion_context(STORE_ID)
    if _rfx_ctx:
        system_extra = system_extra + _rfx_ctx
    messages = _compact_history(list(chat_history))
    messages.append({"role": "user", "content": user_text})

    client = llm.get_async_client()
    ev_loop = asyncio.get_event_loop()
    buffer = ""
    last_edit_len = 0
    last_edit_time = time.monotonic()
    EDIT_EVERY = 35      # Actualiza cada 35 chars (antes 80) — más fluido
    MIN_INTERVAL = 0.5   # Mínimo 0.5s entre edits (antes 1.2s)
    iteration = 0
    use_thinking = _is_complex_query(user_text)
    all_tools_used: list[str] = []  # acumula nombres de tools ejecutadas en todo el loop

    async def _progressive_edit(text: str, cursor: bool = True) -> None:
        nonlocal last_edit_len, last_edit_time
        chars_new = len(text) - last_edit_len
        time_new = time.monotonic() - last_edit_time
        if chars_new >= EDIT_EVERY and time_new >= MIN_INTERVAL:
            try:
                suffix = " ▌" if cursor else ""
                await placeholder.edit_text(_md_to_html(text + suffix), parse_mode=ParseMode.HTML)
                last_edit_len = len(text)
                last_edit_time = time.monotonic()
            except Exception:
                pass

    try:
        while iteration < MAX_AGENT_ITERATIONS:
            iteration += 1
            pending_tools: list[dict] = []
            current_tool: Optional[dict] = None
            final_content: list = []
            round_buffer = ""

            stream_kwargs: dict = {
                "model": llm.MODEL,
                "max_tokens": 2048,
                "system": llm._cached_system(system_extra),
                "tools": CHUWI_TOOLS,
                "tool_choice": {"type": "auto"},
                "messages": messages,
            }
            if use_thinking and iteration == 1:
                stream_kwargs["thinking"] = {"type": "adaptive"}
                stream_kwargs["max_tokens"] = 4096

            async with client.messages.stream(**stream_kwargs) as stream:
                async for event in stream:
                    etype = getattr(event, "type", "")

                    if etype == "content_block_start":
                        block = getattr(event, "content_block", None)
                        btype = getattr(block, "type", "")
                        if btype == "tool_use":
                            label = _TOOL_LABELS.get(block.name, block.name)
                            current_tool = {"id": block.id, "name": block.name, "input": ""}
                            try:
                                suffix = f" (paso {iteration})" if iteration > 1 else ""
                                await placeholder.edit_text(f"⏳ {label}{suffix}...")
                            except Exception:
                                pass
                        elif btype == "thinking":
                            try:
                                await placeholder.edit_text("🤔 Analizando en profundidad...")
                            except Exception:
                                pass

                    elif etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        dtype = getattr(delta, "type", "")
                        if dtype == "text_delta":
                            round_buffer += delta.text
                            buffer = round_buffer
                            await _progressive_edit(buffer)
                        elif dtype == "input_json_delta" and current_tool:
                            current_tool["input"] += getattr(delta, "partial_json", "")

                    elif etype == "content_block_stop":
                        if current_tool:
                            pending_tools.append(current_tool)
                            current_tool = None

                final_msg = await stream.get_final_message()
                final_content = list(final_msg.content)
                stop_reason = final_msg.stop_reason

            if stop_reason != "tool_use" or not pending_tools:
                break

            # Ejecutar todas las tools en PARALELO — 90% mejora de velocidad
            async def _exec_one(tc: dict) -> dict:
                try:
                    t_input = json.loads(tc["input"]) if tc["input"].strip() else {}
                except Exception:
                    t_input = {}
                res = await ev_loop.run_in_executor(
                    None, _execute_tool_sync, tc["name"], t_input, user
                )
                return {
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": json.dumps(res, ensure_ascii=False, default=str),
                }

            tool_results = list(await asyncio.gather(*[_exec_one(tc) for tc in pending_tools]))
            all_tools_used.extend(tc["name"] for tc in pending_tools)

            messages.append({"role": "assistant", "content": final_content})
            messages.append({"role": "user", "content": tool_results})

            buffer = ""
            last_edit_len = 0
            last_edit_time = time.monotonic()

        logger.info(f"[chuwi] agent loop: {iteration} iteraciones, {len(buffer)} chars, tools={all_tools_used}")

    except Exception as e:
        logger.error(f"[chuwi] agent loop error (iter {iteration}): {e}")
        if not buffer:
            try:
                buffer = _agent_respond(chat_history, user_text, user)
            except Exception as e2:
                buffer = f"Error: {e2}"

    # Fire-and-forget reflexion when Kuine was involved (no token cost to user)
    _kuine_tools = {"analyze_product", "run_supervisor_analysis", "evaluate_product"}
    if any(t in _kuine_tools for t in all_tools_used) and buffer:
        asyncio.ensure_future(_reflexion.async_generate_and_save(
            store_id=STORE_ID,
            query=user_text,
            response=buffer,
        ))

    return buffer or "Sin respuesta.", all_tools_used


# ── Detección de palabras clave para estado de ruta/donación (NO para routing general) ──

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
            "📋 <b>Sin brief para hoy todavía.</b>\n\n"
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
        pending = database.get_pending_actions(STORE_ID)
        critical_count = sum(1 for a in pending if (a.get("priority_score") or 0) >= 85)
        high_count = sum(1 for a in pending if 65 <= (a.get("priority_score") or 0) < 85)
        value_at_risk = brief.get("value_at_risk", 0.0) or 0.0
        text = _fmt.format_brief(
            summary=summary,
            brief_date=brief.get("date", ""),
            value_at_risk=float(value_at_risk),
            actions_count=brief.get("actions_count", len(pending)),
            critical_count=critical_count,
            high_count=high_count,
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚡ Ver acciones", callback_data="cmd:acciones"),
                InlineKeyboardButton("🗺 Ruta del día", callback_data="cmd:ruta"),
            ],
            [
                InlineKeyboardButton("📄 Descargar PDF", callback_data="cmd:brief_pdf"),
                InlineKeyboardButton("↩ Menú", callback_data="cmd:menu"),
            ],
        ])

    if is_callback:
        await update_or_query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        chat_id = update_or_query.effective_chat.id if hasattr(update_or_query, "effective_chat") else update_or_query.message.chat_id
        chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
        for i, chunk in enumerate(chunks):
            await update_or_query.message.reply_text(
                chunk,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard if i == len(chunks) - 1 else None,
            )


async def _action_acciones(update_or_query, context, user: Optional[dict], is_callback=False):
    pending = database.get_pending_actions(STORE_ID)
    text = _fmt.format_actions(pending)
    if not pending:
        keyboard = _back_keyboard()
    else:
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
        brief = database.get_latest_brief(STORE_ID)

        critical = sum(1 for a in pending if (a.get("priority_score") or 0) >= 85)
        high = sum(1 for a in pending if 65 <= (a.get("priority_score") or 0) < 85)
        value_at_risk = sum(
            (b.get("quantity") or 0) * ((b.get("products") or {}).get("price") or 0)
            for b in batches
        )
        merma_value = sum(float(l.get("value_lost", 0)) for l in merma_7d)
        donated_qty = donations.get("total_quantity", 0)
        donated_value = donations.get("total_value_donated", 0.0)
        semaforo = "ROJO" if critical >= 5 else ("AMARILLO" if critical >= 2 else "VERDE")

        text = _fmt.format_stats(
            pending_total=len(pending),
            critical=critical,
            high=high,
            batches_expiring=len(batches),
            value_at_risk=round(value_at_risk, 2),
            merma_7d_eur=round(merma_value, 2),
            donated_qty=donated_qty,
            donated_value=float(donated_value),
            brief_date=brief.get("date", "") if brief else "",
            semaforo=semaforo,
        )
    except Exception as e:
        text = f"❌ Error al obtener KPIs: {e}"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ Acciones", callback_data="cmd:acciones"),
            InlineKeyboardButton("🔴 Críticos", callback_data="cmd:criticos"),
        ],
        [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
    ])
    if is_callback:
        await update_or_query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_merma(update_or_query, context, user: Optional[dict], is_callback=False):
    try:
        logs = database.get_merma_history(STORE_ID, days=7)
        text = _fmt.format_merma(logs, days=7)
    except Exception as e:
        text = f"❌ Error al obtener merma: {e}"

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")]])
    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_donaciones(update_or_query, context, user: Optional[dict], is_callback=False):
    try:
        stats = database.get_donation_stats(STORE_ID, days=30)
        text = _fmt.format_donaciones(stats)
    except Exception as e:
        text = f"❌ Error al obtener donaciones: {e}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤝 Registrar donación", callback_data="cmd:donar_flow")],
        [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
    ])
    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
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
        text = _fmt.format_proveedores(stats)
    except Exception as e:
        text = f"❌ Error al obtener proveedores: {e}"

    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_pedido(update_or_query, context, user: Optional[dict], is_callback=False):
    keyboard = _back_keyboard()
    if not _is_manager(user):
        text = "🔒 La sugerencia de pedido es solo para encargados."
        if is_callback:
            await update_or_query.edit_message_text(text, reply_markup=keyboard)
        else:
            await _send(update_or_query, text, reply_markup=keyboard)
        return

    try:
        suggestions = database.get_order_suggestions(STORE_ID)
        text = _fmt.format_pedido(suggestions)
    except Exception as e:
        text = f"❌ Error al calcular pedido: {e}"

    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
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
        "- 11 agentes especializados coordinados por Kuine\n"
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
        "1. KUINE — el cerebro. Loop agéntico con 25 herramientas. "
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
        "Kuine → Evaluator (con Validator) → Price/Stock/Route "
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
                        "donated_at": _dt.now(_dt.now().astimezone().tzinfo).isoformat(),
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

def _auto_save_chat_id(chat_id: int) -> None:
    """Guarda el chat_id en Supabase y en el campo telegram_chat_id de la tienda."""
    try:
        # 1. Guardar en agent_memory para que el notifier lo encuentre
        _mem.remember(STORE_ID, "telegram_admin_chat_id", str(chat_id))
        # 2. Actualizar el campo telegram_chat_id en la tabla stores
        database.get_db().table("stores").update(
            {"telegram_chat_id": str(chat_id)}
        ).eq("id", STORE_ID).execute()
        logger.info(f"[chuwi] chat_id {chat_id} guardado para tienda {STORE_ID}")
    except Exception as e:
        logger.debug(f"[chuwi] auto_save_chat_id: {e}")


_AVATAR_PATH = Path(__file__).parent.parent.parent / "backend" / "static" / "chuwi_avatar.png"


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    tg_name = update.effective_user.first_name or "empleado"

    # Siempre guardar el chat_id de quien haga /start
    _auto_save_chat_id(update.effective_chat.id)

    user = _get_user(tg_id)

    # Enviar avatar si existe
    try:
        if _AVATAR_PATH.exists():
            with open(_AVATAR_PATH, "rb") as f:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=f,
                    caption="<b>Chuwi</b> · Agente operativo de MermaOps",
                    parse_mode=ParseMode.HTML,
                )
    except Exception:
        pass

    if not user:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 Abrir App MermaOps", url="https://t.me/ChuwiMermaOpsBot")],
            [InlineKeyboardButton("🏪 Ver estado de la tienda", callback_data="cmd:estado")],
            [InlineKeyboardButton("🤖 Ver todos los agentes", callback_data="cmd:agentes_info")],
        ])
        await update.message.reply_text(
            f"👋 Hola <b>{tg_name}</b>, soy <b>Chuwi</b>, el agente de <b>MermaOps</b>.\n\n"
            "Para responder con datos de tu tienda, necesitas vincular tu cuenta.\n\n"
            "┌────────────────────────┐\n"
            "│  🔢  <b>Tu ID de Telegram</b>  │\n"
            "└────────────────────────┘\n\n"
            f"<code>{tg_id}</code>\n\n"
            "👆 Cópialo, abre la app MermaOps\n"
            "→ <b>Perfil</b> → pega el número → pulsa <b>Vincular</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
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

        # Log Chuwi↔Kuine: brief generado por Kuine a petición de usuario vía Chuwi
        try:
            chat_key = str(query.message.chat_id)
            u_id = str(query.from_user.id)
            conv_id = _conv_id_cache.get(chat_key) or database.get_active_conversation(STORE_ID, u_id)
            if not conv_id:
                conv_id = database.create_agent_conversation(STORE_ID, u_id)
                _conv_id_cache[chat_key] = conv_id
            database.log_agent_message(
                conversation_id=conv_id, store_id=STORE_ID, role="system",
                content="[coordinación] Chuwi solicitó brief diario a Kuine (supervisor.run_daily_brief)",
                agent_source="kuine",
            )
            database.log_agent_message(
                conversation_id=conv_id, store_id=STORE_ID, role="assistant",
                content=result[:2000], tools_used=["run_daily_brief"], agent_source="kuine",
            )
        except Exception:
            pass

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

    # ── Donación proactiva sugerida por Kuine ── empleado elige entidad con un toque ──
    if data.startswith("donate_now:"):
        # formato: donate_now:{entity}:{batch_id}
        parts = data.split(":", 2)
        entity_key = parts[1] if len(parts) > 1 else "banco_alimentos"
        batch_id = parts[2] if len(parts) > 2 else ""

        if entity_key == "skip":
            await query.edit_message_text(
                "Entendido. La acción queda pendiente en el sistema.",
                reply_markup=_back_keyboard()
            )
            return

        entity_display = {
            "banco_alimentos": "Banco de Alimentos",
            "caritas": "Cáritas",
            "cruz_roja": "Cruz Roja",
            "rebajar": None,
        }.get(entity_key, entity_key)

        if entity_key == "rebajar":
            await query.edit_message_text(
                "Bien. El sistema mantendrá la acción de rebaja de precio activa.",
                reply_markup=_back_keyboard()
            )
            return

        try:
            u_name = (user.get("email") or "empleado").split("@")[0] if user else "empleado"
            batch = None
            qty = 5
            if batch_id:
                batches = database.get_batches_expiring_soon(STORE_ID, days=3)
                batch = next((b for b in batches if b.get("id") == batch_id), None)
                if batch:
                    qty = int(batch.get("quantity", 5))

            database.log_donation({
                "store_id": STORE_ID,
                "batch_id": batch_id or None,
                "entity": entity_display,
                "quantity": qty,
                "value_donated": 0.0,
                "donated_at": datetime.now(timezone.utc).isoformat(),
                "donated_by": u_name,
            })
            product_name = ""
            if batch:
                p = batch.get("products") or {}
                product_name = p.get("name", "")

            await query.edit_message_text(
                f"✅ Donación registrada\n\n"
                f"{'Producto: ' + product_name + chr(10) if product_name else ''}"
                f"Entidad: {entity_display}\n"
                f"Cantidad: {qty} unidades\n"
                f"Registrado por: {u_name}\n\n"
                "Cada donación evita merma y ayuda a quien lo necesita. Gracias.",
                reply_markup=_main_menu_keyboard(_is_manager(user))
            )
        except Exception as e:
            await query.edit_message_text(
                f"Error al registrar la donación: {e}",
                reply_markup=_back_keyboard()
            )
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

    # ── Demo callbacks (avanzar días / reset) ──
    if data.startswith("demo:"):
        await _handle_demo_callback(query, context, data)
        return

    # ── Estado: refresh del semáforo de tienda ──
    if data == "cmd:estado":
        try:
            loop = asyncio.get_running_loop()
            pending = await loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
            batches = await loop.run_in_executor(
                None, database.get_batches_expiring_soon, STORE_ID, 7
            )
            brief = await loop.run_in_executor(None, database.get_latest_brief, STORE_ID)
            value_at_risk = sum(
                (b.get("quantity") or 0) * ((b.get("products") or {}).get("price") or 0)
                for b in batches
            )
            text = _fmt.format_estado(pending, batches, brief, round(value_at_risk, 2))
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⚡ Acciones", callback_data="cmd:acciones"),
                    InlineKeyboardButton("🔴 Críticos", callback_data="cmd:criticos"),
                ],
                [
                    InlineKeyboardButton("🗺 Iniciar ruta", callback_data="cmd:iniciar_ruta"),
                    InlineKeyboardButton("🔄 Actualizar", callback_data="cmd:estado"),
                ],
                [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception as e:
            await query.edit_message_text(f"Error consultando estado: {e}", reply_markup=_back_keyboard())
        return

    # ── Críticos: lista inline ──
    if data == "cmd:criticos":
        try:
            loop = asyncio.get_running_loop()
            pending = await loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
            critical = [a for a in pending if a.get("priority_score", 0) >= 85]
            if not critical:
                await query.edit_message_text(
                    "✅ Sin productos críticos en este momento.\nUsa /estado para el panorama completo.",
                    reply_markup=_back_keyboard()
                )
                return
            lines = [f"🔴 <b>{len(critical)} PRODUCTO(S) CRÍTICO(S)</b>\n"]
            for i, a in enumerate(critical[:8], 1):
                b = (a.get("batches") or {})
                p = (b.get("products") or {}) if b else {}
                action_type = (a.get("action_type") or "revisar").upper()
                score = a.get("priority_score", 0)
                notes = (a.get("notes") or "")[:80]
                lines.append(
                    f"{i}. <b>{p.get('name', 'Producto')}</b>\n"
                    f"   Pasillo {p.get('pasillo', '?')} | Score {score}/100 | {action_type}\n"
                    f"   {notes}"
                )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗺 Iniciar ruta de críticos", callback_data="cmd:iniciar_ruta")],
                [InlineKeyboardButton("⬅️ Menú", callback_data="cmd:menu")],
            ])
            await query.edit_message_text("\n\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception as e:
            await query.edit_message_text(f"Error: {e}", reply_markup=_back_keyboard())
        return

    # ── Agentes: info completa inline ──
    if data == "cmd:agentes_info":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Estado tienda ahora", callback_data="cmd:estado")],
            [InlineKeyboardButton("⬅️ Menú", callback_data="cmd:menu")],
        ])
        await query.edit_message_text(_AGENTES_TEXT, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # ── PDF informe semanal ──
    if data == "cmd:semana_pdf":
        if not _is_manager(user):
            await query.edit_message_text("🔒 El informe semanal PDF es solo para encargados.", reply_markup=_back_keyboard())
            return
        await query.edit_message_text("📊 Generando informe semanal (30-60s)...")
        done = asyncio.Event()
        typing_task = asyncio.create_task(_typing_loop(context.bot, query.message.chat_id, done))
        try:
            loop = asyncio.get_running_loop()
            pdf_bytes = await loop.run_in_executor(None, _generate_weekly_pdf_bytes)
            done.set()
            await typing_task
            if pdf_bytes:
                import io as _io
                fecha = date.today().isoformat()
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=_io.BytesIO(pdf_bytes),
                    filename=f"informe_semanal_{fecha}.pdf",
                    caption=f"📊 <b>Informe Semanal</b> — Super Martínez · Kuine",
                    parse_mode=ParseMode.HTML,
                )
                await query.edit_message_text("✅ Informe semanal enviado.")
            else:
                await query.edit_message_text("Error generando el informe semanal.")
        except Exception as e:
            done.set()
            await typing_task
            await query.edit_message_text(f"Error: {e}")
        return

    # ── PDF del brief ──
    if data == "cmd:brief_pdf":
        await query.edit_message_text("📄 Generando PDF del brief...")
        done = asyncio.Event()
        typing_task = asyncio.create_task(_typing_loop(context.bot, query.message.chat_id, done))
        try:
            loop = asyncio.get_running_loop()
            pdf_bytes = await loop.run_in_executor(None, _generate_brief_pdf_bytes)
            done.set()
            await typing_task
            if pdf_bytes:
                import io as _io
                fecha = date.today().isoformat()
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=_io.BytesIO(pdf_bytes),
                    filename=f"brief_{fecha}.pdf",
                    caption=f"📋 <b>Brief {fecha}</b> — Super Martínez\nGenerado por Kuine · MermaOps",
                    parse_mode=ParseMode.HTML,
                )
                await query.edit_message_text("✅ PDF enviado.")
            else:
                await query.edit_message_text("No hay brief disponible para generar PDF.")
        except Exception as e:
            done.set()
            await typing_task
            await query.edit_message_text(f"Error generando PDF: {e}")
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


async def _do_unlink_telegram(update: Update, user: Optional[dict]) -> None:
    """Desvincula el telegram_user_id del usuario en Supabase."""
    if not user:
        await update.message.reply_text("No tienes cuenta vinculada. Escribe /start.")
        return
    user_id = user.get("id", "")
    tg_name = update.effective_user.first_name or "usuario"
    try:
        database.get_db().table("users").update(
            {"telegram_user_id": None}
        ).eq("id", user_id).execute()
        await update.message.reply_text(
            f"✅ Cuenta desvinculada, {tg_name}.\n\n"
            "Tu Telegram ya no está conectado a MermaOps.\n"
            "Para volver a vincular abre la app → Perfil → Telegram.",
        )
        logger.info(f"[chuwi] Usuario {user_id} desvinculado de Telegram")
    except Exception as e:
        await update.message.reply_text(f"Error al desvincular: {e}")


async def _cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Desvincula el Telegram del usuario autenticado."""
    user = _get_user(update.effective_user.id)
    await _do_unlink_telegram(update, user)


def _upsert_telegram_user(
    telegram_user_id: str,
    telegram_username: Optional[str],
    telegram_chat_id: str,
    linked_user: Optional[dict],
) -> None:
    """Registra o actualiza al usuario de Telegram en la tabla telegram_users."""
    try:
        from datetime import datetime
        now = datetime.utcnow().isoformat()
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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja cualquier mensaje de texto — el núcleo conversacional del agente."""
    tg_user = update.effective_user
    user = _get_user(tg_user.id)

    # Registrar/actualizar en telegram_users (tracking de todos los usuarios)
    _upsert_telegram_user(
        telegram_user_id=str(tg_user.id),
        telegram_username=tg_user.username,
        telegram_chat_id=str(update.effective_chat.id),
        linked_user=user,
    )

    if not user:
        tg_id = tg_user.id
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )
        await update.message.reply_text(
            f"👋 Hola, soy <b>Chuwi</b>, el agente de MermaOps.\n\n"
            f"🔢 <b>Tu ID de Telegram:</b>\n<code>{tg_id}</code>\n\n"
            "Para que pueda responderte con datos de tu tienda:\n"
            "1️⃣ Abre la app MermaOps\n"
            "2️⃣ Ve a <b>Perfil</b>\n"
            "3️⃣ Pega el número de arriba → pulsa <b>Vincular</b>\n\n"
            "Escribe /start para más opciones.",
            parse_mode=ParseMode.HTML,
        )
        return

    chat_id = update.effective_chat.id
    chat_key = str(chat_id)
    user_id = str(tg_user.id)
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

    # ── Desconectar / logout de Telegram ──
    _desconectar_triggers = {
        "desconectar telegram", "desconectar", "logout", "cerrar sesion",
        "cerrar sesión", "desvincular", "desvincular telegram", "salir",
    }
    if user_text.lower().strip() in _desconectar_triggers:
        await _do_unlink_telegram(update, user)
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

    # ── Fase 2: Clasificación de intención (0 tokens, 0ms) ──
    intent_tag = _classify_intent(user_text)
    intent_context = _build_intent_context(intent_tag, STORE_ID)
    logger.info(f"[chuwi] intent={intent_tag} user={user_id[:8] if user_id else '?'}")

    # ── Sesión activa (agent_sessions) — crear si no existe ──
    session_id = _session_cache.get(user_id)
    if not session_id:
        try:
            session_id = database.create_agent_session(STORE_ID, user_id)
            _session_cache[user_id] = session_id
        except Exception:
            session_id = None

    # ── Agente real: Claude decide qué herramientas usar y cómo responder ──
    chat_history = _get_chat_history(chat_key)
    placeholder = await update.message.reply_text("⌛")
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    response, tools_used = await _run_agent_loop(
        context.bot, placeholder, chat_history, user_text, user,
        intent_tag=intent_tag, intent_context=intent_context,
    )

    chat_history.append({"role": "user", "content": user_text})
    chat_history.append({"role": "assistant", "content": response})
    _persist_chat_history(chat_key, _compact_history(chat_history))

    # ── Actualizar stats de sesión ──
    if session_id:
        kuine_used = 1 if "analyze_product" in tools_used else 0
        try:
            database.increment_session_stats(
                session_id,
                tools_called=len(tools_used),
                kuine_calls=kuine_used,
            )
        except Exception:
            pass

    # ── Persistencia en Supabase: agent_conversations + agent_messages ──
    _persist_conversation_message(
        chat_key=chat_key,
        store_id=STORE_ID,
        telegram_user_id=user_id,
        user_text=user_text,
        response=response,
        tools_used=tools_used,
        intent_tag=intent_tag,
    )

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
    """Transcribe nota de voz con Google Speech Recognition y la procesa con el agente."""
    tg_user = update.effective_user
    user_id = str(tg_user.id)
    user = _get_user(tg_user.id)

    if not user:
        await update.message.reply_text(
            f"Primero debes vincular tu cuenta.\n\nEscribe /start — te mostraré tu ID ({tg_user.id})."
        )
        return

    placeholder = await update.message.reply_text("🎙️ Escuchando tu nota de voz...")

    try:
        voice = update.message.voice or update.message.audio
        tg_file = await context.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await tg_file.download_to_drive(tmp_path)

        loop = asyncio.get_running_loop()

        def transcribe() -> str:
            import speech_recognition as sr
            wav_path = tmp_path.replace(".ogg", ".wav")
            try:
                from pydub import AudioSegment
                AudioSegment.from_ogg(tmp_path).export(wav_path, format="wav")
                audio_path = wav_path
            except Exception:
                audio_path = tmp_path

            recognizer = sr.Recognizer()
            recognizer.energy_threshold = 300
            recognizer.dynamic_energy_threshold = True
            with sr.AudioFile(audio_path) as source:
                audio_data = recognizer.record(source)
            try:
                Path(wav_path).unlink(missing_ok=True)
            except Exception:
                pass
            return recognizer.recognize_google(audio_data, language="es-ES")

        try:
            transcription = await loop.run_in_executor(None, transcribe)
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            await placeholder.edit_text(
                f"No he podido entender el audio ({e.__class__.__name__}).\n\nEscríbeme tu pregunta."
            )
            return
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        if not transcription:
            await placeholder.edit_text("No he entendido el audio. Inténtalo de nuevo.")
            return

        await placeholder.edit_text(f"🎙️ Escuché: <i>{html.escape(transcription)}</i>\n\n⏳",
                                     parse_mode=ParseMode.HTML)

        chat_id = update.effective_chat.id
        chat_key = str(chat_id)
        chat_history = _get_chat_history(chat_key)
        intent_tag = _classify_intent(transcription)
        intent_context = _build_intent_context(intent_tag, STORE_ID)

        response, tools_used = await _run_agent_loop(
            context.bot, placeholder, chat_history,
            f"[Nota de voz]: {transcription}",
            user, intent_tag=intent_tag, intent_context=intent_context,
        )

        chat_history.append({"role": "user", "content": f"[Voz] {transcription}"})
        chat_history.append({"role": "assistant", "content": response})
        _persist_chat_history(chat_key, _compact_history(chat_history))
        await _persist_conversation_message(chat_key, user_id, f"[Voz] {transcription}",
                                            response, tools_used, intent_tag)

        session_id = _session_cache.get(user_id)
        if session_id:
            kuine_used = 1 if "analyze_product" in tools_used else 0
            try:
                database.increment_session_stats(session_id, len(tools_used), kuine_used)
            except Exception:
                pass

        keyboard = _smart_keyboard(response, _is_manager(user))
        await placeholder.edit_text(
            _md_to_html(f"🎙️ Escuché: {transcription}\n\n{response}"),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    except Exception as e:
        logger.error(f"[chuwi] voice error: {e}")
        await placeholder.edit_text(f"Error procesando el audio: {e}")


# ── Nuevos comandos — información del sistema y demo ─────────────────────────

_AGENTES_TEXT = """🤖 <b>LOS 11 AGENTES DE MERMAOPS</b>

<b>KUINE</b> — Orquestador (Claude Opus 4.7)
El cerebro del sistema. Investiga la tienda con 25 herramientas, razona con adaptive thinking y coordina todo. Funciona solo: 7 cron jobs (07:30, 12:00, 20:00…).
<i>Demo: /brief genera el análisis completo ahora mismo.</i>

<b>EVALUADOR</b> — Riesgo por producto (Claude Sonnet 4.6)
Score 0-100 por lote. Para score ≥65: extended thinking con normativa y margen mínimo. Para score ≥90 y >30€: consenso de 3 instancias en paralelo.
<i>Demo: /criticos muestra los productos con score más alto.</i>

<b>VALIDADOR</b> — Adversarial
El único agente que puede REVERTIR decisiones. Detecta: precio &lt; coste, CRÍTICO sin acción, FEFO violations. 23 ataques adversariales probados → 100% neutralizados.

<b>CONSENSO</b> — Votación paralela
3 evaluadores en paralelo para casos extremos (score ≥90 AND valor ≥30€). Árbitro con Claude Opus en empate.

<b>PREDICTOR</b> — Anticipación 7 días
Combina historial de merma + Open-Meteo (clima) + día de semana. Predice qué va a caducar ANTES de que sea urgente.
<i>Demo: /prediccion</i>

<b>VISIÓN</b> — Análisis visual (Claude Vision)
Analiza fotos de productos. Detecta estado, daños, fecha visible. Sin barcode. Manda una foto aquí y funciona solo.

<b>ESG</b> — Impacto ambiental
CO2 evitado, agua ahorrada, deducción fiscal Ley 49/2002 (35%). Cada donación genera un registro contable.
<i>Demo: /esg</i>

<b>REPORTERO</b> — Briefs e informes
Brief apertura (07:30), revisión mediodía (12:00), cierre (20:00). Informe semanal con ROI. Informe mensual para el dueño.

<b>NOTIFICADOR</b> — Telegram inteligente
Mensajes con botones de acción directa. Donaciones con un toque. Alertas automáticas si crítico lleva >4h sin resolver.

<b>SCANNER</b> — OpenFoodFacts
Enriquece productos con nombre, imagen y categoría desde la base de datos global de alimentos.

<b>RUTAS</b> — Optimizador de pasillos
Ruta más eficiente por urgencia + ubicación física. Modo ruta guía al empleado acción por acción.
<i>Demo: /ruta</i>"""


async def _cmd_agentes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explica cada agente con nombre, modelo, función y cómo demostrar que funciona."""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Estado tienda ahora", callback_data="cmd:estado")],
        [InlineKeyboardButton("⬅️ Menú", callback_data="cmd:menu")],
    ])
    await update.message.reply_text(
        _AGENTES_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


async def _cmd_kuine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Estado de Kuine: último brief, próxima ejecución, herramientas disponibles."""
    user = _get_user(update.effective_user.id)
    await update.message.reply_text("Consultando estado de Kuine...")
    try:
        loop = asyncio.get_running_loop()
        brief = await loop.run_in_executor(None, database.get_latest_brief, STORE_ID)
        pending = await loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
        critical = [a for a in pending if a.get("priority_score", 0) >= 85]
        alto = [a for a in pending if 65 <= a.get("priority_score", 0) < 85]

        last_brief_date = brief.get("date", "nunca") if brief else "sin brief hoy"
        last_summary = (brief.get("summary") or "")[:200] if brief else ""

        text = (
            f"🧠 <b>KUINE — Estado del orquestador</b>\n\n"
            f"Modelo: Claude Opus 4.7 (adaptive thinking)\n"
            f"Herramientas disponibles: 25\n"
            f"Iteraciones máximas por ciclo: 20\n"
            f"Cron jobs activos: 7\n\n"
            f"━━━ Último análisis ━━━\n"
            f"Fecha: {last_brief_date}\n"
            f"Acciones generadas: {len(pending)} ({len(critical)} CRÍTICAS, {len(alto)} ALTAS)\n"
        )
        if last_summary:
            text += f"\nResumen:\n<i>{last_summary}...</i>\n"

        text += (
            f"\n━━━ Próximas ejecuciones ━━━\n"
            f"• 07:30 — Brief apertura\n"
            f"• 12:00 — Revisión mediodía\n"
            f"• 20:00 — Cierre del día\n"
            f"• Cada 30min — Monitor proactivo\n"
            f"• Cada 2h — Escalación de críticos\n\n"
            f"Escribe /brief para forzar análisis ahora."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Generar brief ahora", callback_data="confirm:runbrief")],
            [InlineKeyboardButton("📋 Ver acciones", callback_data="cmd:acciones")],
        ])
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception as e:
        await update.message.reply_text(f"Error consultando Kuine: {e}")


async def _cmd_demo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Controla la simulación temporal de la demo: /demo 2, /demo reset, /demo estado."""
    user = _get_user(update.effective_user.id)
    args = context.args or []
    cmd = args[0].lower() if args else "ayuda"

    if cmd == "reset":
        await update.message.reply_text("♻️ Reiniciando estado del Super Martínez...")
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: __import__(
                "backend.data.advance_demo", fromlist=["reset"]
            ).reset(STORE_ID))
            await update.message.reply_text(
                "✅ Estado reiniciado al día de hoy.\n"
                "Usa /demo 2 para avanzar días y ver cómo Kuine reacciona."
            )
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
        return

    try:
        days = float(cmd)
    except ValueError:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏩ Avanzar 1 día", callback_data="demo:advance:1")],
            [InlineKeyboardButton("⏩⏩ Avanzar 3 días", callback_data="demo:advance:3")],
            [InlineKeyboardButton("♻️ Reset al estado inicial", callback_data="demo:reset")],
        ])
        await update.message.reply_text(
            "🎬 <b>MODO DEMO — Control temporal</b>\n\n"
            "Simula el paso del tiempo en la tienda. Kuine reacciona automáticamente.\n\n"
            "Comandos:\n"
            "• <code>/demo 1</code> — avanza 1 día\n"
            "• <code>/demo 3</code> — avanza 3 días (aparecen CRÍTICOS)\n"
            "• <code>/demo reset</code> — vuelve al estado inicial\n\n"
            "O usa los botones:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return

    if days < 0.5 or days > 14:
        await update.message.reply_text("Usa un número entre 0.5 y 14 días.")
        return

    msg = await update.message.reply_text(
        f"⏩ Simulando {days:.0f} día(s) en la tienda...\n"
        "Kuine actualizará caducidades, creará acciones y enviará mensajes."
    )
    done = asyncio.Event()
    task = asyncio.create_task(_typing_loop(context.bot, update.effective_chat.id, done))
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: __import__(
                "backend.data.advance_demo", fromlist=["advance"]
            ).advance(days, store_id=STORE_ID)
        )
        done.set()
        await task
        await msg.edit_text(
            f"✅ <b>Simulación completada: +{days:.0f} días</b>\n\n"
            f"• Lotes actualizados: {result.get('batches_updated', 0)}\n"
            f"• Acciones nuevas creadas: {result.get('actions_created', 0)}\n"
            f"• Acciones completadas (simuladas): {result.get('actions_completed', 0)}\n"
            f"• Unidades vendidas (simuladas): {result.get('stock_reduced', 0)}\n"
            f"• Mensajes Telegram enviados: {result.get('telegram_messages_sent', 0)}\n\n"
            "Usa /estado para ver el nuevo estado de la tienda.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        done.set()
        await task
        await msg.edit_text(f"Error en la simulación: {e}")


async def _cmd_yo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el perfil del usuario: ID Telegram, vinculación con app, rol."""
    tg_id = update.effective_user.id
    tg_name = update.effective_user.first_name or "Usuario"
    user = _get_user(tg_id)

    if not user:
        await update.message.reply_text(
            f"👤 <b>Tu perfil</b>\n\n"
            f"Nombre: {tg_name}\n"
            f"ID Telegram: <code>{tg_id}</code>\n"
            f"Estado: ❌ No vinculado con la app\n\n"
            "Para vincular:\n"
            "1. Abre la app → Perfil → Telegram\n"
            f"2. Pega tu ID: <code>{tg_id}</code>\n"
            "3. Pulsa Vincular\n\n"
            "Una vez vinculado tendrás acceso a todas las funciones.",
            parse_mode=ParseMode.HTML,
        )
        return

    role_emoji = {"admin": "👑", "manager": "🔑", "staff": "👷"}.get(user.get("role", ""), "👷")
    await update.message.reply_text(
        f"👤 <b>Tu perfil</b>\n\n"
        f"Nombre: {tg_name}\n"
        f"Email: {user.get('email', '?')}\n"
        f"Rol: {role_emoji} {user.get('role', '?').capitalize()}\n"
        f"ID Telegram: <code>{tg_id}</code>\n"
        f"Estado: ✅ Vinculado con la app\n"
        f"Tienda: {STORE_ID}\n\n"
        "Comandos disponibles: /ayuda\n"
        "Para desvincular escribe: <code>desconectar telegram</code>",
        parse_mode=ParseMode.HTML,
    )


async def _cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Estado de la tienda en tiempo real — funciona sin estar vinculado."""
    msg = await update.message.reply_text("🔍 Consultando estado de la tienda...")
    try:
        loop = asyncio.get_running_loop()
        pending = await loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
        batches = await loop.run_in_executor(
            None, database.get_batches_expiring_soon, STORE_ID, 7
        )
        brief = await loop.run_in_executor(None, database.get_latest_brief, STORE_ID)

        critical = [a for a in pending if a.get("priority_score", 0) >= 85]
        alto = [a for a in pending if 65 <= a.get("priority_score", 0) < 85]
        total_value = sum(
            b.get("quantity", 0) * (b.get("products") or {}).get("price", 0)
            for b in batches
        )

        if len(critical) >= 3:
            semaforo = "🔴 ALERTA"
        elif len(critical) >= 1 or len(alto) >= 3:
            semaforo = "🟡 ATENCIÓN"
        else:
            semaforo = "🟢 NORMAL"

        text = (
            f"📊 <b>SUPER MARTÍNEZ — Estado actual</b>\n"
            f"Semáforo: {semaforo}\n\n"
            f"Acciones pendientes: {len(pending)}\n"
            f"  🔴 CRÍTICAS: {len(critical)}\n"
            f"  🟡 ALTAS: {len(alto)}\n"
            f"  🟢 Resto: {len(pending) - len(critical) - len(alto)}\n\n"
            f"Lotes próximos a caducar (7d): {len(batches)}\n"
            f"Valor en riesgo: {total_value:.2f} €\n"
        )
        if brief:
            text += f"\nÚltimo brief: {brief.get('date', '?')}"

        if critical:
            text += "\n\n━━ CRÍTICOS AHORA ━━"
            for a in critical[:3]:
                b = (a.get("batches") or {})
                p = (b.get("products") or {}) if b else {}
                text += f"\n• {p.get('name', 'Producto')} | Pasillo {p.get('pasillo', '?')} | {a.get('action_type', '?').upper()}"

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Ver todas las acciones", callback_data="cmd:acciones")],
            [InlineKeyboardButton("🗺 Iniciar ruta del día", callback_data="cmd:iniciar_ruta")],
            [InlineKeyboardButton("🔄 Actualizar", callback_data="cmd:estado")],
        ])
        await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception as e:
        await msg.edit_text(f"Error consultando estado: {e}")


async def _cmd_criticos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista de productos críticos (score ≥85) con pasillo y acción exacta."""
    msg = await update.message.reply_text("🔴 Buscando productos críticos...")
    try:
        loop = asyncio.get_running_loop()
        pending = await loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
        critical = [a for a in pending if a.get("priority_score", 0) >= 85]

        if not critical:
            await msg.edit_text(
                "✅ Sin productos críticos en este momento.\n"
                "Usa /estado para ver el panorama completo."
            )
            return

        lines = [f"🔴 <b>{len(critical)} PRODUCTO(S) CRÍTICO(S)</b>\n"]
        for i, a in enumerate(critical[:8], 1):
            b = (a.get("batches") or {})
            p = (b.get("products") or {}) if b else {}
            action_type = (a.get("action_type") or "revisar").upper()
            score = a.get("priority_score", 0)
            notes = (a.get("notes") or "")[:80]
            lines.append(
                f"{i}. <b>{p.get('name', 'Producto')}</b>\n"
                f"   Pasillo {p.get('pasillo', '?')} | Score {score}/100 | {action_type}\n"
                f"   {notes}"
            )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗺 Iniciar ruta de críticos", callback_data="cmd:iniciar_ruta")],
            [InlineKeyboardButton("⬅️ Menú", callback_data="cmd:menu")],
        ])
        await msg.edit_text("\n\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception as e:
        await msg.edit_text(f"Error: {e}")


async def _cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista completa de comandos con descripción."""
    user = _get_user(update.effective_user.id)
    manager = _is_manager(user)
    base = (
        "📚 <b>COMANDOS DE CHUWI</b>\n\n"
        "<b>— Información general —</b>\n"
        "/start — Bienvenida y vinculación de cuenta\n"
        "/yo — Tu perfil y estado de vinculación\n"
        "/estado — Estado de la tienda en tiempo real 🚦\n"
        "/agentes — Qué hace cada agente de IA\n"
        "/kuine — Estado de Kuine (el orquestador)\n"
        "/ayuda — Este mensaje\n\n"
        "<b>— Operaciones diarias —</b>\n"
        "/acciones — Lista de acciones pendientes\n"
        "/criticos — Solo productos con score ≥85\n"
        "/ruta — Iniciar ruta guiada por pasillos\n"
        "/scan [código] — Analizar producto por barcode\n"
        "/brief — Ver el brief de apertura de hoy\n\n"
        "<b>— Estadísticas —</b>\n"
        "/merma — Merma en euros (últimos 7 días)\n"
        "/donaciones — Impacto social de donaciones\n"
        "/prediccion — Previsión de merma 7 días + clima\n"
        "/stats — Estadísticas del semáforo general\n"
    )
    manager_cmds = (
        "\n<b>— Solo encargados —</b>\n"
        "/proveedores — Ficha de proveedores con merma\n"
        "/esg — Métricas ESG (CO2, agua, deducción fiscal)\n"
        "/citar [consulta] — Citar normativa alimentaria\n"
        "/demo [días|reset] — Simular paso del tiempo\n"
        "/kuine — Estado del orquestador\n"
        "/costes — Coste IA real y ahorro por prompt caching\n"
        "/reflexiones — Lecciones aprendidas por el Reflexion Loop\n"
    )
    tip = (
        "\n💡 <b>Tip:</b> También puedes escribir en lenguaje natural.\n"
        "Ej: \"¿qué hago con las fresas del pasillo 5?\"\n"
        "O enviar una foto de cualquier producto para analizarlo."
    )
    text = base + (manager_cmds if manager else "") + tip
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def _cmd_costes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /costes — Muestra el coste real de tokens en la sesión actual y el ahorro
    generado por el prompt caching. Impresionante para la demo del TFM.
    """
    user = _get_user(update.effective_user.id)
    if not _is_manager(user):
        await update.message.reply_text("🔒 Solo encargados pueden ver los costes del sistema.")
        return

    stats = llm.get_cost_summary()
    total   = stats["total_usd"]
    saved   = stats["saved_usd"]
    pct     = stats["saving_pct"]
    calls   = stats["calls"]
    hits    = stats["cache_hit_pct"]
    inp_k   = stats["input_tokens"] // 1000
    out_k   = stats["output_tokens"] // 1000
    cached_k = stats["cache_read_tokens"] // 1000

    # Extrapolación: si ahorro actual es X, en un mes con ~30× más llamadas...
    monthly_saved_est = saved * 30 if calls > 0 else 0.0

    lines = [
        "┌──────────────────────────────────┐",
        "│  💰  <b>COSTES IA — sesión actual</b>",
        "└──────────────────────────────────┘",
        "",
        f"📊 Llamadas al API:    <b>{calls}</b>",
        f"✅ Cache hits:         <b>{hits}%</b> de llamadas",
        "",
        "━" * 34,
        f"💸 Coste real:         <b>${total:.4f}</b>",
        f"🎯 Ahorro por caché:   <b>${saved:.4f}  ({pct}%)</b>",
        "",
        f"📥 Tokens entrada:     <b>{inp_k}K</b>",
        f"📤 Tokens salida:      <b>{out_k}K</b>",
        f"⚡ Tokens cacheados:   <b>{cached_k}K</b>  (10% del precio normal)",
        "",
        "━" * 34,
        f"📅 Proyección mensual: <b>~${monthly_saved_est:.2f} ahorrado</b>",
        "",
        "<i>Prompt caching activo en sistema y herramientas.</i>",
        "<i>Cache TTL: 5 min · Mín. 1024 tokens para activarse.</i>",
    ]
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=_back_keyboard(),
    )


async def _cmd_reflexiones(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /reflexiones — Muestra las lecciones operativas que Chuwi ha aprendido
    de conversaciones anteriores (Reflexion Loop).
    """
    user = _get_user(update.effective_user.id)
    if not _is_manager(user):
        await update.message.reply_text("🔒 Solo encargados pueden ver las reflexiones del sistema.")
        return

    from backend.core import reflexion as _reflexion
    try:
        lessons = _reflexion.load_reflexions(STORE_ID)
    except Exception:
        lessons = []

    if not lessons:
        await update.message.reply_text(
            "🧠 <b>Reflexion Loop activo</b>\n\n"
            "Aún no hay lecciones aprendidas. Chuwi genera reflexiones automáticamente "
            "después de analizar productos con Kuine.\n\n"
            "<i>Tip: analiza un producto y vuelve a consultar /reflexiones.</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    items = "\n".join(f"  {i+1}. {l}" for i, l in enumerate(lessons))
    text = (
        "┌──────────────────────────────────┐\n"
        "│  🧠  <b>LECCIONES APRENDIDAS — Chuwi</b>\n"
        "└──────────────────────────────────┘\n"
        "\n"
        f"<b>{len(lessons)} lecciones activas</b> (buffer rotante de 5):\n"
        "\n"
        f"{items}\n"
        "\n"
        "━" * 34 + "\n"
        "<i>Generadas por Haiku tras cada análisis de Kuine.</i>\n"
        "<i>Se usan automáticamente en el próximo mensaje.</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=_back_keyboard())


# ── PDF helpers ──────────────────────────────────────────────────────────────

def _generate_brief_pdf_bytes() -> bytes | None:
    """Genera el PDF del brief de hoy. Llamar desde run_in_executor."""
    try:
        brief = database.get_latest_brief(STORE_ID)
        if not brief:
            return None
        pending = database.get_pending_actions(STORE_ID)
        critical_actions = [a for a in pending if (a.get("priority_score") or 0) >= 85]
        high_actions = [a for a in pending if 65 <= (a.get("priority_score") or 0) < 85]
        value_at_risk = brief.get("value_at_risk", 0.0) or 0.0
        from backend.core.pdf_generator import generate_brief_pdf
        return generate_brief_pdf(
            brief_text=brief.get("summary", ""),
            brief_date=brief.get("date", ""),
            critical_count=len(critical_actions),
            high_count=len(high_actions),
            value_at_risk=float(value_at_risk),
            actions_count=brief.get("actions_count", len(pending)),
            critical_actions=critical_actions,
            high_actions=high_actions,
        )
    except Exception as e:
        logger.error(f"[chuwi] _generate_brief_pdf_bytes: {e}")
        return None


def _generate_weekly_pdf_bytes() -> bytes | None:
    """Genera el PDF del informe semanal. Llamar desde run_in_executor."""
    try:
        from backend.core.pdf_generator import generate_weekly_pdf
        from backend.agents.reporter import generate_weekly_report
        report_text = generate_weekly_report(STORE_ID)
        merma_week = database.get_merma_history(STORE_ID, days=7)
        merma_eur = sum(float(l.get("value_lost", 0)) for l in merma_week)
        merma_qty = sum(int(l.get("quantity_lost", 0)) for l in merma_week)
        donations = database.get_donation_stats(STORE_ID, days=7)
        return generate_weekly_pdf(
            report_text=report_text,
            merma_eur=merma_eur,
            merma_qty=merma_qty,
            donated_qty=donations.get("total_quantity", 0),
            donated_value=float(donations.get("total_value_donated", 0)),
        )
    except Exception as e:
        logger.error(f"[chuwi] _generate_weekly_pdf_bytes: {e}")
        return None


async def _cmd_informe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Genera y envía el PDF del brief de hoy."""
    user = _get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Primero vincula tu cuenta. Escribe /start.")
        return
    if not _is_manager(user):
        await update.message.reply_text("🔒 El informe PDF es solo para encargados.")
        return

    placeholder = await update.message.reply_text("📄 Generando PDF del brief...")
    done = asyncio.Event()
    task = asyncio.create_task(_typing_loop(context.bot, update.effective_chat.id, done))
    try:
        loop = asyncio.get_running_loop()
        pdf_bytes = await loop.run_in_executor(None, _generate_brief_pdf_bytes)
        done.set()
        await task
        if pdf_bytes:
            import io as _io
            fecha = date.today().isoformat()
            await update.message.reply_document(
                document=_io.BytesIO(pdf_bytes),
                filename=f"brief_{fecha}.pdf",
                caption=(
                    f"📋 <b>Brief {fecha}</b> — Super Martínez\n"
                    "Generado por Kuine · MermaOps"
                ),
                parse_mode=ParseMode.HTML,
            )
            await placeholder.delete()
        else:
            await placeholder.edit_text(
                "❌ No hay brief disponible para hoy.\n"
                "Genéralo con /brief o espera a las 07:30."
            )
    except Exception as e:
        done.set()
        await task
        await placeholder.edit_text(f"Error generando PDF: {e}")


async def _cmd_semana(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Genera y envía el PDF del informe semanal."""
    user = _get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Primero vincula tu cuenta. Escribe /start.")
        return
    if not _is_manager(user):
        await update.message.reply_text("🔒 El informe semanal PDF es solo para encargados.")
        return

    placeholder = await update.message.reply_text(
        "📊 Generando informe semanal... esto puede tardar 30-60 segundos."
    )
    done = asyncio.Event()
    task = asyncio.create_task(_typing_loop(context.bot, update.effective_chat.id, done))
    try:
        loop = asyncio.get_running_loop()
        pdf_bytes = await loop.run_in_executor(None, _generate_weekly_pdf_bytes)
        done.set()
        await task
        if pdf_bytes:
            import io as _io
            from datetime import date as _dt
            fecha = _dt.today().isoformat()
            await update.message.reply_document(
                document=_io.BytesIO(pdf_bytes),
                filename=f"informe_semanal_{fecha}.pdf",
                caption=(
                    f"📊 <b>Informe Semanal</b> — Super Martínez\n"
                    f"Semana del {fecha} · Generado por Kuine · MermaOps"
                ),
                parse_mode=ParseMode.HTML,
            )
            await placeholder.delete()
        else:
            await placeholder.edit_text("❌ Error generando el informe semanal.")
    except Exception as e:
        done.set()
        await task
        await placeholder.edit_text(f"Error: {e}")


# ── Callbacks nuevos para los botones de demo y estado ───────────────────────

async def _handle_demo_callback(
    query, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    """Gestiona demo:advance:N y demo:reset desde botones."""
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "reset":
        await query.edit_message_text("♻️ Reiniciando estado...")
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: __import__(
                "backend.data.advance_demo", fromlist=["reset"]
            ).reset(STORE_ID))
            await query.edit_message_text(
                "✅ Estado reiniciado.\nUsa /estado para ver el nuevo panorama.",
            )
        except Exception as e:
            await query.edit_message_text(f"Error: {e}")
        return

    if action == "advance":
        days = float(parts[2]) if len(parts) > 2 else 1.0
        await query.edit_message_text(f"⏩ Simulando {days:.0f} día(s)...")
        done = asyncio.Event()
        task = asyncio.create_task(_typing_loop(context.bot, query.message.chat_id, done))
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: __import__(
                    "backend.data.advance_demo", fromlist=["advance"]
                ).advance(days, store_id=STORE_ID)
            )
            done.set()
            await task
            await query.edit_message_text(
                f"✅ <b>+{days:.0f} días simulados</b>\n\n"
                f"Lotes: {result.get('batches_updated', 0)} | "
                f"Acciones: {result.get('actions_created', 0)} nuevas | "
                f"Mensajes: {result.get('telegram_messages_sent', 0)}\n\n"
                "Usa /estado o /criticos para ver el impacto.",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            done.set()
            await task
            await query.edit_message_text(f"Error: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

async def _post_init(application) -> None:
    """Registra los comandos en BotFather para autocompletado en Telegram."""
    await application.bot.set_my_commands([
        BotCommand("start", "Bienvenida y vinculación de cuenta"),
        BotCommand("estado", "Estado de la tienda en tiempo real 🚦"),
        BotCommand("acciones", "Lista de acciones pendientes"),
        BotCommand("criticos", "Solo productos críticos 🔴"),
        BotCommand("ruta", "Iniciar ruta guiada por pasillos"),
        BotCommand("brief", "Brief de apertura de hoy"),
        BotCommand("scan", "Analizar producto por barcode"),
        BotCommand("agentes", "Qué hace cada agente de IA"),
        BotCommand("kuine", "Estado del orquestador Kuine"),
        BotCommand("demo", "Simular paso del tiempo (encargado)"),
        BotCommand("yo", "Tu perfil y estado de vinculación"),
        BotCommand("ayuda", "Lista completa de comandos"),
        BotCommand("merma", "Merma en euros últimos 7 días"),
        BotCommand("donaciones", "Impacto social de donaciones"),
        BotCommand("prediccion", "Previsión de merma + clima"),
        BotCommand("esg", "Métricas ESG (CO2, agua, fiscal)"),
        BotCommand("proveedores", "Ficha de proveedores con merma"),
        BotCommand("menu", "Menú interactivo completo"),
        BotCommand("logout", "Desvincular cuenta de Telegram"),
        BotCommand("informe", "Descargar brief de hoy en PDF 📄"),
        BotCommand("semana", "Descargar informe semanal en PDF 📊"),
        BotCommand("costes", "Coste de IA y ahorro por caché (encargado)"),
        BotCommand("reflexiones", "Lecciones aprendidas por Chuwi (Reflexion Loop)"),
    ])


def run() -> None:
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no está definido en .env")

    app = ApplicationBuilder().token(TOKEN).post_init(_post_init).build()

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

    # Comandos nuevos
    app.add_handler(CommandHandler("agentes", _cmd_agentes))
    app.add_handler(CommandHandler("kuine", _cmd_kuine))
    app.add_handler(CommandHandler("demo", _cmd_demo))
    app.add_handler(CommandHandler("yo", _cmd_yo))
    app.add_handler(CommandHandler("estado", _cmd_estado))
    app.add_handler(CommandHandler("criticos", _cmd_criticos))
    app.add_handler(CommandHandler("ayuda", _cmd_ayuda))
    app.add_handler(CommandHandler("logout", _cmd_logout))
    app.add_handler(CommandHandler("informe", _cmd_informe))
    app.add_handler(CommandHandler("semana", _cmd_semana))
    app.add_handler(CommandHandler("costes", _cmd_costes))
    app.add_handler(CommandHandler("reflexiones", _cmd_reflexiones))

    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("[chuwi] Agente activo. Esperando mensajes en Telegram...")
    app.run_polling(drop_pending_updates=True)
