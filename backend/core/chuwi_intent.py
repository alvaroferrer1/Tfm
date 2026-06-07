"""
chuwi_intent — clasificación de intención + proactive intent triggers.

Patrón Fase 2: keyword matching ordenado de más específico a más general.
Patrón Fase 3: ambient agent — detecta "avísame cuando X" y guarda triggers persistentes.
               El scheduler evalúa los triggers y Chuwi actúa sin que nadie pregunte.

Referencia: técnica de intent classification sin LLM descrita en
"Building Effective Agents" (Anthropic, 2024).
Proactive triggers: LangGraph ambient agents pattern (Oct 2025).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from backend.core import database

logger = logging.getLogger("mermaops.chuwi")

# ── Proactive intent trigger detection ───────────────────────────────────────
# Detecta cuando el empleado pide que Chuwi le avise de algo.
# Guarda el trigger en memoria episódica para que el scheduler lo evalúe.

_TRIGGER_PATTERNS = [
    r"avísame\s+cuando\s+(.+)",
    r"avisa\s+(?:me\s+)?cuando\s+(.+)",
    r"alerta\s+(?:me\s+)?(?:si|cuando)\s+(.+)",
    r"dime\s+cuando\s+(.+)",
    r"notifícame\s+(?:si|cuando)\s+(.+)",
    r"manda\s+(?:me\s+)?un\s+mensaje\s+cuando\s+(.+)",
    r"quiero\s+saber\s+cuando\s+(.+)",
    r"quiero\s+que\s+me\s+avises\s+(?:si|cuando)\s+(.+)",
]


def detect_proactive_trigger(text: str, user_id: str, store_id: str) -> Optional[dict]:
    """
    Detecta si el empleado está pidiendo que Chuwi le avise de algo.
    Si detecta un trigger, lo guarda en memoria episódica y devuelve el trigger.
    El scheduler evalúa los triggers periódicamente.

    Ejemplos detectados:
    - "Avísame cuando haya más de 5 críticos" → tipo: umbral_criticos
    - "Avísame cuando el yogur esté a punto de caducar" → tipo: producto_caducidad
    - "Alerta si la merma sube mucho" → tipo: merma_alta

    Returns None si no hay trigger, o dict con el trigger guardado.
    """
    t = text.lower().strip()

    for pattern in _TRIGGER_PATTERNS:
        match = re.search(pattern, t)
        if match:
            condition_text = match.group(1).strip().rstrip('.,!?')
            if len(condition_text) < 5:
                continue

            trigger = {
                "user_id": user_id,
                "store_id": store_id,
                "condition": condition_text,
                "original_text": text[:200],
                "active": True,
            }

            # Guardar en memoria episódica
            try:
                from backend.core import memory as _mem
                _key = f"proactive_trigger_{user_id}"
                _existing_raw = _mem.recall(store_id, _key)
                try:
                    _existing = json.loads(_existing_raw) if _existing_raw else []
                except Exception:
                    _existing = []

                # Evitar duplicados similares
                if not any(condition_text[:30] in t.get("condition", "") for t in _existing):
                    _existing.insert(0, trigger)
                    _mem.remember(store_id, _key, json.dumps(_existing[:5], ensure_ascii=False))
                    logger.info(f"[intent_trigger] Guardado trigger para {user_id}: '{condition_text[:50]}'")

            except Exception as e:
                logger.debug(f"[intent_trigger] Error guardando: {e}")

            return trigger

    return None


def evaluate_proactive_triggers(store_id: str) -> list[dict]:
    """
    Evalúa todos los triggers activos de la tienda contra el estado actual.
    Llamado por el scheduler cada 30 minutos.
    Devuelve lista de triggers que deben dispararse ahora.
    """
    from backend.core import memory as _mem, llm as _llm

    fired_triggers = []

    try:
        # Recuperar todos los triggers del store (buscamos por usuario en memory)
        pending = database.get_pending_actions(store_id)
        critical_count = sum(1 for a in pending if (a.get("priority_score") or 0) >= 85)
        batches = database.get_batches_expiring_soon(store_id, days=2)

        # Para cada usuario con triggers almacenados
        users_with_triggers = set()
        try:
            users_raw = database.get_db().table("users").select("id").eq("store_id", store_id).execute()
            for u in (users_raw.data or []):
                users_with_triggers.add(u.get("id", ""))
        except Exception:
            pass

        for user_id in users_with_triggers:
            _key = f"proactive_trigger_{user_id}"
            triggers_raw = _mem.recall(store_id, _key)
            if not triggers_raw:
                continue
            try:
                triggers = json.loads(triggers_raw)
            except Exception:
                continue

            for trigger in triggers:
                if not trigger.get("active"):
                    continue
                condition = trigger.get("condition", "")

                # Evaluar la condición con Haiku contra el estado actual
                eval_prompt = (
                    f"Estado actual de la tienda:\n"
                    f"- Acciones críticas: {critical_count}\n"
                    f"- Total pendientes: {len(pending)}\n"
                    f"- Lotes caducando en <48h: {len(batches)}\n\n"
                    f"Condición del empleado: '{condition}'\n\n"
                    f"¿Se cumple la condición ahora mismo? Responde solo 'SÍ' o 'NO'."
                )
                try:
                    result = _llm.call_fast(eval_prompt, max_tokens=10).strip().upper()
                    if result.startswith("SÍ") or result.startswith("SI"):
                        trigger["user_id"] = user_id
                        fired_triggers.append(trigger)
                except Exception:
                    pass

    except Exception as e:
        logger.warning(f"[intent_trigger] evaluate error: {e}")

    return fired_triggers

# ── Patrones de intención (más específico primero) ────────────────────────────

_INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    ("registrar_donacion", [
        "donar", "donación", "donacion", "banco de alimentos", "banco alimentos",
        "food bank", "entidad benéfica", "ong",
        "quiero donar", "podemos donar", "vamos a donar", "para donar",
        "lo donamos", "donamos esto", "mandamos al banco",
    ]),
    ("registrar_merma", [
        # Nota: registrar_merma activa el loop agéntico completo (LLM fallback).
        # No existe un contexto pre-cargado porque los detalles de la merma
        # (producto, cantidad, motivo) requieren diálogo con el usuario.
        "registrar merma", "apuntar merma", "anotar merma", "hubo merma",
        "se perdió", "se perdio", "tiré", "tire ",
        "está malo", "esta malo", "se echó a perder", "echo a perder", "echó a perder",
        "hay que tirar", "tirar esto", "para tirar", "ya no sirve",
        "está en mal estado", "esta en mal estado", "se ha puesto mal",
        "se pudrió", "se pudrio", "está podrido", "esta podrido",
        "en mal estado", "deteriorado", "caducado", "ha caducado",
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
        # Participios pasados de acciones de MermaOps — el empleado confirma que actuó
        "rebajado", "retirado", "donado", "movido",
        "he rebajado", "he retirado", "he donado", "ya lo rebajé", "ya rebajé",
        "lo retiré", "lo doné", "ya está retirado", "precio cambiado",
        "ya lo he puesto", "ya lo puse", "ya está hecho",
    ]),
    ("crear_accion", [
        "crear acción", "crear accion", "nueva acción", "nueva accion",
        "añadir acción", "crea una accion", "agregar acción",
    ]),
    ("consulta_estado", [
        "cuantos", "cuántos", "cuanta", "qué caduca", "que caduca",
        "qué hay", "que hay", "estado", "críticos", "criticos", "urgentes", "urgente",
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
    Clasificador de intención en dos etapas:
    1. Keyword matching rápido (0 tokens) — captura el 80% de los casos obvios
    2. Si no hay match claro, usa Haiku para clasificación semántica (~100 tokens)
       Esto captura frases naturales como "veo mucho pan caducando" → consulta_estado

    Intents posibles: registrar_donacion, registrar_merma, pedir_ruta, pedir_brief,
    completar_accion, crear_accion, consulta_estado, configuracion, pregunta_libre.
    """
    t = text.lower().strip()

    # Etapa 1: keyword matching (0 tokens, <1ms)
    for intent, keywords in _INTENT_PATTERNS:
        if any(kw in t for kw in keywords):
            return intent

    # Etapa 2: solo si el texto es suficientemente largo (preguntas cortas → pregunta_libre directamente)
    if len(text) < 8:
        return "pregunta_libre"

    # Haiku semántico para mensajes ambiguos que el regex no captura
    # Ejemplos: "veo mucho pan caducando", "¿cómo vamos con los lácteos?", "se ha puesto malo el queso"
    try:
        from backend.core import llm as _llm
        _prompt = (
            f"Clasifica la siguiente frase de un empleado de supermercado en UNA de estas categorías:\n"
            f"- registrar_donacion: quiere donar productos\n"
            f"- registrar_merma: producto en mal estado, perdido, tirado\n"
            f"- pedir_ruta: quiere saber la ruta o el orden de acciones\n"
            f"- pedir_brief: quiere el resumen del día o estado general\n"
            f"- completar_accion: dice que ya hizo algo, terminó una tarea\n"
            f"- consulta_estado: pregunta cuántos críticos, qué caduca, estado tienda\n"
            f"- pregunta_libre: cualquier otra pregunta o conversación\n\n"
            f"Frase: \"{text[:150]}\"\n\n"
            f"Responde SOLO con el nombre de la categoría, sin explicación."
        )
        result = _llm.call_fast(_prompt, max_tokens=20).strip().lower()
        valid = {
            "registrar_donacion", "registrar_merma", "pedir_ruta",
            "pedir_brief", "completar_accion", "consulta_estado", "pregunta_libre",
        }
        if result in valid:
            logger.debug(f"[intent] Haiku clasificó '{text[:40]}' → {result}")
            return result
    except Exception as e:
        logger.debug(f"[intent] Haiku falló: {e}")

    return "pregunta_libre"


def _build_intent_context(intent: str, store_id: str) -> str:
    """
    Genera contexto adicional según intención detectada.
    Se inyecta en el system prompt para que el agente responda más rápido.
    Falla silenciosamente si Supabase no está disponible.

    Intents con contexto pre-cargado: consulta_estado, pedir_brief,
    completar_accion, pedir_ruta, registrar_donacion.

    Intents sin contexto (LLM fallback): registrar_merma, crear_accion,
    configuracion, pregunta_libre.
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
