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
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

from backend.core import llm, database, memory as _mem
from backend.core import telegram_formatter as _fmt
from backend.agents import supervisor
from backend.core.chuwi_persistence import (
    STORE_ID, MAX_HISTORY,
    _conv_state, _conv_id_cache, _session_cache,
    _user_last_msg, _RATE_LIMIT_SECONDS, _CACHE_TTL_SECONDS,
    _user_cache, _USER_CACHE_TTL,
    _cleanup_stale_caches,
    _history_db_key, _load_history_db, _save_history_db,
    _load_history, _save_history, _get_chat_history,
    _persist_chat_history, _compact_history,
    _get_user, _invalidate_user_cache, _is_manager,
    _get_conv_state, _set_conv_state, _clear_conv_state,
    _upsert_telegram_user, _persist_conversation_message,
)
from backend.core.chuwi_intent import (
    _classify_intent, _build_intent_context, _INTENT_PATTERNS, detect_proactive_trigger
)
from backend.core.chuwi_tools import (
    CHUWI_TOOLS, _TOOL_LABELS, _TOOL_CACHE, _CACHEABLE_TOOLS, _TOOL_CACHE_TTL,
    _tool_cache_key, _execute_tool_sync,
    MAX_AGENT_ITERATIONS, _COMPLEX_KEYWORDS, _is_complex_query,
)
# Re-exportar para compatibilidad con tests e imports externos
from backend.core.chuwi_commands import (  # noqa: E402
    _cmd_agentes, _cmd_kuine, _cmd_demo, _cmd_yo, _cmd_estado,
    _cmd_criticos, _cmd_ayuda, _cmd_costes, _cmd_reflexiones,
    _cmd_informe, _cmd_semana, _handle_demo_callback, _AGENTES_TEXT,
)

load_dotenv()

logger = logging.getLogger("mermaops.chuwi")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


def _safe_err(e: Exception) -> str:
    """Convierte una excepción en mensaje amigable para el usuario. Nunca expone internos."""
    msg = str(e).lower()
    if any(x in msg for x in ["connection", "connect", "network", "unreachable", "refused"]):
        return "No hay conexión con el servidor. Inténtalo de nuevo en unos segundos."
    if any(x in msg for x in ["timeout", "timed out", "time out"]):
        return "La operación tardó demasiado. Inténtalo de nuevo."
    if any(x in msg for x in ["unauthorized", "403", "401", "jwt", "token"]):
        return "No tienes permisos para esta operación."
    if any(x in msg for x in ["not found", "404", "no data"]):
        return "No se encontraron datos. Puede que el sistema no tenga información aún."
    if any(x in msg for x in ["rate limit", "429", "too many"]):
        return "Demasiadas peticiones. Espera un momento e inténtalo de nuevo."
    return "Error interno. Inténtalo de nuevo. Si continúa, contacta al administrador."

# ── Streak counter ───────────────────────────────────────────────────────────
# telegram_user_id (str) -> {"count": int, "date": str}
_streak: dict[str, dict] = {}


def _update_streak(tg_user_id: str) -> int:
    """Increments and returns today's action completion streak for this user."""
    today = date.today().isoformat()
    entry = _streak.get(str(tg_user_id), {})
    if entry.get("date") != today:
        entry = {"count": 0, "date": today}
    entry["count"] += 1
    _streak[str(tg_user_id)] = entry
    return entry["count"]


def _streak_text(count: int) -> str:
    if count < 2:
        return ""
    if count >= 10:
        return f"\n\n🔥🔥 <b>{count} acciones completadas</b> hoy — ¡máquina!"
    if count >= 5:
        return f"\n\n🔥 <b>Racha de {count}</b> — sigue así"
    return f"\n\n✨ <b>{count} completadas</b> hoy"


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

CHUWI_SYSTEM = """Eres Chuwi, el agente operativo del Super Martínez.
Hablas como un compañero de turno que te escribe por WhatsApp, no como un manual de instrucciones.

CÓMO HABLAS:
- Frases cortas. Máximo 2-3 líneas por idea.
- Guiones simples para listas. MAYÚSCULAS para lo urgente. Sin asteriscos, sin negritas, sin tablas.
- Jerga de supermercado español: frescos, lineal, cabecera de góndola, flejes, picar merma, rotura de stock, caja dañada, reposición FEFO, pasillo frío.
- Nunca digas "Ejecutando herramienta X" ni "Llamando a Kuine". La orquestación es tuya, interna. El empleado solo ve la conclusión.

TONO SEGÚN LA HORA DEL DÍA (adapta automáticamente):
- 7:00-9:00 apertura: máxima brevedad. Solo críticos. "Tienes 3 urgentes. Empieza por lácteos pasillo A2."
- 9:00-18:00 turno normal: explica el porqué. Ofrece alternativas.
- 18:00-20:00 cierre: enfocado en cerrar acciones, donar lo que quede, picar merma.
- Fuera de horario: responde pero avisa que la tienda está cerrada.

VOCABULARIO DE ACCIONES (usa siempre estos términos, no los técnicos):
- rebajar → "ponle el fleje amarillo de descuento"
- retirar → "retira del lineal y pica merma"
- donar → "prepáralo para la donación de Cáritas/Banco de Alimentos"
- mover → "baja del almacén y colócalo en el lineal, FEFO"
- revisar → "dale un vistazo y confirma si está bien"

CUANDO HAY MUCHO VOLUMEN (>30 unidades):
- Avisa al encargado del tiempo estimado: "Son 50 yogures — unos 12 minutos con la pistola de precios."
- Sugiere organizarse: "Si tenéis dos personas, uno pone flejes y otro repone."

ERES UN AGENTE CON DATOS REALES:
- Usa las herramientas para responder con hechos, no suposiciones.
- Si preguntan por el estado, llama get_store_overview SIEMPRE.
- Si preguntan qué hacer, llama get_pending_actions Y get_daily_route.
- Si mencionan un código o barcode, llama analyze_product.
- Si hay CRÍTICOS sin resolver, menciónalos primero aunque no te pregunten.

NORMATIVA (explica en lenguaje cotidiano, no técnico):
- Producto caducado que no se puede vender: "Ojo, caducó ayer. Por ley no podemos venderlo ni rebajarlo. Retíralo del lineal y regístralo para donación antes de que acabe el turno."
- Producto con desperfecto físico: "El envase está dañado. No lo pongas en el lineal — o lo donas si el producto está bien, o lo retiras si hay riesgo."

REGLAS:
- Nunca inventes datos. Si no tienes, consulta primero.
- Si el empleado no está registrado, explica cómo vincularse con /start.
- Las fotos: analízalas automáticamente con visión sin que te lo pidan."""


# ── Formato HTML para Telegram ────────────────────────────────────────────────

def _md_to_html(text: str) -> str:
    # Eliminar etiquetas HTML que Claude genere literalmente (antes de escape).
    # Claude a veces emite <b>, </b>, <i>, </i> aunque se le diga que no.
    # Si no las limpiamos, html.escape las convierte en &lt;b&gt; que Telegram
    # muestra como texto literal <b>, que es exactamente el bug.
    text = re.sub(r"</?(?:b|i|u|s|code|pre|em|strong)>", "", text)
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


