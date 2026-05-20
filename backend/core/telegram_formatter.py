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


# ── Brief del día ─────────────────────────────────────────────────────────────

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
        f"┌{'─' * 32}┐",
        f"│  📋  <b>BRIEF — {_e(fecha)}</b>",
        f"└{'─' * 32}┘",
        "",
        f"{semaforo}  <b>{critical_count} crítico(s)</b> · {high_count} alto(s) · {actions_count} acciones",
        f"💰 Valor en riesgo: <b>{value_at_risk:.2f} €</b>",
        "",
        "━" * 34,
        "",
        _e(summary),
    ]
    return "\n".join(lines)


# ── Lista de acciones ─────────────────────────────────────────────────────────

def format_actions(pending: list[dict]) -> str:
    if not pending:
        return "✅ <b>Sin acciones pendientes</b>\nTodo en orden por ahora."

    critical = [a for a in pending if (a.get("priority_score") or 0) >= 85]
    high = [a for a in pending if 65 <= (a.get("priority_score") or 0) < 85]
    low = [a for a in pending if (a.get("priority_score") or 0) < 65]

    lines = [
        f"⚡ <b>ACCIONES PENDIENTES — {len(pending)} total</b>",
        "",
    ]

    if critical:
        lines += [f"🔴 <b>CRÍTICO</b>  ({len(critical)})", "━" * 30]
        for a in critical[:5]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            name = p.get("name", "Producto")
            pasillo = p.get("pasillo", "?")
            action_type = (a.get("action_type") or "revisar").upper()
            score = a.get("priority_score", 0)
            exp = b.get("expiry_date", "")
            try:
                days_left = (_date.fromisoformat(exp) - _date.today()).days if exp else None
                days_str = f"HOY" if days_left == 0 else (f"{days_left}d" if days_left is not None else "?")
            except Exception:
                days_str = "?"
            notes = (a.get("notes") or "")[:60]
            lines.append(
                f"• <b>{_e(name)}</b> · P.{_e(pasillo)} · {days_str}\n"
                f"  → <b>{_e(action_type)}</b>  <i>(score {score}/100)</i>"
            )
            if notes:
                lines.append(f"  <i>{_e(notes)}</i>")
        lines.append("")

    if high:
        lines += [f"🟡 <b>ALTO</b>  ({len(high)})", "━" * 30]
        for a in high[:4]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            name = p.get("name", "Producto")
            pasillo = p.get("pasillo", "?")
            action_type = (a.get("action_type") or "").upper()
            exp = b.get("expiry_date", "")
            try:
                days_left = (_date.fromisoformat(exp) - _date.today()).days if exp else None
                days_str = f"{days_left}d" if days_left is not None else "?"
            except Exception:
                days_str = "?"
            lines.append(f"• <b>{_e(name)}</b> · P.{_e(pasillo)} · {days_str} · {_e(action_type)}")
        lines.append("")

    if low and len(pending) <= 12:
        lines += [f"⚪ <b>BAJO</b>  ({len(low)})", "━" * 30]
        for a in low[:3]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            name = p.get("name", "Producto")
            lines.append(f"• {_e(name)}")
        lines.append("")

    if len(pending) > 10:
        lines.append(f"<i>... y {len(pending) - 10} más. Ver lista completa en la app.</i>")

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

    lines = [
        f"┌{'─' * 32}┐",
        f"│  📊  <b>SUPER MARTÍNEZ</b>",
        f"│  {sem_emoji} <b>{_e(sem_label)}</b>",
        f"└{'─' * 32}┘",
        "",
        f"🔴 Críticas:    <b>{critical}</b>",
        f"🟡 Altas:       <b>{high}</b>",
        f"⚪ Pendientes:  <b>{pending_total}</b> total",
        "",
        "━" * 34,
        f"📦 Lotes caducando (7d): <b>{batches_expiring}</b>",
        f"💰 Valor en riesgo:      <b>{value_at_risk:.2f} €</b>",
        f"📉 Merma 7 días:         <b>{merma_7d_eur:.2f} €</b>",
        f"❤️  Donaciones mes:       <b>{donated_qty} uds</b> ({donated_value:.2f} €)",
    ]
    if brief_date:
        lines += ["", f"<i>Último brief: {_e(brief_date)}</i>"]
    return "\n".join(lines)


# ── Merma ─────────────────────────────────────────────────────────────────────

def format_merma(logs: list[dict], days: int = 7) -> str:
    if not logs:
        return f"✅ <b>Sin merma registrada</b> en los últimos {days} días."

    total_value = sum(float(l.get("value_lost", 0)) for l in logs)
    total_qty = sum(int(l.get("quantity_lost", 0)) for l in logs)

    lines = [
        f"┌{'─' * 32}┐",
        f"│  📉  <b>MERMA — últimos {days} días</b>",
        f"└{'─' * 32}┘",
        "",
        f"💸 <b>{total_value:.2f} €</b> de valor perdido",
        f"📦 <b>{total_qty}</b> unidades perdidas",
        "",
        "━" * 34,
    ]
    for log in logs[:5]:
        batch = log.get("batches") or {}
        product = (batch.get("products") or {}) if batch else {}
        name = product.get("name", log.get("reason", "Sin motivo")[:30])
        fecha = log.get("date", "?")
        qty = log.get("quantity_lost", 0)
        val = float(log.get("value_lost", 0))
        lines.append(f"• <b>{_e(name)}</b>  |  {qty} uds  |  {val:.2f} €  |  {_e(fecha)}")

    if len(logs) > 5:
        lines.append(f"\n<i>... y {len(logs) - 5} registros más en la app.</i>")
    return "\n".join(lines)


