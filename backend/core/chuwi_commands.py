"""
chuwi_commands — Handlers de comandos Telegram (/agentes, /kuine, /demo, ...).

Importa utilidades de chuwi.py en tiempo de ejecución (no a nivel de módulo)
para evitar imports circulares. El patrón es: chuwi.py importa este módulo
dentro de run() (llamada en runtime), por lo que chuwi ya está completamente
cargado cuando Python resuelve los imports de este módulo.

Módulos del sistema Chuwi:
  chuwi.py           — núcleo agéntico, handlers principales, run()
  chuwi_commands.py  — handlers de comandos (/cmd_*) y helpers PDF
  chuwi_persistence.py — estado, historial, caché de usuario, Supabase
  chuwi_intent.py    — clasificador de intención 0-token
"""
from __future__ import annotations

import asyncio
import html
from datetime import date
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from backend.core import database, llm
from backend.core.chuwi_persistence import (
    STORE_ID, _get_user, _is_manager,
)


# ── Utilities re-exported from chuwi.py (cargadas en runtime) ─────────────────
# No importar a nivel de módulo — chuwi_commands se carga desde dentro de run()
# cuando chuwi ya está en sys.modules. Importar aquí es seguro.

def _back_keyboard():
    from backend.core.chuwi import _back_keyboard as _bk
    return _bk()


def _safe_err(e: Exception) -> str:
    from backend.core.chuwi import _safe_err as _se
    return _se(e)


async def _typing_loop(bot, chat_id: int, done: asyncio.Event) -> None:
    from backend.core.chuwi import _typing_loop as _tl
    await _tl(bot, chat_id, done)


async def _generate_brief_background(bot, chat_id: int) -> None:
    """Wrapper: genera brief en background sin requerir user (demo context)."""
    from backend.core.chuwi import _generate_brief_background as _gbb
    await _gbb(bot, chat_id, user=None)


# ── Texto de presentación de los agentes ─────────────────────────────────────