def _format_brief_html(text: str) -> str:
    """Convierte el brief de texto plano de Kuine a HTML visual para Telegram.

    Estructura de salida:
      ┌─ CABECERA FIJA (fecha + semáforo) ──┐
      │  siempre presente, independiente del LLM
      └──────────────────────────────────────┘
      📊 ANÁLISIS (texto del LLM procesado)
      ⚡ ACCIONES (líneas numeradas con iconos de urgencia)
      🗺 RUTA (si la hay)
    """
    import re as _re
    import html as _html
    from datetime import date as _d

    _t = _d.today()
    today = f"{_t.day} de {_t.strftime('%B')} de {_t.year}"
    # Cabecera fija — siempre va arriba, independiente del contenido del LLM
    header = (
        f"┌{'━' * 36}┐\n"
        f"│  📋  <b>BRIEF DE APERTURA — MermaOps</b>\n"
        f"│  📅  <i>{today}</i>\n"
        f"│  🏪  <i>Super Martínez</i>\n"
        f"└{'━' * 36}┘"
    )

    section_icons = {
        "SITUACIÓN": "📊", "SITUACION": "📊",
        "ACCIONES": "⚡", "ACCION": "⚡",
        "RUTA": "🗺",
        "COMPARATIVA": "📈", "BENCHMARK": "📈",
        "VALOR": "💶",
        "SEGUIMIENTO": "📋",
        "PATRÓN": "🧠", "PATRON": "🧠",
        "PREDICCIÓN": "🔮", "PREDICCION": "🔮",
        "RESUMEN": "📌",
        "CIERRE": "🌆",
    }

    lines = text.split("\n")
    out = []
    in_actions = False
    skip_header = True  # salta el encabezado que genera el LLM (lo reemplazamos con el nuestro)

    for line in lines:
        stripped = line.strip()

        # Omitir separadores y el encabezado que genera el LLM
        if stripped.startswith("═") or stripped.startswith("─") or stripped.startswith("━"):
            continue
        if skip_header and ("BRIEF DE APERTURA" in stripped or "BRIEFING" in stripped
                            or "Super Martínez" in stripped or "MermaOps" in stripped
                            or "MERMAOPS" in stripped):
            continue  # el LLM ya generó su cabecera, la ignoramos

        # A partir de la primera sección real, dejamos de saltar
        if skip_header and stripped and stripped == stripped.upper() and len(stripped.split()) >= 2:
            skip_header = False

        # Headers de sección ALL CAPS
        words = stripped.split()
        is_section = (
            stripped and stripped == stripped.upper()
            and 2 <= len(words) <= 8
            and not stripped[0:1].isdigit()
            and not stripped.startswith("•")
        )
        if is_section:
            icon = next((v for k, v in section_icons.items() if k in stripped), "▸")
            in_actions = "ACCION" in stripped or "ACCIÓN" in stripped.upper()
            out.append(f"\n{icon} <b>{_html.escape(stripped)}</b>\n{'─' * 28}")
            continue

        # Líneas de acción numerada: "1. PRODUCTO — CRÍTICO (score) ..."
        action_match = _re.match(r'^(\d+)[.)]\s+(.+?)(?:\s+[—\-–]\s+)(.+)$', stripped)
        if action_match:
            pname = action_match.group(2).strip()
            rest = action_match.group(3).strip()
            urgency = "🔴" if any(w in rest.upper() for w in ("CRÍTICO", "CRITICO")) else \
                      "🟡" if any(w in rest.upper() for w in ("ALTO", "HIGH")) else "🟢"
            out.append(f"\n{urgency} <b>{_html.escape(pname)}</b>")
            out.append(f"   <i>{_html.escape(rest)}</i>")
            in_actions = True
            continue

        # Líneas con bullet •
        if stripped.startswith("•") or stripped.startswith("-"):
            content = stripped.lstrip("•- ").strip()
            urgency = "🔴" if "CRÍTICO" in content.upper() or "CRITICO" in content.upper() else \
                      "🟡" if "ALTO" in content.upper() else ""
            prefix = f"{urgency} " if urgency else "  • "
            out.append(f"{prefix}<b>{_html.escape(content[:50])}</b>" if urgency
                       else f"  • {_html.escape(content)}")
            continue

        # Sub-líneas con sangría
        if line.startswith("   ") and stripped:
            out.append(f"   {_html.escape(stripped)}")
            continue

        # Ruta con →
        if "→" in stripped:
            out.append(f"   🗺 {_html.escape(stripped)}")
            continue

        # Línea vacía
        if not stripped:
            if out and out[-1] != "":
                out.append("")
            continue

        # Texto normal
        out.append(_html.escape(stripped))

    body = "\n".join(out).strip()
    return f"{header}\n\n{body}" if body else header


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
        [
            InlineKeyboardButton("🗺 Mapa supermercado", callback_data="cmd:mapa"),
            InlineKeyboardButton("📋 Historial", callback_data="cmd:historial"),
        ],
        [
            InlineKeyboardButton("📊 Proyección 7 días", callback_data="cmd:merma7"),
            InlineKeyboardButton("🌤 Tiempo tienda", callback_data="cmd:tiempo"),
        ],
        [
            InlineKeyboardButton("📦 Almacén", callback_data="cmd:almacen"),
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
            InlineKeyboardButton("✨ Insights IA", callback_data="cmd:insights"),
            InlineKeyboardButton("🌤 Tiempo tienda", callback_data="cmd:tiempo"),
        ])
        rows.append([
            InlineKeyboardButton("📊 Comparativa tiendas", callback_data="cmd:comparativa"),
            InlineKeyboardButton("⚙️ Perfil tienda", callback_data="cmd:perfil"),
        ])
        rows.append([
            InlineKeyboardButton("⚙️ Generar brief ahora", callback_data="cmd:runbrief"),
            InlineKeyboardButton("🖥 Estado sistema", callback_data="cmd:sistema"),
        ])
        rows.append([
            InlineKeyboardButton("📖 Normativa citada", callback_data="cmd:citar"),
        ])
        rows.append([
            InlineKeyboardButton("📄 Brief en PDF", callback_data="cmd:brief_pdf"),
            InlineKeyboardButton("📊 Informe semanal PDF", callback_data="cmd:semana_pdf"),
        ])
    rows.append([
        InlineKeyboardButton("🖥 Estado sistema", callback_data="cmd:sistema"),
        InlineKeyboardButton("🧪 Simular 7:30", callback_data="cmd:simular"),
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


def _extract_product_info(product: dict, notes: str) -> tuple[str, str, str, str]:
    """(name, pasillo, estanteria, nivel) desde product dict o fallback a notas."""
    name = (product.get("name") or "").strip()
    pasillo = str(product.get("pasillo") or "")
    estanteria = str(product.get("estanteria") or "")
    nivel = str(product.get("nivel") or "")

    if not name and notes:
        stripped = re.sub(r'^(CR[IÍ]TICO|URGENTE|ALTO|MEDIO|BAJO)\.\s*', '', notes, flags=re.IGNORECASE)
        m = re.match(r'^(.+?)\s*\(', stripped)
        if m:
            name = m.group(1).strip()

    if not pasillo and notes:
        m1 = re.search(r'[Pp]asillo\s+(\w+)-E(\w+)-N(\w+)', notes)
        m2 = re.search(r'\(\s*pasillo\s+(\w+),\s*est\.?\s*(\w+),\s*nivel\s*(\w+)', notes, re.IGNORECASE)
        loc = m1 or m2
        if loc:
            pasillo, estanteria, nivel = loc.group(1), loc.group(2), loc.group(3)

    return name or "Producto", pasillo or "?", estanteria or "?", nivel or "?"


def _format_action_card(action: dict, index: int = 0, total: int = 0) -> str:
    """Tarjeta rica por producto: ubicación, urgencia, precio, razonamiento, qué hacer."""
    batch = action.get("batches") or {}
    product = (batch.get("products") or {}) if batch else {}
    notes = action.get("notes", "")
    name, pasillo, estanteria, nivel = _extract_product_info(product, notes)
    atype = action.get("action_type", "revisar")
    score = action.get("priority_score", 0)
    notes = action.get("notes", "")
    new_price = action.get("new_price")
    price_adj = action.get("price_adjustment_pct")
    expiry = batch.get("expiry_date", "")
    current_price = float(product.get("price") or 0)
    cost = float(product.get("cost") or 0)
    qty = int(batch.get("quantity") or 0)

    urgency_icon = "🔴" if score >= 85 else "🟡" if score >= 65 else "🟢"
    action_label = {
        "rebajar": "💰 REBAJAR PRECIO",
        "donar":   "❤️  DONAR",
        "retirar": "🗑 RETIRAR",
        "revisar": "🔍 REVISAR",
        "mover":   "📦 MOVER A TIENDA",
    }.get(atype, atype.upper())

    header = f"{urgency_icon} <b>{name}</b>"
    if index and total:
        header = f"Acción {index}/{total} · {header}"

    lines = [
        header,
        f"📍 Pasillo {pasillo} · Est. {estanteria} · Nivel {nivel}",
        "",
        f"<b>Acción recomendada:</b> {action_label}",
    ]

    if expiry:
        try:
            days = (date.fromisoformat(expiry) - date.today()).days
            if days < 0:
                lines.append(f"⛔ <b>CADUCADO hace {abs(days)} día(s)</b> — {expiry}")
            elif days == 0:
                lines.append(f"⚠️ <b>Caduca HOY</b> — {expiry}")
            elif days == 1:
                lines.append(f"⏰ Caduca <b>mañana</b> — {expiry}")
            else:
                lines.append(f"📅 Caduca en <b>{days} días</b> — {expiry}")
        except Exception:
            lines.append(f"📅 Caduca: {expiry}")

    if qty:
        lines.append(f"📦 Unidades en tienda: <b>{qty}</b>")

    lines.append("")

    # Compute new_price from discount % if not explicitly set
    if atype == "rebajar" and not new_price and price_adj and current_price:
        new_price = round(current_price * (1 - abs(int(price_adj)) / 100), 2)
    if atype == "rebajar" and new_price and current_price:
        recuperacion = round(new_price * qty, 2)
        pct = abs(int(price_adj)) if price_adj else int((1 - new_price / current_price) * 100)
        lines += [
            f"💶 Precio actual: {current_price:.2f}€",
            f"💰 <b>Nuevo precio: {new_price:.2f}€  (−{abs(pct)}%)</b>",
            f"✓ Coste unitario: {cost:.2f}€ — sigues en positivo",
            f"✓ Si vendes todo: recuperas <b>{recuperacion:.2f}€</b>",
            f"   (vs perder {round(qty * cost, 2):.2f}€ si no haces nada)",
        ]
    elif atype == "donar":
        coste_total = round(qty * cost, 2)
        deduccion = round(coste_total * 0.35, 2)
        lines += [
            f"❤️  Donación: {qty} unidades",
            f"💶 Valor a coste: {coste_total:.2f}€",
            f"🏛 Deducción fiscal 35% (Ley 49/2002): <b>{deduccion:.2f}€</b>",
            "   Mejor que tirarlo: impacto social + ahorro fiscal",
        ]
    elif atype == "retirar":
        coste_total = round(qty * cost, 2)
        lines += [
            f"🗑 Unidades a retirar: {qty}",
            f"💸 Pérdida inevitable: {coste_total:.2f}€ a coste",
            "⚠️  Normativa sanitaria: prohibido vender o donar producto caducado",
            "   Registrar en albarán de merma + contenedor residuos orgánicos",
        ]
    elif atype == "mover":
        lines += [
            "📦 Trasladar del almacén a la estantería de tienda",
            "   Reponer el lineal para que sea visible al cliente",
        ]

    if notes and atype not in ("rebajar", "donar", "retirar", "mover"):
        lines += ["", f"<i>{notes[:180]}</i>"]

    return "\n".join(lines)


def _action_card_keyboard(action: dict, remaining: int = 0) -> InlineKeyboardMarkup:
    """Botones específicos por tipo de acción. El empleado decide con un toque."""
    action_id = action.get("id", "")
    atype = action.get("action_type", "revisar")
    new_price = action.get("new_price")
    rows = []

    if atype == "rebajar":
        # Compute display price from discount % if new_price not stored
        if not new_price:
            _orig = float((action.get("batches") or {}).get("products", {}).get("price") or 0) if action.get("batches") else 0
            _pct = abs(int(action.get("price_adjustment_pct") or 0))
            if _orig and _pct:
                new_price = round(_orig * (1 - _pct / 100), 2)
        price_label = f"✅ Confirmar {new_price:.2f}€ (−{abs(int(action.get('price_adjustment_pct') or 0))}%)" if new_price else "✅ Confirmar rebaja"
        rows.append([
            InlineKeyboardButton(price_label, callback_data=f"action_confirm:{action_id}"),
            InlineKeyboardButton("❤️ Donar en vez", callback_data=f"action_donate:{action_id}"),
        ])
    elif atype == "donar":
        rows.append([
            InlineKeyboardButton("❤️ Banco Alimentos", callback_data=f"action_donate_entity:{action_id}:banco_alimentos"),
            InlineKeyboardButton("🕊 Cáritas", callback_data=f"action_donate_entity:{action_id}:caritas"),
        ])
        rows.append([
            InlineKeyboardButton("💰 Rebajar en vez", callback_data=f"action_rebajar_instead:{action_id}"),
        ])
    elif atype == "retirar":
        rows.append([
            InlineKeyboardButton("🗑 Confirmar retirada", callback_data=f"action_confirm:{action_id}"),
            InlineKeyboardButton("❤️ Donar si válido", callback_data=f"action_donate:{action_id}"),
        ])
    elif atype == "mover":
        rows.append([
            InlineKeyboardButton("✅ Ya está en tienda", callback_data=f"action_confirm:{action_id}"),
        ])
    else:  # revisar
        rows.append([
            InlineKeyboardButton("✅ Revisado, todo OK", callback_data=f"action_confirm:{action_id}"),
            InlineKeyboardButton("🔴 Necesita acción", callback_data=f"action_escalate:{action_id}"),
        ])

    nav = []
    if remaining > 0:
        nav.append(InlineKeyboardButton(f"⏭ Siguiente ({remaining} más)", callback_data="cmd:acciones"))
    nav.append(InlineKeyboardButton("📋 Ver todas", callback_data="cmd:acciones"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")])
    return InlineKeyboardMarkup(rows)


# ── Herramientas, cache y agent loop — ver chuwi_tools.py ────────────────────
# CHUWI_TOOLS, _TOOL_LABELS, _execute_tool_sync, MAX_AGENT_ITERATIONS, etc.
# importados arriba desde backend.core.chuwi_tools


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
    ev_loop = asyncio.get_running_loop()
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
            # Cache: tools de lectura se guardan 5 min para reutilizar en siguientes mensajes
            async def _exec_one(tc: dict) -> dict:
                try:
                    t_input = json.loads(tc["input"]) if tc["input"].strip() else {}
                except Exception:
                    t_input = {}
                res = await ev_loop.run_in_executor(
                    None, _execute_tool_sync, tc["name"], t_input, user
                )
                if tc["name"] in _CACHEABLE_TOOLS and "error" not in res:
                    cache_key = _tool_cache_key(tc["name"], t_input)
                    _TOOL_CACHE[cache_key] = (res, time.monotonic())
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


# ── Respuesta de bienvenida ───────────────────────────────────────────────────

def _get_store_quick_stats() -> dict:
    """Estadísticas rápidas de la tienda para el mensaje de bienvenida."""
    try:
        actions = database.get_pending_actions(STORE_ID)
        critical = [a for a in actions if (a.get("priority_score") or 0) >= 85]
        high = [a for a in actions if 65 <= (a.get("priority_score") or 0) < 85]

        critical_products = []
        for a in critical[:3]:
            batch = a.get("batches") or {}
            prod = (batch.get("products") or {}) if batch else {}
            name = prod.get("name", "Producto")
            expiry = (batch.get("expiry_date") or "")
            try:
                days = (date.fromisoformat(expiry) - date.today()).days
                days_txt = "HOY" if days == 0 else ("mañana" if days == 1 else f"en {days}d")
            except Exception:
                days_txt = expiry
            critical_products.append({"name": name, "days": days_txt, "id": str(a.get("id", ""))})

        first_action_id = critical[0].get("id", "") if critical else (actions[0].get("id", "") if actions else "")
        return {
            "pending": len(actions),
            "critical": len(critical),
            "high": len(high),
            "critical_products": critical_products,
            "first_action_id": str(first_action_id),
        }
    except Exception:
        return {"pending": 0, "critical": 0, "high": 0, "critical_products": [], "first_action_id": ""}


def _welcome_text(name: str, is_manager: bool, stats: dict | None = None) -> str:
    pending = (stats or {}).get("pending", 0)
    critical = (stats or {}).get("critical", 0)
    high = (stats or {}).get("high", 0)
    critical_products = (stats or {}).get("critical_products", [])

    # Saludo según la hora del día
    _hour = datetime.now().hour
    if 5 <= _hour < 12:
        greeting_prefix = "Buenos días"
    elif 12 <= _hour < 20:
        greeting_prefix = "Buenas tardes"
    else:
        greeting_prefix = "Buenas noches"

    if critical >= 3:
        status_icon = "🔴"
        status_text = f"<b>ALERTA — {critical} productos CRÍTICOS sin resolver</b>"
    elif critical >= 1:
        status_icon = "🟡"
        status_text = (
            f"<b>{critical} crítico{'s' if critical > 1 else ''}</b>"
            f" · {high} alto{'s' if high != 1 else ''}"
            f" · {pending} pendientes"
        )
    elif pending > 0:
        status_icon = "🟢"
        status_text = f"{pending} acciones pendientes · sin críticos"
    else:
        status_icon = "✅"
        status_text = "Sin alertas. La tienda está en orden."

    # Lista de productos críticos
    critical_list = ""
    if critical_products:
        lines = []
        for cp in critical_products:
            lines.append(f"  🔴 <b>{html.escape(cp['name'])}</b> — caduca {cp['days']}")
        critical_list = "\n" + "\n".join(lines) + "\n"

    if is_manager:
        role_line = "🔑 <b>ENCARGADO</b> — acceso completo al sistema"
        menu_hint = (
            "📋 Brief  ·  ⚡ Acciones  ·  🗺 Ruta\n"
            "📦 Proveedores  ·  🛒 Pedido  ·  🌱 ESG\n"
            "🔮 Predicciones  ·  📄 PDF  ·  ⚙️ Generar brief"
        )
    else:
        role_line = "👷 <b>EMPLEADO</b> — operaciones del día"
        menu_hint = (
            "⚡ Acciones  ·  🗺 Ruta del día\n"
            "✅ Completar tarea  ·  ❤️ Donaciones\n"
            "🔍 Escanear  ·  📊 Merma"
        )

    return (
        f"{greeting_prefix}, <b>{html.escape(name)}</b> 👋\n\n"
        f"{status_icon}  {status_text}"
        f"{critical_list}\n"
        f"{role_line}\n\n"
        f"{menu_hint}\n\n"
        f"Escríbeme en lenguaje natural o usa el menú de abajo."
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
    loop = asyncio.get_running_loop()
    actions = await loop.run_in_executor(None, _get_route_actions)

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
    total = len(actions)
    header = f"🗺 <b>MODO RUTA — {total} acciones pendientes</b>\n\n"
    card = _format_action_card(first, index=1, total=total)
    keyboard = _action_card_keyboard(first, remaining=total - 1)
    await update.message.reply_text(header + card, parse_mode=ParseMode.HTML, reply_markup=keyboard)


# ── Completar acción desde Telegram ──────────────────────────────────────────

async def _handle_action_complete(update: Update, context: ContextTypes.DEFAULT_TYPE, user: Optional[dict]) -> None:
    """
    El empleado dice 'listo' o 'hecho'.
    Muestra las acciones pendientes para que confirme cuál fue.
    """
    try:
        loop = asyncio.get_running_loop()
        pending = await loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
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
            "Error cargando acciones. Inténtalo de nuevo.",
            reply_markup=_back_keyboard()
        )


# ── Acciones del menú ─────────────────────────────────────────────────────────

async def _action_brief(update_or_query, context, user: Optional[dict], is_callback=False):
    loop = asyncio.get_running_loop()
    brief = await loop.run_in_executor(None, database.get_latest_brief, STORE_ID)
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
        pending = await loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
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
        if brief:
            # Edit menu message with compact card (always <4096 chars)
            card = _fmt.format_brief_card(
                brief_date=brief.get("date", ""),
                value_at_risk=float(brief.get("value_at_risk", 0.0) or 0.0),
                actions_count=brief.get("actions_count", 0),
                critical_count=critical_count,
                high_count=high_count,
            )
            await update_or_query.edit_message_text(
                card, parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
            # Send full summary as new message(s) if there is one
            summary = brief.get("summary", "")
            if summary:
                full_text = "📋 <b>Análisis Kuine — completo</b>\n\n" + _fmt._e(summary)
                chunks = [full_text[i:i+4096] for i in range(0, len(full_text), 4096)]
                for chunk in chunks:
                    await update_or_query.message.reply_text(chunk, parse_mode=ParseMode.HTML)
        else:
            await update_or_query.edit_message_text(
                text, parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
    else:
        chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
        for i, chunk in enumerate(chunks):
            await update_or_query.message.reply_text(
                chunk,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard if i == len(chunks) - 1 else None,
            )


async def _action_acciones(update_or_query, context, user: Optional[dict], is_callback=False):
    loop = asyncio.get_running_loop()
    pending = await loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
    text = _fmt.format_actions(pending)

    if not pending:
        keyboard = _back_keyboard()
    else:
        rows = []
        # Botón directo a tarjeta de detalle para cada acción (máx 5)
        _ICON = {"rebajar": "💰", "donar": "❤️", "retirar": "🗑", "revisar": "🔍", "mover": "📦"}
        for a in pending[:5]:
            batch = a.get("batches") or {}
            product = (batch.get("products") or {}) if batch else {}
            name, *_ = _extract_product_info(product, a.get("notes", ""))
            name = name[:22]
            icon = _ICON.get(a.get("action_type", ""), "⚡")
            score = a.get("priority_score", 0)
            urgency = "🔴" if score >= 85 else "🟡" if score >= 65 else "🟢"
            rows.append([InlineKeyboardButton(
                f"{urgency}{icon} {name}",
                callback_data=f"action_detail:{a['id']}"
            )])
        rows.append([
            InlineKeyboardButton("🗺 Modo ruta", callback_data="cmd:iniciar_ruta"),
            InlineKeyboardButton("↩ Menú", callback_data="cmd:menu"),
        ])
        keyboard = InlineKeyboardMarkup(rows)

    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_ruta(update_or_query, context, user: Optional[dict], is_callback=False):
    loop = asyncio.get_running_loop()

    def _sync():
        from backend.agents import route as rt
        # Usa los scores ya calculados en BD — sin llamar al evaluador (sin LLM)
        pending = database.get_pending_actions(STORE_ID)
        if not pending:
            return "Sin acciones pendientes para la ruta de hoy. ✅"
        risk_reports = []
        for action in pending:
            batch = action.get("batches") or {}
            score = action.get("priority_score", 0)
            risk_level = (
                "CRÍTICO" if score >= 85 else
                "ALTO" if score >= 65 else
                "MEDIO" if score >= 40 else "BAJO"
            )
            risk = {
                "score": score,
                "risk_level": risk_level,
                "action": action.get("action_type", "revisar"),
                "reasoning": action.get("notes") or "",
                "price_adjustment_pct": action.get("price_adjustment_pct") or 0,
            }
            risk_reports.append((batch, risk))
        daily_route = rt.generate(STORE_ID, risk_reports)
        return rt.format_route_html(daily_route)

    try:
        response = await loop.run_in_executor(None, _sync)
    except Exception as _re:
        import logging as _rl
        _rl.getLogger("mermaops.chuwi").warning(f"[ruta] error: {_re}", exc_info=True)
        response = f"❌ Error generando la ruta: {str(_re)[:120]}\n\nInténtalo de nuevo."

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Iniciar modo ruta guiada", callback_data="cmd:iniciar_ruta")],
        [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
    ])

    if is_callback:
        await update_or_query.edit_message_text(
            response, parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await update_or_query.message.reply_text(
            response, parse_mode=ParseMode.HTML, reply_markup=keyboard
        )


async def _action_stats(update_or_query, context, user: Optional[dict], is_callback=False):
    """Dashboard KPIs en Telegram — resumen ejecutivo de la tienda en un mensaje."""
    try:
        loop = asyncio.get_running_loop()
        pending, batches, merma_7d, donations, brief = await asyncio.gather(
            loop.run_in_executor(None, database.get_pending_actions, STORE_ID),
            loop.run_in_executor(None, database.get_batches_expiring_soon, STORE_ID, 7),
            loop.run_in_executor(None, database.get_merma_history, STORE_ID, 7),
            loop.run_in_executor(None, database.get_donation_stats, STORE_ID, 30),
            loop.run_in_executor(None, database.get_latest_brief, STORE_ID),
        )

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
        text = "❌ Error obteniendo datos. Inténtalo de nuevo."

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
        loop = asyncio.get_running_loop()
        logs = await loop.run_in_executor(None, database.get_merma_history, STORE_ID, 7)
        text = _fmt.format_merma(logs, days=7)
    except Exception as e:
        text = "❌ Error obteniendo merma. Inténtalo de nuevo."

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")]])
    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_donaciones(update_or_query, context, user: Optional[dict], is_callback=False):
    try:
        loop = asyncio.get_running_loop()
        stats = await loop.run_in_executor(None, database.get_donation_stats, STORE_ID, 30)
        text = _fmt.format_donaciones(stats)
    except Exception as e:
        text = "❌ Error obteniendo donaciones. Inténtalo de nuevo."

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
        loop = asyncio.get_running_loop()
        stats = await loop.run_in_executor(None, database.get_supplier_stats, STORE_ID)
        text = _fmt.format_proveedores(stats)
    except Exception as e:
        text = "❌ Error obteniendo proveedores. Inténtalo de nuevo."

    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_pedido(update_or_query, context, user: Optional[dict], is_callback=False):
    if not _is_manager(user):
        text = "🔒 La sugerencia de pedido es solo para encargados."
        kb = _back_keyboard()
        if is_callback:
            await update_or_query.edit_message_text(text, reply_markup=kb)
        else:
            await _send(update_or_query, text, reply_markup=kb)
        return

    # Show thinking indicator
    if is_callback:
        await update_or_query.edit_message_text("🛒 Analizando stock y merma histórica...")
    else:
        await _send(update_or_query, "🛒 Analizando stock y merma histórica...")

    try:
        loop = asyncio.get_running_loop()
        suggestions = await loop.run_in_executor(None, database.get_order_suggestions, STORE_ID)

        # Enrich with merma history per product
        try:
            merma_history = await loop.run_in_executor(None, database.get_merma_history, STORE_ID, 30)
            # Build merma map: product_id -> total lost
            merma_map: dict[str, float] = {}
            for log in merma_history:
                pid = str(log.get("product_id") or log.get("batch_id") or "")
                if pid:
                    merma_map[pid] = merma_map.get(pid, 0) + float(log.get("value_lost") or 0)
        except Exception:
            merma_map = {}

        # Format AI-enhanced order suggestions
        lines = [
            "🛒 <b>Pedido semanal — análisis IA</b>",
            f"<i>Basado en {len(suggestions)} productos · merma últimos 30d</i>",
            "",
        ]

        if not suggestions:
            lines.append("Sin sugerencias de pedido para esta semana.")
        else:
            for s in suggestions[:12]:
                pid = str(s.get("product_id", ""))
                name = (s.get("product_name") or s.get("name") or "Producto")[:28]
                current = s.get("current_stock", s.get("quantity", 0))
                suggested = s.get("suggested_quantity", s.get("reorder_qty", 20))
                supplier = (s.get("supplier_name") or s.get("supplier") or "")[:16]
                merma_val = merma_map.get(pid, 0)

                # Risk indicator based on merma history
                risk = "🔴" if merma_val > 20 else "🟡" if merma_val > 5 else "🟢"
                merma_note = f" · merma {merma_val:.0f}€/mes" if merma_val > 0 else ""
                supplier_note = f" · {supplier}" if supplier else ""

                lines.append(f"{risk} <b>{name}</b>")
                lines.append(f"   Stock: {current} uds → pedir <b>{suggested}</b>{supplier_note}{merma_note}")
                lines.append("")

        # AI recommendation note
        high_merma = [(s, merma_map.get(str(s.get("product_id", "")), 0)) for s in suggestions]
        high_merma.sort(key=lambda x: -x[1])
        if high_merma and high_merma[0][1] > 10:
            worst = high_merma[0][0]
            worst_name = (worst.get("product_name") or worst.get("name") or "")[:20]
            lines += [
                f"⚠️ <b>Atención:</b> {worst_name} tiene alta merma histórica.",
                "Considera pedir menos cantidad y con más frecuencia.",
                "",
            ]

        text = "\n".join(lines)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Exportar PDF", callback_data="cmd:semana"),
             InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
        ])

    except Exception as e:
        logger.error(f"[pedido] Error: {e}", exc_info=True)
        text = "❌ Error calculando pedido. Inténtalo de nuevo."
        kb = _back_keyboard()

    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        # Send as new message (the previous "analizando..." was already sent)
        await _send(update_or_query, text, reply_markup=kb)


async def _action_runbrief(update_or_query, context, user: Optional[dict], is_callback=False):
    # Si ya hay brief de hoy, mostrarlo directamente — sin confirmación
    loop = asyncio.get_running_loop()
    existing = await loop.run_in_executor(None, database.get_latest_brief, STORE_ID)
    if existing:
        from datetime import date as _date
        if str(existing.get("date", "")) == str(_date.today()):
            summary = existing.get("summary", "Sin resumen disponible.")
            text = f"📋 <b>Brief del día</b> ({existing.get('date','')})\n\n{summary[:3000]}"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Regenerar ahora", callback_data="confirm:runbrief"),
                 InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
            ])
            if is_callback:
                await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            else:
                await _send(update_or_query, text, reply_markup=kb)
            return

    # No hay brief de hoy — ofrecer generarlo (cualquier usuario)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Generar brief ahora (~60s)", callback_data="confirm:runbrief")],
        [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
    ])
    text = (
        "📋 <b>Sin brief para hoy todavía</b>\n\n"
        "Se genera automáticamente a las <b>07:30</b> cada día.\n"
        "Puedes generarlo ahora — tarda ~60s y te llega aquí cuando esté listo.\n"
        "Puedes seguir usando Chuwi mientras tanto."
    )
    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await _send(update_or_query, text, reply_markup=kb)


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
        [InlineKeyboardButton("🧠 Ver los 12 agentes de IA", callback_data="cmd:tour_agentes")],
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
        "- 12 agentes especializados coordinados por Kuine\n"
        "- IA con extended thinking para productos críticos\n"
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
        "1. KUINE — el cerebro. Loop agéntico con 16 herramientas. "
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
        loop = asyncio.get_running_loop()
        pending = await loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
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
            name, *_ = _extract_product_info(product, action.get("notes", ""))
            name = name[:22]
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
        text = _safe_err(e)
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
                        "donated_at": datetime.now(timezone.utc).isoformat(),
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
        loop = asyncio.get_running_loop()
        actions = await loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
        donar_actions = [a for a in actions if a.get("action_type") in ("donar", "rebajar", "retirar")]
    except Exception as e:
        text = "Error obteniendo acciones. Inténtalo de nuevo."
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
        text = "Error obteniendo datos ESG. Inténtalo de nuevo."

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
        text = "Error calculando predicciones. Inténtalo de nuevo."

    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


# ── WMO code → (emoji, label) ─────────────────────────────────────────────────
_WMO: dict[int, tuple[str, str]] = {
    0: ("☀️", "Despejado"), 1: ("🌤", "Poco nuboso"), 2: ("⛅", "Parcialmente nublado"),
    3: ("☁️", "Nublado"), 45: ("🌫", "Niebla"), 48: ("🌫", "Niebla helada"),
    51: ("🌦", "Llovizna"), 53: ("🌦", "Llovizna"), 55: ("🌧", "Llovizna intensa"),
    61: ("🌧", "Lluvia ligera"), 63: ("🌧", "Lluvia"), 65: ("🌧", "Lluvia intensa"),
    71: ("❄️", "Nieve ligera"), 73: ("❄️", "Nieve"), 75: ("❄️", "Nieve intensa"),
    80: ("🌦", "Chubascos"), 81: ("🌦", "Chubascos"), 82: ("⛈", "Chubascos fuertes"),
    95: ("⛈", "Tormenta"), 96: ("⛈", "Tormenta con granizo"), 99: ("⛈", "Tormenta intensa"),
}
_DIAS_TG = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _wmo_info(code: int) -> tuple[str, str]:
    for c in [code, (code // 10) * 10, 0]:
        if c in _WMO:
            return _WMO[c]
    return ("🌡", "Variable")


def _tg_day(d: str) -> str:
    try:
        from datetime import datetime as _dt2
        return _DIAS_TG[_dt2.fromisoformat(d).weekday()]
    except Exception:
        return d[-5:]


async def _action_tiempo(update_or_query, context, user: Optional[dict], is_callback=False):
    """Tiempo del día según la ubicación real de la tienda — Open-Meteo."""
    keyboard = _back_keyboard()
    try:
        loop = asyncio.get_running_loop()

        # Obtener lat/lon de la tienda desde config
        def _get_store_loc():
            try:
                store = database.get_db().table("stores").select("config, name").eq("id", STORE_ID).single().execute()
                cfg = store.data.get("config") or {}
                return (
                    float(cfg.get("lat", 40.4168)),
                    float(cfg.get("lon", -3.7038)),
                    cfg.get("city") or store.data.get("name") or "Madrid",
                )
            except Exception:
                return 40.4168, -3.7038, "Madrid"

        lat, lon, city = await loop.run_in_executor(None, _get_store_loc)

        from backend.agents.predictor import get_weather_forecast
        forecast = await loop.run_in_executor(None, get_weather_forecast, lat, lon, 6)

        if not forecast:
            text = "❌ No se pudo obtener el tiempo. Inténtalo en unos minutos."
        else:
            hoy = forecast[0]
            temp = hoy.get("temp_max") or 0
            code = int(hoy.get("weather_code") or 0)
            precip = hoy.get("precipitation_mm") or 0
            hum = hoy.get("relative_humidity_2m_max") or 0
            uv = hoy.get("uv_index_max") or 0
            wind = hoy.get("windspeed_10m_max") or 0
            icon, label = _wmo_info(code)

            hot_days = sum(1 for f in forecast if f.get("is_hot"))
            rain_days = sum(1 for f in forecast if f.get("is_rainy"))
            storm_days = sum(1 for f in forecast if f.get("is_storm"))

            alert = ""
            if storm_days >= 1:
                alert = f"\n\n⛈ <b>ALERTA TORMENTA</b> — {storm_days} día(s) con tormenta prevista.\nRevisa los frescos y asegura el acceso al almacén."
            elif hot_days >= 2:
                alert = f"\n\n🌡 <b>ATENCION:</b> {hot_days} días con >30°C previstos.\nRiesgo elevado en cárnicos, lácteos y panadería."
            elif rain_days >= 3:
                alert = f"\n\n🌧 <b>Lluvia {rain_days} días</b> — esperar menos clientes de lo habitual.\nRevisa el plan de pedidos de frescos."

            # Línea de forecast 5 días
            forecast_line = "  ".join(
                f"{_tg_day(f['date'])} {_wmo_info(int(f.get('weather_code') or 0))[0]} {round(f.get('temp_max') or 0)}°"
                for f in forecast[1:6]
            )

            lines = [
                f"┌{'━' * 34}┐",
                f"│  🌤  <b>TIEMPO — {html.escape(city)}</b>",
                f"│  📅  Hoy {html.escape(hoy.get('date', ''))[:10]}",
                f"└{'━' * 34}┘",
                "",
                f"{icon}  <b>{html.escape(label)}</b>  ·  <b>{round(temp)}°C máx</b>",
                f"💧 Humedad: {round(hum)}%  ·  🌧 Lluvia: {precip:.1f}mm  ·  💨 Viento: {round(wind)} km/h",
                f"☀️ UV: {round(uv)}/11",
                "",
                "━" * 36,
                f"📅 <b>Próximos 5 días</b>",
                f"<code>{forecast_line}</code>",
                alert,
                "",
                "<i>Datos Open-Meteo · actualizado cada hora</i>",
            ]
            text = "\n".join(l for l in lines if l is not None)

    except Exception as e:
        logger.error(f"[tiempo] {e}", exc_info=True)
        text = "❌ Error obteniendo el tiempo. Inténtalo de nuevo."

    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_insights(update_or_query, context, user: Optional[dict], is_callback=False):
    """Insights IA estratégicos — solo encargado, generados con Haiku en <10s."""
    keyboard = _back_keyboard()

    if not _is_manager(user):
        text = "🔒 Los insights estratégicos son solo para encargados."
        if is_callback:
            await update_or_query.edit_message_text(text, reply_markup=keyboard)
        else:
            await _send(update_or_query, text, reply_markup=keyboard)
        return

    # Mostrar placeholder
    wait_text = "✨ <b>Generando insights IA...</b>\n\n<i>Haiku analiza merma, tiempo y acciones (~10s)</i>"
    if is_callback:
        await update_or_query.edit_message_text(wait_text, parse_mode=ParseMode.HTML)
    else:
        await _send(update_or_query, wait_text)

    try:
        loop = asyncio.get_running_loop()

        # Recoger datos en paralelo
        pending, merma_7d, donations, forecast_data = await asyncio.gather(
            loop.run_in_executor(None, database.get_pending_actions, STORE_ID),
            loop.run_in_executor(None, database.get_merma_history, STORE_ID, 7),
            loop.run_in_executor(None, database.get_donation_stats, STORE_ID, 30),
            loop.run_in_executor(None, lambda: __import__(
                'backend.agents.predictor', fromlist=['get_weather_forecast']
            ).get_weather_forecast()),
        )

        critical = sum(1 for a in pending if (a.get("priority_score") or 0) >= 85)
        high = sum(1 for a in pending if 65 <= (a.get("priority_score") or 0) < 85)
        merma_val = sum(float(l.get("value_lost", 0)) for l in merma_7d)
        donated_val = float(donations.get("total_value_donated") or 0)
        hot_days = sum(1 for f in forecast_data if f.get("is_hot"))
        today_temp = round(forecast_data[0].get("temp_max") or 0) if forecast_data else "?"
        today_label = _wmo_info(int((forecast_data[0].get("weather_code") or 0)))[1] if forecast_data else "Variable"

        prompt = f"""Eres el asesor estratégico del Super Martínez. Genera un insight ejecutivo de 5 puntos concretos.

DATOS HOY:
- Acciones pendientes: {len(pending)} ({critical} críticas, {high} altas)
- Merma 7 días: {merma_val:.2f} €
- Donaciones 30 días: {donated_val:.2f} €
- Tiempo hoy: {today_temp}°C, {today_label}
- Días calurosos semana: {hot_days}

Genera EXACTAMENTE 5 insights accionables con este formato:
💡 [INSIGHT CORTO EN NEGRITA]
   [1-2 frases de contexto y acción concreta]

Máximo 400 palabras. Céntrate en reducción de costes, merma y oportunidades comerciales.
No uses markdown, solo texto plano y los emojis que indico."""

        import anthropic as _ant
        ant_client = _ant.Anthropic()
        resp = await loop.run_in_executor(
            None,
            lambda: ant_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
        )
        insights_text = resp.content[0].text if resp.content else "Sin insights disponibles."

        header = (
            f"┌{'━' * 34}┐\n"
            f"│  ✨  <b>INSIGHTS IA — Hoy</b>\n"
            f"│  📅  {date.today().isoformat()}\n"
            f"└{'━' * 34}┘\n\n"
        )
        text = header + html.escape(insights_text) + (
            f"\n\n<i>🌡 {today_temp}°C · {today_label} · {len(pending)} acciones · merma {merma_val:.0f}€/sem</i>"
        )

    except Exception as e:
        logger.error(f"[insights] {e}", exc_info=True)
        text = "❌ Error generando insights. Inténtalo de nuevo."

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔮 Predicciones", callback_data="cmd:prediccion"),
         InlineKeyboardButton("📊 Dashboard", callback_data="cmd:stats")],
        [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
    ])
    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await _send(update_or_query, text, reply_markup=kb)


_PASILLO_NAMES = {
    "1": "🍞 Panadería", "2": "🥛 Lácteos", "3": "🥩 Carnicería",
    "4": "🐟 Pescadería", "5": "🥦 Frutas y Verduras",
}

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
            text = "Error consultando normativa. Inténtalo de nuevo."

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")]])
    if is_callback:
        await update_or_query.edit_message_text(
            _md_to_html(text), parse_mode=ParseMode.HTML, reply_markup=keyboard
        )
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_simular(update_or_query, context, user: Optional[dict], is_callback=False) -> None:
    """Panel de simulación para demo — dispara cada evento del scheduler manualmente."""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌅 07:30 — Brief + predicción", callback_data="confirm:simular")],
        [InlineKeyboardButton("☀️ 12:00 — Check de mediodía", callback_data="confirm:sim_mediodia")],
        [InlineKeyboardButton("🌆 20:00 — Cierre del día", callback_data="confirm:sim_cierre")],
        [InlineKeyboardButton("🔔 Alerta proactiva (monitor 30 min)", callback_data="confirm:sim_proactiva")],
        [InlineKeyboardButton("🚨 Escalación críticos (2h sin resolver)", callback_data="confirm:sim_escalacion")],
        [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
    ])
    text = (
        "🧪 <b>PANEL DE SIMULACIÓN — MermaOps</b>\n\n"
        "Dispara cualquier evento del scheduler ahora mismo, sin esperar al horario real.\n"
        "Útil para demo y presentación.\n\n"
        "📅 <b>Eventos programados:</b>\n"
        "• 07:30 — Brief diario de Kuine (IA)\n"
        "• 12:00 — Check de mediodía + alertas\n"
        "• 20:00 — Cierre del día + resumen\n"
        "• Cada 30 min — Monitor proactivo de donaciones\n"
        "• Cada 2h — Escalación de críticos sin resolver\n\n"
        "👇 Selecciona qué quieres simular ahora:"
    )
    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await _send(update_or_query, text, reply_markup=kb)


