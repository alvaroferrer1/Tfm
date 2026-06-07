"""
telegram_formatter.py — Plantillas HTML con formato visual para mensajes de Chuwi.

Usa caracteres Unicode (━, •, ◉) y HTML de Telegram (no MarkdownV2).
Todos los textos se escapan antes de insertar en el HTML.
"""
from __future__ import annotations
import html
from datetime import date as _date


def _e(text) -> str:
    """Escapa para HTML de Telegram."""
    return html.escape(str(text))


def _semaforo_emoji(semaforo: str) -> str:
    s = semaforo.upper()
    if "ROJO" in s or "ALERTA" in s:
        return "🔴"
    if "AMARILLO" in s or "ATENCI" in s:
        return "🟡"
    return "🟢"


def _days_str(exp: str) -> str:
    if not exp:
        return "?"
    try:
        days = (_date.fromisoformat(exp) - _date.today()).days
        if days < 0:
            return f"<b>CADUCADO hace {-days}d</b>"
        if days == 0:
            return "<b>HOY</b>"
        return f"{days}d"
    except Exception:
        return "?"


# ── Brief del día ─────────────────────────────────────────────────────────────

def format_brief_card(
    brief_date: str = "",
    value_at_risk: float = 0.0,
    actions_count: int = 0,
    critical_count: int = 0,
    high_count: int = 0,
) -> str:
    """Compact card: stats only, no full summary. Safe for edit_message_text (≤4096)."""
    fecha = brief_date or _date.today().isoformat()
    semaforo = "🔴 ALERTA" if critical_count >= 3 else "🟡 ATENCIÓN" if critical_count >= 1 else "🟢 NORMAL"
    lines = [
        f"┌{'━' * 34}┐",
        f"│  📋  <b>BRIEF DE APERTURA</b>",
        f"│  📅  {_e(fecha)}",
        f"└{'━' * 34}┘",
        "",
        f"{semaforo}",
        "",
        f"🔴 Críticos: <b>{critical_count}</b>   🟡 Altos: <b>{high_count}</b>   ⚡ Acciones: <b>{actions_count}</b>",
        f"💰 Valor en riesgo: <b>{value_at_risk:.2f} €</b>",
        "",
        "📄 El análisis completo de Kuine aparece a continuación ↓",
    ]
    return "\n".join(lines)


def format_brief(
    summary: str,
    brief_date: str = "",
    value_at_risk: float = 0.0,
    actions_count: int = 0,
    critical_count: int = 0,
    high_count: int = 0,
) -> str:
    fecha = brief_date or _date.today().isoformat()
    semaforo = "🔴 ALERTA" if critical_count >= 3 else "🟡 ATENCIÓN" if critical_count >= 1 else "🟢 NORMAL"

    lines = [
        f"┌{'━' * 34}┐",
        f"│  📋  <b>BRIEF DE APERTURA — {_e(fecha)}</b>",
        f"└{'━' * 34}┘",
        "",
        f"{semaforo}  ·  <b>{critical_count}</b> crítico(s)  ·  <b>{high_count}</b> alto(s)  ·  <b>{actions_count}</b> acciones",
        f"💰 Valor en riesgo hoy: <b>{value_at_risk:.2f} €</b>",
        "",
        "━" * 36,
        "🧠 <b>ANÁLISIS DE KUINE</b>",
        "━" * 36,
        "",
        _e(summary) if summary else "<i>Sin resumen disponible.</i>",
    ]
    return "\n".join(lines)


# ── Lista de acciones ─────────────────────────────────────────────────────────