# ── Donaciones ────────────────────────────────────────────────────────────────

def format_donaciones(stats: dict) -> str:
    if stats.get("total_donations", 0) == 0:
        return (
            "❤️ <b>Sin donaciones registradas este mes.</b>\n\n"
            "Cuando registres una donación desde la app o con /donar,\naparecerá aquí."
        )

    lines = [
        f"┌{'─' * 32}┐",
        f"│  ❤️   <b>IMPACTO SOCIAL — este mes</b>",
        f"└{'─' * 32}┘",
        "",
        f"🤝 <b>{stats['total_donations']}</b> donaciones realizadas",
        f"📦 <b>{stats['total_quantity']}</b> unidades donadas",
        f"💚 <b>{stats.get('total_value_donated', 0):.2f} €</b> de valor entregado",
        "",
        "━" * 34,
        "<b>Por entidad:</b>",
    ]
    for entity, qty in sorted((stats.get("by_entity") or {}).items(), key=lambda x: -x[1]):
        lines.append(f"  • {_e(entity)}: <b>{qty}</b> uds")
    lines += [
        "",
        "🌱 <i>Cada unidad donada es merma evitada\ny ayuda a quien lo necesita.</i>",
    ]
    return "\n".join(lines)


# ── Proveedores ───────────────────────────────────────────────────────────────

def format_proveedores(stats: list[dict]) -> str:
    if not stats:
        return "📦 <b>Sin datos de proveedores</b> todavía."

    lines = [
        f"┌{'─' * 32}┐",
        f"│  📦  <b>FICHA DE PROVEEDORES</b>",
        f"└{'─' * 32}┘",
        "<i>Merma promedio — base para negociación</i>",
        "",
    ]
    for s in stats[:20]:  # Telegram 4096-char limit
        risk = s.get("risk", "BAJO")
        icon = "🔴" if risk == "ALTO" else ("🟡" if risk == "MEDIO" else "🟢")
        lines.append(
            f"{icon} <b>{_e(s['name'])}</b>\n"
            f"   Merma: <b>{s.get('avg_merma_pct', 0)}%</b>  ·  "
            f"{s.get('product_count', 0)} productos  ·  Riesgo {_e(risk)}"
        )
        if risk == "ALTO":
            lines.append("   <i>⚠️ Revisar condiciones de entrega con este proveedor</i>")
        lines.append("")
    return "\n".join(lines)


# ── Pedido semanal ────────────────────────────────────────────────────────────

def format_pedido(suggestions: list[dict]) -> str:
    if not suggestions:
        return (
            "🛒 <b>Sin sugerencias de pedido</b>\n"
            "Se generan con al menos 7 días de historial de merma."
        )

    total = sum(s.get("estimated_value", 0) for s in suggestions)
    lines = [
        f"┌{'─' * 32}┐",
        f"│  🛒  <b>PEDIDO SEMANAL SUGERIDO</b>",
        f"└{'─' * 32}┘",
        f"<b>{len(suggestions)}</b> productos  ·  Valor est. <b>{total:.2f} €</b>",
        "",
        "━" * 34,
    ]
    for s in suggestions[:10]:
        lines.append(
            f"• <b>{_e(s['product_name'])}</b>  ·  {s['order_qty']} uds\n"
            f"  Almacén: {s.get('current_warehouse_stock', 0)}  ·  <b>{s.get('estimated_value', 0):.2f} €</b>"
        )
    if len(suggestions) > 10:
        lines.append(f"\n<i>... y {len(suggestions) - 10} más. Ver en la app.</i>")
    lines += ["", "<i>Basado en merma histórica de los últimos 30 días.</i>"]
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
        f"┌{'─' * 32}┐",
        f"│  📊  <b>SUPER MARTÍNEZ</b>",
        f"│  {_e(semaforo)}",
        f"└{'─' * 32}┘",
        "",
        f"🔴 Críticas:    <b>{len(critical)}</b>",
        f"🟡 Altas:       <b>{len(alto)}</b>",
        f"⚪ Pendientes:  <b>{len(pending)}</b> total",
        f"📦 Lotes (7d):  <b>{len(batches)}</b>",
        f"💰 En riesgo:   <b>{value_at_risk:.2f} €</b>",
    ]
    if brief:
        lines.append(f"\n<i>Último brief: {_e(brief.get('date', '?'))}</i>")
    if critical:
        lines += ["", "━" * 34, "<b>CRÍTICOS AHORA:</b>"]
        for a in critical[:4]:
            b = a.get("batches") or {}
            p = (b.get("products") or {}) if b else {}
            at = (a.get("action_type") or "revisar").upper()
            lines.append(
                f"• <b>{_e(p.get('name', 'Producto'))}</b>  "
                f"P.{_e(p.get('pasillo', '?'))}  →  {_e(at)}"
            )
    return "\n".join(lines)