async def _simulate_730_background(bot, chat_id: int, user: Optional[dict]) -> None:
    """Ejecuta predicción + brief en background, igual que el scheduler a las 07:30."""
    loop = asyncio.get_running_loop()

    await bot.send_message(chat_id=chat_id, text="🔮 Paso 1/2: Ejecutando predicción de merma...")
    try:
        from backend.agents.predictor import predict_merma_risk, generate_prediction_brief
        predictions = await loop.run_in_executor(None, predict_merma_risk, STORE_ID)
        if predictions:
            pred_text = await loop.run_in_executor(None, generate_prediction_brief, STORE_ID)
            await bot.send_message(
                chat_id=chat_id,
                text=f"🔮 <b>Predicción completada:</b>\n\n{pred_text[:2000]}",
                parse_mode=ParseMode.HTML,
            )
        else:
            await bot.send_message(chat_id=chat_id, text="🔮 Predicción: sin datos suficientes.")
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"🔮 Predicción: error — {str(e)[:80]}")

    await bot.send_message(chat_id=chat_id, text="📋 Paso 2/2: Generando brief con Kuine (IA)... ~60s")
    try:
        # send_telegram=False: Kuine no manda por notifier, lo enviamos aquí con formato
        result = await loop.run_in_executor(
            None, lambda: supervisor.run_daily_brief(STORE_ID, send_telegram=False)
        )
        formatted = _format_brief_html(result)
        chunks = [formatted[i:i+4000] for i in range(0, max(len(formatted), 1), 4000)]
        for chunk in chunks:
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML)
        await bot.send_message(
            chat_id=chat_id,
            text="✅ <b>Simulación 07:30 completada.</b>\nEsto es exactamente lo que ocurre cada mañana de forma automática.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 Descargar brief en PDF", callback_data="cmd:brief_pdf")],
                [InlineKeyboardButton("⚡ Ver acciones generadas", callback_data="cmd:acciones"),
                 InlineKeyboardButton("🗺 Ruta del día", callback_data="cmd:ruta")],
                [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
            ]),
        )
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"📋 Brief: error — {str(e)[:80]}")
        await bot.send_message(
            chat_id=chat_id,
            text="↩ Volver al menú",
            reply_markup=_back_keyboard(),
        )