def format_actions(pending: list[dict]) -> str:
    if not pending:
        return (
            "✅ <b>Sin acciones pendientes</b>\n\n"
            "Todo el inventario está en orden. Kuine no detecta urgencias ahora mismo.\n\n"
            "<i>Se revisa automáticamente cada 2 horas.</i>"
        )

    critical = [a for a in pending if (a.get("priority_score") or 0) >= 85]
    high = [a for a in pending if 65 <= (a.get("priority_score") or 0) < 85]
    low = [a for a in pending if (a.get("priority_score") or 0) < 65]

    value_at_risk = 0.0
    for a in pending:
        b = a.get("batches") or {}
        p = (b.get("products") or {}) if b else {}
        qty = b.get("quantity") or 0
        price = p.get("price") or 0.0
        value_at_risk += qty * price

    lines = [
        f"⚡ <b>ACCIONES PENDIENTES</b>",
        f"<i>{len(pending)} acciones · 💰 {value_at_risk:.2f} € en riesgo</i>",
        "",
    ]

    if critical:
        lines += [
            f"🔴 <b>CRÍTICO</b>  <i>({len(critical)} acciones — requieren atención inmediata)</i>",
            "━" * 36,
        ]
        for a in critical[:6]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            name = p.get("name", "Producto")
            pasillo = p.get("pasillo", "?")
            categoria = p.get("category", "")
            action_type = (a.get("action_type") or "revisar").upper()
            score = a.get("priority_score", 0)
            exp = b.get("expiry_date", "")
            qty = b.get("quantity") or 0
            price = p.get("price") or 0.0
            days_s = _days_str(exp)
            notes = (a.get("notes") or "")[:80]
            val = qty * price
            cat_str = f"  <i>{_e(categoria)}</i>" if categoria else ""
            lines.append(
                f"• <b>{_e(name)}</b>{cat_str}\n"
                f"  📍 Pasillo {_e(str(pasillo))}  ·  📅 Caduca: {days_s}  ·  {qty} uds ({val:.2f} €)\n"
                f"  ➜ <b>{_e(action_type)}</b>  <code>Score: {score}/100</code>"
            )
            if notes:
                lines.append(f"  <i>💬 {_e(notes)}</i>")
            lines.append("")

    if high:
        lines += [
            f"🟡 <b>ALTO</b>  <i>({len(high)} acciones — antes del mediodía)</i>",
            "━" * 36,
        ]
        for a in high[:5]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            name = p.get("name", "Producto")
            pasillo = p.get("pasillo", "?")
            action_type = (a.get("action_type") or "").upper()
            score = a.get("priority_score", 0)
            exp = b.get("expiry_date", "")
            qty = b.get("quantity") or 0
            days_s = _days_str(exp)
            lines.append(
                f"• <b>{_e(name)}</b>  ·  P.{_e(str(pasillo))}  ·  {days_s}  ·  {qty} uds\n"
                f"  ➜ {_e(action_type)}  <code>{score}/100</code>"
            )
        lines.append("")

    if low:
        lines += [
            f"⚪ <b>BAJO</b>  <i>({len(low)} acciones — cuando haya tiempo)</i>",
            "━" * 36,
        ]
        for a in low[:4]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            name = p.get("name", "Producto")
            pasillo = p.get("pasillo", "?")
            exp = b.get("expiry_date", "")
            days_s = _days_str(exp)
            lines.append(f"• {_e(name)}  ·  P.{_e(str(pasillo))}  ·  {days_s}")
        lines.append("")

    if len(pending) > 12:
        lines.append(f"<i>... y {len(pending) - 12} acciones más. Ver lista completa en la app.</i>")

    return "\n".join(lines)


# ── Dashboard / Stats ─────────────────────────────────────────────────────────

