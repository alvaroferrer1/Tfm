"""
Route Agent — genera la ruta óptima del día ordenada por FEFO y prioridad.
Agrupa por pasillo, ordena críticos primero, estima tiempo total.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date


_TIME_PER_ACTION_MINUTES: dict[str, int] = {
    "retirar": 3,
    "rebajar": 2,
    "donar": 5,
    "mover": 4,
    "revisar": 2,
    "reponer": 5,
    "ok": 1,
}


def generate(store_id: str, risk_reports: list[tuple]) -> dict:
    """
    Genera la ruta del día agrupada por pasillo.
    risk_reports: lista de (batch_dict, risk_dict)
    Devuelve dict con metadata y acciones agrupadas.
    """
    by_pasillo: dict[str, list] = defaultdict(list)
    total_value = 0.0
    total_time = 0

    for batch, risk in risk_reports:
        product = batch.get("products", {})

        # Soporte para risk como dict (nuevo) o str (legacy)
        if isinstance(risk, dict):
            score = risk.get("score", 0)
            risk_level = risk.get("risk_level", "BAJO")
            action = risk.get("action", "revisar")
            reasoning = risk.get("reasoning", "")
        else:
            risk_str = str(risk)
            score = 90 if "CRÍTICO" in risk_str else 70 if "ALTO" in risk_str else 40 if "MEDIO" in risk_str else 15
            risk_level = "CRÍTICO" if "CRÍTICO" in risk_str else "ALTO" if "ALTO" in risk_str else "MEDIO" if "MEDIO" in risk_str else "BAJO"
            action = "rebajar" if "rebajar" in risk_str.lower() else "revisar"
            reasoning = risk_str

        pasillo = str(product.get("pasillo", "?"))
        qty = batch.get("quantity", 0)
        price = float(product.get("price", 0))
        value = round(qty * price, 2)
        total_value += value

        action_time = _TIME_PER_ACTION_MINUTES.get(action, 2)
        total_time += action_time

        try:
            days_left = (date.fromisoformat(batch.get("expiry_date", "9999-12-31")) - date.today()).days
        except ValueError:
            days_left = 999

        by_pasillo[pasillo].append({
            "batch_id": batch.get("id", ""),
            "product_id": product.get("id", ""),
            "product_name": product.get("name", ""),
            "estanteria": product.get("estanteria", ""),
            "nivel": product.get("nivel", ""),
            "expiry_date": batch.get("expiry_date", ""),
            "days_left": days_left,
            "quantity": qty,
            "value_at_risk": value,
            "risk_level": risk_level,
            "score": score,
            "action": action,
            "reasoning": reasoning,
            "minutes_estimated": action_time,
        })

    # Ordenar pasillos numéricamente
    ordered_pasillos = dict(
        sorted(by_pasillo.items(), key=lambda x: (x[0].isdigit() is False, x[0]))
    )

    # Dentro de cada pasillo: FEFO (días_left ASC) con críticos primero
    for pasillo in ordered_pasillos:
        ordered_pasillos[pasillo].sort(
            key=lambda x: (x["risk_level"] not in ("CRÍTICO", "ALTO"), x["days_left"])
        )

    return {
        "pasillos": ordered_pasillos,
        "total_actions": sum(len(v) for v in ordered_pasillos.values()),
        "total_value_at_risk": round(total_value, 2),
        "estimated_minutes": total_time,
        "route_order": list(ordered_pasillos.keys()),
        "critical_count": sum(
            1 for items in ordered_pasillos.values()
            for item in items if item["risk_level"] == "CRÍTICO"
        ),
    }


def format_route_message(route: dict) -> str:
    """Formatea la ruta como texto limpio para Telegram (sin markdown con asteriscos)."""
    if not route or not route.get("pasillos"):
        return "Sin ruta para hoy."

    pasillos = route.get("pasillos", {})
    route_order = route.get("route_order", list(pasillos.keys()))

    lines = [
        f"RUTA DEL DIA — {route.get('total_actions', 0)} acciones | "
        f"{route.get('estimated_minutes', 0)} min estimados | "
        f"Valor en riesgo: {route.get('total_value_at_risk', 0)} euros",
        "",
        "Recorrido: " + " → ".join(f"Pasillo {p}" for p in route_order),
        "",
    ]

    for pasillo in route_order:
        items = pasillos.get(pasillo, [])
        lines.append(f"PASILLO {pasillo} ({len(items)} acciones):")
        for item in items:
            urgency_icon = "!!!" if item["risk_level"] == "CRÍTICO" else "!" if item["risk_level"] == "ALTO" else " "
            lines.append(
                f"  {urgency_icon} {item['product_name']} "
                f"| E{item['estanteria']}-N{item['nivel']} "
                f"| Caduca {item['expiry_date']} ({item['days_left']} dias) "
                f"| {item['quantity']} uds "
                f"| ACCION: {item['action'].upper()}"
            )
        lines.append("")

    return "\n".join(lines).rstrip()


def format_route_html(route: dict) -> str:
    """Versión HTML para Telegram con formato mejorado."""
    if not route or not route.get("pasillos"):
        return "Sin ruta para hoy."

    pasillos = route.get("pasillos", {})
    route_order = route.get("route_order", list(pasillos.keys()))

    lines = [
        f"<b>RUTA DEL DIA</b>",
        f"{route.get('total_actions', 0)} acciones — {route.get('estimated_minutes', 0)} min — "
        f"Valor en riesgo: <b>{route.get('total_value_at_risk', 0)} euros</b>",
        "",
        "Recorrido: " + " → ".join(f"Pasillo {p}" for p in route_order),
        "",
    ]

    for pasillo in route_order:
        items = pasillos.get(pasillo, [])
        lines.append(f"<b>Pasillo {pasillo}</b> ({len(items)} acciones)")
        for item in items:
            icon = "🔴" if item["risk_level"] == "CRÍTICO" else "🟡" if item["risk_level"] == "ALTO" else "🟢"
            lines.append(
                f"{icon} <b>{item['product_name']}</b> "
                f"E{item['estanteria']}-N{item['nivel']} | "
                f"Caduca {item['expiry_date']} | "
                f"{item['quantity']} uds | "
                f"<b>{item['action'].upper()}</b>"
            )
        lines.append("")

    return "\n".join(lines).rstrip()