async def _sim_mediodia_background(bot, chat_id: int) -> None:
    """Simula el check de mediodía de Kuine (12:00) — para demo en presentación."""
    loop = asyncio.get_running_loop()
    await bot.send_message(chat_id=chat_id, text="☀️ <b>CHECK MEDIODÍA — Kuine analizando...</b>", parse_mode=ParseMode.HTML)
    try:
        result = await loop.run_in_executor(None, lambda: supervisor.run_intraday_check(STORE_ID))
        formatted = _format_brief_html(result) if result else "Sin novedades en el check de mediodía."
        chunks = [formatted[i:i+4000] for i in range(0, max(len(formatted), 1), 4000)]
        for chunk in chunks:
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML)
        await bot.send_message(
            chat_id=chat_id,
            text="☀️ <b>Check de mediodía completado.</b>\nEsto ocurre automáticamente a las 12:00 cada día.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚡ Ver acciones pendientes", callback_data="cmd:acciones")],
                [InlineKeyboardButton("🧪 Más simulaciones", callback_data="cmd:simular")],
                [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
            ]),
        )
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"Error en check mediodía: {str(e)[:100]}", reply_markup=_back_keyboard())


async def _sim_cierre_background(bot, chat_id: int) -> None:
    """Simula el cierre del día de Kuine (20:00) — para demo en presentación."""
    loop = asyncio.get_running_loop()
    await bot.send_message(chat_id=chat_id, text="🌆 <b>CIERRE DEL DÍA — Kuine generando resumen...</b>", parse_mode=ParseMode.HTML)
    try:
        result = await loop.run_in_executor(None, lambda: supervisor.run_closing(STORE_ID))
        formatted = _format_brief_html(result) if result else "Cierre del día sin incidencias."
        chunks = [formatted[i:i+4000] for i in range(0, max(len(formatted), 1), 4000)]
        for chunk in chunks:
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML)
        await bot.send_message(
            chat_id=chat_id,
            text="🌆 <b>Cierre completado.</b>\nEsto ocurre automáticamente a las 20:00 cada día.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🧪 Más simulaciones", callback_data="cmd:simular")],
                [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
            ]),
        )
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"Error en cierre: {str(e)[:100]}", reply_markup=_back_keyboard())


async def _sim_proactiva_background(bot, chat_id: int) -> None:
    """Simula el monitor proactivo de donaciones (cada 30 min) — para demo."""
    loop = asyncio.get_running_loop()
    try:
        batches = await loop.run_in_executor(None, database.get_batches_expiring_soon, STORE_ID, 2)
        pending_ids = {a.get("batch_id") for a in await loop.run_in_executor(None, database.get_pending_actions, STORE_ID)}
        candidatos = [b for b in batches if b.get("id") not in pending_ids]

        if not candidatos:
            # Sin candidatos reales — usar todos los que caducan pronto para demo
            candidatos = batches[:3]

        if not candidatos:
            await bot.send_message(
                chat_id=chat_id,
                text="🔔 <b>Monitor proactivo</b>\n\nNo hay productos en riesgo inminente ahora mismo. Cuando los haya, Kuine manda botones de acción directa como este:",
                parse_mode=ParseMode.HTML,
            )
            # Mandar un ejemplo ficticio de cómo se vería
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "🔴 <b>KUINE — Donación sugerida</b>\n\n"
                    "<b>Yogur Natural Danone</b> | 🥛 Lácteos\n"
                    "23 unidades | Caduca HOY\n\n"
                    "Stock elevado + caducidad hoy. ¿Lo donamos?\n\n"
                    "<i>(Ejemplo — en producción los datos serían reales)</i>"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❤️ Banco de Alimentos", callback_data="demo:banco"),
                     InlineKeyboardButton("🤝 Cáritas", callback_data="demo:caritas")],
                    [InlineKeyboardButton("🏥 Cruz Roja", callback_data="demo:cruzroja"),
                     InlineKeyboardButton("💰 Mejor rebajar", callback_data="demo:rebajar")],
                    [InlineKeyboardButton("❌ Ya gestionado", callback_data="demo:skip")],
                ]),
            )
        else:
            for batch in candidatos[:2]:
                p = batch.get("products") or {}
                name = p.get("name") or "Producto"
                pasillo = str(p.get("pasillo") or "?")
                pasillo_label = _PASILLO_NAMES.get(pasillo, f"Pasillo {pasillo}")
                qty = batch.get("quantity") or 0
                exp = batch.get("expiry_date") or "?"
                batch_id = batch.get("id") or ""
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"🔴 <b>KUINE — Donación sugerida</b>\n\n"
                        f"<b>{html.escape(name)}</b> | {pasillo_label}\n"
                        f"{qty} unidades | Caduca {exp}\n\n"
                        f"Stock elevado + caducidad próxima. ¿Lo donamos?"
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❤️ Banco de Alimentos", callback_data=f"donate_now:banco_alimentos:{batch_id}"),
                         InlineKeyboardButton("🤝 Cáritas", callback_data=f"donate_now:caritas:{batch_id}")],
                        [InlineKeyboardButton("🏥 Cruz Roja", callback_data=f"donate_now:cruz_roja:{batch_id}"),
                         InlineKeyboardButton("💰 Mejor rebajar", callback_data=f"donate_now:rebajar:{batch_id}")],
                        [InlineKeyboardButton("❌ Ya gestionado", callback_data=f"donate_now:skip:{batch_id}")],
                    ]),
                )
        await bot.send_message(
            chat_id=chat_id,
            text="🔔 <b>Esto llega automáticamente cada 30 minutos en horario comercial.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🧪 Más simulaciones", callback_data="cmd:simular")]]),
        )
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"Error en monitor proactivo: {str(e)[:100]}", reply_markup=_back_keyboard())


async def _sim_escalacion_background(bot, chat_id: int) -> None:
    """Simula la escalación automática de críticos sin resolver — para demo."""
    loop = asyncio.get_running_loop()
    try:
        pending = await loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
        critical = [a for a in pending if (a.get("priority_score") or 0) >= 85]

        if not critical:
            # No hay críticos reales — demo con los de mayor prioridad
            critical = sorted(pending, key=lambda a: a.get("priority_score") or 0, reverse=True)[:3]

        if not critical:
            await bot.send_message(
                chat_id=chat_id,
                text="🚨 <b>Escalación automática</b>\n\nNo hay acciones críticas pendientes. Cuando las haya y lleven más de 2h sin resolver, Kuine manda esta alerta automáticamente.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🧪 Más simulaciones", callback_data="cmd:simular")]]),
            )
            return

        lines = [f"🚨 <b>KUINE — Escalación automática</b>\n\n{len(critical)} acción(es) llevan tiempo sin resolver:\n"]
        for a in critical[:5]:
            batch = a.get("batches") or {}
            product = (batch.get("products") or {}) if batch else {}
            name = product.get("name") or "Producto"
            pasillo = str(product.get("pasillo") or "?")
            pasillo_label = _PASILLO_NAMES.get(pasillo, f"Pasillo {pasillo}")
            score = a.get("priority_score") or 0
            atype = (a.get("action_type") or "revisar").upper()
            icon = "🔴" if score >= 85 else "🟡"
            lines.append(f"{icon} <b>{html.escape(name)}</b> | {pasillo_label} | {atype} | {score}/100")

        lines.append("\n<b>Asignad a alguien o escalad al turno siguiente.</b>")
        await bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚡ Ver y resolver acciones", callback_data="cmd:acciones")],
                [InlineKeyboardButton("🧪 Más simulaciones", callback_data="cmd:simular")],
                [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
            ]),
        )
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"Error en escalación: {str(e)[:100]}", reply_markup=_back_keyboard())


async def _generate_brief_background(bot, chat_id: int, user: Optional[dict]) -> None:
    """Genera el brief en background y manda el resultado cuando termina."""
    loop = asyncio.get_running_loop()
    try:
        # send_telegram=False: evitar que el notifier mande una copia adicional
        result = await loop.run_in_executor(
            None, lambda: supervisor.run_daily_brief(STORE_ID, send_telegram=False)
        )
    except Exception as e:
        result = f"❌ Error generando el brief: {str(e)[:100]}"

    keyboard = _smart_keyboard(result, _is_manager(user))
    try:
        formatted = _format_brief_html(result)
        chunks = [formatted[i:i+4000] for i in range(0, max(len(formatted), 1), 4000)]
        for i, chunk in enumerate(chunks):
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard if i == len(chunks) - 1 else None,
            )
    except Exception:
        try:
            await bot.send_message(chat_id=chat_id, text=result[:4000])
        except Exception:
            pass


async def _action_sistema(update_or_query, context, user: Optional[dict], is_callback=False) -> None:
    """Estado real del scheduler — muestra qué se ejecutó de verdad."""
    loop = asyncio.get_running_loop()

    def _get_system_status():
        try:
            db = database.get_db()
            runs = db.table("agent_runs").select(
                "trigger_source,tools_used,duration_ms,started_at"
            ).eq("store_id", STORE_ID).order("started_at", desc=True).limit(5).execute()
            briefs = db.table("daily_briefs").select("date,actions_count,value_at_risk").eq(
                "store_id", STORE_ID
            ).order("date", desc=True).limit(3).execute()
            decisions = db.table("supervisor_decisions").select(
                "decision_type,score,created_at"
            ).eq("store_id", STORE_ID).order("created_at", desc=True).limit(5).execute()
            return runs.data or [], briefs.data or [], decisions.data or []
        except Exception:
            return [], [], []

    runs, briefs, decisions = await loop.run_in_executor(None, _get_system_status)

    from datetime import datetime as _dt, date as _date
    def _fmt_ts(ts_str):
        if not ts_str:
            return "—"
        try:
            dt = _dt.fromisoformat(ts_str.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%d/%m %H:%M")
        except Exception:
            return ts_str[:16]

    today = str(_date.today())
    lines = ["🤖 <b>Estado real del sistema</b>\n"]

    lines.append("📋 <b>Briefs generados:</b>")
    if briefs:
        for b in briefs[:3]:
            bdate = b.get("date", "?")
            tag = " ← HOY" if str(bdate) == today else ""
            lines.append(f"  • {bdate}{tag} — {b.get('actions_count','?')} acciones, {b.get('value_at_risk',0):.0f}€ en riesgo")
    else:
        lines.append("  (ninguno todavía — usa '🧪 Simular 7:30' para generar)")

    lines.append("\n⚙️ <b>Últimas ejecuciones de Kuine:</b>")
    if runs:
        for r in runs[:5]:
            source = r.get("trigger_source", "?")
            dur = r.get("duration_ms")
            dur_s = f"{dur//1000}s" if dur else "?"
            lines.append(f"  • [{source}] {_fmt_ts(r.get('started_at',''))} — {dur_s}")
    else:
        lines.append("  (sin ejecuciones — el scheduler arranca con el backend)")

    lines.append("\n🎯 <b>Últimas decisiones de Kuine:</b>")
    if decisions:
        for d in decisions[:5]:
            dtype = (d.get("decision_type") or "?").upper()
            score = d.get("score", "?")
            lines.append(f"  • {dtype} — score {score} — {_fmt_ts(d.get('created_at',''))}")
    else:
        lines.append("  (sin decisiones — genera un brief para ver decisiones reales)")

    lines.append(
        "\n⏰ <b>Ejecuciones automáticas programadas:</b>\n"
        "  • 07:00 — Predicción merma\n  • 07:30 — Brief diario (Kuine)\n"
        "  • 12:00 — Check mediodía\n  • 16:00 — Retrospectiva\n"
        "  • 20:00 — Cierre\n  • Cada 2h — Escalación críticos\n"
        "  • Cada 30min — Monitor donaciones"
    )

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Actualizar", callback_data="cmd:sistema"),
         InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
    ])
    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await _send(update_or_query, text, reply_markup=kb)


async def _action_mapa(update_or_query, context, user: Optional[dict], is_callback=False):
    """Mapa visual del supermercado por pasillo."""
    await _cmds._run_cmd_from_action(_cmds._cmd_mapa, update_or_query, context, is_callback)


async def _action_historial(update_or_query, context, user: Optional[dict], is_callback=False):
    """Historial de acciones completadas."""
    await _cmds._run_cmd_from_action(_cmds._cmd_historial, update_or_query, context, is_callback)


async def _action_merma7(update_or_query, context, user: Optional[dict], is_callback=False):
    """Proyección de merma a 7 días."""
    await _cmds._run_cmd_from_action(_cmds._cmd_merma7, update_or_query, context, is_callback)


async def _cmd_simular(update, context):
    user = await _get_or_create_user(update)
    await _action_simular(update, context, user, is_callback=False)


async def _action_almacen(update_or_query, context, user: Optional[dict], is_callback=False):
    """Resumen del almacén: stock con alertas de caducidad próxima."""
    keyboard = _back_keyboard()
    try:
        loop = asyncio.get_running_loop()
        batches = await loop.run_in_executor(None, database.get_batches_expiring_soon, STORE_ID, 14)

        if not batches:
            text = (
                "✅ <b>Almacén sin lotes próximos a caducar</b>\n\n"
                "<i>No hay productos en almacén con caducidad en los próximos 14 días.</i>"
            )
        else:
            criticos = [b for b in batches if (
                date.fromisoformat(b.get("expiry_date", "9999-12-31")) - date.today()
            ).days <= 3]
            proximos = [b for b in batches if 3 < (
                date.fromisoformat(b.get("expiry_date", "9999-12-31")) - date.today()
            ).days <= 7]
            resto = [b for b in batches if (
                date.fromisoformat(b.get("expiry_date", "9999-12-31")) - date.today()
            ).days > 7]

            total_val = sum(
                (b.get("quantity") or 0) * float((b.get("products") or {}).get("price") or 0)
                for b in batches
            )

            lines = [
                f"┌{'━' * 34}┐",
                f"│  📦  <b>ALMACÉN — stock próx. caducidad</b>",
                f"│  📅  {date.today().isoformat()}",
                f"└{'━' * 34}┘",
                "",
                f"<i>{len(batches)} lotes · 💰 {total_val:.2f}€ en riesgo</i>",
                "",
            ]

            if criticos:
                lines += [f"🔴 <b>CRÍTICO ≤3 días</b>  <i>({len(criticos)} lotes)</i>", "─" * 30]
                for b in criticos[:5]:
                    p = (b.get("products") or {})
                    name = p.get("name", "Producto")
                    qty = b.get("quantity") or 0
                    exp = b.get("expiry_date", "")
                    try:
                        d = (date.fromisoformat(exp) - date.today()).days
                        d_txt = "<b>HOY</b>" if d == 0 else f"<b>{d}d</b>"
                    except Exception:
                        d_txt = exp
                    lines.append(f"• <b>{html.escape(name)}</b>  ·  {qty} uds  ·  {d_txt}")
                lines.append("")

            if proximos:
                lines += [f"🟡 <b>ATENCIÓN 4-7 días</b>  <i>({len(proximos)} lotes)</i>", "─" * 30]
                for b in proximos[:5]:
                    p = (b.get("products") or {})
                    name = p.get("name", "Producto")
                    qty = b.get("quantity") or 0
                    exp = b.get("expiry_date", "")
                    try:
                        d = (date.fromisoformat(exp) - date.today()).days
                    except Exception:
                        d = "?"
                    lines.append(f"• {html.escape(name)}  ·  {qty} uds  ·  {d}d")
                lines.append("")

            if resto:
                lines.append(f"🟢 <b>OK 8-14 días:</b> {len(resto)} lotes más sin urgencia")

            lines.append("\n<i>Mover a tienda los críticos antes del brief de mañana</i>")
            text = "\n".join(lines)

    except Exception as e:
        logger.error(f"[almacen] {e}", exc_info=True)
        text = "❌ Error obteniendo datos del almacén. Inténtalo de nuevo."

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Ver acciones pendientes", callback_data="cmd:acciones"),
         InlineKeyboardButton("🗺 Ruta del día", callback_data="cmd:ruta")],
        [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
    ])
    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await _send(update_or_query, text, reply_markup=kb)