def format_stats(
    pending_total: int,
    critical: int,
    high: int,
    batches_expiring: int,
    value_at_risk: float,
    merma_7d_eur: float,
    donated_qty: int,
    donated_value: float,
    brief_date: str = "",
    semaforo: str = "VERDE",
) -> str:
    sem_emoji = _semaforo_emoji(semaforo)
    sem_label = "ALERTA" if "ROJO" in semaforo.upper() else ("ATENCIÓN" if "AMARILLO" in semaforo.upper() else "NORMAL")
    low = max(0, pending_total - critical - high)
    roi_str = ""
    if merma_7d_eur > 0:
        roi_str = f"\n📈 ROI IA (est.):       <b>+{min(95, round(merma_7d_eur * 0.6, 2)):.2f} €/sem evitados</b>"

    lines = [
        f"┌{'━' * 34}┐",
        f"│  📊  <b>SUPER MARTÍNEZ — Dashboard</b>",
        f"│  {sem_emoji} <b>SEMÁFORO {_e(sem_label)}</b>",
        f"└{'━' * 34}┘",
        "",
        "━" * 36,
        "⚡ <b>ACCIONES</b>",
        f"  🔴 Críticas:          <b>{critical}</b>",
        f"  🟡 Altas:             <b>{high}</b>",
        f"  ⚪ Bajas:             <b>{low}</b>",
        f"  📋 Total pendientes:  <b>{pending_total}</b>",
        "",
        "━" * 36,
        "💰 <b>INVENTARIO EN RIESGO</b>",
        f"  📦 Lotes caducando (7d): <b>{batches_expiring}</b>",
        f"  💸 Valor en riesgo:      <b>{value_at_risk:.2f} €</b>",
        f"  📉 Merma registrada 7d:  <b>{merma_7d_eur:.2f} €</b>",
        roi_str if roi_str else "",
        "",
        "━" * 36,
        "❤️  <b>IMPACTO SOCIAL</b>",
        f"  🤝 Donaciones (mes):    <b>{donated_qty} uds</b>",
        f"  💚 Valor donado:        <b>{donated_value:.2f} €</b>",
    ]
    if brief_date:
        lines += ["", f"<i>📋 Último brief: {_e(brief_date)}</i>"]
    lines += ["", "<i>Actualizado ahora por Kuine · MermaOps</i>"]
    return "\n".join(l for l in lines if l is not None)


# ── Merma ─────────────────────────────────────────────────────────────────────

def format_merma(logs: list[dict], days: int = 7) -> str:
    if not logs:
        return (
            f"✅ <b>Sin merma registrada</b> en los últimos {days} días.\n\n"
            "<i>Cuando se registre una acción de retirada o caducidad, aparecerá aquí.</i>"
        )

    total_value = sum(float(l.get("value_lost", 0)) for l in logs)
    total_qty = sum(int(l.get("quantity_lost", 0)) for l in logs)

    # Agrupar por categoría si hay datos
    by_reason: dict[str, float] = {}
    for log in logs:
        reason = log.get("reason") or "Sin motivo"
        by_reason[reason] = by_reason.get(reason, 0) + float(log.get("value_lost", 0))

    lines = [
        f"┌{'━' * 34}┐",
        f"│  📉  <b>MERMA — últimos {days} días</b>",
        f"└{'━' * 34}┘",
        "",
        f"💸 <b>{total_value:.2f} €</b> de valor perdido",
        f"📦 <b>{total_qty}</b> unidades registradas como merma",
        "",
        "━" * 36,
        "<b>Detalle por registro:</b>",
    ]
    for log in logs[:8]:
        batch = log.get("batches") or {}
        product = (batch.get("products") or {}) if batch else {}
        name = product.get("name", log.get("reason", "Producto")[:30])
        fecha = log.get("date", "?")
        qty = log.get("quantity_lost", 0)
        val = float(log.get("value_lost", 0))
        reason = log.get("reason", "")
        reason_str = f"  <i>Motivo: {_e(reason)}</i>" if reason else ""
        lines.append(
            f"• <b>{_e(name)}</b>  ·  {fecha}\n"
            f"  {qty} uds  ·  <b>{val:.2f} €</b>{reason_str}"
        )

    if len(logs) > 8:
        lines.append(f"\n<i>... y {len(logs) - 8} registros más. Ver historial completo en la app.</i>")

    # Top motivos
    if len(by_reason) > 1:
        lines += ["", "━" * 36, "<b>Por motivo:</b>"]
        for reason, val in sorted(by_reason.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"  • {_e(reason)}: <b>{val:.2f} €</b>")

    return "\n".join(lines)


# ── Donaciones ────────────────────────────────────────────────────────────────