_AGENTES_TEXT = """🤖 <b>LOS 12 AGENTES DE MERMAOPS</b>

<b>KUINE</b> — Orquestador (Claude Opus 4.7)
El cerebro del sistema. Investiga la tienda con 16 herramientas, razona con adaptive thinking y coordina todo. Funciona solo: 7 cron jobs (07:30, 12:00, 20:00…).
<i>Demo: /brief genera el análisis completo ahora mismo.</i>

<b>EVALUADOR</b> — Riesgo por producto (Claude Sonnet 4.6)
Score 0-100 por lote. Para score ≥65: extended thinking con normativa y margen mínimo. Para score ≥90 y &gt;30€: consenso de 3 instancias en paralelo.
<i>Demo: /criticos muestra los productos con score más alto.</i>

<b>FORKMERGE</b> — Evaluación paralela (3×Sonnet + Opus)
Para productos con valor &gt;50€ o ya caducados: 3 hipótesis simultáneas (clearance, margin, donation) sintetizadas por Opus. Patrón fork-merge de Anthropic (2024).

<b>VALIDADOR</b> — Adversarial
El único agente que puede REVERTIR decisiones. Detecta: precio &lt; coste, CRÍTICO sin acción, FEFO violations. 23 ataques adversariales probados → 100% neutralizados.

<b>CONSENSO</b> — Votación paralela
3 evaluadores en paralelo para casos extremos (score ≥90 AND valor ≥30€). Árbitro con Claude Opus en empate. Regla: la decisión solo pasa si ≥2/3 coinciden.

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


# ── Comandos informativos ─────────────────────────────────────────────────────

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
    msg = await update.message.reply_text("Consultando estado de Kuine...")
    try:
        loop = asyncio.get_running_loop()
        brief, pending = await asyncio.gather(
            loop.run_in_executor(None, database.get_latest_brief, STORE_ID),
            loop.run_in_executor(None, database.get_pending_actions, STORE_ID),
        )
        critical = [a for a in pending if a.get("priority_score", 0) >= 85]
        alto = [a for a in pending if 65 <= a.get("priority_score", 0) < 85]

        last_brief_date = brief.get("date", "nunca") if brief else "sin brief hoy"
        last_summary = (brief.get("summary") or "")[:200] if brief else ""

        text = (
            f"🧠 <b>KUINE — Estado del orquestador</b>\n\n"
            f"Modelo: Claude Opus 4.7 (adaptive thinking)\n"
            f"Herramientas disponibles: 16\n"
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
        await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception as e:
        await msg.edit_text(_safe_err(e))


async def _cmd_demo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Controla la simulación temporal de la demo: /demo 2, /demo reset, /demo estado."""
    args = context.args or []
    cmd = args[0].lower() if args else "ayuda"

    if cmd == "reset":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Sí, resetear", callback_data="demo:confirm_reset"),
            InlineKeyboardButton("❌ Cancelar", callback_data="demo:cancel"),
        ]])
        await update.message.reply_text(
            "⚠️ <b>¿Resetear el estado de la tienda?</b>\n\n"
            "Esto vuelve al estado inicial del Súper Martínez.\n"
            "Todos los avances de hoy se perderán.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return

    try:
        days = float(cmd)
    except ValueError:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏩ Avanzar 1 día", callback_data="demo:advance:1")],
            [InlineKeyboardButton("⏩⏩ Avanzar 3 días", callback_data="demo:advance:3")],
            [InlineKeyboardButton("♻️ Reset al estado inicial", callback_data="demo:reset_ask")],
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

    if days > 5:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✅ Sí, avanzar {days:.0f} días", callback_data=f"demo:advance:{int(days)}"),
            InlineKeyboardButton("❌ Cancelar", callback_data="demo:cancel"),
        ]])
        await update.message.reply_text(
            f"⚠️ Vas a simular <b>{days:.0f} días</b> de golpe.\n"
            "Esto puede generar muchos críticos y alertas. ¿Continuar?",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
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
        await msg.edit_text(_safe_err(e))


async def _cmd_yo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el perfil del usuario: ID Telegram, vinculación con app, rol."""
    tg_id = update.effective_user.id
    tg_name = update.effective_user.first_name or "Usuario"
    user = await asyncio.get_running_loop().run_in_executor(None, _get_user, tg_id)

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

    role = user.get("role", "staff")
    role_info = {
        "admin":   ("👑", "ADMIN",    "Acceso completo — todas las funciones del sistema"),
        "manager": ("🔑", "ENCARGADO","Acceso completo — proveedores, informes, brief manual"),
        "staff":   ("👷", "EMPLEADO", "Acciones diarias — ruta, estado, completar acciones"),
    }.get(role, ("👷", role.upper(), "Personal de tienda"))
    role_emoji, role_label, role_desc = role_info

    if role in ("admin", "manager"):
        access_lines = (
            "Tienes acceso a TODO:\n"
            "- /brief — generar brief manualmente\n"
            "- /proveedores — ficha de proveedores\n"
            "- /pedido — pedido semanal\n"
            "- /esg — impacto CO2 y deducción fiscal\n"
            "- /prediccion — riesgo a 7 dias\n"
            "- /demo — simular paso del tiempo"
        )
    else:
        access_lines = (
            "Tienes acceso a operaciones del dia:\n"
            "- /estado — semaforo de la tienda\n"
            "- /acciones — que hacer ahora\n"
            "- /ruta — ruta guiada por pasillos\n"
            "- /merma — merma registrada\n"
            "- /donaciones — impacto social\n"
            "Necesitas rol encargado para: brief, proveedores, pedido, ESG"
        )

    await update.message.reply_text(
        f"┌{'─' * 30}┐\n"
        f"│  👤  <b>TU PERFIL</b>\n"
        f"└{'─' * 30}┘\n\n"
        f"Nombre: <b>{html.escape(tg_name)}</b>\n"
        f"Email: {html.escape(user.get('email', '?'))}\n"
        f"ID Telegram: <code>{tg_id}</code>\n"
        f"Tienda: <code>{STORE_ID}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Rol: {role_emoji} <b>{role_label}</b>\n"
        f"<i>{role_desc}</i>\n\n"
        f"{access_lines}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Estado: ✅ Vinculado\n"
        f"Para desvincular: <code>desconectar telegram</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Menu", callback_data="cmd:menu"),
        ]]),
    )


async def _cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Estado de la tienda en tiempo real — funciona sin estar vinculado."""
    msg = await update.message.reply_text("🔍 Consultando estado de la tienda...")
    try:
        loop = asyncio.get_running_loop()
        pending = await loop.run_in_executor(None, database.get_pending_actions, STORE_ID)
        batches = await loop.run_in_executor(None, database.get_batches_expiring_soon, STORE_ID, 7)
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
    except Exception:
        await msg.edit_text("No pude obtener el estado. Inténtalo de nuevo.")


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
        await msg.edit_text(_safe_err(e))


async def _cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista completa de comandos con descripción."""
    user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
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
        "/pedido — Sugerencia de pedido semanal\n"
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
    await update.message.reply_text(base + (manager_cmds if manager else "") + tip, parse_mode=ParseMode.HTML)


async def _cmd_costes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el coste real de tokens y el ahorro por prompt caching."""
    user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
    if not _is_manager(user):
        await update.message.reply_text("🔒 Solo encargados pueden ver los costes del sistema.")
        return

    stats = llm.get_cost_summary()
    total    = stats["total_usd"]
    saved    = stats["saved_usd"]
    pct      = stats["saving_pct"]
    calls    = stats["calls"]
    hits     = stats["cache_hit_pct"]
    inp_k    = stats["input_tokens"] // 1000
    out_k    = stats["output_tokens"] // 1000
    cached_k = stats["cache_read_tokens"] // 1000
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
    """Muestra las lecciones del Reflexion Loop aprendidas por Chuwi."""
    user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
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


# ── PDF helpers ───────────────────────────────────────────────────────────────

def _generate_brief_pdf_bytes() -> bytes | None:
    try:
        brief = database.get_latest_brief(STORE_ID)
        if not brief:
            return None
        pending = database.get_pending_actions(STORE_ID)
        critical_actions = [a for a in pending if (a.get("priority_score") or 0) >= 85]
        high_actions = [a for a in pending if 65 <= (a.get("priority_score") or 0) < 85]
        from backend.core.pdf_generator import generate_brief_pdf
        return generate_brief_pdf(
            brief_text=brief.get("summary", ""),
            brief_date=brief.get("date", ""),
            critical_count=len(critical_actions),
            high_count=len(high_actions),
            value_at_risk=float(brief.get("value_at_risk", 0.0) or 0.0),
            actions_count=brief.get("actions_count", len(pending)),
            critical_actions=critical_actions,
            high_actions=high_actions,
        )
    except Exception:
        return None


def _generate_weekly_pdf_bytes() -> bytes | None:
    try:
        from backend.core.pdf_generator import generate_weekly_pdf
        merma_week = database.get_merma_history(STORE_ID, days=7)
        merma_eur = sum(float(l.get("value_lost", 0)) for l in merma_week)
        merma_qty = sum(int(l.get("quantity_lost", 0)) for l in merma_week)
        donations = database.get_donation_stats(STORE_ID, days=7)
        stored = database.get_weekly_reports(STORE_ID, limit=1)
        if stored and stored[0].get("content"):
            report_text = stored[0]["content"]
        else:
            from backend.agents.reporter import generate_weekly_report
            report_text = generate_weekly_report(STORE_ID)
        return generate_weekly_pdf(
            report_text=report_text,
            merma_eur=merma_eur,
            merma_qty=merma_qty,
            donated_qty=donations.get("total_quantity", 0),
            donated_value=float(donations.get("total_value_donated", 0)),
        )
    except Exception:
        return None


async def _cmd_informe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Genera y envía el PDF del brief de hoy."""
    user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
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
    except Exception:
        done.set()
        await task
        await placeholder.edit_text("Error generando el PDF. Inténtalo de nuevo.")


async def _cmd_semana(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Genera y envía el PDF del informe semanal."""
    user = await asyncio.get_running_loop().run_in_executor(None, _get_user, update.effective_user.id)
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
            fecha = date.today().isoformat()
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
        await placeholder.edit_text(_safe_err(e))


# ── Demo callbacks ────────────────────────────────────────────────────────────

async def _handle_demo_callback(
    query, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    """Gestiona demo:advance:N y demo:reset desde botones inline."""
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "cancel":
        await query.edit_message_text("❌ Operación cancelada.")
        return

    if action == "reset_ask":
        # Botón del menú de ayuda → mostrar confirmación antes de resetear
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Sí, resetear", callback_data="demo:confirm_reset"),
            InlineKeyboardButton("❌ Cancelar", callback_data="demo:cancel"),
        ]])
        await query.edit_message_text(
            "⚠️ <b>¿Resetear el estado de la tienda?</b>\n\n"
            "Esto vuelve al estado inicial del Súper Martínez.\n"
            "Todos los avances de hoy se perderán.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return

    if action in ("reset", "confirm_reset"):
        await query.edit_message_text("♻️ Reiniciando estado...")
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: __import__(
                "backend.data.advance_demo", fromlist=["reset"]
            ).reset(STORE_ID))
            await query.edit_message_text("✅ Estado reiniciado.\nUsa /estado para ver el nuevo panorama.")
        except Exception as e:
            await query.edit_message_text(_safe_err(e))
        return

    if action == "advance":
        days = float(parts[2]) if len(parts) > 2 else 1.0
        await query.edit_message_text(
            f"⏩ <b>Simulando +{days:.0f} día(s)...</b>\n\n"
            "📦 Actualizando lotes y caducidades...",
            parse_mode=ParseMode.HTML,
        )
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

            # Build step-by-step summary
            n_critico = result.get("critical_now", 0)
            n_actions = result.get("actions_created", 0)
            n_completed = result.get("actions_completed", 0)
            n_stock = result.get("stock_reduced", 0)
            newly_critical = result.get("newly_critical", [])
            newly_high = result.get("newly_high", [])

            low_stock = result.get("low_stock_alerts", [])
            restock   = result.get("restock_orders", [])
            expired   = result.get("expired_products", [])

            lines = [f"✅ <b>+{days:.0f} día(s) — Super Martínez</b>", ""]

            if expired:
                lines.append(f"⚠️ Caducados: {', '.join(html.escape(n) for n in expired[:3])}")

            if newly_critical:
                lines.append(f"🔴 <b>Nuevos CRÍTICOS ({len(newly_critical)}):</b>")
                for name in newly_critical[:3]:
                    lines.append(f"  • {html.escape(name)}")
            if newly_high:
                lines.append(f"🟡 Alto riesgo: {', '.join(html.escape(n) for n in newly_high[:3])}")

            lines += ["", f"🛒 Ventas: <b>{n_stock} uds</b> | Acciones: <b>{n_actions}</b> nuevas | <b>{n_completed}</b> completadas"]

            if low_stock:
                lines.append(f"\n⚠️ <b>Stock bajo — pedir pronto:</b>")
                for name in low_stock[:3]:
                    lines.append(f"  • {html.escape(name)}")

            if restock:
                lines.append(f"\n📥 Pedido recibido: {', '.join(html.escape(r) for r in restock[:3])}")

            if n_critico > 0:
                lines += [
                    "",
                    "🤖 <b>Kuine analizando...</b> Brief en camino.",
                ]

            lines += ["", "Usa /criticos · /estado · /brief"]

            await query.edit_message_text(
                "\n".join(lines),
                parse_mode=ParseMode.HTML,
            )

            # Launch brief generation in background if there are criticals
            if n_critico > 0:
                asyncio.create_task(_generate_brief_background(
                    context.bot, query.message.chat_id
                ))

        except Exception as e:
            done.set()
            await task
            await query.edit_message_text(_safe_err(e))

    if action == "dia_completo":
        chat_id = query.message.chat_id
        await query.edit_message_text(
            "🌅 <b>Simulando día completo — Super Martínez</b>\n\n"
            "☀️ <b>07:00</b> — Predictor analiza riesgo y clima...",
            parse_mode=ParseMode.HTML,
        )
        try:
            loop = asyncio.get_running_loop()

            # Step 1: Predictor
            try:
                predict_result = await loop.run_in_executor(
                    None,
                    lambda: __import__(
                        "backend.agents.predictor", fromlist=["predict_merma_risk"]
                    ).predict_merma_risk(STORE_ID)
                )
                risk_level = predict_result.get("risk_level", "medio") if isinstance(predict_result, dict) else "medio"
            except Exception:
                risk_level = "medio"

            await context.bot.send_message(
                chat_id,
                f"✅ <b>07:00</b> — Predictor completado\n"
                f"Riesgo estimado: <b>{risk_level.upper()}</b>\n\n"
                "📋 <b>07:30</b> — Kuine iniciando análisis del inventario...",
                parse_mode=ParseMode.HTML,
            )

            # Step 2: Advance one day
            result = await loop.run_in_executor(
                None,
                lambda: __import__(
                    "backend.data.advance_demo", fromlist=["advance"]
                ).advance(1.0, store_id=STORE_ID)
            )

            n_critico = result.get("critical_now", 0)
            n_actions = result.get("actions_created", 0)
            n_completed = result.get("actions_completed", 0)
            n_stock = result.get("stock_reduced", 0)
            newly_critical = result.get("newly_critical", [])
            newly_high = result.get("newly_high", [])

            # Step 3: Show changes — full picture of what happened
            low_stock = result.get("low_stock_alerts", [])
            restock   = result.get("restock_orders", [])
            expired   = result.get("expired_products", [])
            wh_upd    = result.get("warehouse_updated", 0)

            lines = ["📊 <b>Resumen del día — Super Martínez</b>", ""]

            if expired:
                lines.append(f"⚠️ <b>Caducados hoy ({len(expired)}):</b>")
                for name in expired[:3]:
                    lines.append(f"  • {html.escape(name)} — retirar del lineal")

            if newly_critical:
                lines.append(f"\n🔴 <b>Nuevos CRÍTICOS ({len(newly_critical)}):</b>")
                for name in newly_critical[:4]:
                    lines.append(f"  • {html.escape(name)} — REBAJAR HOY")

            if newly_high:
                lines.append(f"\n🟡 <b>Riesgo Alto ({len(newly_high)}):</b>")
                for name in newly_high[:3]:
                    lines.append(f"  • {html.escape(name)} — vigilar")

            lines += ["", f"🛒 <b>Ventas del día:</b> {n_stock} uds vendidas del lineal"]
            if wh_upd:
                lines.append(f"🏪 <b>Almacén:</b> {wh_upd} movimientos de stock")

            if low_stock:
                lines.append(f"\n⚠️ <b>Stock bajo en almacén — HAY QUE PEDIR:</b>")
                for name in low_stock[:4]:
                    lines.append(f"  • {html.escape(name)} — menos de 5 uds")

            if restock:
                lines.append(f"\n📥 <b>Pedido recibido hoy (viernes):</b>")
                for item in restock[:4]:
                    lines.append(f"  • {html.escape(item)}")

            lines += ["", f"⚡ Acciones nuevas: <b>{n_actions}</b> | Personal completó: <b>{n_completed}</b>"]

            await context.bot.send_message(
                chat_id,
                "\n".join(lines),
                parse_mode=ParseMode.HTML,
            )

            # Step 4: Final message + brief
            await context.bot.send_message(
                chat_id,
                "✅ <b>Día completado.</b>\n\n"
                "🤖 Kuine generando brief del día...\n"
                "Recibirás el análisis completo en unos segundos.",
                parse_mode=ParseMode.HTML,
            )

            # Send Telegram alerts for criticals
            if n_critico > 0:
                try:
                    await loop.run_in_executor(
                        None,
                        lambda: __import__(
                            "backend.data.advance_demo", fromlist=["_send_day_telegram_messages"]
                        )._send_day_telegram_messages(STORE_ID, n_critico, days=1)
                    )
                except Exception:
                    pass

            # Background brief generation
            asyncio.create_task(_generate_brief_background(context.bot, chat_id))

        except Exception as e:
            await context.bot.send_message(chat_id, _safe_err(e))