async def _action_perfil(update_or_query, context, user: Optional[dict], is_callback=False):
    """Ver y configurar el perfil de la tienda — solo encargado."""
    keyboard = _back_keyboard()

    if not _is_manager(user):
        text = "🔒 La configuración de la tienda es solo para encargados."
        if is_callback:
            await update_or_query.edit_message_text(text, reply_markup=keyboard)
        else:
            await _send(update_or_query, text, reply_markup=keyboard)
        return

    try:
        loop = asyncio.get_running_loop()

        def _get_profile():
            store = database.get_db().table("stores").select("id, name, config").eq("id", STORE_ID).single().execute()
            d = store.data or {}
            cfg = d.get("config") or {}
            return d, cfg

        store_data, cfg = await loop.run_in_executor(None, _get_profile)
        name = store_data.get("name") or "Super Martínez"
        city = cfg.get("city") or "Madrid"
        zone = cfg.get("zone_type") or "residencial"
        size = cfg.get("store_size") or "mediano"
        lat = cfg.get("lat") or 40.4168
        lon = cfg.get("lon") or -3.7038

        lines = [
            f"┌{'━' * 34}┐",
            f"│  🏪  <b>PERFIL TIENDA</b>",
            f"│  🆔  <i>{html.escape(STORE_ID)}</i>",
            f"└{'━' * 34}┘",
            "",
            f"🏪 <b>Nombre:</b> {html.escape(name)}",
            f"🏙 <b>Ciudad:</b> {html.escape(city)}",
            f"📍 <b>Coordenadas:</b> {lat:.4f}, {lon:.4f}",
            f"📐 <b>Tamaño:</b> {html.escape(size)}",
            f"🗺 <b>Zona:</b> {html.escape(zone)}",
            "",
            "━" * 36,
            "⚙️ <b>Configurar</b> — escribe en Telegram:",
            "",
            "<code>/perfil ciudad Madrid</code>",
            "<code>/perfil zona residencial</code>",
            "<code>/perfil tamano grande</code>",
            "<code>/perfil lat 40.4168 lon -3.7038</code>",
            "",
            "<i>Las coordenadas afectan al tiempo Open-Meteo que ves en /tiempo</i>",
        ]
        text = "\n".join(lines)

    except Exception as e:
        logger.error(f"[perfil] {e}", exc_info=True)
        text = "❌ Error obteniendo el perfil. Inténtalo de nuevo."

    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await _send(update_or_query, text, reply_markup=keyboard)