def format_donaciones(stats: dict) -> str:
    if stats.get("total_donations", 0) == 0:
        return (
            "❤️ <b>Sin donaciones registradas este mes.</b>\n\n"
            "Cuando registres una donación desde la app o con /donar, aparecerá aquí.\n\n"
            "<i>Cada donación evita merma y genera deducción fiscal del 35% (Ley 49/2002).</i>"
        )

    total = stats.get("total_donations", 0)
    qty = stats.get("total_quantity", 0)
    val = float(stats.get("total_value_donated", 0.0))
    deduccion = val * 0.35

    lines = [
        f"┌{'━' * 34}┐",
        f"│  ❤️   <b>IMPACTO SOCIAL — este mes</b>",
        f"└{'━' * 34}┘",
        "",
        f"🤝 <b>{total}</b> donaciones realizadas",
        f"📦 <b>{qty}</b> unidades donadas",
        f"💚 <b>{val:.2f} €</b> de valor entregado",
        f"🏛 Deducción fiscal est.: <b>{deduccion:.2f} €</b> <i>(35% Ley 49/2002)</i>",
        "",
        "━" * 36,
        "<b>Por entidad beneficiaria:</b>",
    ]
    for entity, e_qty in sorted((stats.get("by_entity") or {}).items(), key=lambda x: -x[1]):
        lines.append(f"  • {_e(entity)}: <b>{e_qty}</b> uds")
    lines += [
        "",
        "━" * 36,
        "🌱 <i>Cada unidad donada es merma evitada y ayuda a quien lo necesita.</i>",
        "<i>El registro de donaciones aparece también en el informe ESG mensual.</i>",
    ]
    return "\n".join(lines)


# ── Proveedores ───────────────────────────────────────────────────────────────

def format_proveedores(stats: list[dict]) -> str:
    if not stats:
        return "📦 <b>Sin datos de proveedores</b> todavía.\n\n<i>Los datos se generan con al menos 7 días de historial de merma por proveedor.</i>"

    alto = [s for s in stats if s.get("risk", "BAJO") == "ALTO"]
    medio = [s for s in stats if s.get("risk", "BAJO") == "MEDIO"]
    bajo = [s for s in stats if s.get("risk", "BAJO") == "BAJO"]

    lines = [
        f"┌{'━' * 34}┐",
        f"│  📦  <b>FICHA DE PROVEEDORES</b>",
        f"└{'━' * 34}┘",
        f"<i>{len(stats)} proveedores activos · Base para negociación</i>",
        "",
    ]

    if alto:
        lines += ["🔴 <b>RIESGO ALTO</b> — revisar condiciones de entrega", "━" * 36]
        for s in alto[:5]:
            lines.append(
                f"• <b>{_e(s['name'])}</b>\n"
                f"  Merma: <b>{s.get('avg_merma_pct', 0)}%</b>  ·  {s.get('product_count', 0)} productos\n"
                f"  <i>⚠️ Posibles problemas en cadena de frío o embalaje</i>"
            )
            lines.append("")

    if medio:
        lines += ["🟡 <b>RIESGO MEDIO</b> — seguimiento recomendado", "━" * 36]
        for s in medio[:5]:
            lines.append(
                f"• <b>{_e(s['name'])}</b>  ·  Merma: <b>{s.get('avg_merma_pct', 0)}%</b>  ·  {s.get('product_count', 0)} prods"
            )
        lines.append("")

    if bajo:
        lines += ["🟢 <b>RIESGO BAJO</b> — proveedores fiables", "━" * 36]
        for s in bajo[:5]:
            lines.append(f"• {_e(s['name'])}  ·  {s.get('avg_merma_pct', 0)}%")
        if len(bajo) > 5:
            lines.append(f"  <i>... y {len(bajo) - 5} más.</i>")
        lines.append("")

    lines += ["<i>Basado en historial de merma de los últimos 30 días.</i>"]
    return "\n".join(lines)


# ── Pedido semanal ────────────────────────────────────────────────────────────