async def _action_comparativa(update_or_query, context, user: Optional[dict], is_callback=False):
    """Benchmark de la tienda vs otras de la cadena — solo encargado."""
    keyboard = _back_keyboard()

    if not _is_manager(user):
        text = "🔒 La comparativa entre tiendas es solo para encargados."
        if is_callback:
            await update_or_query.edit_message_text(text, reply_markup=keyboard)
        else:
            await _send(update_or_query, text, reply_markup=keyboard)
        return

    try:
        loop = asyncio.get_running_loop()
        stores = await loop.run_in_executor(None, database.get_stores_comparison, STORE_ID)

        if not stores:
            text = (
                "📊 <b>Sin datos de comparativa</b>\n\n"
                "La tabla de benchmark está vacía todavía.\n"
                "Los datos se acumulan automáticamente cada mes."
            )
        else:
            current = next((s for s in stores if s.get("is_current")), None)
            others = [s for s in stores if not s.get("is_current")]

            lines = [
                f"┌{'━' * 34}┐",
                f"│  📊  <b>COMPARATIVA — cadena de tiendas</b>",
                f"└{'━' * 34}┘",
                "",
            ]

            if current:
                rank = current.get("rank", "?")
                total = len(stores)
                merma_pct = float(current.get("merma_rate_pct") or 0)
                val = float(current.get("merma_value_eur") or 0)
                actions = current.get("actions_completed") or 0
                donated = float(current.get("donated_value_eur") or 0)

                medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"
                lines += [
                    f"{medal} <b>Tu tienda — Posición {rank}/{total}</b>",
                    f"  📉 Tasa merma: <b>{merma_pct:.2f}%</b>",
                    f"  💸 Merma mes: <b>{val:.2f}€</b>",
                    f"  ✅ Acciones: <b>{actions}</b>",
                    f"  ❤️  Donado: <b>{donated:.2f}€</b>",
                    "",
                    "━" * 36,
                    "<b>Ranking completo:</b>",
                ]

            for s in stores[:8]:
                rank = s.get("rank", "?")
                sname = html.escape((s.get("store_name") or f"Tienda {rank}")[:20])
                merma = float(s.get("merma_rate_pct") or 0)
                is_curr = s.get("is_current", False)
                medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"  {rank}."
                curr_mark = " ← <b>tú</b>" if is_curr else ""
                trend = "📈" if float(s.get("trend_vs_prev_month") or 0) > 0 else "📉"
                lines.append(f"{medal} {sname}  ·  {merma:.2f}% merma {trend}{curr_mark}")

            if not current:
                lines.append("\n<i>Tu tienda no tiene datos en este período todavía.</i>")
            else:
                if rank == 1:
                    lines.append("\n🏆 <b>¡Sois la tienda con menos merma de la cadena!</b>")
                elif rank <= len(stores) // 2:
                    lines.append(f"\n💪 Estáis en la primera mitad. A por el top 3.")
                else:
                    gap = float(stores[0].get("merma_rate_pct") or 0)
                    lines.append(f"\n🎯 La líder tiene {gap:.2f}% merma. Reducid {merma_pct - gap:.2f}pp para llegar al 1er puesto.")

            text = "\n".join(str(l) for l in lines)

    except Exception as e:
        logger.error(f"[comparativa] {e}", exc_info=True)
        text = "❌ Error obteniendo comparativa. Inténtalo de nuevo."

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌱 ESG / Impacto", callback_data="cmd:esg"),
         InlineKeyboardButton("📊 Dashboard", callback_data="cmd:stats")],
        [InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
    ])
    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await _send(update_or_query, text, reply_markup=kb)


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
    "sistema": _action_sistema,
    "simular": _action_simular,
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
    "mapa": _action_mapa,
    "historial": _action_historial,
    "merma7": _action_merma7,
    "tiempo": _action_tiempo,
    "insights": _action_insights,
    "almacen": _action_almacen,
    "perfil": _action_perfil,
    "comparativa": _action_comparativa,
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

    _auto_save_chat_id(update.effective_chat.id)

    _loop = asyncio.get_running_loop()
    user = await _loop.run_in_executor(None, _get_user, tg_id)

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
            [InlineKeyboardButton("🏪 Ver estado sin cuenta", callback_data="cmd:estado")],
        ])
        await update.message.reply_text(
            f"👋 Hola <b>{html.escape(tg_name)}</b>, soy <b>Chuwi</b>.\n\n"
            "Soy el agente de IA de <b>MermaOps</b> — gestión inteligente\n"
            "de merma para supermercados. Coordinado por <b>Kuine</b>.\n\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🔗  <b>Para vincular tu cuenta:</b>\n\n"
            "1️⃣  Abre la app <b>MermaOps</b>\n"
            "2️⃣  Ve a <b>Perfil</b> → Vincular Telegram\n"
            "3️⃣  Pega tu ID:\n\n"
            f"<code>{tg_id}</code>\n\n"
            "4️⃣  Pulsa <b>Vincular</b> y vuelve aquí\n"
            "━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>Sin cuenta solo puedo darte info general.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return

    # Cargar estado real de la tienda para el welcome dinámico
    stats = await _loop.run_in_executor(None, _get_store_quick_stats)
    manager = _is_manager(user)
    keyboard = _main_menu_keyboard(manager)

    # Si hay acción urgente, añadir botón primario "Empezar por aquí" como primera fila
    first_action_id = stats.get("first_action_id", "")
    if first_action_id:
        primary_row = [InlineKeyboardButton("⚡ Empezar por aquí →", callback_data=f"action_detail:{first_action_id}")]
        combined_rows = [primary_row] + list(keyboard.inline_keyboard)
        keyboard = InlineKeyboardMarkup(combined_rows)

    await update.message.reply_text(
        _welcome_text(tg_name, manager, stats),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
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

    _loop = asyncio.get_running_loop()
    user = await _loop.run_in_executor(None, _get_user, update.effective_user.id)
    user_id = str(update.effective_user.id)
    data = query.data or ""

    # ── Menú principal ──
    if data == "cmd:menu":
        manager = _is_manager(user)
        _clear_conv_state(user_id)
        keyboard = _main_menu_keyboard(manager)
        await query.edit_message_text("¿Qué necesitas?", reply_markup=keyboard)
        return

    # ── Confirmación de brief — lanza en background, responde inmediato ──
    if data == "confirm:runbrief":
        chat_id = query.message.chat_id
        await query.edit_message_text(
            "📋 <b>Generando brief en segundo plano...</b>\n\n"
            "Kuine está analizando todos los productos con IA.\n"
            "Te mando el resultado aquí en ~60 segundos.\n"
            "Puedes seguir usando el bot mientras tanto. 👇",
            parse_mode=ParseMode.HTML,
            reply_markup=_back_keyboard(),
        )
        asyncio.create_task(_generate_brief_background(context.bot, chat_id, user))
        return

    # ── Simular 07:30 — ejecuta predicción + brief en background ──
    if data == "confirm:simular":
        chat_id = query.message.chat_id
        await query.edit_message_text(
            "🧪 <b>Simulando las 07:30...</b>\n\n"
            "Ejecutando predicción + brief en background.\n"
            "Te mando los resultados aquí según vayan llegando.\n"
            "Puedes seguir usando el bot. ⏳",
            parse_mode=ParseMode.HTML,
            reply_markup=_back_keyboard(),
        )
        asyncio.create_task(_simulate_730_background(context.bot, chat_id, user))
        return

    # ── Simulación mediodía ──
    if data == "confirm:sim_mediodia":
        chat_id = query.message.chat_id
        await query.edit_message_text(
            "☀️ <b>Simulando check de mediodía (12:00)...</b>\n\nKuine revisa el estado de las acciones y escala si hay críticos sin resolver. ⏳",
            parse_mode=ParseMode.HTML, reply_markup=_back_keyboard(),
        )
        asyncio.create_task(_sim_mediodia_background(context.bot, chat_id))
        return

    # ── Simulación cierre ──
    if data == "confirm:sim_cierre":
        chat_id = query.message.chat_id
        await query.edit_message_text(
            "🌆 <b>Simulando cierre del día (20:00)...</b>\n\nKuine genera el resumen del día y las recomendaciones para mañana. ⏳",
            parse_mode=ParseMode.HTML, reply_markup=_back_keyboard(),
        )
        asyncio.create_task(_sim_cierre_background(context.bot, chat_id))
        return

    # ── Simulación alerta proactiva (monitor 30 min) ──
    if data == "confirm:sim_proactiva":
        chat_id = query.message.chat_id
        await query.edit_message_text(
            "🔔 <b>Simulando monitor proactivo...</b>\n\nKuine busca productos en riesgo inminente y manda botones de acción directa.",
            parse_mode=ParseMode.HTML, reply_markup=_back_keyboard(),
        )
        asyncio.create_task(_sim_proactiva_background(context.bot, chat_id))
        return

    # ── Simulación escalación críticos ──
    if data == "confirm:sim_escalacion":
        chat_id = query.message.chat_id
        await query.edit_message_text(
            "🚨 <b>Simulando escalación automática...</b>\n\nKuine comprueba acciones críticas sin resolver y alerta al equipo.",
            parse_mode=ParseMode.HTML, reply_markup=_back_keyboard(),
        )
        asyncio.create_task(_sim_escalacion_background(context.bot, chat_id))
        return

    # ── Test de alerta — comprueba que las alertas llegan a tu Telegram ──
    if data == "confirm:test_alerta":
        chat_id = query.message.chat_id
        try:
            pending = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
            critical = [a for a in pending if (a.get("priority_score") or 0) >= 85]
            if critical:
                a = critical[0]
                batch = a.get("batches") or {}
                prod = (batch.get("products") or {})
                msg = (
                    f"🔔 <b>TEST DE ALERTA — MermaOps</b>\n\n"
                    f"Si ves esto, las alertas funcionan correctamente.\n\n"
                    f"Ejemplo de alerta real:\n"
                    f"• Producto: <b>{prod.get('name','?')}</b>\n"
                    f"• Prioridad: {a.get('priority_score',0)}/100 (CRÍTICO)\n"
                    f"• Acción: {a.get('action_type','?').upper()}"
                )
            else:
                msg = (
                    "🔔 <b>TEST DE ALERTA — MermaOps</b>\n\n"
                    "Si ves esto, las alertas funcionan correctamente.\n"
                    "Ahora mismo no hay productos críticos, pero cuando los haya "
                    "recibirías este tipo de mensaje automáticamente."
                )
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=_back_keyboard())
        except Exception as e:
            await query.edit_message_text(f"Error en test: {str(e)[:100]}", reply_markup=_back_keyboard())
        return

    # ── Marcar acción completada (legacy) ──
    if data.startswith("complete_action:"):
        action_id = data[16:]
        try:
            u_id = user.get("id", "") if user else ""
            u_name = user.get("email", "empleado").split("@")[0] if user else "empleado"
            # Obtener tipo de acción para el employee patterns
            _pending_all = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
            _act = next((a for a in _pending_all if str(a.get("id")) == str(action_id)), {})
            _atype = _act.get("action_type", "revisar")
            await _loop.run_in_executor(None, database.complete_action, action_id, u_id)
            # Actualizar patrones del empleado cross-session
            _update_employee_patterns(user, _atype, datetime.now().hour)
            await query.edit_message_text(
                f"✅ Acción marcada como completada por {u_name}.\n\nBuen trabajo.",
                reply_markup=_main_menu_keyboard(_is_manager(user))
            )
        except Exception as e:
            await query.edit_message_text(
                "Error al marcar la acción. Inténtalo de nuevo.",
                reply_markup=_back_keyboard()
            )
        return

    # ── Ver tarjeta de detalle de una acción ──
    if data.startswith("action_detail:"):
        action_id = data[14:]
        pending = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
        action = next((a for a in pending if a.get("id") == action_id), None)
        if not action:
            await query.edit_message_text("Esta acción ya no está pendiente.", reply_markup=_back_keyboard())
            return
        idx = pending.index(action) + 1
        card = _format_action_card(action, index=idx, total=len(pending))
        keyboard = _action_card_keyboard(action, remaining=len(pending) - idx)
        await query.edit_message_text(card, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return

    # ── Confirmar acción (rebajar / retirar / mover / revisar OK) ──
    if data.startswith("action_confirm:"):
        action_id = data[15:]
        u_id = user.get("id", "") if user else ""
        u_name = (user.get("email") or "empleado").split("@")[0] if user else "empleado"
        try:
            # Recuperar info antes de completar — guard contra doble-tap
            pending = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
            action = next((a for a in pending if a.get("id") == action_id), None)
            if not action:
                remaining = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
                text = "✅ <b>Ya estaba completada</b>\n\nEsta acción ya fue registrada anteriormente."
                if remaining:
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("▶️ Ver siguiente pendiente", callback_data=f"action_detail:{remaining[0]['id']}")],
                        [InlineKeyboardButton("📋 Ver todas", callback_data="cmd:acciones"), InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
                    ])
                else:
                    keyboard = _main_menu_keyboard(_is_manager(user))
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
                return
            await _loop.run_in_executor(None, database.complete_action, action_id, u_id)

            # Parar SLA tracking — el empleado ha confirmado la acción
            try:
                from backend.agents import notifier as _notifier
                _notifier.acknowledge_alert(action_id)
            except Exception:
                pass

            # Registrar outcome en memoria episódica
            if action:
                try:
                    from backend.core import memory as _mem_mod
                    _batch = action.get("batches") or {}
                    _product = (_batch.get("products") or {}) if _batch else {}
                    _atype = action.get("action_type", "revisar")
                    _qty = int((_batch.get("quantity") or 0))
                    _new_price = action.get("new_price")
                    _cost = float(_product.get("cost") or 0)
                    _result = {"rebajar": "vendido", "donar": "donado", "retirar": "retirado"}.get(_atype, "completado")
                    _val = float(_new_price) * _qty if _new_price and _atype == "rebajar" else round(_qty * _cost * 0.35, 2) if _atype == "donar" else 0.0
                    _mem_mod.record_decision_outcome(
                        STORE_ID, action_id, _atype,
                        _product.get("name", "?"),
                        int(action.get("priority_score") or 0),
                        _result, _val,
                    )
                except Exception:
                    pass

            # Resumen de lo que se hizo
            if action:
                batch = action.get("batches") or {}
                product = (batch.get("products") or {}) if batch else {}
                name = product.get("name", "Producto")
                atype = action.get("action_type", "completar")
                new_price = action.get("new_price")
                original_price = float(product.get("price") or 0)
                discount_pct = abs(int(action.get("price_adjustment_pct") or 0))
                qty = int(batch.get("quantity") or 0)
                expiry = (batch.get("expiry_date") or "")
                # Compute new_price from discount % if not stored
                if atype == "rebajar" and not new_price and discount_pct and original_price > 0:
                    new_price = round(original_price * (1 - discount_pct / 100), 2)
                atype_text = {
                    "rebajar": f"Precio actualizado a {new_price:.2f}€ — etiqueta el estante" if new_price else "Precio rebajado — etiqueta el estante",
                    "retirar": f"{qty} unidades retiradas — registra en albarán de merma",
                    "mover": f"{qty} unidades trasladadas del almacén a tienda",
                    "revisar": "Revisado y conforme",
                }.get(atype, "Completada")
                summary = f"✅ <b>{name}</b>\n{atype_text}"

                # Generar etiqueta PDF de precio cuando es rebajar
                if atype == "rebajar" and new_price and original_price > 0:
                    try:
                        from backend.core.pdf_generator import generate_price_label
                        import io as _io
                        label_bytes = generate_price_label(
                            product_name=name,
                            original_price=original_price,
                            new_price=float(new_price),
                            discount_pct=discount_pct or int((1 - float(new_price)/original_price) * 100),
                            expiry_date=expiry,
                        )
                        await query.message.reply_document(
                            document=_io.BytesIO(label_bytes),
                            filename=f"etiqueta_{name[:20].replace(' ','_')}.pdf",
                            caption=f"🏷️ Etiqueta para imprimir y pegar en el estante de {name}",
                        )
                    except Exception as _pe:
                        logger.debug(f"[label] PDF error: {_pe}")
            else:
                summary = "✅ Acción completada"

            # Streak counter
            try:
                tg_uid = str(update.effective_user.id) if hasattr(update, 'effective_user') and update.effective_user else ""
                streak = _update_streak(tg_uid) if tg_uid else 0
                summary += _streak_text(streak)
            except Exception:
                pass

            # Mostrar siguiente acción pendiente
            remaining = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
            if remaining:
                next_a = remaining[0]
                next_batch = next_a.get("batches") or {}
                next_prod = (next_batch.get("products") or {}) if next_batch else {}
                next_name = next_prod.get("name", "siguiente producto")
                score = next_a.get("priority_score", 0)
                icon = "🔴" if score >= 85 else "🟡"
                text = (
                    f"{summary}\n\n"
                    f"Quedan <b>{len(remaining)}</b> acciones pendientes.\n"
                    f"Siguiente {icon}: <b>{next_name}</b>"
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ Ver siguiente", callback_data=f"action_detail:{next_a['id']}")],
                    [InlineKeyboardButton("📋 Ver todas", callback_data="cmd:acciones"),
                     InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
                ])
            else:
                text = f"{summary}\n\n🏆 <b>¡Sin acciones pendientes!</b>\nTodo gestionado por hoy."
                keyboard = _main_menu_keyboard(_is_manager(user))

            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        except Exception as e:
            await query.edit_message_text("Error al completar la acción. Inténtalo de nuevo.", reply_markup=_back_keyboard())
        return

    # ── Donar desde tarjeta de acción (selección de entidad) ──
    if data.startswith("action_donate:"):
        action_id = data[14:]
        pending = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
        action = next((a for a in pending if a.get("id") == action_id), None)
        if not action:
            await query.edit_message_text("Acción no encontrada.", reply_markup=_back_keyboard())
            return
        batch = action.get("batches") or {}
        product = (batch.get("products") or {}) if batch else {}
        name = product.get("name", "Producto")
        qty = int(batch.get("quantity") or 0)
        cost = float(product.get("cost") or 0)
        deduccion = round(qty * cost * 0.35, 2)
        text = (
            f"❤️ <b>Donar: {name}</b>\n\n"
            f"{qty} unidades · Deducción fiscal: {deduccion:.2f}€\n\n"
            "¿A qué entidad?"
        )
        bid = action.get("batch_id", "")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏛 Banco de Alimentos", callback_data=f"action_donate_entity:{action_id}:banco_alimentos"),
             InlineKeyboardButton("🕊 Cáritas", callback_data=f"action_donate_entity:{action_id}:caritas")],
            [InlineKeyboardButton("🔴 Cruz Roja", callback_data=f"action_donate_entity:{action_id}:cruz_roja"),
             InlineKeyboardButton("↩ Volver", callback_data=f"action_detail:{action_id}")],
        ])
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return

    # ── Confirmar donación con entidad elegida ──
    if data.startswith("action_donate_entity:"):
        parts = data.split(":", 2)
        action_id = parts[1] if len(parts) > 1 else ""
        entity_key = parts[2] if len(parts) > 2 else "banco_alimentos"
        entity_names = {
            "banco_alimentos": "Banco de Alimentos",
            "caritas": "Cáritas",
            "cruz_roja": "Cruz Roja",
        }
        entity_display = entity_names.get(entity_key, entity_key)
        u_id = user.get("id", "") if user else ""
        u_name = (user.get("email") or "empleado").split("@")[0] if user else "empleado"
        try:
            pending = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
            action = next((a for a in pending if a.get("id") == action_id), None)
            if not action:
                rem = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
                text = "✅ <b>Ya estaba completada</b>\n\nEsta donación ya fue registrada anteriormente."
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Siguiente", callback_data=f"action_detail:{rem[0]['id']}")]]) if rem else _main_menu_keyboard(_is_manager(user))
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
                return
            batch = (action.get("batches") or {}) if action else {}
            product = (batch.get("products") or {}) if batch else {}
            name = product.get("name", "Producto")
            qty = int(batch.get("quantity") or 0)
            cost = float(product.get("cost") or 0)
            batch_id = (action or {}).get("batch_id", "")

            donation_data = {
                "store_id": STORE_ID,
                "batch_id": batch_id or None,
                "entity": entity_display,
                "quantity": qty,
                "value_donated": round(qty * cost, 2),
                "donated_at": datetime.now(timezone.utc).isoformat(),
                "donated_by": u_name,
            }
            await _loop.run_in_executor(None, database.log_donation, donation_data)
            await _loop.run_in_executor(None, lambda: database.complete_action(action_id, u_id, notes=f"Donado a {entity_display}"))

            # SLA ACK + outcome tracking
            try:
                from backend.agents import notifier as _notifier
                _notifier.acknowledge_alert(action_id)
                from backend.core import memory as _mem_mod
                _score = int((action or {}).get("priority_score") or 0)
                _mem_mod.record_decision_outcome(
                    STORE_ID, action_id, "donar", name, _score,
                    "donado", round(qty * cost * 0.35, 2),
                )
            except Exception:
                pass

            deduccion = round(qty * cost * 0.35, 2)
            remaining = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
            text = (
                f"❤️ <b>Donación registrada</b>\n\n"
                f"Producto: <b>{name}</b>\n"
                f"Entidad: {entity_display}\n"
                f"Cantidad: {qty} unidades\n"
                f"Valor donado: {round(qty * cost, 2):.2f}€\n"
                f"Deducción fiscal: <b>{deduccion:.2f}€</b>\n\n"
                f"Quedan {len(remaining)} acciones pendientes."
            )
            # Streak counter
            try:
                tg_uid = str(update.effective_user.id) if hasattr(update, 'effective_user') and update.effective_user else ""
                streak = _update_streak(tg_uid) if tg_uid else 0
                text += _streak_text(streak)
            except Exception:
                pass
            if remaining:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ Siguiente acción", callback_data=f"action_detail:{remaining[0]['id']}")],
                    [InlineKeyboardButton("📋 Ver todas", callback_data="cmd:acciones"),
                     InlineKeyboardButton("↩ Menú", callback_data="cmd:menu")],
                ])
            else:
                keyboard = _main_menu_keyboard(_is_manager(user))
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        except Exception as e:
            await query.edit_message_text("Error al registrar la donación. Inténtalo de nuevo.", reply_markup=_back_keyboard())
        return

    # ── Escalar revisión a acción urgente ──
    if data.startswith("action_escalate:"):
        action_id = data[16:]
        u_id = user.get("id", "") if user else ""
        try:
            await _loop.run_in_executor(None, lambda: database.get_db().table("actions").update({
                "action_type": "rebajar",
                "priority_score": 85,
                "notes": "Escalado desde revisión — necesita acción urgente",
            }).eq("id", action_id).execute())
            pending = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
            action = next((a for a in pending if a.get("id") == action_id), None)
            if action:
                card = _format_action_card(action)
                keyboard = _action_card_keyboard(action, remaining=len(pending) - 1)
                await query.edit_message_text(
                    "🔴 Escalado a CRÍTICO. Nueva tarjeta:\n\n" + card,
                    parse_mode=ParseMode.HTML, reply_markup=keyboard
                )
            else:
                await query.edit_message_text("Actualizado.", reply_markup=_back_keyboard())
        except Exception as e:
            await query.edit_message_text(_safe_err(e), reply_markup=_back_keyboard())
        return

    # ── Rebajar en vez de donar ──
    if data.startswith("action_rebajar_instead:"):
        action_id = data[23:]
        try:
            pending = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
            action = next((a for a in pending if a.get("id") == action_id), None)
            if action:
                batch = action.get("batches") or {}
                product = (batch.get("products") or {}) if batch else {}
                current_price = float(product.get("price") or 0)
                new_price = round(current_price * 0.5, 2)
                await _loop.run_in_executor(None, lambda: database.get_db().table("actions").update({
                    "action_type": "rebajar",
                    "new_price": new_price,
                    "price_adjustment_pct": 50,
                    "notes": "Cambiado de donación a rebaja de precio",
                }).eq("id", action_id).execute())
                updated = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
                action = next((a for a in updated if a.get("id") == action_id), action)
                card = _format_action_card(action)
                keyboard = _action_card_keyboard(action, remaining=len(updated) - 1)
                await query.edit_message_text(card, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            else:
                await query.edit_message_text("Acción no encontrada.", reply_markup=_back_keyboard())
        except Exception as e:
            await query.edit_message_text(_safe_err(e), reply_markup=_back_keyboard())
        return

    # ── Modo ruta: confirmar acción completada ──
    if data.startswith("route_done:"):
        action_id = data[11:]
        state = _get_conv_state(user_id)
        if state["mode"] == "route_active":
            # Marcar como completada
            try:
                u_id = user.get("id", "") if user else ""
                await _loop.run_in_executor(None, database.complete_action, action_id, u_id)
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
                    f"🏁 <b>RUTA COMPLETADA</b>\n\n"
                    f"✅ {completed} acciones completadas\n"
                    f"⏭ {skipped} saltadas\n\n"
                    "Buen trabajo. Las acciones saltadas siguen pendientes en la app.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=_main_menu_keyboard(_is_manager(user))
                )
            else:
                _set_conv_state(user_id, "route_active", state["data"])
                actions = await _loop.run_in_executor(None, _get_route_actions)
                remaining_actions = [a for a in actions if a.get("id") in action_ids[current_idx:]]
                if remaining_actions:
                    next_action = remaining_actions[0]
                    total = len(action_ids)
                    card = _format_action_card(next_action, index=current_idx + 1, total=total)
                    keyboard = _action_card_keyboard(next_action, remaining=total - current_idx - 1)
                    await query.edit_message_text(card, parse_mode=ParseMode.HTML, reply_markup=keyboard)
                else:
                    _clear_conv_state(user_id)
                    await query.edit_message_text("✅ Ruta completada.", reply_markup=_main_menu_keyboard(_is_manager(user)))
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
                    "Ruta terminada. Tienes acciones saltadas pendientes.",
                    reply_markup=_main_menu_keyboard(_is_manager(user))
                )
            else:
                actions = await _loop.run_in_executor(None, _get_route_actions)
                remaining = [a for a in actions if a.get("id") in action_ids[current_idx:]]
                if remaining:
                    next_action = remaining[0]
                    total = len(action_ids)
                    card = _format_action_card(next_action, index=current_idx + 1, total=total)
                    keyboard = _action_card_keyboard(next_action, remaining=total - current_idx - 1)
                    await query.edit_message_text(card, parse_mode=ParseMode.HTML, reply_markup=keyboard)
                else:
                    _clear_conv_state(user_id)
                    await query.edit_message_text("Ruta terminada.", reply_markup=_main_menu_keyboard(_is_manager(user)))
        return

    # ── Botones de demo (ejemplo ficticio en simulación proactiva) ──
    if data.startswith("demo:"):
        _demo_map = {"banco": "Banco de Alimentos", "caritas": "Cáritas", "cruzroja": "Cruz Roja", "rebajar": "rebaja de precio", "skip": "marcado como gestionado"}
        _demo_what = _demo_map.get(data[5:], data[5:])
        await query.edit_message_text(
            f"✅ <b>Demo — acción registrada</b>\n\nEn un caso real, el producto quedaría asignado a <b>{_demo_what}</b>.\nEsto es exactamente lo que haría un empleado con un solo toque.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🧪 Más simulaciones", callback_data="cmd:simular")]]),
        )
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
            cost = 0.0
            if batch_id:
                batches = database.get_batches_expiring_soon(STORE_ID, days=14)
                batch = next((b for b in batches if b.get("id") == batch_id), None)
                if batch:
                    qty = int(batch.get("quantity", 5))
                    p_info = batch.get("products") or {}
                    cost = float(p_info.get("cost", 0) or 0)

            database.log_donation({
                "store_id": STORE_ID,
                "batch_id": batch_id or None,
                "entity": entity_display,
                "quantity": qty,
                "value_donated": round(qty * cost, 2),
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
                "Error al registrar la donación. Inténtalo de nuevo.",
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
                actions = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
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
            max_qty = int(state_data.get("max_quantity") or 1)

            # Botones de cantidad directa — no requiere texto
            qty_options = sorted(set(filter(lambda x: x > 0 and x <= max_qty, [
                max(1, max_qty // 4),
                max(1, max_qty // 2),
                max_qty,
            ])))
            state_data["quantity"] = qty_options[-1]  # pre-select full cantidad
            _set_conv_state(user_id, "donation_flow", state_data)

            rows = [
                [InlineKeyboardButton(
                    f"{'Todo: ' if q == max_qty else ''}{q} uds{' (completo)' if q == max_qty else ''}",
                    callback_data=f"donation_qty:{action_id}:{q}"
                )] for q in qty_options
            ]
            rows.append([InlineKeyboardButton("↩ Volver", callback_data=f"donation_step:select_entity:{action_id}")])

            await query.edit_message_text(
                f"Donando a <b>{entity_name}</b>: {product_name}\n\n¿Cuántas unidades donas?",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(rows)
            )
            return

        if step == "cancel":
            _clear_conv_state(user_id)
            await query.edit_message_text(
                "Donación cancelada.",
                reply_markup=_main_menu_keyboard(_is_manager(user))
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
                donation_cost = 0.0
                try:
                    pending_actions = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
                    matched_action = next((a for a in pending_actions if a.get("id") == action_id), None)
                    if matched_action:
                        b_info = (matched_action.get("batches") or {})
                        p_info = (b_info.get("products") or {}) if b_info else {}
                        donation_cost = float(p_info.get("cost", 0) or 0)
                except Exception:
                    pass
                await _loop.run_in_executor(None, database.complete_action, action_id, user.get("id", u_name))
                from datetime import datetime, timezone as _tz
                donation_data_log = {
                    "store_id": STORE_ID,
                    "action_id": action_id,
                    "entity": entity_name,
                    "quantity": quantity,
                    "product_name": product_name,
                    "donated_by": user.get("email", u_name),
                    "value_donated": round(quantity * donation_cost, 2),
                    "donated_at": datetime.now(_tz.utc).isoformat(),
                }
                await _loop.run_in_executor(None, database.log_donation, donation_data_log)
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
                    "Error al registrar la donación. Inténtalo de nuevo.",
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

    # ── Selección de cantidad de donación (botones directos) ──
    if data.startswith("donation_qty:"):
        parts = data.split(":", 2)
        action_id = parts[1] if len(parts) > 1 else ""
        qty_str = parts[2] if len(parts) > 2 else "0"
        quantity = int(qty_str) if qty_str.isdigit() else 0
        state = _get_conv_state(user_id)
        state_data = state.get("data", {})
        state_data["quantity"] = quantity
        _set_conv_state(user_id, "donation_flow", state_data)
        entity_key = state_data.get("entity", "")
        entity_name = next((n for n, k in _DONATION_ENTITIES if k == entity_key), entity_key)
        product_name = state_data.get("product_name", "Producto")
        cost_per_unit = 0.0
        try:
            actions = await _loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
            matched = next((a for a in actions if a.get("id") == action_id), None)
            if matched:
                cost_per_unit = float(((matched.get("batches") or {}).get("products") or {}).get("cost", 0) or 0)
        except Exception:
            pass
        valor = round(quantity * cost_per_unit, 2)
        deduccion = round(valor * 0.35, 2)
        text = (
            f"❤️ <b>Confirmar donación</b>\n\n"
            f"Producto: <b>{product_name}</b>\n"
            f"Entidad: {entity_name}\n"
            f"Cantidad: <b>{quantity} uds</b>\n"
            f"Valor coste: {valor:.2f}€\n"
            f"Deducción fiscal estimada: <b>{deduccion:.2f}€</b>"
        )
        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirmar donación", callback_data=f"donation_step:confirm:{action_id}")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="donation_step:cancel:")],
            ])
        )
        return

    # ── Iniciar modo ruta desde callback ──
    if data == "cmd:iniciar_ruta":
        actions = await _loop.run_in_executor(None, _get_route_actions)
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
        total = len(actions)
        header = f"🗺 <b>MODO RUTA — {total} acciones pendientes</b>\n\n"
        card = _format_action_card(first, index=1, total=total)
        keyboard = _action_card_keyboard(first, remaining=total - 1)
        await query.edit_message_text(header + card, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return

    # ── Demo callbacks (avanzar días / reset) ──
    if data.startswith("demo:"):
        from backend.core.chuwi_commands import _handle_demo_callback
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
            await query.edit_message_text("No pude obtener el estado. Inténtalo de nuevo.", reply_markup=_back_keyboard())
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
            await query.edit_message_text(_safe_err(e), reply_markup=_back_keyboard())
        return

    # ── Agentes: info completa inline ──
    if data == "cmd:agentes_info":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Estado tienda ahora", callback_data="cmd:estado")],
            [InlineKeyboardButton("⬅️ Menú", callback_data="cmd:menu")],
        ])
        from backend.core.chuwi_commands import _AGENTES_TEXT
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
        pdf_bytes = None
        try:
            loop = asyncio.get_running_loop()
            pdf_bytes = await asyncio.wait_for(
                loop.run_in_executor(None, __import__('backend.core.chuwi_commands', fromlist=['_generate_weekly_pdf_bytes'])._generate_weekly_pdf_bytes), timeout=120
            )
        except asyncio.TimeoutError:
            pdf_bytes = None
        except Exception as e:
            logger.error(f"[chuwi] weekly pdf error: {e}", exc_info=True)
            pdf_bytes = None
        finally:
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
            await query.edit_message_text("No se pudo generar el informe. Inténtalo de nuevo.")
        return

    # ── PDF del brief ──
    if data == "cmd:brief_pdf":
        await query.edit_message_text("📄 Generando PDF del brief...")
        done = asyncio.Event()
        typing_task = asyncio.create_task(_typing_loop(context.bot, query.message.chat_id, done))
        pdf_bytes = None
        try:
            loop = asyncio.get_running_loop()
            pdf_bytes = await asyncio.wait_for(
                loop.run_in_executor(None, __import__('backend.core.chuwi_commands', fromlist=['_generate_brief_pdf_bytes'])._generate_brief_pdf_bytes), timeout=60
            )
        except asyncio.TimeoutError:
            pdf_bytes = None
        except Exception as e:
            logger.error(f"[chuwi] brief pdf error: {e}", exc_info=True)
            pdf_bytes = None
        finally:
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
            await query.edit_message_text("No hay brief disponible. Genera uno primero desde el dashboard.")
        return

    # ── Callbacks de alertas de stock ──────────────────────────────────────────
    if data == "stock_skip":
        await query.answer("Entendido.")
        await query.edit_message_reply_markup(reply_markup=None)
        return

    # ── SLA dismiss — empleado descarta seguimiento ──
    if data.startswith("sla_dismiss:"):
        action_id = data[12:]
        try:
            from backend.agents import notifier as _notifier
            _notifier.acknowledge_alert(action_id)
        except Exception:
            pass
        await query.answer("Entendido. Te avisaré si la situación empeora.")
        await query.edit_message_reply_markup(reply_markup=None)
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

        raw_scan = await loop.run_in_executor(
            None, supervisor.run_scan, STORE_ID, barcode, (user or {}).get("id", "")
        )
        response = raw_scan["text"] if isinstance(raw_scan, dict) else raw_scan
        _scan_thinking = raw_scan.get("thinking_summary", "") if isinstance(raw_scan, dict) else ""
        if _scan_thinking and len(_scan_thinking) > 10:
            response = response + f"\n\n🧠 <i>Kuine (extended thinking): {_scan_thinking[:250]}</i>"
    except Exception as e:
        response = "Error analizando el producto. Inténtalo de nuevo."
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


def _update_employee_patterns(user: Optional[dict], action_type: str, hour: int) -> None:
    """
    Actualiza la memoria cross-session de un empleado.
    Aprende: qué tipo de acciones hace habitualmente, a qué horas trabaja.
    Se usa para personalizar las respuestas de Chuwi a cada persona.
    """
    if not user:
        return
    user_id = user.get("id", "")
    if not user_id:
        return
    try:
        from backend.core import memory as _mem
        _key = f"employee_patterns_{user_id}"
        _existing = _mem.recall(STORE_ID, _key) or ""

        # Actualizar resumen con lo nuevo (no guardar toda la historia, solo el patrón)
        _action_label = {
            "rebajar": "rebaja precios", "donar": "dona productos",
            "retirar": "retira productos", "mover": "mueve stock", "revisar": "revisa pasillos",
        }.get(action_type, "completa acciones")
        _hour_label = "mañana" if hour < 12 else "tarde" if hour < 18 else "noche"
        _pattern = f"Habitualmente {_action_label} por la {_hour_label}."

        if _pattern not in _existing:
            _new = f"{_pattern} {_existing}"[:250]
            _mem.remember(STORE_ID, _key, _new.strip())
    except Exception:
        pass


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
    employee_memory = ""
    if user:
        role = user.get("role", "staff")
        name = user.get("email", "").split("@")[0] or "empleado"
        user_id = user.get("id", "")
        if role in ("admin", "manager"):
            role_hint = f"\nHablas con {name}, encargado/gestor. Da respuestas con contexto estratégico y acceso completo."
        else:
            role_hint = f"\nHablas con {name}, personal de tienda. Da instrucciones concretas e inmediatas."

        # Cross-session memory: patrones de este empleado específico
        if user_id:
            try:
                from backend.core import memory as _mem
                _emp_key = f"employee_patterns_{user_id}"
                _emp_data = _mem.recall(STORE_ID, _emp_key)
                if _emp_data:
                    employee_memory = f"\n\nPATRONES DE {name.upper()}: {_emp_data[:200]}"
            except Exception:
                pass

    context_block = "\n".join(context_lines)
    return (
        CHUWI_SYSTEM
        + role_hint
        + employee_memory
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
        _invalidate_user_cache(update.effective_user.id)
        await update.message.reply_text(
            f"✅ Cuenta desvinculada, {tg_name}.\n\n"
            "Tu Telegram ya no está conectado a MermaOps.\n"
            "Para volver a vincular abre la app → Perfil → Telegram.",
        )
        logger.info(f"[chuwi] Usuario {user_id} desvinculado de Telegram")
    except Exception as e:
        await update.message.reply_text("Error al desvincular tu cuenta. Inténtalo de nuevo.")


async def _cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Desvincula el Telegram del usuario autenticado."""
    user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
    await _do_unlink_telegram(update, user)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja cualquier mensaje de texto — el núcleo conversacional del agente."""
    # Solo chats privados
    if update.effective_chat and update.effective_chat.type != "private":
        return

    tg_user = update.effective_user
    _loop = asyncio.get_running_loop()

    # Rate limiting: máximo 1 mensaje cada 2 segundos por usuario
    import time as _time
    _now = _time.monotonic()
    _last = _user_last_msg.get(str(tg_user.id), 0.0)
    if _now - _last < _RATE_LIMIT_SECONDS:
        await update.message.reply_text("⏳ Un momento, proceso tu mensaje anterior...")
        return
    _user_last_msg[str(tg_user.id)] = _now
    _cleanup_stale_caches()
    # _get_user hace una llamada síncrona a Supabase — mover a executor para no bloquear
    user = await _loop.run_in_executor(None, _get_user, tg_user.id)

    # Registrar/actualizar en telegram_users: fire-and-forget para no bloquear
    asyncio.ensure_future(_loop.run_in_executor(
        None, _upsert_telegram_user,
        str(tg_user.id), tg_user.username,
        str(update.effective_chat.id), user,
    ))

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

    # ── Proactive intent trigger detection ──────────────────────────────────
    # Detecta "avísame cuando X". Si lo encuentra, guarda trigger y responde directamente.
    # No continúa al loop del agente — evitar doble respuesta.
    _trigger = detect_proactive_trigger(user_text, user_id, STORE_ID)
    if _trigger:
        await update.message.reply_text(
            f"✅ Listo. Te avisaré cuando: <b>{_trigger['condition'][:100]}</b>\n\n"
            f"Monitorizo esto automáticamente cada 30 minutos y te mando un DM si se cumple.",
            parse_mode="HTML",
            reply_markup=_back_keyboard()
        )
        return  # no continuar — la respuesta ya está dada

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
    _INTENT_LOADING = {
        "consulta_acciones":   "⚡ Revisando acciones pendientes...",
        "consulta_estado":     "📊 Cargando estado de la tienda...",
        "consulta_brief":      "📋 Leyendo el brief del día...",
        "consulta_ruta":       "🗺 Generando ruta del día...",
        "completar_accion":    "✅ Procesando acción...",
        "consulta_stats":      "📈 Calculando estadísticas...",
        "consulta_donaciones": "❤️ Cargando datos de donaciones...",
        "consulta_prediccion": "🔮 Consultando predicción...",
        "escaneo_producto":    "📸 Analizando producto...",
        "pregunta_libre":      "💬 Chuwi está pensando...",
    }
    _loading_msg = _INTENT_LOADING.get(intent_tag, "⌛ Un momento...")
    placeholder = await update.message.reply_text(_loading_msg)

    # Typing indicator continuo mientras el agente trabaja (cada 4s)
    async def _keep_typing():
        while True:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(4.0)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    typing_task = asyncio.create_task(_keep_typing())

    try:
        response, tools_used = await asyncio.wait_for(
            _run_agent_loop(
                context.bot, placeholder, chat_history, user_text, user,
                intent_tag=intent_tag, intent_context=intent_context,
            ),
            timeout=55.0,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[chuwi] timeout 55s en agent loop para user={user_id[:8] if user_id else '?'}")
        response = (
            "⏱ <b>Tardé demasiado.</b>\n\n"
            "Kuine está procesando algo complejo. Prueba de nuevo o sé más específico.\n"
            "<i>Ej: «¿qué acciones hay?» · «muéstrame los críticos»</i>"
        )
        tools_used = []
        retry_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Reintentar", callback_data="cmd:acciones"),
            InlineKeyboardButton("📋 Brief", callback_data="cmd:brief"),
        ]])
        try:
            await placeholder.edit_text(response, parse_mode=ParseMode.HTML, reply_markup=retry_kb)
        except Exception:
            pass
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

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
    _loop = asyncio.get_running_loop()
    user = await _loop.run_in_executor(None, _get_user, update.effective_user.id)
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

        caption = (update.message.caption or "").strip()

        loop = asyncio.get_running_loop()

        # Detectar si es análisis de estantería/sección completa
        _shelf_keywords = ["pasillo", "sección", "seccion", "lineal", "estantería", "estanteria", "zona", "área", "area"]
        _is_shelf = any(kw in caption.lower() for kw in _shelf_keywords) or len(photo_bytes) > 400_000

        def run_vision():
            if _is_shelf:
                from backend.agents.vision import analyze_shelf, format_shelf_result
                import base64 as _b64
                _img_b64 = _b64.b64encode(bytes(photo_bytes)).decode()
                # Extraer pasillo del caption si lo dice
                _pasillo = ""
                for word in caption.split():
                    if word.isdigit():
                        _pasillo = word
                        break
                productos = analyze_shelf(_img_b64, pasillo=_pasillo)
                return {"_shelf": True, "productos": productos}, format_shelf_result(productos, _pasillo)
            else:
                from backend.agents.vision import analyze_from_telegram_file, format_vision_result
                result = analyze_from_telegram_file(
                    file_bytes=bytes(photo_bytes),
                    product_name=caption or "",
                )
                return result, format_vision_result(result)

        result, formatted = await loop.run_in_executor(None, run_vision)

        action = "revisar"
        urgency = "normal"
        if result.get("_shelf"):
            productos = result.get("productos", [])
            action = "revisar"
            urgency = "hoy" if any(p.get("urgencia") in ("inmediata", "hoy") for p in productos) else "normal"
        else:
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

        # Actualizar patrones del empleado — usa análisis visual regularmente
        _update_employee_patterns(user, "revisar", datetime.now().hour)

    except Exception as e:
        logger.error(f"[chuwi] Error en análisis visual: {e}", exc_info=True)
        await placeholder.edit_text(
            f"No he podido analizar la foto: {e}\n\n"
            "Puedes escanear el código de barras escribiéndolo directamente."
        )