def format_pedido(suggestions: list[dict]) -> str:
    if not suggestions:
        return (
            "🛒 <b>Sin sugerencias de pedido</b>\n\n"
            "Se generan con al menos 7 días de historial de merma.\n"
            "<i>Vuelve a consultar mañana si acabas de configurar el sistema.</i>"
        )

    total = sum(s.get("estimated_value", 0) for s in suggestions)
    lines = [
        f"┌{'━' * 34}┐",
        f"│  🛒  <b>PEDIDO SEMANAL SUGERIDO</b>",
        f"└{'━' * 34}┘",
        f"<b>{len(suggestions)}</b> productos  ·  Valor estimado: <b>{total:.2f} €</b>",
        "",
        "━" * 36,
    ]
    for s in suggestions[:10]:
        wh = s.get("current_warehouse_stock", 0)
        shelf = s.get("current_shelf_stock", 0)
        est = s.get("estimated_value", 0)
        lines.append(
            f"• <b>{_e(s['product_name'])}</b>  ·  Pedir: <b>{s['order_qty']} uds</b>\n"
            f"  Stock tienda: {shelf}  ·  Almacén: {wh}  ·  <b>{est:.2f} €</b>"
        )
    if len(suggestions) > 10:
        lines.append(f"\n<i>... y {len(suggestions) - 10} productos más. Ver lista completa en la app.</i>")
    lines += [
        "",
        "━" * 36,
        "<i>Basado en merma histórica y rotación de los últimos 30 días.</i>",
        "<i>Pedido generado por Kuine — revisa precios antes de enviar al proveedor.</i>",
    ]
    return "\n".join(lines)


# ── Estado general (semáforo rápido) ─────────────────────────────────────────

def format_estado(
    pending: list[dict],
    batches: list[dict],
    brief: dict | None,
    value_at_risk: float,
) -> str:
    critical = [a for a in pending if (a.get("priority_score") or 0) >= 85]
    alto = [a for a in pending if 65 <= (a.get("priority_score") or 0) < 85]
    semaforo = (
        "🔴 ALERTA" if len(critical) >= 3
        else "🟡 ATENCIÓN" if (len(critical) >= 1 or len(alto) >= 3)
        else "🟢 NORMAL"
    )

    lines = [
        f"┌{'━' * 34}┐",
        f"│  📊  <b>SUPER MARTÍNEZ — Estado ahora</b>",
        f"│  {_e(semaforo)}",
        f"└{'━' * 34}┘",
        "",
        f"🔴 Críticas:    <b>{len(critical)}</b>",
        f"🟡 Altas:       <b>{len(alto)}</b>",
        f"⚪ Pendientes:  <b>{len(pending)}</b> total",
        f"📦 Lotes (7d):  <b>{len(batches)}</b>",
        f"💰 En riesgo:   <b>{value_at_risk:.2f} €</b>",
    ]
    if brief:
        lines.append(f"\n<i>📋 Último brief: {_e(brief.get('date', '?'))}</i>")
    if critical:
        lines += ["", "━" * 36, "🔴 <b>CRÍTICOS AHORA — acción requerida:</b>"]
        for a in critical[:5]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            at = (a.get("action_type") or "revisar").upper()
            exp = b.get("expiry_date", "")
            days_s = _days_str(exp)
            qty = b.get("quantity") or 0
            lines.append(
                f"• <b>{_e(p.get('name', 'Producto'))}</b>  P.{_e(str(p.get('pasillo', '?')))}\n"
                f"  📅 {days_s}  ·  {qty} uds  ·  ➜ {_e(at)}"
            )
    if alto and len(critical) == 0:
        lines += ["", "━" * 36, "🟡 <b>ALTOS — antes del mediodía:</b>"]
        for a in alto[:4]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            at = (a.get("action_type") or "").upper()
            lines.append(f"• <b>{_e(p.get('name', 'Producto'))}</b>  P.{_e(str(p.get('pasillo', '?')))}  ➜ {_e(at)}")
    lines += ["", "<i>Actualizado ahora · Kuine analiza el inventario cada 2h</i>"]
    return "\n".join(lines)