async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Inline query — el empleado escribe @ChuwiMermaOpsBot <producto> en cualquier chat
    y recibe en tiempo real el estado de ese producto: urgencia, días restantes y acción recomendada.
    No requiere abrir el bot. Responde en <2s usando solo datos de BD (sin LLM).
    """
    query = update.inline_query
    if not query:
        return

    search = (query.query or "").strip().lower()
    results: list[InlineQueryResultArticle] = []

    try:
        # Buscar productos que coincidan con el texto
        batches = database.get_batches_expiring_soon(STORE_ID, days=30)

        matches = [
            b for b in batches
            if search == "" or search in (b.get("products") or {}).get("name", "").lower()
        ][:8]

        if not matches and search:
            # Nada encontrado
            results.append(InlineQueryResultArticle(
                id="noresult",
                title=f"Sin resultados para '{search}'",
                description="Prueba con otro nombre de producto",
                input_message_content=InputTextMessageContent(
                    f"Kuine: no encontré productos que coincidan con '{search}'."
                ),
            ))
        elif not matches:
            results.append(InlineQueryResultArticle(
                id="hint",
                title="Escribe el nombre de un producto",
                description="Ej: baguette, leche, pollo...",
                input_message_content=InputTextMessageContent(
                    "Escribe @ChuwiMermaOpsBot + nombre del producto para ver su estado."
                ),
            ))
        else:
            for i, batch in enumerate(matches):
                product = batch.get("products") or {}
                name = product.get("name", "Producto")
                pasillo = product.get("pasillo", "?")
                qty = batch.get("quantity", 0)
                exp = batch.get("expiry_date", "")
                urgency = batch.get("urgency", "normal")

                try:
                    from datetime import date
                    days_left = (date.fromisoformat(exp) - date.today()).days if exp else 999
                except Exception:
                    days_left = 999

                urgency_icon = {
                    "critico": "🔴", "alto": "🟡", "normal": "🟢", "caducado": "⚫"
                }.get(urgency, "⚪")

                if days_left <= 0:
                    estado = "CADUCADO"
                    urgency_icon = "⚫"
                elif days_left <= 2:
                    estado = f"CRÍTICO — {days_left} día(s)"
                    urgency_icon = "🔴"
                elif days_left <= 5:
                    estado = f"ALTO — {days_left} días"
                    urgency_icon = "🟡"
                else:
                    estado = f"{days_left} días"

                title = f"{urgency_icon} {name}"
                desc = f"Pasillo {pasillo} | {qty} uds | {estado}"
                msg = (
                    f"{urgency_icon} <b>{name}</b>\n"
                    f"Pasillo {pasillo} | {qty} unidades\n"
                    f"Caduca: {exp} ({estado})\n"
                    f"Abre Chuwi para gestionar esta acción."
                )
                results.append(InlineQueryResultArticle(
                    id=f"batch_{i}_{batch.get('id','')[:8]}",
                    title=title,
                    description=desc,
                    input_message_content=InputTextMessageContent(
                        msg, parse_mode=ParseMode.HTML
                    ),
                ))
    except Exception as e:
        logger.warning(f"[inline_query] error: {e}")
        results.append(InlineQueryResultArticle(
            id="error",
            title="Error al consultar datos",
            description="El sistema está procesando. Inténtalo en un momento.",
            input_message_content=InputTextMessageContent("Kuine no pudo responder. Inténtalo en el chat."),
        ))

    await query.answer(results, cache_time=30, is_personal=True)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Transcribe nota de voz con Google Speech Recognition y la procesa con el agente."""
    tg_user = update.effective_user
    user_id = str(tg_user.id)
    _loop = asyncio.get_running_loop()
    user = await _loop.run_in_executor(None, _get_user, tg_user.id)

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
        _persist_conversation_message(
            chat_key=chat_key,
            store_id=STORE_ID,
            telegram_user_id=user_id,
            user_text=f"[Voz] {transcription}",
            response=response,
            tools_used=tools_used,
            intent_tag=intent_tag,
        )

        session_id = _session_cache.get(user_id)
        if session_id:
            kuine_used = 1 if "analyze_product" in tools_used else 0
            try:
                database.increment_session_stats(session_id, len(tools_used), kuine_used)
            except Exception:
                pass

        # Reflexion Loop: aprende de las voz también (fire-and-forget)
        if "analyze_product" in tools_used:
            from backend.core import reflexion as _rfx
            asyncio.ensure_future(_rfx.async_generate_and_save(
                STORE_ID, f"[Voz] {transcription}", response
            ))

        # Actualizar patrones del empleado — usa voz regularmente
        _update_employee_patterns(user, "revisar", datetime.now().hour)

        keyboard = _smart_keyboard(response, _is_manager(user))
        await placeholder.edit_text(
            _md_to_html(f"🎙️ Escuché: {transcription}\n\n{response}"),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

        # Respuesta de voz TTS — Chuwi responde también con nota de voz
        try:
            _tts_client = _get_openai()
            if _tts_client:
                import io as _io
                _tts_resp = _tts_client.audio.speech.create(
                    model="tts-1",
                    voice="nova",  # voz femenina, clara, natural
                    input=response[:500],  # limitar para no generar audio muy largo
                )
                _audio_bytes = _io.BytesIO(_tts_resp.content)
                _audio_bytes.name = "chuwi_response.mp3"
                await update.message.reply_voice(
                    voice=_audio_bytes,
                    caption="🔊 Chuwi también te responde en voz",
                )
        except Exception as _tts_e:
            logger.debug(f"[chuwi_tts] TTS no disponible: {_tts_e}")

    except Exception as e:
        logger.error(f"[chuwi] voice error: {e}")
        await placeholder.edit_text("No pude procesar el audio. Inténtalo de nuevo.")


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
        BotCommand("pedido", "Sugerencia de pedido semanal (encargado)"),
        BotCommand("costes", "Coste de IA y ahorro por caché (encargado)"),
        BotCommand("stats", "Estadísticas de uso de IA: tokens, coste, modelos"),
        BotCommand("reflexiones", "Lecciones aprendidas por Chuwi (Reflexion Loop)"),
        BotCommand("hoy", "Resumen express del día en segundos"),
        BotCommand("tiempo", "Tiempo de la tienda hoy y 5 días 🌤"),
        BotCommand("insights", "Insights IA estratégicos del día ✨ (encargado)"),
        BotCommand("almacen", "Stock del almacén con alertas de caducidad próxima 📦"),
        BotCommand("comparativa", "Benchmark vs otras tiendas de la cadena 📊 (encargado)"),
        BotCommand("perfil", "Ver y configurar parámetros de la tienda ⚙️ (encargado)"),
    ])


def chat_direct(
    message: str,
    history: list[dict],
    user: Optional[dict] = None,
) -> tuple[str, list[str]]:
    """
    Chat directo con Chuwi desde la app Flutter (sin Telegram).
    Usa el mismo loop agéntico con herramientas reales y memoria conversacional.
    """
    system_extra = _build_agent_system(user)
    intent = _classify_intent(message)
    intent_ctx = _build_intent_context(intent, STORE_ID)

    compact_history = _compact_history(list(history))

    response, tool_trace = llm.run_agentic_loop(
        prompt=message,
        tools=CHUWI_TOOLS,
        tool_executor=lambda name, inp: _execute_tool_sync(name, inp, user),
        system_extra=system_extra + (f"\n\n{intent_ctx}" if intent_ctx else ""),
        max_tokens=1024,
        max_iterations=MAX_AGENT_ITERATIONS,
        initial_messages=compact_history,
    )

    tool_names = [
        t.get("tool") if isinstance(t, dict) else str(t)
        for t in tool_trace if t is not None
    ]

    # Update employee cross-session patterns if they completed actions via chat
    if user and any(t == "complete_action" for t in tool_names):
        _update_employee_patterns(user, "completar", datetime.now().hour)

    return response, tool_names


async def chat_direct_stream(
    message: str,
    history: list[dict],
    user: Optional[dict] = None,
):
    """
    Versión streaming de chat_direct — genera eventos SSE en tiempo real.
    Cada token de Claude se emite inmediatamente al cliente.

    Eventos emitidos:
    - {"type": "tool", "name": "...", "label": "..."} — cuando Claude llama una herramienta
    - {"type": "token", "content": "..."} — cada fragmento de texto generado
    - {"type": "done", "tools": [...], "full_response": "..."} — al finalizar
    - {"type": "error", "message": "..."} — si algo falla

    Esto transforma la UX: primer token en <400ms en vez de esperar 5-10s.
    Patrón producción: Perplexity, Claude, ChatGPT usan SSE para sus chats.
    """
    system_extra = _build_agent_system(user)
    intent = _classify_intent(message)
    intent_ctx = _build_intent_context(intent, STORE_ID)

    compact_history = _compact_history(list(history))
    messages = compact_history + [{"role": "user", "content": message}]
    system_full = system_extra + (f"\n\n{intent_ctx}" if intent_ctx else "")

    client = llm.get_async_client()
    all_tools_used: list[str] = []
    full_response = ""
    iteration = 0

    try:
        while iteration < MAX_AGENT_ITERATIONS:
            iteration += 1
            pending_tools: list[dict] = []
            current_tool: Optional[dict] = None
            final_content: list = []

            stream_kwargs = {
                "model": llm.MODEL,
                "max_tokens": 1024,
                "system": llm._cached_system(system_full),
                "tools": CHUWI_TOOLS,
                "tool_choice": {"type": "auto"},
                "messages": messages,
            }

            async with client.messages.stream(**stream_kwargs) as stream:
                async for event in stream:
                    etype = getattr(event, "type", "")

                    if etype == "content_block_start":
                        block = getattr(event, "content_block", None)
                        btype = getattr(block, "type", "")
                        if btype == "tool_use":
                            current_tool = {"id": block.id, "name": block.name, "input": ""}
                            label = _TOOL_LABELS.get(block.name, block.name)
                            yield {"type": "tool", "name": block.name, "label": label}

                    elif etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        dtype = getattr(delta, "type", "")
                        if dtype == "text_delta":
                            token = delta.text
                            full_response += token
                            yield {"type": "token", "content": token}
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

            # Ejecutar herramientas en paralelo
            ev_loop = asyncio.get_running_loop()

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
            full_response = ""  # reset buffer for next iteration

    except Exception as e:
        logger.error(f"[chat_stream] error: {e}")
        yield {"type": "error", "message": "Error procesando la respuesta. Inténtalo de nuevo."}
        return

    yield {"type": "done", "tools": all_tools_used, "full_response": full_response}


def run() -> None:
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no está definido en .env")

    app = ApplicationBuilder().token(TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("menu", handle_menu))

    async def handle_tour(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_tour(update, ctx, user, is_callback=False)

    async def handle_ruta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _start_route_mode(update, ctx, user)

    app.add_handler(CommandHandler("tour", handle_tour))
    app.add_handler(CommandHandler("ruta", handle_ruta))

    async def handle_donar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_donar_flow(update, ctx, user, is_callback=False)

    async def handle_esg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_esg(update, ctx, user, is_callback=False)

    async def handle_prediccion(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_prediccion(update, ctx, user, is_callback=False)

    async def handle_tiempo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_tiempo(update, ctx, user, is_callback=False)

    async def handle_insights(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_insights(update, ctx, user, is_callback=False)

    async def handle_almacen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_almacen(update, ctx, user, is_callback=False)

    async def handle_comparativa(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_comparativa(update, ctx, user, is_callback=False)

    async def handle_perfil_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Muestra perfil o actualiza parámetros: /perfil ciudad Madrid, /perfil lat 40.4 lon -3.7"""
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        if not _is_manager(user):
            await update.message.reply_text("🔒 Solo para encargados.", reply_markup=_back_keyboard())
            return
        args = ctx.args or []
        if not args:
            await _action_perfil(update, ctx, user, is_callback=False)
            return
        # /perfil ciudad Madrid / /perfil zona residencial / /perfil tamano grande / /perfil lat X lon Y
        key = args[0].lower()
        val = " ".join(args[1:])
        valid_keys = {"ciudad", "zona", "tamano", "tamaño"}
        try:
            loop = asyncio.get_running_loop()
            def _update_cfg():
                store = database.get_db().table("stores").select("config").eq("id", STORE_ID).single().execute()
                cfg = dict(store.data.get("config") or {})
                if key == "ciudad":
                    cfg["city"] = val
                elif key in ("zona", "zone"):
                    cfg["zone_type"] = val
                elif key in ("tamano", "tamaño", "size"):
                    cfg["store_size"] = val
                elif key == "lat" and len(args) >= 4 and args[2].lower() == "lon":
                    cfg["lat"] = float(args[1])
                    cfg["lon"] = float(args[3])
                else:
                    return None
                database.get_db().table("stores").update({"config": cfg}).eq("id", STORE_ID).execute()
                return cfg
            new_cfg = await loop.run_in_executor(None, _update_cfg)
            if new_cfg is None:
                await update.message.reply_text(
                    "Uso: /perfil ciudad [ciudad] | /perfil zona [tipo] | /perfil tamano [pequeño/mediano/grande] | /perfil lat X lon Y",
                    reply_markup=_back_keyboard()
                )
            else:
                await update.message.reply_text(
                    f"✅ Perfil actualizado.\n\nUsa /tiempo para ver el tiempo con las nuevas coordenadas.",
                    reply_markup=_back_keyboard()
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Error actualizando perfil: {str(e)[:80]}", reply_markup=_back_keyboard())

    app.add_handler(CommandHandler("donar", handle_donar))
    app.add_handler(CommandHandler("esg", handle_esg))
    app.add_handler(CommandHandler("prediccion", handle_prediccion))
    app.add_handler(CommandHandler("tiempo", handle_tiempo))
    app.add_handler(CommandHandler("insights", handle_insights))
    app.add_handler(CommandHandler("almacen", handle_almacen))
    app.add_handler(CommandHandler("comparativa", handle_comparativa))
    app.add_handler(CommandHandler("perfil", handle_perfil_cmd))

    async def handle_merma(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_merma(update, ctx, user, is_callback=False)

    async def handle_donaciones(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_donaciones(update, ctx, user, is_callback=False)

    async def handle_proveedores(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_proveedores(update, ctx, user, is_callback=False)

    async def handle_brief(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_brief(update, ctx, user, is_callback=False)

    async def handle_acciones(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_acciones(update, ctx, user, is_callback=False)

    async def handle_scan_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Permite /scan 8410031001001 directamente como comando Telegram."""
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
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
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_stats(update, ctx, user, is_callback=False)

    async def handle_hoy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Resumen express del día: sin LLM, solo BD, responde en <1s."""
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        if not user:
            await update.message.reply_text("Vincula tu cuenta primero con /start.")
            return
        try:
            pending = database.get_pending_actions(STORE_ID)
            criticos = [a for a in pending if (a.get("priority_score") or 0) >= 85]
            altos = [a for a in pending if 65 <= (a.get("priority_score") or 0) < 85]
            semaforo = "🔴" if len(criticos) >= 5 else "🟡" if len(criticos) >= 2 else "🟢"

            lines = [
                f"{semaforo} <b>Estado del día — {date.today().isoformat()}</b>\n",
                f"🔴 Críticos: <b>{len(criticos)}</b>",
                f"🟡 Altos: <b>{len(altos)}</b>",
                f"📋 Total pendiente: <b>{len(pending)}</b>",
            ]
            if criticos:
                lines.append("\n<b>Más urgentes:</b>")
                for a in criticos[:3]:
                    batch = a.get("batches") or {}
                    prod = (batch.get("products") or {})
                    name = prod.get("name", "Producto")
                    pasillo = prod.get("pasillo", "?")
                    score = a.get("priority_score", 0)
                    lines.append(f"  • {name} | Pasillo {pasillo} | {score}/100")

            lines.append("\nUsa /acciones para ver la lista completa.")
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Ver acciones", callback_data="cmd:acciones"),
                InlineKeyboardButton("🗺 Ruta del día", callback_data="cmd:ruta"),
            ]])
            await update.message.reply_text(
                "\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    app.add_handler(CommandHandler("hoy", handle_hoy))
    app.add_handler(CommandHandler("stats", handle_stats))
    app.add_handler(CommandHandler("merma", handle_merma))
    app.add_handler(CommandHandler("donaciones", handle_donaciones))
    app.add_handler(CommandHandler("proveedores", handle_proveedores))
    app.add_handler(CommandHandler("brief", handle_brief))
    app.add_handler(CommandHandler("acciones", handle_acciones))
    app.add_handler(CommandHandler("scan", handle_scan_cmd))

    async def handle_citar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        args = ctx.args or []
        await _action_citar(update, ctx, user, is_callback=False, cmd_args=args)

    app.add_handler(CommandHandler("citar", handle_citar))

    async def handle_pedido(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Sugerencia de pedido semanal para encargados."""
        user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
        await _action_pedido(update, ctx, user, is_callback=False)

    app.add_handler(CommandHandler("pedido", handle_pedido))

    # Comandos informativos y de sistema — definidos en chuwi_commands.py
    # Import lazy para evitar circularidad (chuwi_commands importa de chuwi en runtime)
    from backend.core import chuwi_commands as _cmds
    app.add_handler(CommandHandler("agentes", _cmds._cmd_agentes))
    app.add_handler(CommandHandler("kuine", _cmds._cmd_kuine))
    app.add_handler(CommandHandler("demo", _cmds._cmd_demo))
    app.add_handler(CommandHandler("simular", _cmd_simular))
    app.add_handler(CommandHandler("yo", _cmds._cmd_yo))
    app.add_handler(CommandHandler("estado", _cmds._cmd_estado))
    app.add_handler(CommandHandler("criticos", _cmds._cmd_criticos))
    app.add_handler(CommandHandler("ayuda", _cmds._cmd_ayuda))
    app.add_handler(CommandHandler("logout", _cmd_logout))
    app.add_handler(CommandHandler("informe", _cmds._cmd_informe))
    app.add_handler(CommandHandler("semana", _cmds._cmd_semana))
    app.add_handler(CommandHandler("hoja", _cmds._cmd_hoja))
    app.add_handler(CommandHandler("costes", _cmds._cmd_costes))
    app.add_handler(CommandHandler("reflexiones", _cmds._cmd_reflexiones))
    app.add_handler(CommandHandler("mapa", _cmds._cmd_mapa))
    app.add_handler(CommandHandler("historial", _cmds._cmd_historial))
    app.add_handler(CommandHandler("merma7", _cmds._cmd_merma7))

    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(InlineQueryHandler(handle_inline_query))

    logger.info("[chuwi] Agente activo. Esperando mensajes en Telegram...")
    app.run_polling(drop_pending_updates=True)
